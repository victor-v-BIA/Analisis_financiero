"""Presentación y gráficas de las razones financieras."""

from html import escape

import pandas as pd
import plotly.express as px

from core.financial_ratios import (
    _RAZONES_PORCENTAJE,
    _nivel_razon,
    _valor_razon,
    criterios_razon,
)


_RAZONES_LABELS = {
    "current_ratio": "Razón Circulante",
    "quick_ratio": "Prueba Ácida",
    "total_debt_ratio": "Endeudamiento Total",
    "debt_equity_ratio": "Apalancamiento (Pasivo/Capital)",
    "gross_profit_margin": "Margen Bruto",
    "return_on_sales": "Margen Neto (ROS)",
    "return_on_equity": "Rentabilidad del Capital (ROE)",
    "total_asset_turnover": "Rotación de Activos Totales",
}

_RAZONES_PILARES = (
    ("Liquidez de Corto Plazo", ("current_ratio", "quick_ratio")),
    ("Estructura de Capital y Deuda", ("total_debt_ratio", "debt_equity_ratio")),
    (
        "Rentabilidad y Eficiencia Declarada",
        ("gross_profit_margin", "return_on_sales", "return_on_equity", "total_asset_turnover"),
    ),
)

_RAZONES_MATRIZ_LABELS = {
    "current_ratio": "Razón Circulante (Activo CP / Pasivo CP)",
    "quick_ratio": "Prueba Ácida ((Activo CP - Inv.) / Pasivo CP)",
    "total_debt_ratio": "Endeudamiento Total (Pasivo / Activo)",
    "debt_equity_ratio": "Apalancamiento (Pasivo / Capital Contable)",
    "gross_profit_margin": "Margen Bruto",
    "return_on_sales": "Margen Neto (ROS)",
    "return_on_equity": "Retorno sobre Capital (ROE)",
    "total_asset_turnover": "Rotación de Activos Totales",
}

_RAZONES_DESCRIPCION = {
    "current_ratio": (
        "Cuántos pesos de activos de corto plazo tiene la empresa por cada peso de deuda que vence en menos de un año. "
        "Un valor menor a 1.00x indica que sus recursos de corto plazo no alcanzan para cubrir esas obligaciones."
    ),
    "quick_ratio": "Capacidad de cubrir pasivos circulantes sin depender de inventarios.",
    "total_debt_ratio": (
        "Qué proporción de los activos de la empresa está financiada con pasivos. "
        "El subtítulo (Pasivo/Capital) indica cuántos pesos debe por cada peso que han aportado o acumulado los socios."
    ),
    "debt_equity_ratio": "Pasivo por cada unidad de capital contable.",
    "gross_profit_margin": "Utilidad bruta como proporción de las ventas.",
    "return_on_sales": (
        "Qué porcentaje de sus ingresos se convirtió en utilidad o pérdida al final del ejercicio, "
        "según su declaración anual."
    ),
    "return_on_equity": (
        "Cuánto ganó o perdió la empresa en relación con el capital de sus socios. "
        "Un valor negativo indica que la pérdida del ejercicio redujo su patrimonio."
    ),
    "total_asset_turnover": "Ventas generadas por cada unidad de activos.",
}

_RAZONES_ESTADOS = {
    "Óptimo": ("green", "🟢"),
    "Vigilancia": ("orange", "🟠"),
    "Crítico": ("red", "🔴"),
    "Atípico": ("blue", "🔵"),
}
_RAZONES_CLASES = {
    "Óptimo": "optimo",
    "Vigilancia": "vigilancia",
    "Crítico": "critico",
    "Atípico": "atipico",
}
_RAZONES_KPI_CARDS = (
    ("current_ratio", "Liquidez (Razón Circulante)", "Capacidad de pago a corto plazo"),
    ("total_debt_ratio", "Endeudamiento Total", "Pasivo Total / Activo Total"),
    ("return_on_sales", "Margen Neto Declarado (ROS)", "Utilidad / Pérdida neta sobre ingresos"),
    ("return_on_equity", "Rentabilidad del Capital (ROE)", "Utilidad / Pérdida neta sobre capital al cierre"),
)


