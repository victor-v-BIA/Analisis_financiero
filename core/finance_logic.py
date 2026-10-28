# Modelos financieros (resumen_mensual, matriz_anual, cruces PPD)
'''Contiene todo el motor matemático y
financiero del sistema: resúmenes mensuales,
matrices anuales, cruces PPD, plazos y cálculos de dictamen.'''

import pandas as pd
import streamlit as st
import io
import unicodedata
import re
import numpy as np
from config import (CODIGO_VERSION, DIAS_GRACIA_PPD, MESES_ES, COLUMNAS_DETALLE_ANUAL,PERIODOS_EVALUACION,MARGEN_SEGURIDAD_PCT,TASA_REFERENCIA_ANUAL
,BANDAS_DICTAMEN,PESOS_INDICE,REGLAS_INDICE,MIN_MESES_MARGEN, VENTANA_MARGEN_MESES, MIN_ANIOS_ESTABILIDAD, SIN_DICTAMEN)


from core.loader import (_facturas_cache,
                    excluir_años_incompletos, cargar_base,
                      _complementos_cache, _facturas_egresos_cache, preparar_complementos_egresos, obtener_anios_analisis)

from utils import(_resolver_fecha_pagos, a_fecha, _mxn, _nombre_abreviado, _lista_anios, a_numero,_columna_unica,
                  buscar_columna)
from config import (_RFC_GENERICOS )


def resumen_mensual(facturas: pd.DataFrame, complementos: pd.DataFrame, ejercicios: list[int]) -> pd.DataFrame:
    """Una fila por mes de cada ejercicio seleccionado (los 12 meses de cada año, en orden cronológico).

    Facturado_* = devengado por fecha de factura (solo Tipo Documento 'Factura', sin NCR). Cobrado_PPD = Cobro
    Efectivo del REP agrupado por Fecha_Cobro (Fecha de Pago; ya definida al leer cada archivo). Cobrado_Total = PUE (se asume cobrado al facturar) + Cobrado_PPD.
    NCR_* = Notas de Crédito por fecha de emisión. Ingreso_Neto = Cobrado_Total - NCR_Total.
    """
    meses = pd.PeriodIndex([f"{a}-{m:02d}" for a in sorted(ejercicios) for m in range(1, 13)], freq="M")
    normal = facturas[~facturas["Es_NCR"]].assign(Mes=facturas["Fecha"].dt.to_period("M"))
    # El Total de una NCR puede venir en negativo en el archivo de origen (signo o formato contable); se usa su
    # valor absoluto para que "Total Notas de Crédito" sea siempre una magnitud positiva y el Ingreso Neto reste
    # correctamente, sea cual sea la convención de signo del archivo.
    ncr = (facturas[facturas["Es_NCR"]]
           .assign(Mes=facturas["Fecha"].dt.to_period("M"), Total=lambda d: d["Total"].abs()))
    piv = normal.pivot_table(index="Mes", columns="Metodo_Pago", values="Total", aggfunc="sum", fill_value=0.0)
    piv = piv.reindex(index=meses, columns=["PUE", "PPD"], fill_value=0.0).fillna(0.0)
    ncr_mes = ncr.groupby("Mes")["Total"].sum().reindex(meses, fill_value=0.0)
    rep = (complementos.assign(Mes=complementos["Fecha_Cobro"].dt.to_period("M"))
           .groupby("Mes")["Cobro_Efectivo"].sum().reindex(meses, fill_value=0.0))

    out = pd.DataFrame({
        "Facturado_PUE": piv["PUE"], "Facturado_PPD": piv["PPD"], "Cobrado_PPD": rep, "NCR_Total": ncr_mes,
    })
    out["Facturado_Total"] = out["Facturado_PUE"] + out["Facturado_PPD"]
    out["Cobrado_Total"] = out["Facturado_PUE"] + out["Cobrado_PPD"]
    out["Ingreso_Neto"] = out["Cobrado_Total"] - out["NCR_Total"]
    out["PPD_Facturado_Acum"] = out["Facturado_PPD"].cumsum()
    out["PPD_Cobrado_Acum"] = out["Cobrado_PPD"].cumsum()
    out["PPD_Por_Cobrar_Acum"] = out["PPD_Facturado_Acum"] - out["PPD_Cobrado_Acum"]
    out.index = out.index.strftime("%Y-%m")
    out.index.name = "Mes"
    return out



def ncr_por_año(fac: pd.DataFrame) -> pd.Series:
    """Total de Notas de Crédito (df_ncr) agrupado por Año de emisión. Sin desglose PUE/PPD.

    Se agrupa por Año explícitamente y aparte del resumen mensual, para que la matriz anual cruce los montos
    por su propio índice de año y no dependa de la reconstrucción de años a partir del índice mensual.
    Devuelve NCR_Total, NCR_PUE y NCR_PPD (NCR_PUE se usa para el Ingreso Neto de la gráfica anual de Flujo de Efectivo).
    """
    df_ncr = fac[fac["Es_NCR"]].copy()
    df_ncr["Año"] = df_ncr["Fecha"].dt.year
    # Total ya es numérico (viene de a_numero), pero se refuerza con to_numeric por si llegara como texto.
    df_ncr["Total"] = pd.to_numeric(df_ncr["Total"], errors="coerce").abs()
    es_pue = df_ncr["Metodo_Pago"].astype(str).str.contains("PUE", case=False, na=False)
    es_ppd = df_ncr["Metodo_Pago"].astype(str).str.contains("PPD", case=False, na=False)
    ncr_pue_por_año = df_ncr[es_pue].groupby("Año")["Total"].sum()
    ncr_ppd_por_año = df_ncr[es_ppd].groupby("Año")["Total"].sum()
    return pd.DataFrame({
        "NCR_Total": df_ncr.groupby("Año")["Total"].sum(),
        "NCR_PUE": ncr_pue_por_año,
        "NCR_PPD": ncr_ppd_por_año,
    }).fillna(0.0)


def complementos_vigentes(rep: pd.DataFrame) -> float:
    """Complementos de pago: suma de TODOS los importes vigentes (`Cobro_Efectivo`) de la base de complementos ya filtrada al periodo, sin exigir
    coincidencia por UUID con las facturas cargadas. Única fuente de las tarjetas, el desglose anual y «Método de cobro» (vista Total)."""
    return float(rep["Cobro_Efectivo"].sum())


def diferencia_ppd(facturado_ppd, complementos):
    """Única fórmula de la diferencia PPD: Facturación PPD vigente − Complementos (escalares o Series por año). NO fuerza negativos a cero: si los
    complementos superan la facturación PPD del periodo (pagan facturas de otros ejercicios), la diferencia sale negativa tal cual."""
    return facturado_ppd - complementos


