import unittest

import pandas as pd

from views.income_expense_detail import _algun_anio_actividad_fuera_periodo


class IncomeExpenseDetailTests(unittest.TestCase):
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