def _formato_razon(metrica: str, valor: float) -> str:
    if pd.isna(valor):
        return "n/a"
    if metrica in _RAZONES_PORCENTAJE:
        return f"{valor * 100:.1f}%"
    return f"{valor:.2f}x"


def _cambio_razon(metrica: str, actual: float, previo: float) -> str | None:
    if pd.isna(actual) or pd.isna(previo):
        return None
    cambio = actual - previo
    return f"{cambio * 100:+.1f} pp" if metrica in _RAZONES_PORCENTAJE else f"{cambio:+.2f}x"


def _html_tarjetas_razones(
    razones: pd.DataFrame,
    ultimo: int,
    previo: int | None,
) -> tuple[str, list[tuple[str, str, str]]]:
    html = [
        """
        <style>
        .razones-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:1rem}
        .razones-kpi-card{box-sizing:border-box;min-height:126px;padding:14px 16px;border:1px solid #D1D5DB;
            border-radius:12px;background:#F3F4F6;color:#1F2937;display:flex;flex-direction:column;justify-content:space-between}
        .razones-kpi-title{display:flex;align-items:center;gap:5px;color:#4B5563;font-size:.86rem;font-weight:600}
        .razones-kpi-info{display:inline-flex;width:13px;height:13px;align-items:center;justify-content:center;
            border:1px solid #6B7280;border-radius:50%;font-size:9px;font-weight:700;line-height:1}
        .razones-kpi-main{display:flex;align-items:center;gap:9px;margin:.25rem 0}
        .razones-kpi-value{color:#111827;font-size:1.55rem;font-weight:700;line-height:1.8rem}
        .razones-kpi-status{display:inline-flex;align-items:center;gap:5px;padding:.13rem .5rem;border:1px solid;
            border-radius:1rem;font-size:.72rem;font-weight:600;white-space:nowrap}
        .razones-kpi-status-dot{width:9px;height:9px;border-radius:50%}
        .razones-kpi-status.optimo{color:#047857;background:#E7F7EE;border-color:#86D8A7}
        .razones-kpi-status.optimo .razones-kpi-status-dot{background:#16A34A}
        .razones-kpi-status.vigilancia{color:#B45309;background:#FFF3E0;border-color:#FDBA74}
        .razones-kpi-status.vigilancia .razones-kpi-status-dot{background:#D97706}
        .razones-kpi-status.critico{color:#B91C1C;background:#FEECEC;border-color:#FCA5A5}
        .razones-kpi-status.critico .razones-kpi-status-dot{background:#DC2626}
        .razones-kpi-status.atipico{color:#1D4ED8;background:#EFF6FF;border-color:#93C5FD}
        .razones-kpi-status.atipico .razones-kpi-status-dot{background:#2563EB}
        .razones-kpi-delta{color:#6B7280;font-size:.74rem;line-height:1.1rem}
        .razones-kpi-description{color:#6B7280;font-size:.72rem;line-height:1rem;margin-top:.18rem}
        @media(max-width:700px){.razones-kpi-grid{grid-template-columns:1fr}}
        </style>
        <div class="razones-kpi-grid">
        """
    ]
    datos_pdf = []
    for metrica, titulo, descripcion in _RAZONES_KPI_CARDS:
        valor = _valor_razon(razones, metrica, ultimo)
        nivel = _nivel_razon(razones, metrica, ultimo)
        previo_valor = _valor_razon(razones, metrica, previo) if previo is not None else float("nan")
        cambio = _cambio_razon(metrica, valor, previo_valor)
        if cambio is not None and previo is not None:
            flecha = "▲" if valor > previo_valor else "▼" if valor < previo_valor else "•"
            texto_cambio = f"{flecha} {cambio} vs {previo}"
        else:
            texto_cambio = "Sin ejercicio previo comparable"

        if metrica == "total_debt_ratio":
            pasivo_capital = _valor_razon(razones, "debt_equity_ratio", ultimo)
            if pd.notna(pasivo_capital):
                descripcion = f"{descripcion} · {_formato_razon('debt_equity_ratio', pasivo_capital)} Pasivo/Capital"

        if nivel is None:
            estado_html = '<span class="razones-kpi-status">Estado no disponible</span>'
            estado_pdf = "Estado no disponible"
        else:
            clase = _RAZONES_CLASES[nivel]
            estado_html = (
                f'<span class="razones-kpi-status {clase}"><span class="razones-kpi-status-dot"></span>'
                f'{escape(nivel)}</span>'
            )
            estado_pdf = nivel

        html.append(
            '<article class="razones-kpi-card">'
            f'<div class="razones-kpi-title">{escape(titulo)}'
            f'<span class="razones-kpi-info" title="{escape(_RAZONES_DESCRIPCION[metrica])}">i</span></div>'
            f'<div class="razones-kpi-main"><span class="razones-kpi-value">{escape(_formato_razon(metrica, valor))}</span>'
            f'{estado_html}</div>'
            f'<div class="razones-kpi-delta">{escape(texto_cambio)}</div>'
            f'<div class="razones-kpi-description">{escape(descripcion)}</div>'
            '</article>'
        )
        datos_pdf.append(
            (titulo, _formato_razon(metrica, valor), f"{estado_pdf} · {texto_cambio} · {descripcion}")
        )
    html.append("</div>")
    return "".join(html), datos_pdf


