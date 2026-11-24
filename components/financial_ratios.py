"""Presentación y gráficas de las razones financieras."""

from html import escape

import pandas as pd
import plotly.express as px

from core.financial_ratios import (
    _RAZONES_PORCENTAJE,
    _ejercicio_previo_con_informacion,
    _lectura_razon,
    _nivel_razon,
    _tendencia_razon,
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

_RAZONES_PDF_COLORES = {
    "Óptimo": "#16A34A",
    "Vigilancia": "#D97706",
    "Crítico": "#DC2626",
    "Atípico": "#2563EB",
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


def _ultimo_ejercicio_con_informacion(razones: pd.DataFrame, metrica: str) -> int | None:
    for anio in reversed(list(razones.columns)):
        if pd.notna(_valor_razon(razones, metrica, anio)):
            return anio
    return None


def _texto_tendencia(tendencia: str | None) -> str:
    if tendencia == "Mejora":
        return "↑ Mejora"
    if tendencia == "Deterioro":
        return "↓ Deterioro"
    if tendencia == "Estable":
        return "→ Estable"
    return ""


def _color_razon(metrica: str, lectura: str | None) -> str:
    if lectura == "Cobertura suficiente" or lectura == "Bajo" or lectura == "Utilidad":
        return "#16A34A"
    if lectura in ("Cobertura ajustada", "Moderado", "Elevado"):
        return "#D97706"
    if lectura in ("Cobertura insuficiente", "Muy elevado", "Pérdida"):
        return "#DC2626"
    if lectura == "Liquidez excedente" or lectura == "Atípico":
        return "#2563EB"
    if lectura == "Capital contable negativo" or lectura == "No interpretable":
        return "#6B7280"
    return "#9CA3AF"


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
            border-radius:1rem;font-size:.72rem;font-weight:600;white-space:nowrap;
            color:#4B5563;background:#E5E7EB;border-color:#CBD5E1}
        .razones-kpi-status-dot{display:inline-block;width:.48rem;height:.48rem;border-radius:50%}
        .razones-kpi-delta{color:#6B7280;font-size:.74rem;line-height:1.1rem}
        .razones-kpi-description{color:#6B7280;font-size:.72rem;line-height:1rem;margin-top:.18rem}
        @media(max-width:700px){.razones-kpi-grid{grid-template-columns:1fr}}
        </style>
        <div class="razones-kpi-grid">
        """
    ]
    datos_pdf = []
    for metrica, titulo, descripcion in _RAZONES_KPI_CARDS:
        anio_metrica = _ultimo_ejercicio_con_informacion(razones, metrica)
        valor = _valor_razon(razones, metrica, anio_metrica) if anio_metrica is not None else float("nan")
        lectura = _lectura_razon(razones, metrica, anio_metrica) if anio_metrica is not None else None
        previo, tendencia = _tendencia_razon(razones, metrica, anio_metrica) if anio_metrica is not None else (None, None)
        texto_tendencia = _texto_tendencia(tendencia)
        if previo is not None:
            texto_cambio = f"vs {previo}" + (f" · {_texto_tendencia(tendencia)}" if texto_tendencia else "")
        else:
            texto_cambio = "Sin ejercicio previo comparable"

        if metrica == "total_debt_ratio":
            pasivo_capital = _valor_razon(razones, "debt_equity_ratio", anio_metrica) if anio_metrica is not None else float("nan")
            if pd.notna(pasivo_capital):
                descripcion = f"{descripcion} · {_formato_razon('debt_equity_ratio', pasivo_capital)} Pasivo/Capital"

        if lectura is None:
            estado_html = '<span class="razones-kpi-status">Sin lectura descriptiva</span>'
            estado_pdf = "Sin lectura descriptiva"
        else:
            detalle = f"{lectura}{(' · ' + texto_tendencia) if texto_tendencia else ''}"
            color_estado = _color_razon(metrica, lectura)
            estado_html = (
                '<span class="razones-kpi-status">'
                f'<span class="razones-kpi-status-dot" style="background:{color_estado}"></span>'
                f'{escape(detalle)}</span>'
            )
            estado_pdf = f'<font color="{color_estado}">&#8226;</font> {escape(detalle)}'

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
    anio_ultimo = next(
        (
            anio
            for anio in reversed(anios)
            if any(pd.notna(_valor_razon(razones, metrica, anio)) for metrica in razones.index)
        ),
        anios[-1],
    )
    columnas = ["Razón", *(str(anio) for anio in anios), f"Lectura {anio_ultimo}"]
    html = [
        """
        <style>
        .razones-tabla-wrap{width:100%;overflow-x:auto}
        .razones-tabla{width:100%;min-width:760px;border-collapse:collapse;font-size:.86rem;
            font-variant-numeric:tabular-nums}
        .razones-tabla th,.razones-tabla td{padding:.52rem .6rem;border-bottom:1px solid rgba(128,128,128,.28)}
        .razones-tabla th{background:rgba(128,128,128,.12);font-weight:600;white-space:nowrap}
        .razones-tabla tr.razon-pilar td{background:rgba(128,128,128,.09);font-weight:700;text-align:center}
        .razones-tabla th:first-child,.razones-tabla td:first-child{text-align:left}
        .razones-tabla .razon-anio,.razones-tabla .razon-valor{text-align:right;white-space:nowrap}
        .razones-tabla .razon-estado{text-align:center;white-space:nowrap}
        .razones-tabla .razon-pilar td{background:rgba(128,128,128,.09);font-weight:700}
        .razones-tabla .razon-dot{display:inline-block;width:.48rem;height:.48rem;
            border-radius:50%;margin-right:.35rem;vertical-align:middle}
        .razones-tabla .razon-badge{display:inline-block;border:1px solid;border-radius:1rem;
            padding:.12rem .58rem;font-size:.76rem;font-weight:600;
            color:#4B5563;background:#E5E7EB;border-color:#CBD5E1}
        .razones-tabla .razon-badge-dot{display:inline-block;width:.48rem;height:.48rem;
            border-radius:50%;margin-right:.35rem;vertical-align:middle}
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
        if columna.startswith("Lectura"):
            encabezado = (
                f'{escape(columna)} <span title="Lectura descriptiva del último ejercicio con información, '
                'con base en rangos generales de referencia y su variación contra el ejercicio anterior. '
                'Los rangos pueden variar según el giro de la empresa. Liquidez: suficiente 1.20x–2.50x, '
                'ajustada 1.00x–1.20x, insuficiente &lt;1.00x. Endeudamiento: bajo &lt;30%, moderado '
                '30%–55%, elevado 55%–75%, muy elevado &gt;75%.">ⓘ</span>'
            )
        else:
            encabezado = escape(columna)
        html.append(f'<th class="{clase}">{encabezado}</th>')
    html.append("</tr></thead><tbody>")

    filas_pdf = []
    filas_pilar = []
    for pilar, metricas in _RAZONES_PILARES:
        disponibles = [metrica for metrica in metricas if metrica in razones.index]
        if not disponibles:
            continue
        html.append(f'<tr class="razon-pilar"><td colspan="{len(columnas)}">{escape(pilar)}</td></tr>')
        filas_pilar.append(len(filas_pdf))
        filas_pdf.append({
            "Razón": f"<b>{escape(pilar)}</b>",
            **{str(anio): "" for anio in anios},
            f"Lectura {anio_ultimo}": "",
        })
        for metrica in disponibles:
            tooltip = escape(f"{_RAZONES_DESCRIPCION[metrica]} {criterios_razon(metrica)}")
            fila_html = [f'<tr><td title="{tooltip}">{escape(_RAZONES_MATRIZ_LABELS[metrica])}</td>']
            fila_pdf = {"Razón": _RAZONES_MATRIZ_LABELS[metrica]}
            for anio in anios:
                valor = _valor_razon(razones, metrica, anio)
                if pd.isna(valor):
                    texto = "s/i"
                    fila_html.append(
                        '<td class="razon-valor" '
                        'title="Sin información disponible para este ejercicio">s/i</td>'
                    )
                else:
                    texto = _formato_razon(metrica, valor)
                    anio_metrica = anio
                    lectura_anio = _lectura_razon(razones, metrica, anio_metrica)
                    color_anio = _color_razon(metrica, lectura_anio)
                    fila_html.append(
                        f'<td class="razon-valor" title="{tooltip}">'
                        f'<span class="razon-dot" style="background:{color_anio}"></span>{escape(texto)}</td>'
                    )
                if pd.isna(valor):
                    fila_pdf[str(anio)] = "s/i"
                else:
                    fila_pdf[str(anio)] = (
                        f'<font color="{_color_razon(metrica, lectura_anio)}">&#8226;</font> {escape(texto)}'
                    )

            anio_metrica = _ultimo_ejercicio_con_informacion(razones, metrica)
            lectura = _lectura_razon(razones, metrica, anio_metrica) if anio_metrica is not None else None
            previo, tendencia = _tendencia_razon(razones, metrica, anio_metrica) if anio_metrica is not None else (None, None)
            texto_tendencia = _texto_tendencia(tendencia)
            if metrica in ("gross_profit_margin", "total_asset_turnover") and lectura is None:
                detalle = texto_tendencia
            else:
                detalle = lectura or ""
                if texto_tendencia:
                    detalle = f"{detalle} · {texto_tendencia}" if detalle else texto_tendencia

            if metrica == "gross_profit_margin" and lectura == "Atípico":
                detalle = (
                    '<span title="Un margen bruto cercano al 100% indica que casi no se reportó costo de ventas '
                    'frente a los ingresos. Es común en empresas de servicios o cuando el costo se registra como '
                    'gasto de operación, por lo que este margen no es comparable con años donde sí se reporta costo '
                    'de ventas.">Atípico ⓘ</span>'
                )
                if texto_tendencia:
                    detalle = f"{detalle} · {texto_tendencia}"

            if not detalle:
                fila_html.append('<td class="razon-estado">s/i</td>')
                fila_pdf[f"Lectura {anio_ultimo}"] = "s/i"
            else:
                color_lectura = _color_razon(metrica, lectura)
                fila_html.append(
                    f'<td class="razon-estado"><span class="razon-badge">'
                    f'<span class="razon-badge-dot" style="background:{color_lectura}"></span>'
                    f'{detalle}</span></td>'
                )
                texto_pdf = (
                    detalle.replace('<span title="', "")
                    .replace("</span>", "")
                    .replace("ⓘ", "")
                )
                fila_pdf[f"Lectura {anio_ultimo}"] = (
                    f'<font color="{color_lectura}">&#8226;</font> {escape(texto_pdf.strip())}'
                )
            fila_html.append("</tr>")
            html.extend(fila_html)
            filas_pdf.append(fila_pdf)

    html.append("</tbody></table></div>")
    df_pdf = pd.DataFrame(filas_pdf, columns=columnas)
    df_pdf.attrs["span_rows"] = filas_pilar
    return "".join(html), df_pdf


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
    fig.update_traces(line_width=2.5, marker_size=7, textposition="top right", textfont_size=9)
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
        title=None,
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
                "font": {"size": 16}, "title": None},
        height=350,
        margin={"l": 48, "r": 8, "t": 48, "b": 92},
        font={"color": "#64748B", "size": 14},
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
            lectura = _lectura_razon(razones, metrica, anio)
            if pd.notna(valor) and lectura != "Atípico":
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
        title=None,
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
                "font": {"size": 16}, "title": None},
        height=350,
        margin={"l": 48, "r": 8, "t": 48, "b": 95},
        font={"color": "#64748B", "size": 14},
        hovermode="x unified",
    )
    return fig
