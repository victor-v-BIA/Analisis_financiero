import unittest

import numpy as np
import pandas as pd

from core.finance_logic import facturas_a_mxn
from core.loader import (
    _anual_ppd_cache,
    _concentracion_cache,
    _clasificar_base_clase_sat,
    _factor_mxn_productos,
    _resumen_sf_cache,
    emitidos_productos_sat,
    egresos_productos_sat,
    leer_facturas,
    leer_facturas_egresos,
)


class CurrencyConversionTests(unittest.TestCase):
    def test_product_exchange_rate_priority_and_mxn_default(self):
        factor, usa_dof = _factor_mxn_productos(
            pd.Series(["", "USD", "USD", "USD", "USD"]),
            pd.Series([0, 18, 0, np.nan, 0]),
            pd.Series([np.nan, 19, 19, np.nan, 0]),
            pd.Series([20, 20, 20, 21, 0]),
        )

        self.assertEqual(factor.iloc[:4].tolist(), [1, 18, 19, 21])
        self.assertTrue(usa_dof.iloc[3])
        self.assertTrue(pd.isna(factor.iloc[4]))

    def test_issued_products_use_active_invoice_uuid_and_mxn_amounts(self):
        headers = pd.DataFrame({
            "UUID": ["A", "B", "C", "D"],
            "Estatus": ["Activo", "Activo", "Activo", "Cancelado"],
            "Tipo Documento": ["Factura", "Factura", "NCR", "Factura"],
            "Tipo de Cambio": [20, 19, 18, 17],
        })
        products = pd.DataFrame({
            "UUID CFDI Emitido": ["A", "A", "B", "C", "D", "X"],
            "Clave": ["10101010"] * 6,
            "Fecha": ["2025-01-01"] * 6,
            "Estatus": ["Activo"] * 6,
            "Tipo Documento": ["Factura"] * 6,
            "Importe": [100] * 6,
            "Descuento": [10, 10, 0, 0, 0, 0],
            "Moneda": ["MXN", "USD", "USD", "USD", "USD", "USD"],
            "Tipo de Cambio": [0] * 6,
            "Tipo de Cambio DOF": [21] * 6,
            "Impuestos Trasladados": [15] * 6,
            "Impuestos Retenidos": [2] * 6,
        })

        result = emitidos_productos_sat(products, headers)

        self.assertEqual(result["UUID"].tolist(), ["A", "A", "B"])
        self.assertEqual(result["Tipo_Cambio_Aplicado"].tolist(), [1, 20, 19])
        self.assertEqual(result.loc[1, "SubTotal_Neto_MXN"], 1800)
        self.assertEqual(result.loc[1, "Monto_MXN"], 2060)
        self.assertEqual(result.attrs["filas_sin_cruce"], 1)
        detalle = result.attrs["detalle_partidas_sin_cruce"]
        self.assertEqual(detalle["UUID CFDI Emitido"].tolist(), ["X"])
        self.assertEqual(detalle["Clave"].tolist(), ["10101010"])

    def test_issued_products_accept_ccr_rows_and_prefer_sat_key(self):
        headers = pd.DataFrame({
            "UUID": ["A"],
            "Estatus": ["Activo"],
            "Tipo Documento": ["Factura"],
            "Tipo de Cambio": [1],
        })
        products = pd.DataFrame({
            "UUID CFDI Emitido": ["A"],
            "Clave": ["INTERNAL-CODE"],
            "Clave SAT": ["10101010"],
            "Fecha": ["2025-01-01"],
            "Importe": [100],
            "Descuento": [0],
            "Moneda": ["MXN"],
            "Tipo de Cambio": [0],
            "Impuestos Trasladados": [16],
            "Impuestos Retenidos": [0],
        })

        result = emitidos_productos_sat(products, headers)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Clave"], "10101010")
        self.assertEqual(result.iloc[0]["Monto_MXN"], 116)

    def test_received_products_prefer_header_rate_to_dof(self):
        headers = pd.DataFrame({
            "UUID": ["R1", "R2"],
            "Estatus": ["Activo", "Cancelado"],
            "Tipo Documento": ["Factura", "Factura"],
            "Tipo de Cambio": [19, 17],
        })
        products = pd.DataFrame({
            "UUID CFDI Recibido": ["R1", "R2"],
            "Codigo SAT": ["10101010"] * 2,
            "Fecha": ["2025-01-01"] * 2,
            "Importe": [100] * 2,
            "Moneda": ["USD"] * 2,
            "Tipo de Cambio": [0] * 2,
            "Tipo de Cambio DOF": [21] * 2,
            "Impuestos Trasladados": [15] * 2,
            "Impuestos Retenidos": [2] * 2,
        })

        result = egresos_productos_sat(products, headers)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Tipo_Cambio_Aplicado"], 19)
        self.assertEqual(result.iloc[0]["SubTotal_Neto_MXN"], 1900)
        self.assertEqual(result.iloc[0]["Monto_MXN"], 2147)

    def test_received_products_without_uuid_inherit_header_rate_by_partida(self):
        headers = pd.DataFrame({
            "UUID": ["R1"],
            "Estatus": ["Activo"],
            "Tipo Documento": ["Factura"],
            "Fecha": ["2025-01-01"],
            "RFC Emisor": ["SUP"],
            "Moneda": ["USD"],
            "SubTotal": [200],
            "Total": [220],
            "Tipo de Cambio": [20],
        })
        products = pd.DataFrame({
            "Codigo SAT": ["10101010", "10101010"],
            "Fecha": ["2025-01-01", "2025-01-01"],
            "RFC Emisor": ["SUP", "SUP"],
            "Importe": [100, 100],
            "Descuento": [0, 0],
            "Moneda": ["USD", "USD"],
            "Tipo de Cambio": [0, 0],
            "Tipo de Cambio DOF": [21, 21],
            "Impuestos Trasladados": [10, 10],
            "Impuestos Retenidos": [0, 0],
            "Partida": [1, 2],
        })

        result = egresos_productos_sat(products, headers)

        self.assertEqual(result["Tipo_Cambio_Aplicado"].tolist(), [20, 20])
        self.assertEqual(result["SubTotal_Neto_MXN"].sum(), 4000)
        self.assertEqual(result["Monto_MXN"].sum(), 4400)

    def test_invoice_headers_use_mxn_columns_or_received_fallback(self):
        emitted_csv = (
            b"UUID,Fecha y Hora,RFC Emisor,Nombre Emisor,Estatus,Tipo Documento,"
            b"Metodo de Pago,Total,Total MXN TC,Subtotal MXN TC\n"
            b"E1,2025-01-01,X,Y,Activo,Factura,PUE,100,2000,1800\n"
        )
        emitted, _ = leer_facturas("SAT CFDIs Emitidos.csv", emitted_csv)
        self.assertEqual(emitted.iloc[0]["Total"], 2000)
        self.assertEqual(emitted.iloc[0]["SubTotal"], 1800)

        received_csv = (
            b"UUID,Fecha y Hora,RFC Emisor,Nombre Emisor,Estatus,Tipo Documento,"
            b"Metodo de Pago,Total,Moneda,Tipo de Cambio\n"
            b"R1,2025-01-01,X,Y,Activo,Factura,PUE,100,USD,19\n"
            b"R2,2025-01-01,X,Y,Activo,Factura,PUE,100,USD,0\n"
        )
        received, _ = leer_facturas_egresos(
            "SAT CFDIs Recibidos.csv", received_csv
        )
        converted, excluded = facturas_a_mxn(received)
        self.assertEqual(converted.loc[converted["UUID"] == "R1", "Total"].iloc[0], 1900)
        self.assertTrue(pd.isna(received.loc[received["UUID"] == "R2", "Total"]).all())
        self.assertEqual(excluded, 1)

    def test_issued_sat_export_without_issuer_rfc_does_not_use_customer_rfc(self):
        emitted_csv = (
            b"UUID,Fecha y Hora,RFC Receptor,Razon Social,Estatus,Tipo Documento,"
            b"Metodo de Pago,Total,Total MXN TC\n"
            b"E1,2025-01-01,CUSTOMER1,Cliente Uno,Activo,Factura,PUE,100,2000\n"
        )

        emitted, _ = leer_facturas(
            "SAT CFDIs Emitidos Nuevo CCR.csv", emitted_csv
        )

        self.assertEqual(emitted.iloc[0]["Total"], 2000)
        self.assertEqual(emitted.iloc[0]["RFC_Receptor"], "CUSTOMER1")
        self.assertEqual(emitted.iloc[0]["Nombre_Receptor"], "Cliente Uno")
        self.assertEqual(emitted.iloc[0]["RFC_Emisor"], "")

    def test_annual_ppd_cache_reprocesses_updated_ccr_invoice_file(self):
        _anual_ppd_cache.clear()
        self.addCleanup(_anual_ppd_cache.clear)

        invalid_invoice = (
            b"Fecha y Hora,RFC Receptor,Razon Social,Estatus,Tipo Documento\n"
            b"2025-01-15,CUSTOMER1,Cliente Uno,Activo,Factura\n"
        )
        complement = (
            b"UUID,Saldo Inicial,Saldo Final,Fecha de Pago\n"
            b"PAY1,2000,0,2025-02-01\n"
        )
        args = ("clientes", ("emitidos.csv", invalid_invoice),
                ("complementos.csv", complement), (2025,), "cache-test")
        failed, error = _anual_ppd_cache(*args)
        self.assertIsNone(failed)
        self.assertIsNotNone(error)

        valid_invoice = (
            b"UUID,Fecha y Hora,RFC Receptor,Razon Social,Estatus,Tipo Documento,"
            b"Metodo de Pago,Total,Total MXN TC,Moneda\n"
            b"E1,2025-01-15,CUSTOMER1,Cliente Uno,Activo,Factura,PPD,100,2000,USD\n"
        )
        result, error = _anual_ppd_cache(
            "clientes", ("emitidos.csv", valid_invoice),
            ("complementos.csv", complement), (2025,), "cache-test"
        )

        self.assertIsNone(error)
        self.assertIsNotNone(result)
        self.assertEqual(result.iloc[0]["Facturación PPD"], 2000)
        self.assertEqual(result.iloc[0]["Complementos"], 2000)

    def test_income_dashboard_caches_reprocess_updated_ccr_invoice_file(self):
        _concentracion_cache.clear()
        _resumen_sf_cache.clear()
        self.addCleanup(_concentracion_cache.clear)
        self.addCleanup(_resumen_sf_cache.clear)

        invalid_invoice = (
            b"Fecha y Hora,RFC Receptor,Razon Social,Estatus,Tipo Documento\n"
            b"2025-01-15,CUSTOMER1,Cliente Uno,Activo,Factura\n"
        )
        valid_invoice = (
            b"UUID,Fecha y Hora,RFC Receptor,Razon Social,Estatus,Tipo Documento,"
            b"Metodo de Pago,Total,Total MXN TC,Moneda\n"
            b"E1,2025-01-15,CUSTOMER1,Cliente Uno,Activo,Factura,PPD,100,2000,USD\n"
        )
        file_name = "emitidos.csv"
        args = (file_name, invalid_invoice)
        bad_concentracion = _concentracion_cache(args, (2025,), "cache-test")
        bad_resumen = _resumen_sf_cache(args, (2025,), "cache-test")
        self.assertIsNotNone(bad_concentracion["motivo"])
        self.assertIsNotNone(bad_resumen["motivo"])

        args = (file_name, valid_invoice)
        concentracion = _concentracion_cache(args, (2025,), "cache-test")
        resumen = _resumen_sf_cache(args, (2025,), "cache-test")

        self.assertIsNone(concentracion["motivo"])
        self.assertEqual(concentracion["total_general"], 2000)
        self.assertIsNone(resumen["motivo"])
        self.assertIn(2025, resumen["anios"])

    def test_module_classifier_distinguishes_issued_products_from_received(self):
        emitted_products = (
            b"UUID CFDI Emitido,Clave SAT,Fecha,Importe,Impuestos Trasladados,"
            b"Impuestos Retenidos\n"
            b"E1,10101010,2025-01-15,100,16,0\n"
        )
        received_products = (
            b"UUID CFDI Recibido,Codigo SAT,Fecha,Importe,Impuestos Trasladados,"
            b"Impuestos Retenidos\n"
            b"R1,10101010,2025-01-15,100,16,0\n"
        )

        self.assertEqual(
            _clasificar_base_clase_sat(
                "CFDIs Emitidos Productos (6) Nuevo CCR.csv",
                emitted_products,
                "classifier-test",
            ),
            "emitidos",
        )
        self.assertEqual(
            _clasificar_base_clase_sat(
                "CFDI Recibidos Productos CCR Nuevo.csv",
                received_products,
                "classifier-test",
            ),
            "egresos",
        )


if __name__ == "__main__":
    unittest.main()