def _html_matriz_razones(
    razones: pd.DataFrame,
    anios: list[int],
) -> tuple[str, pd.DataFrame]:
    anio_ultimo = anios[-1]
    columnas = ["Razón", *(str(anio) for anio in anios), f"Semáforo {anio_ultimo}"]
    html = [
        """
        <style>
        .razones-tabla-wrap{width:100%;overflow-x:auto}
        .razones-tabla{width:100%;min-width:760px;border-collapse:collapse;font-size:.86rem;
            font-variant-numeric:tabular-nums}
        .razones-tabla th,.razones-tabla td{padding:.52rem .6rem;border-bottom:1px solid rgba(128,128,128,.28)}
        .razones-tabla th{background:rgba(128,128,128,.12);font-weight:600;white-space:nowrap}
        .razones-tabla th:first-child,.razones-tabla td:first-child{text-align:left}
        .razones-tabla .razon-anio,.razones-tabla .razon-valor{text-align:right;white-space:nowrap}
        .razones-tabla .razon-estado{text-align:center;white-space:nowrap}
        .razones-tabla .razon-pilar td{background:rgba(128,128,128,.09);font-weight:700}
        .razones-tabla .razon-dot,.razones-tabla .razon-badge-dot{display:inline-block;width:.48rem;height:.48rem;
            border-radius:50%;margin-right:.35rem;vertical-align:middle}
        .razones-tabla .optimo .razon-dot,.razones-tabla .optimo .razon-badge-dot{background:#16a34a}
        .razones-tabla .vigilancia .razon-dot,.razones-tabla .vigilancia .razon-badge-dot{background:#d97706}
        .razones-tabla .critico .razon-dot,.razones-tabla .critico .razon-badge-dot{background:#dc2626}
        .razones-tabla .atipico .razon-dot,.razones-tabla .atipico .razon-badge-dot{background:#2563eb}
        .razones-tabla .razon-badge{display:inline-block;border:1px solid;border-radius:1rem;
            padding:.12rem .58rem;font-size:.76rem;font-weight:600}
        .razones-tabla .optimo.razon-badge{color:#047857;background:#e7f7ee;border-color:#86d8a7}
        .razones-tabla .vigilancia.razon-badge{color:#b45309;background:#fff3e0;border-color:#fdba74}
        .razones-tabla .critico.razon-badge{color:#b91c1c;background:#feecec;border-color:#fca5a5}
        .razones-tabla .atipico.razon-badge{color:#1d4ed8;background:#eff6ff;border-color:#93c5fd}
        </style>
        <div class="razones-tabla-wrap"><table class="razones-tabla"><thead><tr>
        """
    ]
    for indice, columna in enumerate(columnas):
        clase = (
            "razon-anio" if 0 < indice < len(columnas) - 1
            else "razon-estado" if indice == len(columnas) - 1
            else ""
        )
        html.append(f'<th class="{clase}">{escape(columna)}</th>')
    html.append("</tr></thead><tbody>")

    filas_pdf = []
    for pilar, metricas in _RAZONES_PILARES:
        disponibles = [metrica for metrica in metricas if metrica in razones.index]
        if not disponibles:
            continue
        html.append(f'<tr class="razon-pilar"><td colspan="{len(columnas)}">{escape(pilar)}</td></tr>')
        filas_pdf.append({
            "Razón": f"<b>{escape(pilar)}</b>",
            **{str(anio): "" for anio in anios},
            f"Semáforo {anio_ultimo}": "",
        })
        for metrica in disponibles:
            tooltip = escape(f"{_RAZONES_DESCRIPCION[metrica]} {criterios_razon(metrica)}")
            fila_html = [f'<tr><td title="{tooltip}">{escape(_RAZONES_MATRIZ_LABELS[metrica])}</td>']
            fila_pdf = {"Razón": _RAZONES_MATRIZ_LABELS[metrica]}
            for anio in anios:
                valor = _valor_razon(razones, metrica, anio)
                nivel = _nivel_razon(razones, metrica, anio)
                if nivel is None:
                    texto = "—"
                    fila_html.append(f'<td class="razon-valor">{texto}</td>')
                else:
                    clase = _RAZONES_CLASES[nivel]
                    texto = _formato_razon(metrica, valor)
                    fila_html.append(
                        f'<td class="razon-valor {clase}" title="{tooltip}">'
                        f'<span class="razon-dot"></span>{escape(texto)}</td>'
                    )
                fila_pdf[str(anio)] = f"{_RAZONES_ESTADOS[nivel][1]} {texto}" if nivel else texto

            estado_ultimo = _nivel_razon(razones, metrica, anio_ultimo)
            if estado_ultimo is None:
                fila_html.append('<td class="razon-estado">—</td>')
                fila_pdf[f"Semáforo {anio_ultimo}"] = "n/d"
            else:
                clase = _RAZONES_CLASES[estado_ultimo]
                fila_html.append(
                    f'<td class="razon-estado"><span class="razon-badge {clase}">'
                    f'<span class="razon-badge-dot"></span>{escape(estado_ultimo)}</span></td>'
                )
                fila_pdf[f"Semáforo {anio_ultimo}"] = estado_ultimo
            fila_html.append("</tr>")
            html.extend(fila_html)
            filas_pdf.append(fila_pdf)

    html.append("</tbody></table></div>")
    return "".join(html), pd.DataFrame(filas_pdf, columns=columnas)