def facturas_a_mxn(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Facturas recibidas con `Total` (y `SubTotal`) convertidos a MXN (`Factor_MXN` = 1 en pesos, Tipo de Cambio en moneda extranjera) ANTES de
    agregarlos. Una factura extranjera sin Tipo de Cambio válido se excluye (nunca se suma sin convertir). Los complementos ('Monto MXN') ya vienen
    en pesos y NO se vuelven a convertir. Devuelve (DataFrame en MXN, n de facturas excluidas)."""
    if "Factor_MXN" not in df.columns:
        return df, 0
    ok = df["Factor_MXN"].notna()
    out = df[ok].copy()
    for c in ("Total", "SubTotal"):
        if c in out.columns:
            out[c] = out[c] * out["Factor_MXN"]
    return out, int((~ok).sum())


def resumen_egresos(pue, ppd, complementos, nomina) -> dict:
    """Única función de cálculo de Egresos (tarjetas, desglose anual y gráficas; escalares o Series por año): Facturación = PUE + PPD (Total en MXN);
    Diferencia PPD = Facturación PPD − Complementos (`diferencia_ppd`, sin forzar negativos); Pagado Total = PUE + Complementos; Egreso Total =
    PUE + Complementos + Nómina. Las Notas de Crédito se presentan aparte y NO se descuentan de ningún indicador de este resumen."""
    return {"facturacion": pue + ppd, "pue": pue, "ppd": ppd, "complementos": complementos, "diferencia": diferencia_ppd(ppd, complementos),
            "nomina": nomina, "pagado_total": pue + complementos, "egreso_total": pue + complementos + nomina}


def matriz_anual(res: pd.DataFrame, ncr_anual: pd.DataFrame) -> pd.DataFrame:
    """Una fila por año con los mismos rubros de los KPI (Flujo de Efectivo) a partir del resumen mensual.

    `ncr_anual` (salida de `ncr_por_año`) se reindexa sobre los años de la matriz con `fill_value=0`: un año sin
    Notas de Crédito debe quedar en 0 real, no perderse por no calzar con el índice. Las Notas de Crédito se muestran
    únicamente con su total (sin desglose PUE / PPD).
    """
    cols = ["Facturado_Total", "Facturado_PUE", "Facturado_PPD", "Cobrado_Total", "Cobrado_PPD"]
    a = res[cols].groupby(pd.PeriodIndex(res.index, freq="M").year).sum()
    ncr_a = ncr_anual.reindex(a.index, fill_value=0.0)
    pct = (a["Cobrado_PPD"] / a["Facturado_PPD"] * 100).where(a["Facturado_PPD"] != 0)
    m = pd.DataFrame({
        "Facturación Emitida Total": a["Facturado_Total"],
        "\xa0\xa0\xa0\xa0Facturación PUE": a["Facturado_PUE"],
        "\xa0\xa0\xa0\xa0Facturación PPD": a["Facturado_PPD"],
        "Complementos de Pago Emitidos": a["Cobrado_PPD"],
        "Cobrado Total (PUE + Complementos)": a["Cobrado_Total"],
        "Notas de Crédito": ncr_a["NCR_Total"],
    })
    # Ingreso Neto por año = "Cobrado Total (PUE + Complementos)" - "Notas de Crédito" de ese mismo año.
    m["Ingreso Neto"] = a["Cobrado_Total"] - ncr_a["NCR_Total"]
    m["Ingreso por Cobrar"] = diferencia_ppd(a["Facturado_PPD"], a["Cobrado_PPD"])
    m["% Cobranza PPD"] = pct
    m.index = m.index.astype(str)
    m.index.name = "Año"
    return m


def ncr_por_año_egresos(fac: pd.DataFrame) -> pd.DataFrame:
    """Notas de Crédito (Tipo Documento = 'NCR') de Facturas Recibidas, agrupadas por Año de emisión y
    desglosadas por Método de Pago (PUE/PPD) -sin exigir que toda NCR lo traiga; NCR_PUE + NCR_PPD puede no
    igualar NCR_Total si alguna fila no especifica método-.

    Valor absoluto del Total: algunas bases lo traen en negativo (formato contable) y 'Notas de Crédito' debe
    ser siempre una magnitud positiva para poder restarse directamente del Pagado Total.
    """
    df_ncr = fac[fac["Es_NCR"]].copy()
    df_ncr["Año"] = df_ncr["Fecha"].dt.year
    df_ncr["Total"] = df_ncr["Total"].abs()
    es_pue = df_ncr["Metodo_Pago"].astype(str).str.upper() == "PUE"
    es_ppd = df_ncr["Metodo_Pago"].astype(str).str.upper() == "PPD"
    return pd.DataFrame({
        "NCR_Total": df_ncr.groupby("Año")["Total"].sum(),
        "NCR_PUE": df_ncr[es_pue].groupby("Año")["Total"].sum(),
        "NCR_PPD": df_ncr[es_ppd].groupby("Año")["Total"].sum(),
    }).fillna(0.0)


def excluir_cfdis_divisas(facturas: pd.DataFrame, productos: pd.DataFrame) -> tuple[pd.DataFrame, set[str], dict[str, int]]:
    """Excluye CFDI que coinciden sin ambigüedad con conceptos de compra de divisas.

    El archivo de productos no tiene UUID, por lo que la relación se limita a RFC emisor, fecha e importe
    exacto al centavo. Solo se aceptan grupos donde el número de conceptos y CFDI coincidentes es el mismo.
    """
    columnas = {
        "Clave": buscar_columna(productos.columns, "Clave"),
        "RFC Emisor": buscar_columna(productos.columns, "RFC Emisor"),
        "Fecha": buscar_columna(productos.columns, "Fecha"),
        "Importe": buscar_columna(productos.columns, "Importe"),
    }
    faltantes = [nombre for nombre, columna in columnas.items() if columna is None]
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas en el archivo de productos: {faltantes}")

    clave = (productos[columnas["Clave"]].fillna("").astype(str).str.strip()
             .str.replace(r"\.0$", "", regex=True))
    filas = productos.loc[clave.eq("84121603")].copy()
    estadisticas = {"conceptos": len(filas), "coincidencias": 0, "sin_coincidencia": 0, "ambiguos": 0}
    if filas.empty:
        return facturas.copy(), set(), estadisticas

    conceptos = pd.DataFrame({
        "_RFC": filas[columnas["RFC Emisor"]].fillna("").astype(str).str.strip().str.upper(),
        "_Fecha": a_fecha(filas[columnas["Fecha"]]),
        "_Importe": a_numero(filas[columnas["Importe"]]).round(2),
    }, index=filas.index)
    conceptos = conceptos[
        conceptos["_RFC"].ne("") & conceptos["_Fecha"].notna() & conceptos["_Importe"].notna()
    ]
    estadisticas["sin_coincidencia"] += len(filas) - len(conceptos)

    facturas_validas = facturas.loc[~facturas["Es_NCR"]].copy()
    candidatos = pd.DataFrame({
        "_RFC": facturas_validas["RFC_Emisor"].fillna("").astype(str).str.strip().str.upper(),
        "_Fecha": facturas_validas["Fecha"],
        "_Importe": pd.to_numeric(facturas_validas["Total"], errors="coerce").round(2),
        "_UUID": facturas_validas["UUID"].fillna("").astype(str).str.strip().str.upper(),
    }, index=facturas_validas.index)
    candidatos = candidatos[
        candidatos["_RFC"].ne("") & candidatos["_Fecha"].notna()
        & candidatos["_Importe"].notna() & candidatos["_UUID"].ne("")
    ]

    columnas_clave = ["_RFC", "_Fecha", "_Importe"]
    conteo_conceptos = conceptos.groupby(columnas_clave).size().rename("_Conceptos")
    conteo_facturas = candidatos.groupby(columnas_clave).size().rename("_Facturas")
    conteos = pd.concat([conteo_conceptos, conteo_facturas], axis=1).fillna(0).astype(int)
    exactos = conteos[conteos["_Conceptos"].eq(conteos["_Facturas"]) & conteos["_Conceptos"].gt(0)].index
    no_coinciden = conteos[~conteos.index.isin(exactos)]
    estadisticas["sin_coincidencia"] += int(no_coinciden.loc[no_coinciden["_Facturas"].eq(0), "_Conceptos"].sum())
    estadisticas["ambiguos"] = int(no_coinciden.loc[no_coinciden["_Facturas"].gt(0), "_Conceptos"].sum())

    if len(exactos):
        conceptos_exactos = conceptos.set_index(columnas_clave).loc[exactos].reset_index()
        candidatos_exactos = candidatos.set_index(columnas_clave).loc[exactos].reset_index()
        # Los conteos por clave son iguales; con importes idénticos, las UUID no afectan el total excluido.
        excluir = set(candidatos_exactos["_UUID"])
        estadisticas["coincidencias"] = len(conceptos_exactos)
    else:
        excluir = set()

    resultado = facturas.loc[
        ~facturas["UUID"].fillna("").astype(str).str.strip().str.upper().isin(excluir)
    ].copy()
    return resultado, excluir, estadisticas


def excluir_complementos_de_cfdis(complementos: pd.DataFrame, uuids: set[str]) -> tuple[pd.DataFrame, int | None]:
    """Excluye complementos enlazados por UUID a CFDI de divisas; None indica que no existe columna de relación."""
    if not uuids:
        return complementos.copy(), 0
    columna_relacion = buscar_columna(complementos.columns, "UUID DR") or buscar_columna(
        complementos.columns, "Documento Relacionado")
    if columna_relacion is None:
        return complementos.copy(), None
    relacionados = complementos[columna_relacion].fillna("").astype(str).str.strip().str.upper()
    excluir = relacionados.isin(uuids)
    return complementos.loc[~excluir].copy(), int(excluir.sum())


def matriz_anual_egresos(fac: pd.DataFrame, pagado_ppd_por_año: pd.Series, ncr_anual: pd.DataFrame,
                         nomina_por_año: pd.Series, ejercicios: list[int]) -> pd.DataFrame:
    """Una fila por año con los mismos rubros de los KPI de Egresos: Notas de Crédito y Nómina Pagada.

    `fac` trae tanto Factura como NCR (bandera Es_NCR) filtradas por los ejercicios seleccionados; Facturación/
    Pagado se calculan SOLO con Factura (`~Es_NCR`). `pagado_ppd_por_año` ya viene agrupada por Año desde la
    base de complementos de pago (Base PAGO). `ncr_anual` (salida de ncr_por_año_egresos) ya viene agrupada por
    Año de emisión. Las Notas de Crédito se ven únicamente con su total (sin detalle PUE/PPD). `nomina_por_año` ya viene agrupada por Año desde la Base de
    Nómina. Reindexa sobre `ejercicios` para que un año sin datos quede en 0 real, no se pierda.
    """
    idx = pd.Index(sorted(ejercicios), name="Año")
    fac_factura = fac[~fac["Es_NCR"]]
    fact_pue = fac_factura[fac_factura["Metodo_Pago"] == "PUE"].groupby(
        fac_factura["Fecha"].dt.year)["Total"].sum().reindex(idx, fill_value=0.0)
    fact_ppd = fac_factura[fac_factura["Metodo_Pago"] == "PPD"].groupby(
        fac_factura["Fecha"].dt.year)["Total"].sum().reindex(idx, fill_value=0.0)
    pagado_ppd = pagado_ppd_por_año.reindex(idx, fill_value=0.0)
    ncr_a = ncr_anual.reindex(idx, fill_value=0.0)
    nomina = nomina_por_año.reindex(idx, fill_value=0.0)
    cifras = resumen_egresos(fact_pue, fact_ppd, pagado_ppd, nomina)          # la misma función de las tarjetas y las gráficas
    fact_total, pagado_total, egreso_total, saldo_ppd = cifras["facturacion"], cifras["pagado_total"], cifras["egreso_total"], cifras["diferencia"]
    egreso_operativo_neto = pagado_total - ncr_a["NCR_Total"]                  # indicador aparte: las NCR no se descuentan del Egreso Total
    pct_saldo_ppd = (saldo_ppd / fact_ppd * 100).where(fact_ppd != 0, 0.0)

    m = pd.DataFrame({
        "Facturación Recibida Total": fact_total,
        "\xa0\xa0\xa0\xa0Facturación PUE": fact_pue,
        "\xa0\xa0\xa0\xa0Facturación PPD": fact_ppd,
        "Pagado Total (PUE + Complementos)": pagado_total,
        "Complementos de Pago Recibidos": pagado_ppd,
        "Notas de Crédito": ncr_a["NCR_Total"],
    })
    m["Egreso Operativo Neto"] = egreso_operativo_neto
    m["Pagos a Nómina"] = nomina
    m["Egreso Total (Operación + Nómina)"] = egreso_total
    m["Saldo PPD por Pagar"] = saldo_ppd
    m["% Saldo PPD por Pagar"] = pct_saldo_ppd
    m.index = m.index.astype(str)
    m.index.name = "Año"
    return m

def resumen_mensual_egresos(fac_factura: pd.DataFrame, df_rep: pd.DataFrame, ejercicios: list[int]) -> pd.DataFrame:
    """Una fila por mes de cada ejercicio seleccionado, análoga a `resumen_mensual` pero para Egresos.

    Facturado_* = devengado por fecha de factura (`fac_factura` ya viene sin NCR). Pagado_PPD = Monto_Num de
    los complementos de pago (`df_rep` ya viene filtrado a los ejercicios seleccionados), agrupado por
    su fecha de pago (Fecha Pago) vía la columna "Mes" que ya trae asignada.
    """
    meses = pd.PeriodIndex([f"{a}-{m:02d}" for a in sorted(ejercicios) for m in range(1, 13)], freq="M")
    fac_mes = fac_factura.assign(Mes=fac_factura["Fecha"].dt.to_period("M"))
    piv = fac_mes.pivot_table(index="Mes", columns="Metodo_Pago", values="Total", aggfunc="sum", fill_value=0.0)
    piv = piv.reindex(index=meses, columns=["PUE", "PPD"], fill_value=0.0).fillna(0.0)
    pagado_mes = df_rep.groupby("Mes")["Monto_Num"].sum().reindex(meses, fill_value=0.0)

    out = pd.DataFrame({"Facturado_PUE": piv["PUE"], "Facturado_PPD": piv["PPD"], "Pagado_PPD": pagado_mes})
    out["Facturado_Total"] = out["Facturado_PUE"] + out["Facturado_PPD"]
    out["Pagado_Total"] = out["Facturado_PUE"] + out["Pagado_PPD"]
    out["PPD_Facturado_Acum"] = out["Facturado_PPD"].cumsum()
    out["PPD_Pagado_Acum"] = out["Pagado_PPD"].cumsum()
    out.index = out.index.strftime("%Y-%m")
    out.index.name = "Mes"
    return out



def _uuids_pue(facturas: pd.DataFrame) -> frozenset:
    """UUID (normalizado: sin espacios, mayúsculas) de las facturas vigentes con Método de Pago PUE (sin NCR), calculado sobre
    la base completa antes de recortar por la ventana de 5 años: un complemento puede apuntar a una factura PUE de otro año."""
    pue = facturas[~facturas["Es_NCR"] & (facturas["Metodo_Pago"] == "PUE")]
    return frozenset(pue["UUID"].astype(str).str.strip().str.upper())



def _cruce_saldo_insoluto(df_fac: pd.DataFrame, df_pagos: pd.DataFrame, excluir_ncr: bool = False) -> pd.DataFrame:
    """Cruza facturas PPD con sus Complementos de Pago por 'UUID' / 'UUID DR' y calcula el Saldo Insoluto.

    Nomenclatura exacta y fija, sin tolerancia a variantes ni acentos (confirmada contra el origen de datos
    real): 'UUID', 'Metodo de Pago', 'Total', 'Fecha y Hora' y 'Estatus' en las facturas; 'UUID DR' y
    'Monto MXN' en los Complementos de Pago. Si falta alguna, el KeyError se deja propagar al llamador -que
    decide el mensaje según de qué archivo se trate-. Se usa igual para Ingresos y Egresos: ambos comparten la
    misma estructura (esta es la Única Fuente de Verdad: Dashboard Ejecutivo y las tarjetas de Ingresos/Egresos
    llaman a esta misma función con los mismos parámetros para no divergir nunca en un centavo).

    Filtro innegociable de Estatus: solo se consideran facturas 'Vigente'/'Activo' (limpio, sin acentos ni
    mayúsculas). Una factura Cancelada no representa una obligación de cobro/pago real y debe excluirse del
    cruce por completo, sin importar su Método de Pago o Tipo de Documento -de lo contrario el Saldo Insoluto
    queda inflado con facturas que ya no existen-.

    `excluir_ncr=True` (Morosidad, y las tarjetas "Saldo PPD por Cobrar/Pagar" homologadas) además exige
    'Tipo Documento' de Ingreso -código SAT 'I' o, en bases que aún usan el texto legado, 'Factura'- para
    excluir ESTRICTAMENTE las Notas de Crédito ('E' / 'NCR') y no inflar el saldo con ellas. La Brecha de
    Capital (excluir_ncr=False, default) no aplica este filtro adicional: ahí una NCR sí debe descontarse del
    saldo, no simplemente ignorarse.
    """
    fac_ppd = df_fac[df_fac["Metodo de Pago"].astype(str).str.contains("PPD", case=False, na=False)].copy()
    estatus_limpio = fac_ppd["Estatus"].astype(str).str.strip().str.upper()
    fac_ppd = fac_ppd[estatus_limpio.isin(["VIGENTE", "ACTIVO"])]
    if excluir_ncr:
        tipo_doc = fac_ppd["Tipo Documento"].astype(str).str.strip().str.upper()
        fac_ppd = fac_ppd[tipo_doc.isin(["I", "FACTURA"])]

    monto_mxn = pd.to_numeric(
        _columna_unica(df_pagos, "Monto MXN").astype(str).str.replace("$", "", regex=False)
                                             .str.replace(",", "", regex=False), errors="coerce").fillna(0)
    uuid_dr = _columna_unica(df_pagos, "UUID DR")
    pagos_agrupados = pd.DataFrame({"UUID DR": uuid_dr, "Monto MXN": monto_mxn}).groupby(
        "UUID DR", as_index=False)["Monto MXN"].sum()

    df_merge = pd.merge(fac_ppd, pagos_agrupados, left_on="UUID", right_on="UUID DR", how="left")
    df_merge["Monto MXN"] = df_merge["Monto MXN"].fillna(0)
    df_merge["Total"] = pd.to_numeric(
        df_merge["Total"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce").fillna(0)
    df_merge["Saldo_Insoluto"] = df_merge["Total"] - df_merge["Monto MXN"]
    return df_merge


def _total_facturado_ppd_vigente(df_fac: pd.DataFrame) -> float:
    """Suma 'Total' de las facturas con Método de Pago PPD, Tipo Documento de Ingreso ('I'/'Factura') y
    Estatus 'Vigente'/'Activo' -el mismo universo limpio que _cruce_saldo_insoluto(excluir_ncr=True), pero sin
    cruzar contra pagos: es la mitad "Facturado" de la resta macro del Dashboard Ejecutivo."""
    metodo_ppd = df_fac["Metodo de Pago"].astype(str).str.contains("PPD", case=False, na=False)
    tipo_doc = df_fac["Tipo Documento"].astype(str).str.strip().str.upper().isin(["I", "FACTURA"])
    estatus = df_fac["Estatus"].astype(str).str.strip().str.upper().isin(["VIGENTE", "ACTIVO"])
    total = pd.to_numeric(
        df_fac["Total"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce").fillna(0)
    return float(total[metodo_ppd & tipo_doc & estatus].sum())


def _total_pagado(df_pagos: pd.DataFrame) -> float:
    """Suma cruda de 'Monto MXN' en el archivo de pagos completo, sin cruzar factura por factura -la mitad
    "Cobrado/Pagado" de la resta macro del Dashboard Ejecutivo."""
    monto = pd.to_numeric(
        df_pagos["Monto MXN"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce").fillna(0)
    return float(monto.sum())


def _tabla_contraparte(df: pd.DataFrame, col_rfc: str | None, col_nombre: str | None,
                       saldo_total: float) -> pd.DataFrame:
    """Tabla completa (todas las contrapartes, no solo el Top 3) de `df` por 'Saldo_Insoluto', agrupadas por
    RFC -identificador único- cuando existe, o por Razón Social si no hay RFC. Incluye el conteo de facturas
    únicas (UUID) que integran cada saldo. Devuelve columnas separadas y sin truncar -'RFC', 'Razón Social',
    'Facturas Pendientes', 'Saldo Insoluto' y '% del Saldo'-, ordenadas de mayor a menor saldo.
    """
    col_id = col_rfc or col_nombre
    columnas_agg = {"Saldo Insoluto": ("Saldo_Insoluto", "sum"), "Facturas Pendientes": ("UUID", "nunique")}
    if col_rfc and col_nombre:
        columnas_agg["Razón Social"] = (col_nombre, "first")
    tabla = (df.groupby(col_id).agg(**columnas_agg)
            .sort_values("Saldo Insoluto", ascending=False).reset_index())

    if col_rfc:
        tabla = tabla.rename(columns={col_id: "RFC"})
        if not col_nombre:
            tabla["Razón Social"] = "n/a"
    else:
        tabla = tabla.rename(columns={col_id: "Razón Social"})
        tabla["RFC"] = "n/a"
    tabla["% del Saldo"] = (tabla["Saldo Insoluto"] / saldo_total * 100) if saldo_total else 0.0
    return tabla[["RFC", "Razón Social", "Facturas Pendientes", "Saldo Insoluto", "% del Saldo"]]


def _aplicaciones_pago_validas(df_fac: pd.DataFrame, df_pagos: pd.DataFrame) -> dict | None:
    """Aplicaciones de pago con relación documental real (UUID DR = UUID de una factura vigente tipo Factura)
    y días válidos = Fecha de Pago − Fecha de Emisión (ambas sin hora). SIEMPRE la 'Fecha de Pago' del archivo
    de pagos para calcular los días. Excluye (y cuenta aparte) las filas con alguna fecha faltante o con
    intervalo negativo; nunca las convierte en 0.

    `Fecha_Agrup` es la fecha que decide a QUÉ AÑO pertenece la aplicación en la comparación anual: la misma
    fecha de pago. No interviene en el cálculo de los días.

    Devuelve {'validos': DataFrame, 'n_total', 'n_sin_fecha', 'n_negativos'} o `None` si faltan columnas."""
    if "UUID DR" not in df_pagos.columns or "UUID" not in df_fac.columns:
        return None
    col_fecha_pago = _resolver_fecha_pagos(df_pagos.columns)
    if col_fecha_pago is None:
        return None

    fac = df_fac.copy()
    estatus_fac = fac["Estatus"].astype(str).str.strip().str.upper()
    fac = fac[estatus_fac.isin(["VIGENTE", "ACTIVO"])]
    tipo_doc = fac["Tipo Documento"].astype(str).str.strip().str.upper()
    fac = fac[tipo_doc.isin(["I", "FACTURA"])]
    fac["Fecha_Emision"] = a_fecha(fac["Fecha y Hora"])  # DD/MM/YYYY o ISO (pd.to_datetime las lee mes-primero)
    fac = (fac[["UUID", "Fecha_Emision"]].dropna(subset=["Fecha_Emision"])
                                         .drop_duplicates(subset="UUID", keep="first"))

    pagos = df_pagos.copy()
    if "Estatus" in pagos.columns:
        estatus_pago = pagos["Estatus"].astype(str).str.strip().str.upper()
        pagos = pagos[~estatus_pago.isin(["CANCELADO", "CANCELADA"])]
    pagos["Fecha_Pago"] = a_fecha(pagos[col_fecha_pago])
    pagos["Fecha_Agrup"] = pagos["Fecha_Pago"]
    pagos["Monto"] = pd.to_numeric(
        _columna_unica(pagos, "Monto MXN").astype(str).str.replace("$", "", regex=False)
                                          .str.replace(",", "", regex=False), errors="coerce").fillna(0)

    cruce = pd.merge(pagos[["UUID DR", "Fecha_Pago", "Fecha_Agrup", "Monto"]], fac, left_on="UUID DR",
                     right_on="UUID", how="inner")
    n_total = int(len(cruce))
    sin_fecha = cruce["Fecha_Emision"].isna() | cruce["Fecha_Pago"].isna()
    n_sin_fecha = int(sin_fecha.sum())
    validos = cruce[~sin_fecha].copy()
    validos["Dias"] = (validos["Fecha_Pago"] - validos["Fecha_Emision"]).dt.days
    negativos = validos["Dias"] < 0
    n_negativos = int(negativos.sum())
    return {"validos": validos[~negativos], "n_total": n_total, "n_sin_fecha": n_sin_fecha,
            "n_negativos": n_negativos}


def _tiempos_por_periodo(df_fac: pd.DataFrame, df_pagos: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Días entre la emisión de la factura PPD y la fecha de su pago, agrupados por el periodo de la fecha de pago real del
    complemento (`Fecha_Agrup`, ver `_aplicaciones_pago_validas`): `freq='M'` -> Año-Mes ('YYYY-MM') y `freq='Y'` -> Año ('YYYY').
    Cada periodo usa SUS propias aplicaciones válidas: 'dias_promedio' (ponderado por el importe aplicado; None si el importe
    suma 0), 'dias_mediana' (mediana simple), 'n_validos' y 'monto_valido'. Un periodo sin aplicaciones válidas no aparece (nunca
    se rellena con 0); las aplicaciones sin fecha de pago quedan fuera (`attrs['n_sin_periodo']`). Índice 'Periodo' ordenado."""
    columnas = ["dias_promedio", "dias_mediana", "n_validos", "monto_valido"]
    vacio = pd.DataFrame(columns=columnas, index=pd.Index([], name="Periodo", dtype="object"))
    vacio.attrs["n_sin_periodo"] = 0
    aplicaciones = _aplicaciones_pago_validas(df_fac, df_pagos)
    if aplicaciones is None or aplicaciones["validos"].empty:
        return vacio
    validos = aplicaciones["validos"]
    sin_fecha = validos["Fecha_Agrup"].isna()
    validos = validos[~sin_fecha]
    if validos.empty:
        vacio.attrs["n_sin_periodo"] = int(sin_fecha.sum())
        return vacio
    filas = {}
    for periodo, g in validos.groupby(validos["Fecha_Agrup"].dt.to_period(freq)):
        monto = float(g["Monto"].sum())
        filas[str(periodo)] = {"dias_promedio": float((g["Dias"] * g["Monto"]).sum() / monto) if monto else None,
                               "dias_mediana": float(g["Dias"].median()), "n_validos": int(len(g)), "monto_valido": monto}
    out = pd.DataFrame.from_dict(filas, orient="index", columns=columnas).sort_index()
    out.index.name = "Periodo"
    out.attrs["n_sin_periodo"] = int(sin_fecha.sum())
    return out


def _valor_mxn_facturas(df: pd.DataFrame, metodo_pago: str | None) -> tuple[pd.Series | None, str | None, int]:
    """Serie 'Mes' (Period[M]) -> suma de Total convertido a MXN de facturas activas (Vigente/Activo, Tipo
    Documento 'I'/'Factura', excluye NCR), agrupadas por mes de emisión. `metodo_pago` filtra además por
    'Metodo de Pago' (p. ej. "PUE"); None para no filtrar por método.

    Conversión de moneda: factor 1 si es MXN o no hay columna 'Moneda'; si es extranjera, requiere 'Tipo de
    Cambio' válido (>0) o la factura queda EXCLUIDA de la suma (nunca se suma sin convertir) -mismo criterio
    que la Sección 5 (Concentración)-.

    Devuelve (serie | None, motivo | None, n_excluidas_por_moneda). `serie` es `None` si falta alguna columna
    indispensable (Total/SubTotal, Fecha de emisión, Estatus, o 'Metodo de Pago' cuando `metodo_pago` no es
    `None`) -nunca se asume $0 por una columna faltante-.
    """
    col_fecha = buscar_columna(df.columns, "Fecha y Hora") or buscar_columna(df.columns, "Fecha")
    col_valor = buscar_columna(df.columns, "Total") or buscar_columna(df.columns, "SubTotal")   # el Total (con impuestos), igual que el resto del tablero
    col_estatus = buscar_columna(df.columns, "Estatus")
    col_tipo = buscar_columna(df.columns, "Tipo Documento")
    col_metodo = buscar_columna(df.columns, "Metodo de Pago")
    faltantes = [n for n, c in (("Fecha de emisión", col_fecha), ("Total/SubTotal", col_valor),
                                ("Estatus", col_estatus)) if c is None]
    if metodo_pago is not None and col_metodo is None:
        faltantes.append("Metodo de Pago")
    if faltantes:
        return None, "faltan columnas: " + ", ".join(faltantes), 0

    activos = df[col_estatus].astype(str).str.strip().str.upper().isin(["VIGENTE", "ACTIVO"])
    if col_tipo is not None:
        activos &= df[col_tipo].astype(str).str.strip().str.upper().isin(["I", "FACTURA"])
    if metodo_pago is not None:
        activos &= df[col_metodo].astype(str).str.strip().str.upper() == metodo_pago.upper()
    d = df[activos]
    if d.empty:
        return pd.Series(dtype=float), None, 0

    valor_crudo = pd.to_numeric(d[col_valor].astype(str).str.replace("$", "", regex=False)
                                             .str.replace(",", "", regex=False), errors="coerce").fillna(0)
    col_moneda = buscar_columna(df.columns, "Moneda")
    col_tc = buscar_columna(df.columns, "Tipo de Cambio")
    if col_moneda is not None:
        moneda = d[col_moneda].astype(str).str.strip().str.upper()
        es_mxn = moneda.isin(["MXN", "PESOS", "PESO MEXICANO", "NAN", ""])
    else:
        es_mxn = pd.Series(True, index=d.index)
    if col_tc is not None:
        tipo_cambio = pd.to_numeric(d[col_tc].astype(str).str.replace("$", "", regex=False)
                                              .str.replace(",", "", regex=False), errors="coerce")
    else:
        tipo_cambio = pd.Series(1.0, index=d.index)
    factor = tipo_cambio.where(~es_mxn, 1.0)
    convertible = es_mxn | (factor.notna() & (factor > 0))
    n_excluidas = int((~convertible).sum())
    valor_mxn = (valor_crudo * factor).where(convertible)

    fechas = a_fecha(d[col_fecha])  # DD/MM/YYYY o ISO (pd.to_datetime las lee mes-primero)
    mensual = pd.DataFrame({"Mes": fechas.dt.to_period("M"), "Valor": valor_mxn}).dropna(subset=["Mes", "Valor"])
    return mensual.groupby("Mes")["Valor"].sum(), None, n_excluidas


def _rep_mensual_mxn(df: pd.DataFrame) -> tuple[pd.Series | None, str | None]:
    """Serie 'Mes' (Period[M]) -> suma de Complementos de Pago activos, agrupados por mes de su fecha de pago real
    ('Fecha de Pago'; 'Fecha Pago' en Egresos). Usa 'Monto MXN' si la columna
    existe (ya viene en MXN); si no, cae a Saldo Inicial − Saldo Final (mismo fallback que
    `_total_pagado_tolerante`, asumido ya en MXN -ningún Complemento de este archivo trae 'Moneda'/'Tipo de
    Cambio' propios en la práctica, a diferencia de las facturas-).

    Devuelve (serie | None, motivo | None); `serie` es `None` si falta 'Fecha de Pago' o tanto 'Monto MXN'
    como 'Saldo Inicial'/'Saldo Final'.
    """
    col_fecha = _resolver_fecha_pagos(df.columns)
    col_estatus = buscar_columna(df.columns, "Estatus")
    col_monto = buscar_columna(df.columns, "Monto MXN")
    col_si = buscar_columna(df.columns, "Saldo Inicial")
    col_sf = buscar_columna(df.columns, "Saldo Final")
    if col_fecha is None:
        return None, "falta columna de Fecha de Pago"
    if col_monto is None and (col_si is None or col_sf is None):
        return None, "falta 'Monto MXN' (o 'Saldo Inicial'/'Saldo Final' como alternativa)"

    activos = pd.Series(True, index=df.index)
    if col_estatus is not None:
        activos &= df[col_estatus].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])
    d = df[activos]
    if d.empty:
        return pd.Series(dtype=float), None

    if col_monto is not None:
        monto = pd.to_numeric(d[col_monto].astype(str).str.replace("$", "", regex=False)
                                           .str.replace(",", "", regex=False), errors="coerce").fillna(0)
    else:
        si = pd.to_numeric(d[col_si].astype(str).str.replace("$", "", regex=False)
                                     .str.replace(",", "", regex=False), errors="coerce").fillna(0)
        sf = pd.to_numeric(d[col_sf].astype(str).str.replace("$", "", regex=False)
                                     .str.replace(",", "", regex=False), errors="coerce").fillna(0)
        monto = si - sf

    fechas = a_fecha(d[col_fecha])  # DD/MM/YYYY o ISO (pd.to_datetime las lee mes-primero)
    mensual = pd.DataFrame({"Mes": fechas.dt.to_period("M"), "Valor": monto}).dropna(subset=["Mes"])
    return mensual.groupby("Mes")["Valor"].sum(), None


