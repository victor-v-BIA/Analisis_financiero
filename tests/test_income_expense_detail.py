import unittest
from unittest.mock import patch

import pandas as pd

from components.charts import fig_barra_distribucion_100
from core.loader import descripciones_clase_sat
from views.income_expense_detail import (
    _algun_anio_actividad_fuera_periodo,
    _seleccionar_corte_clases,
    tabla_clase_sat,
)


class IncomeExpenseDetailTests(unittest.TestCase):
    def test_class_cut_selector_returns_the_selected_mode_and_count(self):
        detalle = pd.DataFrame({
            "Clase": ["10101010", "10101011"],
            "Monto_MXN": [60, 40],
        })

        with patch(
            "views.income_expense_detail.st.pills",
            return_value="50%",
        ):
            n_clases, modo = _seleccionar_corte_clases(detalle, key="test_corte")

        self.assertEqual(modo, "50%")
        self.assertEqual(n_clases, 1)

    def test_pdf_bar_chart_normalizes_distribution_to_100_percent(self):
        fig = fig_barra_distribucion_100(
            "Distribución de facturación",
            ["Clase A", "Clase B"],
            [3, 1],
            bar_width=0.60,
        )

        self.assertEqual(fig.layout.barmode, "stack")
        self.assertTrue(all(trace.width == 0.60 for trace in fig.data))
        self.assertEqual([trace.x[0] for trace in fig.data], [75, 25])
        self.assertEqual(
            [trace.name for trace in fig.data],
            ["Clase A (75.0%)", "Clase B (25.0%)"],
        )

    def test_sat_table_aggregates_by_full_eight_digit_key(self):
        detalle = pd.DataFrame({
            "Clase": ["10101010", "10101011", "10101010"],
            "Monto_MXN": [100, 250, 50],
            "SubTotal_Neto_MXN": [90, 225, 45],
        })

        tabla = tabla_clase_sat(detalle)

        filas = tabla.loc[tabla["Tipo"] == "fila"].set_index("Clase")
        self.assertEqual(filas.loc["10101010", "Total"], 150)
        self.assertEqual(filas.loc["10101011", "Total"], 250)
        self.assertEqual(filas.loc["10101010", "Subtotal"], 135)

    def test_sat_descriptions_use_the_exact_eight_digit_catalog_entry(self):
        detalle = pd.DataFrame({"Clase": ["10101010", "10101011", "01010101"]})
        catalogo = {
            "claves": {
                "10101010": "Descripción A",
                "10101011": "Descripción B",
            },
        }

        descripciones = descripciones_clase_sat(detalle, catalogo)

        self.assertEqual(descripciones["10101010"], "Descripción A")
        self.assertEqual(descripciones["10101011"], "Descripción B")
        self.assertNotEqual(descripciones["10101010"], descripciones["10101011"])
        self.assertEqual(
            descripciones["01010101"], "Clave genérica (Sin clasificación específica)"
        )

    def test_activity_before_or_after_analysis_period_triggers_note(self):
        actividades = pd.DataFrame({
            "Fecha de inicio": ["15/03/2020", "01/01/2021", "31/12/2025", "01/01/2026"],
        })

        self.assertTrue(
            _algun_anio_actividad_fuera_periodo(actividades, [2021, 2025])
        )

    def test_activities_only_inside_analysis_period_do_not_trigger_note(self):
        actividades = pd.DataFrame({
            "Fecha de inicio": ["01/01/2021", "15/06/2023", "31/12/2025"],
        })

        self.assertFalse(
            _algun_anio_actividad_fuera_periodo(actividades, [2021, 2023, 2025])
        )

    def test_missing_or_invalid_activity_dates_do_not_trigger_note(self):
        actividades = pd.DataFrame({
            "Fecha de inicio": [None, "fecha inválida"],
        })

        self.assertFalse(
            _algun_anio_actividad_fuera_periodo(actividades, [2021, 2025])
        )
        self.assertFalse(
            _algun_anio_actividad_fuera_periodo(
                pd.DataFrame(columns=["Fecha de inicio"]), [2021, 2025]
            )
        )


if __name__ == "__main__":
    unittest.main()
