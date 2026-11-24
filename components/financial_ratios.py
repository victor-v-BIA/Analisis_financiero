"""Tarjetas y matriz de razones financieras reportadas."""

import pandas as pd

from core.financial_ratios import _RAZONES_PORCENTAJE, _valor_razon


_RAZONES = (
    ("current_ratio", "Razón circulante", "Liquidez", False),
    ("quick_ratio", "Prueba ácida", "Liquidez", False),
    ("cash_to_assets", "Efectivo a activo total", "Liquidez", False),
    ("net_working_capital_to_sales", "Capital de trabajo a ventas", "Liquidez", False),
    ("total_debt_ratio", "Endeudamiento total", "Estructura y deuda", False),
    ("debt_equity_ratio", "Apalancamiento", "Estructura y deuda", False),
    ("coverage", "Cobertura de intereses", "Estructura y deuda", True),
    ("gross_profit_margin", "Margen bruto", "Rentabilidad y eficiencia", False),
    ("return_on_sales", "Margen neto (ROS)", "Rentabilidad y eficiencia", False),
    ("return_on_equity", "Rendimiento sobre capital (ROE)", "Rentabilidad y eficiencia", False),
    ("total_asset_turnover", "Rotación de activos totales", "Rentabilidad y eficiencia", False),
)

_PILARES = (
    ("Liquidez", ("current_ratio", "quick_ratio", "cash_to_assets", "net_working_capital_to_sales")),
    ("Estructura y deuda", ("total_debt_ratio", "debt_equity_ratio", "coverage")),
    (
        "Rentabilidad y eficiencia",
        ("gross_profit_margin", "return_on_sales", "return_on_equity", "total_asset_turnover"),
    ),
)

_TARJETAS = (
    (
        "net_working_capital_to_sales",
        "Capital de trabajo a ventas",
        "Recursos de corto plazo menos deudas de corto plazo, por cada peso vendido.",
    ),
    (
        "cash_to_assets",
        "Efectivo a activo total",
        "Proporción de los activos que está en efectivo.",
    ),
    (
        "debt_equity_ratio",
        "Apalancamiento",
        "Pesos de deuda por cada peso de capital propio.",
    ),
    (
        "return_on_equity",
        "Rendimiento sobre capital (ROE)",
        "Utilidad o pérdida por cada peso de capital propio.",
    ),
    (
        "total_asset_turnover",
        "Rotación de activos totales",
        "Pesos vendidos por cada peso de activo.",
    ),
    (
        "coverage",
        "Cobertura de intereses",
        "Veces que la utilidad operativa cubre los intereses.",
    ),
)

NOTA_RAZONES = (
    "Nota: Razones financieras que algunas instituciones bancarias pueden obtener a partir de las "
    "declaraciones de la empresa para conocer su situación financiera según lo declarado. Se presentan "
    "solo como referencia: cada banco puede aplicar métricas internas y otros criterios de evaluación."
)


def _formato_razon(metrica: str, valor: float) -> str:
    if pd.isna(valor):
        return "s/i"
    if metrica == "total_asset_turnover" and valor > 100:
        return "n.c."
    if metrica in _RAZONES_PORCENTAJE:
        sufijo = "*" if metrica == "gross_profit_margin" and valor >= 0.95 else ""
        return f"{valor * 100:.1f}%{sufijo}"
    return f"{valor:.2f}x"


def _ultimo_ejercicio_con_informacion(razones: pd.DataFrame) -> int | None:
    for anio in reversed(list(razones.columns)):
        if any(pd.notna(_valor_razon(razones, metrica, anio)) for metrica in razones.index):
            return int(anio)
    return None