def _nomina_mensual_mxn(df: pd.DataFrame) -> tuple[pd.Series | None, str | None]:
    """Serie 'Mes' (Period[M]) -> suma de nómina Vigente/Activa (columna 'Total', tratada como nómina neta
    documentada -el archivo no trae Percepciones/Deducciones por separado-), agrupada por mes de 'Fecha de
    Pago' ('Fecha Pago' o 'Fecha de Certificación' alternativas). Devuelve (serie | None, motivo | None); `serie` es `None` si falta
    'Total', 'Fecha de Pago' o 'Estatus'.
    """
    col_fecha = (buscar_columna(df.columns, "Fecha de Pago")
                 or buscar_columna(df.columns, "Fecha Pago")
                 or buscar_columna(df.columns, "Fecha de Certificación"))
    col_total = buscar_columna(df.columns, "Total")
    col_estatus = buscar_columna(df.columns, "Estatus")
    faltantes = [n for n, c in (("Fecha de Pago/Certificación", col_fecha), ("Total", col_total),
                                ("Estatus", col_estatus)) if c is None]
    if faltantes:
        return None, "faltan columnas: " + ", ".join(faltantes)

    activos = df[col_estatus].astype(str).str.strip().str.upper().isin(["VIGENTE", "ACTIVO"])
    d = df[activos]
    if d.empty:
        return pd.Series(dtype=float), None
    total = pd.to_numeric(d[col_total].astype(str).str.replace("$", "", regex=False)
                                       .str.replace(",", "", regex=False), errors="coerce").fillna(0)
    fechas = a_fecha(d[col_fecha])  # DD/MM/YYYY o ISO (pd.to_datetime las lee mes-primero)
    mensual = pd.DataFrame({"Mes": fechas.dt.to_period("M"), "Valor": total}).dropna(subset=["Mes"])
    return mensual.groupby("Mes")["Valor"].sum(), None