def _fig_liquidez_razones(razones: pd.DataFrame):
    filas = []
    for metrica in ("current_ratio", "quick_ratio"):
        if metrica not in razones.index:
            continue
        for anio in razones.columns:
            valor = _valor_razon(razones, metrica, anio)
            if pd.notna(valor):
                filas.append({
                    "Ejercicio": anio,
                    "Razón": _RAZONES_LABELS[metrica],
                    "Valor": valor,
                    "Etiqueta": _formato_razon(metrica, valor),
                })
    fig = px.line(
        pd.DataFrame(filas),
        x="Ejercicio",
        y="Valor",
        color="Razón",
        markers=True,
        text="Etiqueta",
        color_discrete_map={"Razón Circulante": "#3B82F6", "Prueba Ácida": "#8B5CF6"},
    )
    anios = list(razones.columns)
    fig.update_traces(line_width=2.5, marker_size=7, textposition="top left", textfont_size=9)
    for traza in fig.data:
        if traza.name == "Prueba Ácida":
            traza.textposition = "bottom center"
    fig.add_scatter(
        x=anios,
        y=[1.0] * len(anios),
        mode="lines",
        name="Umbral mínimo de liquidez (1.00x)",
        line={"color": "#EF4444", "dash": "dot", "width": 1.5},
    )
    fig.update_layout(
        title={"text": "Liquidez de Corto Plazo vs. Umbral Mínimo", "x": 0.5, "xanchor": "center"},
        xaxis={
            "title": None,
            "tickmode": "array",
            "tickvals": anios,
            "ticktext": [str(anio) for anio in anios],
            "showgrid": False,
        },
        yaxis={
            "title": None,
            "range": [0.6, 1.7],
            "tickmode": "array",
            "tickvals": [0.8, 1.0, 1.2, 1.4, 1.6],
            "tickformat": ".2f",
            "ticksuffix": "x",
            "gridcolor": "rgba(148,163,184,0.22)",
            "zeroline": False,
        },
        legend={"orientation": "h", "x": 0, "xanchor": "left", "y": -0.28, "yanchor": "top",
                "font": {"size": 10}, "title": None},
        height=350,
        margin={"l": 48, "r": 8, "t": 48, "b": 92},
        font={"color": "#64748B", "size": 10},
        hovermode="x unified",
    )
    return fig


