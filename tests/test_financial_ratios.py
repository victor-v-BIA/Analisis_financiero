import io
import unittest

import pandas as pd
from pypdf import PdfReader

from components.financial_ratios import (
    NOTA_RAZONES,
    _formato_razon,
    _matriz_razones,
    _tarjetas_razones,
    _ultimo_ejercicio_con_informacion,
)
from components.pdf_generator import (
    _financial_ratio_cards_table,
    generate_modular_pdf,
)
from core.financial_ratios import _normalizar_tabla_razones


class FinancialRatiosTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame({
            "Categoría": [
                "liquidity > current_ratio",
                "liquidity > quick_ratio",
                "liquidity > cash_to_assets",
                "liquidity > net_working_capital_to_sales",
                "leverage > total_debt_ratio",
                "leverage > debt_equity_ratio",
                "leverage > coverage",
                "profitability > gross_profit_margin",
                "profitability > return_on_sales",
                "profitability > return_on_equity",
                "profitability > total_asset_turnover",
                "profitability > roa",
            ],
            2021: [1.1, None, None, None, None, None, None, None, None, None, None, 0.08],
            2022: [1.2, None, None, None, None, None, None, None, None, None, None, 0.09],
            2023: [1.3, None, None, None, None, None, None, None, None, None, None, 0.10],
            2024: [1.4, 0.9, None, 0.1, 0.45, 3.0, None, 0.8, 0.08, None, 5, 0.11],
            2025: [1.5, 1.0, "23%", 0.12, 0.47, 2.8, 2.4, 0.94, 0.09, 0.15, 20, 0.12],
            2026: [1.6, 1.05, None, None, 0.49, None, None, 0.95, 0.10, 0.18, 101, 0.13],
        })
        self.ratios = _normalizar_tabla_razones(self.source)

    def test_parser_keeps_recent_years_and_valid_zero_values(self):
        self.assertEqual(list(self.ratios.columns), [2022, 2023, 2024, 2025, 2026])
        self.assertEqual(self.ratios.at["current_ratio", 2024], 1.4)
        self.assertEqual(len(self.ratios.index), 11)
        self.assertNotIn("roa", self.ratios.index)

        with_zero = _normalizar_tabla_razones(pd.DataFrame({
            "category": ["leverage > total_debt_ratio"],
            "2025": [0],
        }))
        self.assertEqual(with_zero.at["total_debt_ratio", 2025], 0)

    def test_spanish_metric_names_are_recognized(self):
        razones = _normalizar_tabla_razones(pd.DataFrame({
            "Categoría": [
                "Liquidez > Razón circulante",
                "Liquidez > Capital de trabajo a ventas",
                "Estructura y deuda > Cobertura de intereses",
                "Rentabilidad > Rendimiento sobre capital",
            ],
            "2025": [1.25, 0.12, 2.5, 0.18],
        }))
        self.assertEqual(
            set(razones.index),
            {"current_ratio", "net_working_capital_to_sales", "coverage", "return_on_equity"},
        )

    def test_percentage_formatting_and_latest_card_value(self):
        self.assertEqual(self.ratios.at["cash_to_assets", 2025], 0.23)
        self.assertEqual(_formato_razon("gross_profit_margin", 0.95), "95.0%*")
        self.assertEqual(_formato_razon("total_asset_turnover", 101), "n.c.")

        ultimo = _ultimo_ejercicio_con_informacion(self.ratios)
        tarjetas_html, tarjetas = _tarjetas_razones(self.ratios, ultimo)
        self.assertEqual(ultimo, 2026)
        coverage = next(card for card in tarjetas if card["titulo"] == "Cobertura de intereses")
        self.assertEqual(coverage["valor"], "2.40x (2025)")
        self.assertEqual(len(tarjetas), 6)
        self.assertIn("Pesos de deuda por cada peso de capital propio.", tarjetas_html)

    def test_metrics_empty_in_every_year_are_omitted(self):
        razones = _normalizar_tabla_razones(pd.DataFrame({
            "Categoría": ["liquidity > current_ratio"],
            "2024": [None],
            "2025": [None],
        }))
        self.assertTrue(razones.empty)
        self.assertIsNone(_ultimo_ejercicio_con_informacion(razones))

    def test_matrix_rows_footnotes_and_single_page_pdf(self):
        matriz_html, matriz, notas = _matriz_razones(self.ratios)
        self.assertIn("Liquidez", matriz_html)
        self.assertIn("white-space:nowrap;text-align:center", matriz_html)
        self.assertIn("n.c.: dato no comparable", notas[1])
        self.assertTrue(any(note.startswith("* Margen bruto atípico") for note in notas))
        self.assertIn("span_rows", matriz.attrs)

        cards = _tarjetas_razones(
            self.ratios,
            _ultimo_ejercicio_con_informacion(self.ratios),
        )[1]
        cards_table = _financial_ratio_cards_table(cards)
        cards_table.wrap(504, 100000)
        self.assertEqual(len(set(cards_table._rowHeights)), 1)

        pdf = generate_modular_pdf(
            "Reporte de prueba",
            "Ejercicios fiscales",
            [{
                "type": "financial_ratios",
                "section_title": "9. Posición Financiera",
                "cards_title": "Indicadores de evaluación crediticia — Ejercicio 2026",
                "cards": cards,
                "note": NOTA_RAZONES,
                "insight": "Insight de prueba para validar el orden.",
                "matrix_title": "Evolución de razones financieras de los últimos cinco ejercicios fiscales",
                "df": matriz,
                "footnotes": notas,
            }],
        )
        reader = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 1)
        texto = reader.pages[0].extract_text()
        self.assertIn("Indicadores de evaluación crediticia", texto)
        self.assertIn("n.c.: dato no comparable", texto)
        self.assertLess(texto.index("Razón circulante"), texto.index("Insight:"))
        self.assertLess(
            texto.index("Insight:"),
            texto.index("Nota: Razones financieras que algunas instituciones bancarias"),
        )


if __name__ == "__main__":
    unittest.main()