def _balance_documental_mensual(df_fac_ing, df_pago_ing, df_fac_egr, df_pago_egr, df_nomina,
                                rep_ing=None, rep_egr=None, anios=None) -> dict:
    """Balance documental estimado mensual = Cobros estimados (facturas PUE de Ingresos por fecha de emisión
    + Complementos de Pago de Ingresos por fecha de pago) − Pagos estimados a proveedores (mismo criterio en
    Egresos) − Nómina neta documentada (por fecha de pago).

    Evita doble conteo PUE−REP por construcción: las facturas PPD NUNCA se suman directamente -solo entran a
    través de su propio Complemento de Pago (REP)-, el mismo principio que `resumen_mensual()`/
    `resumen_mensual_egresos()` usan en los módulos operativos (Cobrado_Total = Facturado_PUE + Cobrado_PPD).
    Los complementos se agrupan por 'Fecha de Pago' (`df_pago_ing`/`df_pago_egr` son los archivos de Pago).
    `rep_ing`/`rep_egr` (opcionales) son los complementos MENSUALES ya calculados con la
    lógica de los módulos de Ingresos/Egresos (`rep_mensual_clientes`/`rep_mensual_proveedores`), cada uno como
    (serie 'Mes' -> importe | None, motivo | None); si se dan, sustituyen a `_rep_mensual_mxn` para ese lado.

    Cada uno de los 3 "pilares" (Cobros, Pagos, Nómina) se calcula de forma independiente; si a CUALQUIERA le
    falta una columna indispensable, el pilar completo queda indisponible (nunca se asume $0) y el resultado
    global se marca `disponible=False`, con el motivo de cada pilar faltante en `motivos`.

    El periodo mostrado es la UNIÓN de los meses con al menos un registro válido en cualquiera de las 5
    fuentes, limitado a la ventana de 5 años `anios` (`anios_5`, mismo criterio que el resto del tablero) -un mes
    fuera de ese rango no se sintetiza como balance $0: no hay evidencia de que esté cubierto por los
    archivos subidos, a diferencia de un mes DENTRO del rango que sí tuvo $0 real en algún pilar-.

    Devuelve {'disponible': bool, 'motivos': dict, 'mensual': DataFrame | None, 'balance_total': float | None,
    'n_excluidas_moneda': int}. `mensual` trae columnas 'Cobros', 'Pagos', 'Nomina', 'Balance', indexado por
    'Mes' (Period[M], nombre de índice 'Mes'). `balance_total` es SIEMPRE `mensual['Balance'].sum()` -nunca
    un cálculo macro independiente- para que el KPI acumulado y la suma de los meses mostrados coincidan por
    construcción.
    """
    pue_ing, motivo_cobros_pue, excl_ing = _valor_mxn_facturas(df_fac_ing, "PUE")
    rep_ing, motivo_cobros_rep = rep_ing if rep_ing is not None else _rep_mensual_mxn(df_pago_ing)
    pue_egr, motivo_pagos_pue, excl_egr = _valor_mxn_facturas(df_fac_egr, "PUE")
    rep_egr, motivo_pagos_rep = rep_egr if rep_egr is not None else _rep_mensual_mxn(df_pago_egr)
    nomina, motivo_nomina = _nomina_mensual_mxn(df_nomina)

    motivos = {}
    if pue_ing is None or rep_ing is None:
        motivos["Cobros estimados"] = motivo_cobros_pue or motivo_cobros_rep
    if pue_egr is None or rep_egr is None:
        motivos["Pagos estimados a proveedores"] = motivo_pagos_pue or motivo_pagos_rep
    if nomina is None:
        motivos["Nómina neta documentada"] = motivo_nomina
    if motivos:
        return {"disponible": False, "motivos": motivos, "mensual": None, "balance_total": None,
               "n_excluidas_moneda": 0}

    todos_los_meses = sorted(set(pue_ing.index) | set(rep_ing.index) | set(pue_egr.index)
                             | set(rep_egr.index) | set(nomina.index))
    todos_los_meses = [m for m in todos_los_meses if anios is None or m.year in anios]
    if not todos_los_meses:
        return {"disponible": False,
               "motivos": {"Periodo": "ningún mes con datos dentro del rango de años completos"},
               "mensual": None, "balance_total": None, "n_excluidas_moneda": 0}

    idx = pd.PeriodIndex(todos_los_meses, freq="M")
    mensual = pd.DataFrame({
        "Cobros": pue_ing.reindex(idx, fill_value=0.0) + rep_ing.reindex(idx, fill_value=0.0),
        "Pagos": pue_egr.reindex(idx, fill_value=0.0) + rep_egr.reindex(idx, fill_value=0.0),
        "Nomina": nomina.reindex(idx, fill_value=0.0),
    }).sort_index()
    mensual.index.name = "Mes"
    mensual["Balance"] = mensual["Cobros"] - mensual["Pagos"] - mensual["Nomina"]

    # Cobertura (solo informativa, NO altera `mensual`): ¿hubo al menos un registro en el mes para cada pilar?
    # Un $0 por falta de registros es indistinguible de un $0 real, por eso se reporta aparte -y tener
    # registros tampoco demuestra que el mes esté completo-.
    cobertura = pd.DataFrame({
        "Cobros": idx.isin(pue_ing.index.union(rep_ing.index)),
        "Pagos": idx.isin(pue_egr.index.union(rep_egr.index)),
        "Nomina": idx.isin(nomina.index),
    }, index=idx)
    cobertura.index.name = "Mes"
    fuentes_vacias = [n for n, s in (("Facturas PUE de Ingresos", pue_ing), ("Complementos de pago de Ingresos", rep_ing),
                                     ("Facturas PUE de Egresos", pue_egr), ("Complementos de pago de Egresos", rep_egr),
                                     ("Nómina", nomina)) if s.empty]
    return {"disponible": True, "motivos": {}, "mensual": mensual, "cobertura": cobertura,
           "fuentes_vacias": fuentes_vacias,
           "balance_total": float(mensual["Balance"].sum()), "n_excluidas_moneda": excl_ing + excl_egr}


_MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                "octubre", "noviembre", "diciembre"]


def _flujo_bruto_mensual(balance: dict) -> pd.DataFrame:
    """Ritmo operativo BRUTO por mes (Flujo de Efectivo), a partir del mismo `balance['mensual']` de la Sección 2: 'Cobros'
    (PUE + complementos de Ingresos) y 'Pagos' = Pagos Totales (proveedores PUE + complementos de Egresos + Nómina). Un
    componente sin registros en el mes queda NaN (nunca se asume $0). Columnas: Año, Mes (1-12), Cobros, Pagos."""
    mensual = balance["mensual"].sort_index()
    cob = balance["cobertura"].reindex(mensual.index)
    return pd.DataFrame({
        "Año": mensual.index.year.to_numpy(), "Mes": mensual.index.month.to_numpy(),
        "Cobros": mensual["Cobros"].where(cob["Cobros"]).to_numpy(),
        "Pagos": (mensual["Pagos"] + mensual["Nomina"]).where(cob["Pagos"] | cob["Nomina"]).to_numpy()})


def _promedios_mensuales_historicos(flujo: pd.DataFrame, anios: list[int]) -> pd.DataFrame:
    """Promedio histórico de Cobros y Pagos por mes calendario (Ene-Dic) sobre los años seleccionados; los meses sin
    registros de un año no entran al promedio. Columnas: Mes_Num, Mes, Cobros_Promedio, Pagos_Promedio, Anios_Cobros, Anios_Pagos."""
    sel = flujo[flujo["Año"].isin([int(a) for a in anios])]
    g = sel.groupby("Mes")
    out = pd.DataFrame({"Cobros_Promedio": g["Cobros"].mean(), "Pagos_Promedio": g["Pagos"].mean(),
                        "Anios_Cobros": g["Cobros"].count(), "Anios_Pagos": g["Pagos"].count()}).reindex(range(1, 13))
    out[["Anios_Cobros", "Anios_Pagos"]] = out[["Anios_Cobros", "Anios_Pagos"]].fillna(0).astype(int)
    out.insert(0, "Mes", [MESES_ES[m - 1] for m in out.index])
    out.insert(0, "Mes_Num", out.index)
    return out.reset_index(drop=True)


def _ohlc_mensual(flujo: pd.DataFrame, anios: list[int], columna: str) -> pd.DataFrame:
    """OHLC por mes calendario (Ene-Dic) de `columna` ('Cobros' o 'Pagos') para velas japonesas, sobre los años seleccionados:
    Open = flujo bruto del año más antiguo con dato ese mes, Close = el del año más reciente con dato, High / Low = máximo y
    mínimo históricos de ese mes. Columnas: Mes_Num, Mes, Open, High, Low, Close, Anio_Open, Anio_Close, N_Anios."""
    sel = flujo[flujo["Año"].isin([int(a) for a in anios])].dropna(subset=[columna]).sort_values("Año")
    filas = []
    for m in range(1, 13):
        g = sel[sel["Mes"] == m]
        if g.empty:
            filas.append({"Mes_Num": m, "Mes": MESES_ES[m - 1], "Open": np.nan, "High": np.nan, "Low": np.nan, "Close": np.nan,
                          "Anio_Open": None, "Anio_Close": None, "N_Anios": 0})
            continue
        v = g[columna]
        filas.append({"Mes_Num": m, "Mes": MESES_ES[m - 1], "Open": float(v.iloc[0]), "High": float(v.max()), "Low": float(v.min()),
                      "Close": float(v.iloc[-1]), "Anio_Open": int(g["Año"].iloc[0]), "Anio_Close": int(g["Año"].iloc[-1]),
                      "N_Anios": int(len(g))})
    return pd.DataFrame(filas)


def _anios_cobertura_completa(mensual: pd.DataFrame, cobertura: pd.DataFrame) -> list[int]:
    """Años 'completos y comparables': los 12 meses presentes en `mensual` Y, en cada mes, al menos un
    registro en cada pilar (Cobros, Pagos, Nómina). Es un criterio de PRESENCIA de registros, no una prueba
    de integridad: un año que pasa el filtro puede seguir teniendo información faltante que no se ve."""
    anios = []
    for anio_it, grupo in mensual.groupby(mensual.index.year):
        if len(grupo) == 12 and bool(cobertura.loc[grupo.index].all().all()):
            anios.append(int(anio_it))
    return anios


def _limitaciones_cobertura(mensual: pd.DataFrame, cobertura: pd.DataFrame, anios_ok: list[int],
                            fuentes_vacias: list[str]) -> list[str]:
    """Lista de limitaciones (texto) a mostrar: fuentes sin ningún registro y años NO comparables, con el
    motivo (meses sin registros en ninguna fuente / meses con algún pilar sin registros). Los meses sin
    registros nunca se interpretan como $0 real."""
    avisos = []
    if fuentes_vacias:
        avisos.append("sin registros en " + ", ".join(fuentes_vacias) + " (los totales no incluyen ese componente)")
    for anio_it in sorted(set(mensual.index.year)):
        if anio_it in anios_ok:
            continue
        cob = cobertura[cobertura.index.year == anio_it]
        faltan_meses = 12 - len(cob)
        con_pilar_faltante = int((~cob.all(axis=1)).sum())
        partes = []
        if faltan_meses:
            partes.append(f"{faltan_meses} mes(es) sin registros en ninguna fuente")
        if con_pilar_faltante:
            partes.append(f"{con_pilar_faltante} mes(es) con algún componente sin registros")
        avisos.append(f"{anio_it}: " + "; ".join(partes))
    return avisos


def _series_anuales_por_mes(flujo: pd.DataFrame, anios: list[int]) -> dict:
    """Series Year-over-Year para la gráfica de Tendencia: {'Cobros': DataFrame, 'Pagos': DataFrame}, cada uno con 12 filas (Mes 1-12)
    y UNA columna por año seleccionado (orden ascendente) con el flujo bruto de ese mes y año. Un mes sin registros queda NaN."""
    sel = sorted(int(a) for a in anios)
    base = flujo[flujo["Año"].isin(sel)]
    return {col: base.pivot(index="Mes", columns="Año", values=col).reindex(index=range(1, 13), columns=sel)
            for col in ("Cobros", "Pagos")}


def _resumen_ciclos(prom: pd.DataFrame, ohlc_cobros: pd.DataFrame) -> dict:
    """Hallazgos de las tarjetas ejecutivas, con los años seleccionados. `holgura` = mes de mayor (Cobros − Pagos) promedio;
    `riesgo` = mes de menor (Cobros − Pagos) promedio (el mayor déficit, o el menor superávit si todos son positivos);
    ambos como (mes, diferencia) y solo con meses que tienen promedio de cobros Y de pagos. `volatil` = (mes, |Close − Open|) del
    mes con la vela de cuerpo más grande de Cobros (solo si algún mes tiene cuerpo > 0, o sea al menos 2 años distintos).
    Cada clave es `None` cuando no hay datos para calcularla."""
    dif = (prom["Cobros_Promedio"] - prom["Pagos_Promedio"]).dropna()
    nombre = lambda num: _MESES_LARGO[int(num) - 1].capitalize()
    holgura = riesgo = volatil = None
    if not dif.empty:
        mh, mr = dif.idxmax(), dif.idxmin()
        holgura = (nombre(prom.loc[mh, "Mes_Num"]), float(dif.loc[mh]))
        riesgo = (nombre(prom.loc[mr, "Mes_Num"]), float(dif.loc[mr]))
    cuerpo = (ohlc_cobros["Close"] - ohlc_cobros["Open"]).abs().dropna()
    if not cuerpo.empty and cuerpo.max() > 0.005:
        mv = cuerpo.idxmax()
        volatil = (nombre(ohlc_cobros.loc[mv, "Mes_Num"]), float(cuerpo.loc[mv]))
    return {"holgura": holgura, "riesgo": riesgo, "volatil": volatil}