def _tarjetas_razones(
    razones: pd.DataFrame,
    ultimo: int,
) -> tuple[str, list[dict[str, str]]]:
    tarjetas = []
    for metrica, titulo, descripcion in _TARJETAS:
        if metrica not in razones.index:
            continue
        ejercicios = [
            int(anio) for anio in reversed(list(razones.columns))
            if pd.notna(_valor_razon(razones, metrica, anio))
        ]
        if not ejercicios:
            continue
        anio = ejercicios[0]
        valor = _formato_razon(metrica, _valor_razon(razones, metrica, anio))
        if anio != ultimo:
            valor = f"{valor} ({anio})"
        tarjetas.append({
            "titulo": titulo,
            "valor": valor,
            "descripcion": descripcion,
        })

    html = [
        """
        <style>
        .razones-evaluacion-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:.45rem 0 1rem}
        .razones-evaluacion-card{box-sizing:border-box;min-height:112px;padding:12px 14px;border:1px solid #D1D5DB;
            border-radius:10px;background:#F9FAFB;color:#1F2937;display:flex;flex-direction:column;justify-content:space-between}
        .razones-evaluacion-title{font-size:.82rem;font-weight:600;color:#374151}
        .razones-evaluacion-value{font-size:1.45rem;font-weight:700;line-height:1.8rem;color:#111827;margin:.22rem 0}
        .razones-evaluacion-description{font-size:.75rem;line-height:1.05rem;color:#4B5563}
        @media(max-width:850px){.razones-evaluacion-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:550px){.razones-evaluacion-grid{grid-template-columns:1fr}}
        </style>
        <div class="razones-evaluacion-grid">
        """
    ]
    for tarjeta in tarjetas:
        html.append(
            '<article class="razones-evaluacion-card">'
            f'<div class="razones-evaluacion-title">{tarjeta["titulo"]}</div>'
            f'<div class="razones-evaluacion-value">{tarjeta["valor"]}</div>'
            f'<div class="razones-evaluacion-description">{tarjeta["descripcion"]}</div>'
            "</article>"
        )
    html.append("</div>")
    return "".join(html), tarjetas


def _matriz_razones(
    razones: pd.DataFrame,
) -> tuple[str, pd.DataFrame, list[str]]:
    anios = [int(anio) for anio in razones.columns]
    columnas = ["Razón", *(str(anio) for anio in anios)]
    html = [
        """
        <style>
        .razones-tabla-wrap{width:100%;overflow-x:auto}
        .razones-tabla{width:100%;min-width:760px;border-collapse:collapse;font-size:.86rem;
            font-variant-numeric:tabular-nums}
        .razones-tabla th,.razones-tabla td{padding:.52rem .6rem;border-bottom:1px solid rgba(128,128,128,.28)}
        .razones-tabla th{background:rgba(128,128,128,.12);font-weight:600;white-space:nowrap;text-align:center}
        .razones-tabla td:first-child{text-align:left}
        .razones-tabla td:not(:first-child){text-align:right;white-space:nowrap}
        .razones-tabla tr.razones-pilar td{background:rgba(128,128,128,.09);font-weight:700;text-align:center}
        </style>
        """,
        '<div class="razones-tabla-wrap"><table class="razones-tabla"><thead><tr>',
        "".join(f"<th>{columna}</th>" for columna in columnas),
        "</tr></thead><tbody>",
    ]
    filas_pdf = []
    filas_pilar = []
    metricas_mostradas = []

    for pilar, claves in _PILARES:
        disponibles = [
            metrica for metrica in claves
            if metrica in razones.index
            and razones.loc[metrica].notna().any()
        ]
        if not disponibles:
            continue
        html.append(f'<tr class="razones-pilar"><td colspan="{len(columnas)}">{pilar}</td></tr>')
        filas_pilar.append(len(filas_pdf))
        filas_pdf.append({"Razón": pilar, **{str(anio): "" for anio in anios}})
        for metrica in disponibles:
            etiqueta = next(nombre for clave, nombre, _, _ in _RAZONES if clave == metrica)
            metricas_mostradas.append(metrica)
            fila_html = [f"<tr><td>{etiqueta}</td>"]
            fila_pdf = {"Razón": etiqueta}
            for anio in anios:
                valor = _valor_razon(razones, metrica, anio)
                texto = _formato_razon(metrica, valor)
                fila_html.append(f"<td>{texto}</td>")
                fila_pdf[str(anio)] = texto
            fila_html.append("</tr>")
            html.extend(fila_html)
            filas_pdf.append(fila_pdf)

    html.append("</tbody></table></div>")
    matriz_pdf = pd.DataFrame(filas_pdf, columns=columnas)
    matriz_pdf.attrs["span_rows"] = filas_pilar

    notas = []
    if any(
        pd.isna(razones.loc[metrica, anio])
        for metrica in metricas_mostradas
        for anio in razones.columns
    ):
        notas.append("s/i: sin información disponible para este ejercicio.")
    if (
        "total_asset_turnover" in metricas_mostradas
        and (razones.loc["total_asset_turnover"] > 100).any()
    ):
        notas.append("n.c.: dato no comparable en la base de origen.")
    if (
        "gross_profit_margin" in metricas_mostradas
        and (razones.loc["gross_profit_margin"] >= 0.95).any()
    ):
        notas.append(
            "* Margen bruto atípico: en estos ejercicios casi no se reportó costo de ventas, "
            "por lo que no es comparable con los demás años."
        )
    return "".join(html), matriz_pdf, notas