def _fig_estructura_razones(razones: pd.DataFrame):
    filas = []
    for metrica in ("total_debt_ratio", "gross_profit_margin", "return_on_sales"):
        if metrica not in razones.index:
            continue
        for anio in razones.columns:
            valor = _valor_razon(razones, metrica, anio)
            if pd.notna(valor) and _nivel_razon(razones, metrica, anio) != "Atípico":
                filas.append({
                    "Ejercicio": anio,
                    "Razón": _RAZONES_LABELS[metrica],
                    "Valor": valor * 100,
                    "Etiqueta": _formato_razon(metrica, valor),
                })
    if not filas:
        return None
    fig = px.line(
        pd.DataFrame(filas),
        x="Ejercicio",
        y="Valor",
        color="Razón",
        markers=True,
        text="Etiqueta",
        color_discrete_map={
            "Endeudamiento Total": "#F59E0B",
            "Margen Bruto": "#60A5FA",
            "Margen Neto (ROS)": "#34D399",
        },
    )
    anios = list(razones.columns)
    fig.update_traces(line_width=2.5, marker_size=7, textposition="top center", textfont_size=9)
    for traza in fig.data:
        if traza.name == "Margen Bruto":
            traza.textposition = "bottom center"
        elif traza.name == "Margen Neto (ROS)":
            traza.textposition = "top right"
    fig.update_layout(
        title={"text": "Estructura Patrimonial vs. Márgenes Declarados %", "x": 0.5, "xanchor": "center"},
        xaxis={
            "title": None,
            "tickmode": "array",
            "tickvals": anios,
            "ticktext": [str(anio) for anio in anios],
            "showgrid": False,
        },
        yaxis={
            "title": None,
            "range": [-25, 100],
            "tickmode": "array",
            "tickvals": [-20, 0, 20, 40, 60, 80],
            "tickformat": ".0f",
            "ticksuffix": "%",
            "gridcolor": "rgba(148,163,184,0.22)",
            "zeroline": True,
            "zerolinecolor": "#9CA3AF",
            "zerolinewidth": 1.5,
        },
        legend={"orientation": "h", "x": 0, "xanchor": "left", "y": -0.28, "yanchor": "top",
                "font": {"size": 10}, "title": None},
        height=350,
        margin={"l": 48, "r": 8, "t": 48, "b": 92},
        font={"color": "#64748B", "size": 10},
        hovermode="x unified",
    )
    return fig