def _comentarios_cobros_pagos(mensual: pd.DataFrame, anios_ok: list[int], anio_sel: int) -> dict:
    """Hasta tres hallazgos descriptivos (texto) sobre la diferencia mensual Cobros − Pagos a proveedores −
    Nómina. Solo se incluye un hallazgo si hay evidencia suficiente; sin ella la clave simplemente no existe.
    Las cifras salen SIEMPRE de `mensual` (ningún año, mes ni importe fijo en el código).

    - 'recurrencia': para cada año completo y comparable, los 3 meses de menor diferencia; se analiza solo con
      >= 3 años y se marca un mes como patrón candidato si aparece en >= 2/3 de esos años (criterio descriptivo
      interno, no umbral financiero). 'Menor diferencia' no es 'resultado negativo'.
    - 'concentracion' (año `anio_sel`, debe ser completo): participación de los 2 meses de mayor diferencia
      positiva sobre la suma de las diferencias mensuales POSITIVAS (denominador que evita porcentajes
      engañosos cuando hay meses negativos) y suma de los otros 10 meses. Describe componentes, no causas.
    - 'origen' (año `anio_sel` vs. `anio_previo`, ambos completos): Δdiferencia = Δcobros − Δproveedores − Δnómina
      (concilia exacto, se verifica); principal componente, compensaciones y conteo de meses por encima/debajo
      del mismo mes del año anterior. Solo pesos -nunca % sobre bases cero o negativas-."""
    out = {}
    anio_previo = anio_sel - 1  # año calendario inmediato anterior (nunca se sustituye por otro)

    # --- 1. Recurrencia ---
    if len(anios_ok) >= 3:
        conteo: dict[int, int] = {}
        for anio_it in anios_ok:
            serie = mensual.loc[mensual.index.year == anio_it, "Balance"]
            for periodo, _ in sorted(serie.items(), key=lambda kv: (kv[1], kv[0].month))[:3]:
                conteo[periodo.month] = conteo.get(periodo.month, 0) + 1
        total_anios = len(anios_ok)
        lista_anios = ", ".join(str(x) for x in sorted(anios_ok))
        candidatos = sorted(((m, n) for m, n in conteo.items() if n * 3 >= 2 * total_anios),
                            key=lambda mn: (-mn[1], mn[0]))
        if candidatos:
            frases = [f"{_MESES_LARGO[m - 1].capitalize()} ({n} de {total_anios})" if len(candidatos) > 1
                      else f"{_MESES_LARGO[m - 1].capitalize()}" for m, n in candidatos]
            if len(candidatos) == 1:
                out["recurrencia"] = (f"{frases[0]} estuvo entre los tres meses con menor diferencia entre cobros "
                                      f"y pagos en {candidatos[0][1]} de {total_anios} años comparables ({lista_anios}). Es un "
                                      "periodo a revisar al programar desembolsos (menor diferencia no implica "
                                      "resultado negativo).")
            else:
                out["recurrencia"] = (f"{', '.join(frases)} estuvieron entre los tres meses con menor diferencia "
                                      f"entre cobros y pagos en los años comparables ({lista_anios}). Son periodos a revisar al "
                                      "programar desembolsos (menor diferencia no implica resultado negativo).")

    if anio_sel not in anios_ok:
        return out
    datos = mensual[mensual.index.year == anio_sel]
    mes_txt = lambda p: _MESES_LARGO[p.month - 1].capitalize()

    # --- 2. Dependencia de meses puntuales ---
    positivas = datos["Balance"][datos["Balance"] > 0]
    if positivas.empty:
        out["concentracion"] = (f"Ningún mes de {anio_sel} tuvo diferencia positiva entre cobros y pagos; la "
                                f"diferencia anual fue {_mxn(datos['Balance'].sum())}.")
    elif len(positivas) == 1:
        unico = positivas.index[0]
        resto = float(datos["Balance"].drop(unico).sum())
        out["concentracion"] = (f"Solo {mes_txt(unico)} tuvo diferencia positiva en {anio_sel} "
                                f"({_mxn(positivas.iloc[0])}); los otros once meses sumaron {_mxn(resto)}"
                                + (", es decir, en conjunto fueron negativos" if resto < 0 else "") + ".")
    else:
        top2 = positivas.nlargest(2)
        participacion = float(top2.sum() / positivas.sum() * 100)
        resto = float(datos["Balance"].drop(top2.index).sum())
        det = datos.loc[top2.index]
        out["concentracion"] = (
            f"{mes_txt(top2.index[0])} y {mes_txt(top2.index[1])} concentraron {participacion:.1f}% de las "
            f"diferencias mensuales positivas de {anio_sel}. Los otros diez meses sumaron {_mxn(resto)}"
            + (", es decir, en conjunto fueron negativos" if resto < 0 else "")
            + f". En esos dos meses se observan cobros por {_mxn(det['Cobros'].sum())}, pagos a proveedores "
              f"por {_mxn(det['Pagos'].sum())} y nómina por {_mxn(det['Nomina'].sum())}. Lectura histórica, "
              "no una proyección.")

    # --- 3. Origen del cambio vs. el año anterior ---
    if (anio_previo) in anios_ok:
        previo = mensual[mensual.index.year == anio_previo]
        d_cobros = float(datos["Cobros"].sum() - previo["Cobros"].sum())
        d_prov = float(datos["Pagos"].sum() - previo["Pagos"].sum())
        d_nom = float(datos["Nomina"].sum() - previo["Nomina"].sum())
        d_dif = float(datos["Balance"].sum() - previo["Balance"].sum())
        if abs((d_cobros - d_prov - d_nom) - d_dif) < 0.01:  # concilia exacto; si no, se omite el hallazgo
            if abs(d_dif) < 0.5:
                out["origen"] = f"La diferencia anual no cambió frente a {anio_previo}."
            else:
                aporte = {
                    ("el aumento de cobros" if d_cobros > 0 else "la disminución de cobros"): d_cobros,
                    ("el aumento de pagos a proveedores" if d_prov > 0
                     else "la disminución de pagos a proveedores"): -d_prov,
                    ("el aumento de nómina" if d_nom > 0 else "la disminución de nómina"): -d_nom,
                }
                aporte = {k: v for k, v in aporte.items() if abs(v) >= 0.5}
                a_favor = {k: v for k, v in aporte.items() if v * d_dif > 0}
                en_contra = {k: v for k, v in aporte.items() if v * d_dif < 0}
                if not a_favor:
                    return out
                principal = max(a_favor, key=lambda k: abs(a_favor[k]))
                verbo, sustantivo = ("aumentó", "del aumento") if d_dif > 0 else ("disminuyó", "de la reducción")
                texto = (f"La diferencia anual {verbo} {_mxn(abs(d_dif))} frente a {anio_previo}. "
                         f"{principal[0].upper() + principal[1:]} explica aritméticamente "
                         f"{_mxn(abs(a_favor[principal]))} {sustantivo}")
                otros = {k: v for k, v in a_favor.items() if k != principal}
                if otros:
                    texto += ", junto con " + " y ".join(f"{k} ({_mxn(abs(v))})" for k, v in otros.items())
                if en_contra:
                    comp = " y ".join(f"{k} ({_mxn(abs(v))})" for k, v in en_contra.items())
                    texto += f", parcialmente compensado por {comp}"
                previo_idx = previo["Balance"].copy()
                previo_idx.index = previo_idx.index.month
                actual_idx = datos["Balance"].copy()
                actual_idx.index = actual_idx.index.month
                comparables = actual_idx.subtract(previo_idx.reindex(actual_idx.index))
                n_mayor, n_menor = int((comparables > 0).sum()), int((comparables < 0).sum())
                n_ref, comp_txt, n_otro = (n_menor, "menor", n_mayor) if d_dif < 0 else (n_mayor, "mayor", n_menor)
                texto += (f". La diferencia fue {comp_txt} que un año antes en {n_ref} de los 12 meses"
                          + (f" (en {n_otro} fue {'mayor' if comp_txt == 'menor' else 'menor'})" if n_otro else "")
                          + ".")
                out["origen"] = texto
    return out


def _base_facturacion_emitida(f_fac, anios=None) -> tuple[pd.DataFrame | None, str | None]:
    """Base de "Facturación Emitida Total" del módulo de Ingresos (la misma del Índice de Concentración): facturas
    'Activo' de Tipo Factura, PUE y PPD, columna `Total` (sin conversión de moneda, igual que Ingresos), SIN notas de
    crédito, de la ventana de 5 años (`anios_5`). Devuelve (DataFrame[Fecha, RFC_Receptor, Nombre_Receptor,
    Total] | None, motivo | None); `None` si falta una columna indispensable (incluido RFC Receptor)."""
    try:
        facturas, _ = _facturas_cache(f_fac.name, f_fac.getvalue(), CODIGO_VERSION)
        facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturas", anios)
    except KeyError as e:
        return None, e.args[0]
    if "RFC_Receptor" not in facturas.columns:
        return None, "la Facturación Emitida no trae la columna RFC Receptor"
    base = facturas[~facturas["Es_NCR"]].copy()
    if "Nombre_Receptor" not in base.columns:
        base["Nombre_Receptor"] = ""
    return base[["Fecha", "RFC_Receptor", "Nombre_Receptor", "Total"]], None


def _clientes_sin_facturacion(base: pd.DataFrame, anio_sel: int) -> dict:
    """Clientes (RFC Receptor) con facturas vigentes en el año anterior (`anio_sel` − 1) y NINGUNA factura vigente en
    `anio_sel`, comparando AÑOS CALENDARIO COMPLETOS (la última fecha de factura no se toma como corte de la base: los
    años fuera de la ventana `anios_5` ya vienen excluidos). `base` = salida de `_base_facturacion_emitida` (PUE y PPD,
    columna Total, sin notas de crédito). Solo se mira la facturación emitida: ningún complemento de pago decide si un
    cliente sigue comprando. RFC vacío o genérico no identifica clientes (se informa su % de la facturación anterior).

    Devuelve {'disponible': False, 'motivo': str} (sin periodo anterior o sin facturas en el año) o el detalle:
    'tabla' (RFC, Cliente, Última fecha, Facturación anterior, % de la facturación total anterior; ordenada de mayor a
    menor), 'n', 'monto', 'pct', 'total_prev' (facturación total del año anterior, con TODOS los RFC),
    'pct_excluido' y 'meses_sin_facturas'. Tarjetas, gráfica y tabla salen de esta misma 'tabla'."""
    anio_prev = anio_sel - 1
    anios = base["Fecha"].dt.year
    if anio_prev not in set(anios):
        return {"disponible": False, "motivo": f"la base no tiene facturas emitidas en {anio_prev} para comparar con {anio_sel}."}
    if anio_sel not in set(anios):
        return {"disponible": False, "motivo": f"la base no tiene facturas emitidas en {anio_sel}."}
    rfc = base["RFC_Receptor"].fillna("").astype(str).str.strip().str.upper()
    rfc = rfc.where(rfc != "NAN", "")
    identificable = (rfc != "") & ~rfc.isin(_RFC_GENERICOS)
    en_prev, en_sel = anios == anio_prev, anios == anio_sel
    total_prev = float(base.loc[en_prev, "Total"].sum())
    prev_ident = base[en_prev & identificable].assign(RFC=rfc[en_prev & identificable])
    if prev_ident.empty:
        return {"disponible": False, "motivo": f"no hay facturación de clientes identificables en {anio_prev}."}
    con_factura_actual = set(rfc[en_sel & identificable])
    por_rfc = prev_ident.groupby("RFC")["Total"].sum()
    sin = por_rfc[~por_rfc.index.isin(con_factura_actual)].sort_values(ascending=False)
    # Última factura observada hasta el cierre del periodo analizado (31/12 de `anio_sel`), con todo el historial de la base.
    hasta_corte = (anios <= anio_sel) & identificable
    ultima = base[hasta_corte].assign(RFC=rfc[hasta_corte]).groupby("RFC")["Fecha"].max()
    nombres = (base[identificable].assign(RFC=rfc[identificable]).dropna(subset=["Nombre_Receptor"])
               .query("Nombre_Receptor != ''").groupby("RFC")["Nombre_Receptor"].first())
    tabla = pd.DataFrame({"RFC": sin.index, "Cliente": [nombres.get(r, r) for r in sin.index],
                          "Última fecha": [ultima.get(r) for r in sin.index], "Facturación anterior": sin.values})
    tabla["% anterior"] = tabla["Facturación anterior"] / total_prev * 100 if total_prev else float("nan")
    meses_ref = set(pd.period_range(f"{anio_prev}-01", f"{anio_sel}-12", freq="M"))
    meses_con_facturas = set(base["Fecha"].dt.to_period("M"))
    monto = float(sin.sum())
    excluido = float(base.loc[en_prev & ~identificable, "Total"].sum())
    return {"disponible": True, "anio_sel": anio_sel, "anio_prev": anio_prev, "tabla": tabla, "n": int(len(sin)),
            "monto": monto, "pct": (monto / total_prev * 100) if total_prev else None, "total_prev": total_prev,
            "pct_excluido": (excluido / total_prev * 100) if total_prev else 0.0,
            "meses_sin_facturas": sorted(meses_ref - meses_con_facturas)}


def _tabla_clientes_sin_facturacion(res: dict) -> pd.DataFrame:
    """Tabla única de la sección 6, a partir de `res["tabla"]` (ordenada de mayor a menor facturación anterior): Cliente, RFC (el RFC receptor de la base, no
    deducido del nombre), Última factura, Facturado [año anterior] (MXN) y Participación (%), más la fila final "Total · X clientes" (suma de importes y de
    porcentajes; el % es sobre la facturación TOTAL del año anterior, no sobre el total de la lista). El nombre se muestra abreviado (`_nombre_abreviado`) y
    el nombre completo viaja en `tabla.attrs["nombres_completos"]` para el tooltip de `_html_tabla_sin_facturacion`."""
    p = res["anio_prev"]
    tabla = res["tabla"]
    col_monto, col_pct = f"Facturado {p} (MXN)", "Participación (%)"
    cuerpo = pd.DataFrame({
        "RFC": tabla["RFC"].astype(str).to_numpy(),
        "Cliente": [_nombre_abreviado(c) for c in tabla["Cliente"]],
        "Última factura": [f"{f:%d/%m/%Y}" if pd.notna(f) else "" for f in tabla["Última fecha"]],
        col_monto: tabla["Facturación anterior"].to_numpy(), col_pct: tabla["% anterior"].to_numpy()})
    n = len(cuerpo)
    total = pd.DataFrame([{"Cliente": f"Total · {n} cliente{'s' if n != 1 else ''}", "RFC": "", "Última factura": "",
                           col_monto: cuerpo[col_monto].sum(), col_pct: cuerpo[col_pct].sum()}])
    salida = pd.concat([cuerpo, total], ignore_index=True)
    salida.attrs["nombres_completos"] = [str(c) for c in tabla["Cliente"]] + [total.iloc[0]["Cliente"]]
    return salida



def _armar_anual_ppd(facturacion: pd.Series, complementos: pd.Series) -> pd.DataFrame:
    """Comparativo anual documental: Año, Facturación PPD, Complementos, Diferencia = Complementos − Facturación
    (negativa = rezago; positiva = recuperación de cartera; se conservan los negativos) y Porcentaje = Diferencia / Facturación × 100 (`None` -'N/D'- si la facturación
    del año es 0). Ambas series vienen YA agrupadas por año con los mismos cálculos de los módulos operativos."""
    fact = pd.Series(facturacion.to_numpy(dtype=float), index=[int(a) for a in facturacion.index]).sort_index()
    comp = pd.Series(complementos.to_numpy(dtype=float), index=[int(a) for a in complementos.index]).reindex(
        fact.index, fill_value=0.0)
    anios = list(fact.index)
    dif = comp - fact
    return pd.DataFrame({"Año": anios, "Facturación PPD": fact.values, "Complementos": comp.values,
                         "Diferencia": dif.values,
                         "Porcentaje": [(d / f * 100) if f != 0 else None for d, f in zip(dif.values, fact.values)]})


def anual_ppd_clientes(f_fac, f_rep, anios=None) -> pd.DataFrame:
    """Facturación PPD vs. Complementos por año -Clientes-, con los MISMOS pasos que `modulo_ingresos()` (sin
    filtros de ejercicio, o sea todos los años de las facturas): `_facturas_cache` + `excluir_años_incompletos`,
    `_complementos_cache` (Cobro Efectivo por Fecha_Cobro: fecha de pago),
    `resumen_mensual` y `matriz_anual`. Los complementos NO se reasignan al año de su factura. Lanza KeyError si
    algún archivo no trae las columnas esperadas."""
    facturas, _ = _facturas_cache(f_fac.name, f_fac.getvalue(), CODIGO_VERSION)
    if anios is None:
        anios = obtener_anios_analisis(facturas)
    facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturas", anios)
    rep_total, _ = _complementos_cache(f_rep.name, f_rep.getvalue(), CODIGO_VERSION)
    rep_total, _ = excluir_años_incompletos(rep_total, "Fecha_Cobro", "Complementos de pago", anios)
    if facturas.empty:
        return _armar_anual_ppd(pd.Series(dtype=float), pd.Series(dtype=float))
    ejercicios = sorted(int(a) for a in anios)   # eje canónico: los 5 años (un año sin movimientos queda en 0.0)
    rep = rep_total[rep_total["Fecha_Cobro"].dt.year.isin(ejercicios)]
    res = resumen_mensual(facturas, rep, ejercicios)
    m = matriz_anual(res, ncr_por_año(facturas))
    return _armar_anual_ppd(
        m["\xa0\xa0\xa0\xa0Facturación PPD"], m["Complementos de Pago Emitidos"])


def anual_ppd_proveedores(f_fac, f_rep, anios=None) -> pd.DataFrame:
    """Igual que `anual_ppd_clientes` para Egresos, con los MISMOS pasos que `modulo_egresos()`:
    `_facturas_egresos_cache` + `excluir_años_incompletos`, `preparar_complementos_egresos` (Monto MXN por su
    propia fecha: Fecha Pago) y `matriz_anual_egresos`."""
    facturas, _ = _facturas_egresos_cache(f_fac.name, f_fac.getvalue(), CODIGO_VERSION)
    if anios is None:
        anios = obtener_anios_analisis(None, facturas)
    facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturación recibida", anios)
    if facturas.empty:
        return _armar_anual_ppd(pd.Series(dtype=float), pd.Series(dtype=float))
    ejercicios = sorted(int(a) for a in anios)   # eje canónico: los 5 años (un año sin movimientos queda en 0.0)
    nombre_fecha = "Fecha Pago"
    df_rep = cargar_base(f_rep)
    col_monto, col_fecha = buscar_columna(df_rep.columns, "Monto MXN"), buscar_columna(df_rep.columns, nombre_fecha)
    faltantes = [n for n, c in (("Monto MXN", col_monto), (nombre_fecha, col_fecha)) if c is None]
    if faltantes:
        raise KeyError(f"Faltan columnas: {faltantes}. Columnas encontradas: {list(df_rep.columns)}")
    df_rep = preparar_complementos_egresos(df_rep, col_monto, col_fecha)
    rep_por_año = df_rep[df_rep["Año"].isin(ejercicios)].groupby("Año")["Monto_Num"].sum()
    m = matriz_anual_egresos(facturas, rep_por_año, ncr_por_año_egresos(facturas), pd.Series(dtype=float),
                             ejercicios)
    return _armar_anual_ppd(
        m["\xa0\xa0\xa0\xa0Facturación PPD"], m["Complementos de Pago Recibidos"])


def rep_mensual_clientes(f_fac, f_rep, anios=None) -> tuple[pd.Series | None, str | None]:
    """Complementos de Clientes por MES con los MISMOS pasos que `modulo_ingresos()` / `anual_ppd_clientes()`:
    `_complementos_cache` (Cobro Efectivo = Saldo Inicial − Saldo Final por Fecha_Cobro: fecha de pago),
    `excluir_años_incompletos` y solo los años de las facturas.
    Devuelve (serie 'Mes' -> importe | None, motivo | None)."""
    try:
        facturas, _ = _facturas_cache(f_fac.name, f_fac.getvalue(), CODIGO_VERSION)
        uuids_pue = _uuids_pue(facturas)   # cruce de UUIDs: el PUE ya se suma como factura, su REP no se suma otra vez
        if anios is None:
            anios = obtener_anios_analisis(facturas)
        facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturas", anios)
        rep, _ = _complementos_cache(f_rep.name, f_rep.getvalue(), CODIGO_VERSION)
        rep, _ = excluir_años_incompletos(rep, "Fecha_Cobro", "Complementos de pago", anios)
    except KeyError as e:
        return None, e.args[0]
    ejercicios = sorted(int(a) for a in anios)
    rep = rep[rep["Fecha_Cobro"].dt.year.isin(ejercicios)]
    if len(uuids_pue) and "UUID_DR" in rep.columns:
        rep = rep[~rep["UUID_DR"].isin(uuids_pue)]
    return rep.groupby(rep["Fecha_Cobro"].dt.to_period("M"))["Cobro_Efectivo"].sum(), None


def rep_mensual_proveedores(f_fac, f_rep, anios=None) -> tuple[pd.Series | None, str | None]:
    """Complementos de Proveedores por MES con los MISMOS pasos que `modulo_egresos()` / `anual_ppd_proveedores()`:
    `preparar_complementos_egresos` (Monto MXN por su propia fecha: Fecha Pago) y solo los años de la facturación recibida (`excluir_años_incompletos`)."""
    try:
        facturas, _ = _facturas_egresos_cache(f_fac.name, f_fac.getvalue(), CODIGO_VERSION)
        uuids_pue = _uuids_pue(facturas)   # cruce de UUIDs: el PUE ya se suma como factura, su REP no se suma otra vez
        if anios is None:
            anios = obtener_anios_analisis(None, facturas)
        facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturación recibida", anios)
    except KeyError as e:
        return None, e.args[0]
    ejercicios = sorted(int(a) for a in anios)
    nombre_fecha = "Fecha Pago"
    df_rep = cargar_base(f_rep)
    col_monto, col_fecha = buscar_columna(df_rep.columns, "Monto MXN"), buscar_columna(df_rep.columns, nombre_fecha)
    faltantes = [n for n, c in (("Monto MXN", col_monto), (nombre_fecha, col_fecha)) if c is None]
    if faltantes:
        return None, f"faltan columnas: {', '.join(faltantes)}"
    col_est = buscar_columna(df_rep.columns, "Estatus")
    if col_est is not None:   # solo complementos vigentes
        df_rep = df_rep[df_rep[col_est].astype(str).str.strip().str.upper().isin(["VIGENTE", "ACTIVO"])]
    col_rel = buscar_columna(df_rep.columns, "Documento Relacionado") or buscar_columna(df_rep.columns, "UUID DR")
    if col_rel is not None and len(uuids_pue):
        df_rep = df_rep[~df_rep[col_rel].fillna("").astype(str).str.strip().str.upper().isin(uuids_pue)]
    df_rep = preparar_complementos_egresos(df_rep, col_monto, col_fecha)
    df_rep = df_rep[df_rep["Año"].isin(ejercicios)]
    return df_rep.groupby("Mes")["Monto_Num"].sum(), None


def _tabla_detalle_anual(anual: pd.DataFrame) -> pd.DataFrame:
    """Detalle anual a mostrar: las MISMAS filas por año que las barras (el mismo `anual`), sin redondear -el
    formato se aplica al mostrar-. El porcentaje NO va aquí: ya está en las gráficas."""
    return pd.DataFrame({
        COLUMNAS_DETALLE_ANUAL[0]: anual["Año"].astype(int),
        COLUMNAS_DETALLE_ANUAL[1]: anual["Facturación PPD"],
        COLUMNAS_DETALLE_ANUAL[2]: anual["Complementos"],
        COLUMNAS_DETALLE_ANUAL[3]: anual["Diferencia"]}).reset_index(drop=True)


def _monto_por_cuota(cuota: float, tasa_m: float, plazo: int) -> float:
    """Monto de crédito estimado (ingeniería inversa, valor actual de la anualidad): cuota = 0 -> 0; tasa 0 -> cuota * plazo; tasa > 0 ->
    cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)."""
    if cuota <= 0 or plazo <= 0:
        return 0.0
    return cuota * plazo if tasa_m <= 0 else cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)


def _excedente_homologado(balance: dict) -> pd.DataFrame:
    """Sección 7 HEREDA el Flujo Neto de la Sección 2: la serie mensual `balance['mensual']['Balance']` (= Cobros − Pagos a proveedores − Nómina, ya calculada por
    `_balance_documental_mensual`) se usa tal cual. Aquí NO se extrae, cruza ni resta nada: una fila por mes, ordenada cronológicamente, con la
    columna Excedente_Mensual_Homologado (negativos conservados)."""
    return pd.DataFrame({"Excedente_Mensual_Homologado": balance["mensual"]["Balance"].astype(float)}).sort_index()


def _periodo_evaluacion(tabla: pd.DataFrame, periodo: str) -> pd.DataFrame:
    """Los últimos N meses cronológicos de la tabla (meses con registros en los tres componentes); 'Historial completo' = todos."""
    n = PERIODOS_EVALUACION[periodo]
    return tabla if n is None else tabla.sort_index().tail(n)


def _rango_meses_texto(tabla: pd.DataFrame) -> str:
    """'ene 2025 a dic 2025' del rango cronológico de la tabla."""
    p0, p1 = tabla.index.min(), tabla.index.max()
    return f"{MESES_ES[p0.month - 1].lower()} {p0.year} a {MESES_ES[p1.month - 1].lower()} {p1.year}"


def _dictamen_credito(evaluado: pd.DataFrame, plazo: int) -> dict:
    """Motor de veredicto de la Sección 7 sobre el Flujo Neto mensual de la Sección 2 (`Excedente_Mensual_Homologado`) del periodo
    evaluado: `maximo` / `minimo` = mejor y peor mes histórico (con su `mes_maximo` / `mes_minimo`; el mínimo puede ser negativo).
    Escenario A (`apto=False`, flujo mínimo <= 0): no apto para cuota fija -> mensualidad 0 y monto 0. Escenario B (`apto=True`,
    flujo mínimo > 0): mensualidad = `MARGEN_SEGURIDAD_PCT` % del flujo MÍNIMO (no del promedio) y monto = valor presente de esa
    cuota con la tasa fija `TASA_REFERENCIA_ANUAL` y el plazo elegido. Total a pagar = mensualidad × plazo."""
    serie = evaluado["Excedente_Mensual_Homologado"]
    minimo, maximo = float(serie.min()), float(serie.max())
    apto = minimo > 0.005
    cuota = minimo * MARGEN_SEGURIDAD_PCT / 100 if apto else 0.0
    return {"maximo": maximo, "mes_maximo": serie.idxmax(), "minimo": minimo, "mes_minimo": serie.idxmin(), "apto": apto,
            "cuota": cuota, "monto": _monto_por_cuota(cuota, TASA_REFERENCIA_ANUAL / 12 / 100, plazo), "total": cuota * plazo,
            "cubiertos": int((serie >= cuota - 0.005).sum()) if apto else 0}


def _dictamen_indice(indice: float) -> tuple[str, str]:
    """(texto, color) del índice (0–100): 85 o más Sólido; 70 a menos de 85 Adecuado; 50 a menos de 70 Moderado; menos de 50 Débil. Solo desempeño documental."""
    for minimo, texto, color in BANDAS_DICTAMEN:
        if indice >= minimo:
            return texto, color
    return BANDAS_DICTAMEN[-1][1], BANDAS_DICTAMEN[-1][2]


def _puntos_margen(margen_pct: float) -> int:
    return 0 if margen_pct < 0 else 20 if margen_pct < 3 else 50 if margen_pct < 8 else 75 if margen_pct < 15 else 100


def _puntos_cobranza(efectividad_pct: float) -> int:
    return 100 if efectividad_pct >= 95 else 75 if efectividad_pct >= 85 else 50 if efectividad_pct >= 70 else 20 if efectividad_pct >= 50 else 0


def _puntos_estabilidad(cv_pct: float) -> int:
    return 100 if cv_pct <= 10 else 75 if cv_pct <= 20 else 50 if cv_pct <= 35 else 20 if cv_pct <= 50 else 0


def _puntos_crecimiento(cagr_pct: float) -> int:
    return 100 if cagr_pct >= 10 else 75 if cagr_pct >= 5 else 50 if cagr_pct >= 0 else 20 if cagr_pct >= -5 else 0


def _pilar(nombre: str, peso: int, regla: str, estado: str, s=None, real: str = "") -> dict:
    """Un pilar: estado 'ok' (puntaje s de 0 a 100, incluido un cero real), 
    'no_aplica' o 'insuficiente'. Los puntos obtenidos son s × peso ÷ 100 solo si el estado es 'ok'."""
    return {"nombre": nombre, "peso": peso, "regla": regla, "estado": estado, "s": s, "pts": (s * peso / 100) if estado == "ok" else None, "real": real}



def _indice_desempeno(balance: dict, traz: dict) -> dict:
    """Índice de Desempeño Financiero (Basado en CFDI), 3 pilares sobre 100 puntos: 1) margen de excedente documental (40), 2) efectividad de cobranza PPD (35), 3) estabilidad y
    crecimiento (25). Casos especiales EXPLÍCITOS: 'ok' (valor numérico, incluido el cero), 'no_aplica' (p. ej. no hay facturas PPD) y 'insuficiente'. Nunca se redistribuyen pesos en
    silencio: con algún pilar 'insuficiente' NO hay índice (datos insuficientes); con un pilar 'no_aplica' el índice es el % de los puntos APLICABLES y se declara cuáles no aplicaron.
    Notas de crédito: solo información complementaria (0 puntos). Los indicadores de calidad y trazabilidad no puntúan (ver `_trazabilidad_indicadores`)."""
    (n1, w1), (n2, w2), (n3, w3) = PESOS_INDICE
    # --- Pilar 1: margen de excedente documental (Flujo Neto de la sección 2) ---
    if not balance["disponible"]:
        p1 = _pilar(n1, w1, REGLAS_INDICE[0], "insuficiente", real="Resumen mensual de la sección 2 no disponible.")
    else:
        m = balance["mensual"].sort_index().tail(VENTANA_MARGEN_MESES)
        cobros, flujo = float(m["Cobros"].sum()), float(m["Balance"].sum())
        if len(m) < MIN_MESES_MARGEN or cobros <= 0:
            p1 = _pilar(n1, w1, REGLAS_INDICE[0], "insuficiente",
                        real=f"{len(m)} mes(es) con registros (mínimo {MIN_MESES_MARGEN})" if len(m) < MIN_MESES_MARGEN else "Sin cobros documentados en el periodo.")
        else:
            margen = flujo / cobros * 100
            p1 = _pilar(n1, w1, REGLAS_INDICE[0], "ok", _puntos_margen(margen), f"Margen de excedente documental: {margen:.1f}% sobre {len(m)} meses ({_rango_meses_texto(m)})")
            p1["valor"] = margen
    # --- Pilar 2: efectividad de cobranza PPD (importes aplicados por REP contra facturas PPD) ---
    if traz["ppd_total"] == 0:
        p2 = _pilar(n2, w2, REGLAS_INDICE[1], "no_aplica", real="No aplica: no hay facturas PPD en el periodo (cobranza solo en PUE).")
    elif traz["ppd_n_elegibles"] == 0 or traz["ppd_monto_elegible"] <= 0:
        p2 = _pilar(n2, w2, REGLAS_INDICE[1], "insuficiente", real=f"Ninguna factura PPD tiene más de {DIAS_GRACIA_PPD} días de antigüedad al corte.")
    else:
        efec = traz["ppd_aplicado"] / traz["ppd_monto_elegible"] * 100
        p2 = _pilar(n2, w2, REGLAS_INDICE[1], "ok", _puntos_cobranza(efec),
                    f"Aplicado por REP: {efec:.1f}% de {traz['ppd_n_elegibles']} facturas PPD con más de {DIAS_GRACIA_PPD} días (corte {traz['corte']:%d/%m/%Y})")
        p2["valor"] = efec
    # --- Pilar 3: estabilidad y crecimiento, medidos por separado ---
    anual = pd.Series(traz["facturacion_anual"]).sort_index()
    con = anual[anual > 0]
    if len(con) < MIN_ANIOS_ESTABILIDAD:
        p3 = _pilar(n3, w3, REGLAS_INDICE[2], "insuficiente", real=f"{len(con)} año(s) con facturación (mínimo {MIN_ANIOS_ESTABILIDAD})")
    else:
        cv = float(con.std() / con.mean() * 100)
        cagr = ((float(con.iloc[-1]) / float(con.iloc[0])) ** (1 / (len(con) - 1)) - 1) * 100
        s_est, s_cre = _puntos_estabilidad(cv), _puntos_crecimiento(cagr)
        s3 = max(s_est, s_cre)
        if cagr < -5:
            s3 = min(s3, 20)
        p3 = _pilar(n3, w3, REGLAS_INDICE[2], "ok", s3, f"Estabilidad (variación anual): {cv:.1f}% → {s_est} pts · Crecimiento anual compuesto: {cagr:.1f}% → {s_cre} pts")
        p3.update({"cv": cv, "cagr": cagr, "s_est": s_est, "s_cre": s_cre})
    pilares = [p1, p2, p3]
    insuf = [p["nombre"] for p in pilares if p["estado"] == "insuficiente"]
    no_ap = [p for p in pilares if p["estado"] == "no_aplica"]
    aplicables = sum(p["peso"] for p in pilares if p["estado"] == "ok")
    if insuf or aplicables == 0:
        indice, dictamen, notas = None, SIN_DICTAMEN, ["Datos insuficientes en: " + "; ".join(insuf) + ". No se calcula el índice ni se redistribuyen pesos." if insuf
                                                       else "Ningún pilar es aplicable."]
    else:
        obtenidos = sum(p["pts"] for p in pilares if p["estado"] == "ok")
        indice = obtenidos / aplicables * 100
        dictamen = _dictamen_indice(indice)
        notas = ([f"Índice calculado sobre {aplicables} de 100 puntos posibles: {', '.join(p['nombre'] for p in no_ap)} no aplica (su peso de "
                  f"{sum(p['peso'] for p in no_ap)} puntos NO se redistribuye; el índice es el % de los puntos aplicables, por lo que no es comparable con bases donde sí aplica)."]
                 if no_ap else [])
    # --- información complementaria: Notas de Crédito (0 puntos; ni más ni menos notas es «mejor» por sí mismo) ---
    pct_ncr = traz["ncr_monto"] / traz["ventas_total"] * 100 if traz["ventas_total"] > 0 else None
    if traz["ncr_n"] == 0:
        ncr_txt = "Sin notas de crédito en el periodo (valor cero)."
    elif pct_ncr is None:
        ncr_txt = f"{traz['ncr_n']} notas de crédito por {_mxn(traz['ncr_monto'])}; no hay ventas contra las cuales compararlas."
    else:
        nivel = "marginal (menos de 1%)" if pct_ncr < 1 else "moderada (de 1% a menos de 5%)" if pct_ncr < 5 else "relevante (5% o más)"
        ncr_txt = f"{traz['ncr_n']} notas de crédito por {_mxn(traz['ncr_monto'])}, equivalentes a {pct_ncr:.2f}% de la facturación emitida: magnitud {nivel}."
    return {"pilares": pilares, "indice": indice, "obtenidos": sum(p["pts"] for p in pilares if p["estado"] == "ok"), "aplicables": aplicables,
            "dictamen": dictamen, "notas": notas, "ncr_texto": ncr_txt, "pct_ncr": pct_ncr}


def _trazabilidad_indicadores(balance: dict, traz: dict) -> dict:
    """Panel «Calidad y trazabilidad de la información»: indicadores de integridad de los datos (NO puntúan ni se presentan como incumplimiento). Cada uno es una bandera
    con umbral duro: PPD exigibles sin ningún complemento de pago (más de 5 % del importe), complementos cuyo UUID relacionado no está en la base de facturas (1 o más), facturas PUE con complemento asociado
    (1 o más), notas de crédito emitidas con método PPD (1 o más) y meses de los últimos 24 sin registros en algún componente (1 o más). 0 banderas Consistente; 1-2 con
    Observaciones; 3 o más Irregular."""
    filas = []
    if traz["ppd_n_elegibles"]:
        pct = traz["ppd_monto_sin_rep"] / traz["ppd_monto_elegible"] * 100
        filas.append(("Facturas PPD sin ningún complemento de pago", f"{traz['ppd_n_sin_rep']} de {traz['ppd_n_elegibles']} facturas con más de {DIAS_GRACIA_PPD} días ({_mxn(traz['ppd_monto_sin_rep'])}, {pct:.1f}% del importe)", pct > 5))
    else:
        filas.append(("Facturas PPD sin ningún complemento de pago", "No evaluable: sin facturas PPD con antigüedad suficiente.", None))
    filas.append(("Complementos sin factura relacionada en la base", f"{traz['rep_n_sin_factura']} de {traz['rep_n']} complementos ({_mxn(traz['rep_monto_sin_factura'])})", traz["rep_n_sin_factura"] >= 1))
    filas.append(("Facturas PUE con complemento asociado", f"{traz['pue_con_rep']} facturas (el complemento ligado no se suma otra vez)", traz["pue_con_rep"] >= 1))
    filas.append(("Notas de crédito emitidas con método PPD", f"{traz['ncr_n_ppd']} de {traz['ncr_n']} notas ({_mxn(traz['ncr_monto_ppd'])})", traz["ncr_n_ppd"] >= 1))
    if balance["disponible"]:
        m, cob = balance["mensual"].sort_index().tail(VENTANA_MARGEN_MESES), balance["cobertura"]
        sin_cob = int((~cob.reindex(m.index).all(axis=1)).sum())
        filas.append(("Meses sin registros en algún componente (últimos 24)", f"{sin_cob} de {len(m)} meses", sin_cob >= 1))
    else:
        filas.append(("Meses sin registros en algún componente (últimos 24)", "No evaluable: resumen mensual no disponible.", None))
    banderas = sum(1 for _, _, b in filas if b)
    texto, color = (("Trazabilidad Consistente", "#10B981") if banderas == 0 else ("Trazabilidad con Observaciones", "#F59E0B") if banderas <= 2
                    else ("Trazabilidad Irregular", "#EF4444"))
    return {"filas": filas, "banderas": banderas, "dictamen": (texto, color)}



def _rebase(serie: dict, anios, base: int) -> list:
    """Serie anual re-expresada en Base 100 = año `base`; NaN donde falta el dato (o si falta el año base)."""
    b = serie.get(base)
    return [(serie[a] / b * 100) if (b and a in serie) else float("nan") for a in anios]


def _anio_base(anios, empresa: list, externa: dict) -> int | None:
    """Primer año disponible: el primero de los ejercicios activos con ingreso/gasto > 0 y dato en la serie externa."""
    for a, v in zip(anios, empresa):
        if v > 0 and externa.get(a):
            return a
    return None

# COMENTARIO: SE ELIMINO
def _insight_ingresos_gastos(anios, ing, gas) -> str:
    sup = [a for a, i, g in zip(anios, ing, gas) if i > g]
    deficit = [a for a, i, g in zip(anios, ing, gas) if g > i]
    dif = ing[-1] - gas[-1]
    return (f"<b>Insight Analítico:</b> superávit (ingresos &gt; gastos) en {_lista_anios(sup)}; déficit (gastos &gt; ingresos) en "
            f"{_lista_anios(deficit)}. En {anios[-1]}: ingresos {ing[-1]:,.1f} MDP vs. gastos {gas[-1]:,.1f} MDP, "
            f"{'superávit' if dif >= 0 else 'déficit'} de {abs(dif):,.1f} MDP. Los gastos son la facturación recibida (no un estado de resultados).")


def _ultimo_valido(anios, *series):
    for i in range(len(anios) - 1, -1, -1):
        if all(pd.notna(s[i]) for s in series):
            return i
    return None


def _insight_itaee(anios, ing_idx, itaee_idx, sector, base) -> str:
    i = _ultimo_valido(anios, ing_idx, itaee_idx)
    if i is None or anios[i] == base:
        return "<b>Insight Analítico:</b> sin información suficiente del ITAEE para comparar el crecimiento acumulado."
    d = ing_idx[i] - itaee_idx[i]
    pos = ("por encima del" if d > 1 else "por debajo del" if d < -1 else "en línea con el")
    return (f"<b>Insight Analítico:</b> entre {base} y {anios[i]} los ingresos acumulan {ing_idx[i] - 100:+.1f}% (índice {ing_idx[i]:.1f}) "
            f"frente a {itaee_idx[i] - 100:+.1f}% del ITAEE de «{sector}» (índice {itaee_idx[i]:.1f}): {pos} sector ({d:+.1f} puntos).")


def _insight_inpp(anios, gas_idx, inpp_idx, sector, base) -> str:
    i = _ultimo_valido(anios, gas_idx, inpp_idx)
    if i is None or anios[i] == base:
        return "<b>Insight Analítico:</b> sin información suficiente del INPP para comparar el crecimiento de los gastos."
    d = gas_idx[i] - inpp_idx[i]
    if d <= 0:
        lectura = "crecieron por debajo de la inflación del productor (eficiencia operativa)"
    else:
        lectura = "crecieron por encima de la inflación del productor (presión inflacionaria en costos)"
    return (f"<b>Insight Analítico:</b> entre {base} y {anios[i]} los gastos acumulan {gas_idx[i] - 100:+.1f}% (índice {gas_idx[i]:.1f}) "
            f"frente a {inpp_idx[i] - 100:+.1f}% del INPP de «{sector}» (índice {inpp_idx[i]:.1f}): {lectura} ({d:+.1f} puntos).")


def _insight_tiie(anios, ing, tiie) -> str:
    pares = [(anios[k], ing[k] / ing[k - 1] * 100 - 100, tiie[k] - tiie[k - 1]) for k in range(1, len(anios))
             if ing[k - 1] > 0 and pd.notna(tiie[k]) and pd.notna(tiie[k - 1])]
    if not pares:
        return "<b>💡 Inteligencia de Mercado:</b> se necesitan dos o más ejercicios consecutivos con dato de TIIE para evaluar la sensibilidad."
    alza = [c for _, c, d in pares if d > 0.25]
    baja = [c for _, c, d in pares if d < -0.25]
    primero = next((v for v in tiie if pd.notna(v)), None)
    ultimo = next((v for v in reversed(tiie) if pd.notna(v)), None)
    txt = f"la TIIE promedio pasó de {primero:.2f}% a {ultimo:.2f}% en el periodo. " if primero is not None else ""
    txt += (f"En {len(alza)} año(s) de alza de tasas los ingresos variaron {np.mean(alza):+.1f}% en promedio" if alza
            else "No hubo años de alza de tasas en el periodo")
    txt += (f"; en {len(baja)} año(s) de baja, {np.mean(baja):+.1f}%. " if baja else "; sin años de baja de tasas. ")
    if len(pares) >= 3 and np.std([c for _, c, _ in pares]) > 0 and np.std([d for _, _, d in pares]) > 0:
        r = float(np.corrcoef([c for _, c, _ in pares], [d for _, _, d in pares])[0, 1])
        nivel = "baja" if abs(r) < 0.3 else "moderada" if abs(r) < 0.6 else "alta"
        txt += f"Correlación entre el crecimiento anual de ingresos y el cambio de la TIIE: {r:+.2f} (sensibilidad {nivel}). "
    return f"<b>💡 Inteligencia de Mercado:</b> {txt}Lectura descriptiva con pocos años; no prueba causalidad."


def _preparar_concentracion(df: pd.DataFrame, col_nombre: str | None, col_rfc: str | None) -> pd.DataFrame:
    """Base de las gráficas de Concentración y Riesgo de Dependencia (sin Notas de Crédito, ya filtrada por ejercicios): columnas
    `Razon_Social` (nombre de la contraparte; si falta, su RFC; si falta todo, 'Sin identificar'), `Año` (de la fecha de emisión),
    `Periodo` ('AAAA-MM'), `Metodo_Pago` (PUE/PPD), `UUID`, `SubTotal` (solo si el archivo lo trae) y `Total`."""
    nombre = df[col_nombre].astype(str).str.strip() if col_nombre else pd.Series("", index=df.index)
    rfc = df[col_rfc].astype(str).str.strip() if col_rfc else pd.Series("", index=df.index)
    razon = nombre.where(nombre.ne("") & nombre.str.lower().ne("nan"), rfc).replace({"": "Sin identificar", "nan": "Sin identificar"})
    nombre_crudo = nombre.where(nombre.ne("") & nombre.str.lower().ne("nan"), "")
    out = pd.DataFrame({"Razon_Social": razon, "Año": df["Fecha"].dt.year, "Mes": df["Fecha"].dt.month, "Periodo": df["Fecha"].dt.strftime("%Y-%m"),
                        "Metodo_Pago": df["Metodo_Pago"], "Total": df["Total"], "UUID": df["UUID"],
                        "RFC_Receptor": rfc.where(rfc.str.lower().ne("nan"), "").str.upper(), "Nombre_Crudo": nombre_crudo})
    if "SubTotal" in df.columns:
        out["SubTotal"] = df["SubTotal"]
    return out


def _normalizar_por_rfc(df: pd.DataFrame) -> pd.DataFrame:
    """Normalización por RFC (solo para el Bump Chart): con el CFDI 4.0 un mismo cliente trae varias variantes de Razón Social, así que cada
    RFC Receptor recibe UNA sola `Razon_Social_Limpia` -la más reciente (último Periodo) entre sus nombres reales, nunca el RFC de relleno-.
    Sin RFC en la fila, la entidad es su propia Razón Social. Agrega `Razon_Social_Limpia` (nombre único) y `Entidad` (RFC o, sin RFC, el nombre);
    no depende de `monto_calc`."""
    d = df.assign(Entidad=df["RFC_Receptor"].where(df["RFC_Receptor"].ne(""), df["Razon_Social"]))
    reales = d[d["Nombre_Crudo"].ne("")].sort_values("Periodo", kind="stable")
    mapeo = reales.groupby("Entidad")["Nombre_Crudo"].last().rename("Razon_Social_Limpia")        # nombre más reciente por RFC
    d = d.merge(mapeo, left_on="Entidad", right_index=True, how="left")
    d["Razon_Social_Limpia"] = d["Razon_Social_Limpia"].fillna(d["Razon_Social"])                    # RFC sin ningún nombre real: se muestra el RFC
    return d


def _pagos_por_factura(df_pagos: pd.DataFrame) -> pd.DataFrame | None:
    """Paso A del cruce: complementos de pago ACTIVOS (Estatus 'Activo'; 'Vigente' se acepta como sinónimo, como en el resto del tablero)
    agrupados por 'UUID DR' (factura relacionada, normalizada: sin espacios y en mayúsculas) con la suma de 'Monto MXN'. Una fila por factura
    pagada: así un merge posterior NO duplica facturas con varios complementos (parciales). `None` si el archivo no trae esas columnas."""
    c_uuid = buscar_columna(df_pagos.columns, "UUID DR") or buscar_columna(df_pagos.columns, "Documento Relacionado") \
        or buscar_columna(df_pagos.columns, "UUID Relacionado")
    c_monto, c_estatus = buscar_columna(df_pagos.columns, "Monto MXN"), buscar_columna(df_pagos.columns, "Estatus")
    if c_uuid is None or c_monto is None:
        return None
    d = df_pagos
    if c_estatus is not None:
        d = d[d[c_estatus].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])]
    d = pd.DataFrame({"UUID DR": d[c_uuid].astype(str).str.strip().str.upper(), "Monto MXN": a_numero(d[c_monto]).fillna(0.0)})
    return d.groupby("UUID DR")["Monto MXN"].sum().reset_index()


def _desglose_cobros(df_fac: pd.DataFrame, pagos_agrupados: pd.DataFrame, col_monto: str) -> tuple[pd.DataFrame, float]:
    """Pasos B y C: `left merge` de las facturas (`UUID`, `Metodo_Pago`, `Total`, `SubTotal`; vigentes, tipo Factura, sin NCR) con los pagos ya
    agrupados (`left_on='UUID'`, `right_on='UUID DR'`; nulos de 'Monto MXN' = 0). `prop_pagada = (Monto MXN / Total).clip(0, 1)` (siempre sobre
    el Total de la factura, para que funcione igual con 'SubTotal'). Por fila: PUE -> `Monto_PUE = col_monto`; PPD -> `Monto_PPD_Cobrado =
    col_monto * prop_pagada` y `Monto_PPD_Pendiente = col_monto * (1 - prop_pagada)`. Devuelve (DataFrame con esas 3 columnas, diferencia
    `Monto_PUE + Monto_PPD_Cobrado + Monto_PPD_Pendiente - col_monto.sum()`): debe ser 0 al centavo (cuadratura entre ambas gráficas)."""
    d = df_fac.assign(UUID_clave=df_fac["UUID"].astype(str).str.strip().str.upper())
    n = len(d)
    d = d.merge(pagos_agrupados, left_on="UUID_clave", right_on="UUID DR", how="left")
    assert len(d) == n, "el cruce no debe duplicar facturas"
    d["Monto MXN"] = d["Monto MXN"].fillna(0.0)
    total = d["Total"].to_numpy(dtype=float)
    prop = pd.Series(np.divide(d["Monto MXN"].to_numpy(dtype=float), total, out=np.zeros(n), where=total != 0), index=d.index).clip(lower=0, upper=1)
    es_pue, es_ppd = d["Metodo_Pago"].eq("PUE"), d["Metodo_Pago"].eq("PPD")
    base = d[col_monto].astype(float)
    d["Monto_PUE"] = base.where(es_pue, 0.0)
    d["Monto_PPD_Cobrado"] = (base * prop).where(es_ppd, 0.0)
    d["Monto_PPD_Pendiente"] = (base * (1 - prop)).where(es_ppd, 0.0)
    dif = float((d["Monto_PUE"] + d["Monto_PPD_Cobrado"] + d["Monto_PPD_Pendiente"]).sum() - base.sum())
    return d, dif


def _serie_mensual_por_anio(d: pd.DataFrame, col_monto: str) -> pd.DataFrame:
    """Monto mensual NETO (sin acumular) de `col_monto`: 12 filas (Mes 1-12) x una columna por Año del DataFrame; un mes sin facturas queda NaN.
    La suma de TODAS sus celdas es igual a `d[col_monto].sum()` (mismo DataFrame base de las otras dos gráficas)."""
    return d.pivot_table(index="Mes", columns="Año", values=col_monto, aggfunc="sum").reindex(range(1, 13)).sort_index(axis=1)


def _resumen_metodo_cobro(d: pd.DataFrame, col_monto: str) -> dict:
    """Montos del desglose (mismo DataFrame filtrado que las dos gráficas): total, PUE, PPD total, PPD pendiente y PPD cobrado."""
    pue, cob, pen = (float(d[c].sum()) for c in ("Monto_PUE", "Monto_PPD_Cobrado", "Monto_PPD_Pendiente"))
    return {"total": float(d[col_monto].sum()), "pue": pue, "ppd": cob + pen, "pendiente": pen, "cobrado": cob}


def _resumen_metodo_cobro_global(d: pd.DataFrame, complementos: float) -> dict:
    """Vista Total de «Método de cobro», con la lógica global de las tarjetas y del desglose anual: total = facturación PUE + PPD vigente (`Total`);
    PPD cobrado = Complementos (`complementos_vigentes`, sin cruce por UUID) y PPD pendiente = `diferencia_ppd(Facturación PPD, Complementos)`
    (puede ser negativa)."""
    pue = float(d["Monto_PUE"].sum())
    ppd = float((d["Monto_PPD_Cobrado"] + d["Monto_PPD_Pendiente"]).sum())
    return {"total": float(d["Total"].sum()), "pue": pue, "ppd": ppd, "cobrado": float(complementos), "pendiente": diferencia_ppd(ppd, float(complementos))}


def _ranking_anual(df: pd.DataFrame, col_monto: str, top: int = 10) -> pd.DataFrame:
    """Ranking COMPLETO de proveedores por año, antes de seleccionar a nadie: agrupa por Año y RFC Emisor (`_normalizar_por_rfc`: una sola razón social
    por RFC; sin RFC en la fila, el nombre es la entidad), suma `col_monto` (Total en MXN, facturas vigentes sin NCR) y numera 1..N dentro de cada año
    (mayor a menor; empates por RFC). Devuelve Año, Entidad (RFC), Razon_Social_Limpia, RFC, Monto, Rango, Total_Anio (toda la facturación recibida del
    año), Participacion (Monto / Total_Anio) y `En_Top` (Rango <= `top`)."""
    d = _normalizar_por_rfc(df)
    info = d.drop_duplicates("Entidad").set_index("Entidad")[["Razon_Social_Limpia", "RFC_Receptor"]]
    g = d.groupby(["Año", "Entidad"], as_index=False)[col_monto].sum().rename(columns={col_monto: "Monto"})
    g["Total_Anio"] = g.groupby("Año")["Monto"].transform("sum")
    g = g[g["Monto"] > 0].sort_values(["Año", "Monto", "Entidad"], ascending=[True, False, True], kind="stable")
    g["Rango"] = g.groupby("Año").cumcount() + 1
    g["Razon_Social_Limpia"] = g["Entidad"].map(info["Razon_Social_Limpia"])
    g["RFC"] = g["Entidad"].map(info["RFC_Receptor"]).replace("", "N/D")
    g["Participacion"] = g["Monto"] / g["Total_Anio"]
    g["En_Top"] = g["Rango"] <= top
    return g.reset_index(drop=True)



def _resumen_nomina_gastos(res: dict) -> dict:
    """Nómina vs. Gastos alineado con el Egreso Total: proveedores = PUE + Complementos; nómina = Total de la nómina activa."""
    return {"total": res["egreso_total"], "gastos": res["pue"] + res["complementos"], "nomina": res["nomina"]}
