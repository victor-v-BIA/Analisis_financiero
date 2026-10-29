# Constructores de gráficos Plotly (devuelven objetos go.Figure)
'''
Agrupa todas las funciones que construyen objetos
de Plotly (go.Figure o px) y renderizan tablas HTML personalizadas.
'''
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd
import html
import plotly.express as px
from config import (COLOR,COLOR_DIF_CERO,COLOR_DIF_POSITIVA,COLOR_DIF_NEGATIVA,
                    METRICAS_VISUALIZAR,MESES_ES,
                    COLOR_VELA_SUBE,COLOR_VELA_BAJA,
                    COLOR_LINEA_PROMEDIO,ANCHOS_SIN_FACTURACION,CSS_SIN_FACTURACION,
                    ANCHOS_DETALLE_ANUAL,CSS_DETALLE_ANUAL, PALETA_BUMP,PALETA_BUMP_INGRESOS, PALETA_ING,
                    SEPARADOR_PIE,TEXTO_SOBRE_ING,NOMBRE_NOMINA,COLOR_GASTOS,COLOR_NOMINA,
                    NOMBRE_EGR_PUE,NOMBRE_EGR_PPD,COLOR_EGR_PUE,COLOR_EGR_PPD)

from utils import (_mxn_2d, _importe_abreviado_2d,_abrev_monto, _nombre_abreviado, _abrev_signo, _formatear_mxn )

from core.finance_logic import (_dictamen_indice, _normalizar_por_rfc, _serie_mensual_por_anio, _ranking_anual)

def _layout_plotly(fig: go.Figure, y_titulo: str = "MXN", altura: int = 320) -> go.Figure:
    """Margenes reducidos, fondo transparente (hereda el del tema) y altura consistente (320 por defecto,
    igual que las gráficas Altair; `altura` permite overridearla para gráficas específicas, p. ej. la dona de
    Concentración de Ingresos, sin afectar el resto de las gráficas que comparten este helper)."""
    fig.update_layout(margin=dict(l=90, r=10, t=30, b=10), height=altura, legend_title_text=None,
                      xaxis_title=None, yaxis_title=y_titulo, plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified")
    return fig


def _layout_eco(fig: go.Figure, anios_str: list[str], titulo_y: str) -> go.Figure:
    fig = _layout_plotly(fig, y_titulo=titulo_y, altura=330)
    fig.update_layout(margin=dict(l=90, r=10, t=40, b=40), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=anios_str, showgrid=False)
    return fig


def render_notas_reporte(key: str) -> None:
    """Renderiza el campo de notas ejecutivas asociado a una gráfica."""
    


def render_grafica(
    fig: go.Figure,
    key: str,
    incluir_notas: bool = True,
    width: str = "stretch",
) -> None:
    """Renderiza una gráfica Plotly interactiva y, opcionalmente, sus notas ejecutivas."""
    fig.update_layout(autosize=True)
    st.plotly_chart(fig, width=width, key=f"plot_{key}")
    if incluir_notas:
        render_notas_reporte(key)


def _grafica_plazos_comparativa(ing: pd.DataFrame, egr: pd.DataFrame, anual: bool) -> go.Figure:
    """UNA sola gráfica con Cobros (Clientes, verde) y Pagos (Proveedores, naranja/rojo) en el mismo eje, para ver la brecha entre
    ambos plazos. SIEMPRE líneas con marcadores (`go.Scatter`) para que se lea la tendencia: `anual=True` por Año (eje categórico,
    `mode='lines+markers+text'` con el valor a 1 decimal sobre cada punto) y `anual=False` por Año-Mes sobre una línea de tiempo
    continua (`mode='lines+markers'`, sin texto: los valores solo en el hover). Un periodo sin promedio en una serie queda como hueco (nunca 0). El hover muestra ambos
    promedios, la diferencia (Cobro − Pago, sin redondear previo), la mediana de cada serie y las aplicaciones válidas.
    Eje Y: «Días promedio/mediana»."""
    freq = "Y" if anual else "M"
    claves = sorted(set(ing.index) | set(egr.index))
    periodos = [str(p) for p in pd.period_range(claves[0], claves[-1], freq=freq)]
    ing, egr = ing.reindex(periodos), egr.reindex(periodos)
    v = lambda x: None if pd.isna(x) else float(x)
    y_c, y_p = [v(x) for x in ing["dias_promedio"]], [v(x) for x in egr["dias_promedio"]]
    dias = lambda x: f"{x:.1f} días" if x is not None else "Sin datos"
    custom = [[dias(c), dias(p), f"{c - p:+.1f} días" if c is not None and p is not None else "Sin datos",
               dias(v(mc)), dias(v(mp)), 0 if pd.isna(nc) else int(nc), 0 if pd.isna(np_) else int(np_)]
              for c, p, mc, mp, nc, np_ in zip(y_c, y_p, ing["dias_mediana"], egr["dias_mediana"], ing["n_validos"], egr["n_validos"])]
    plantilla = ("<b>%{x}</b><br>Días de cobro: %{customdata[0]} (mediana %{customdata[3]})"
                 "<br>Días de pago: %{customdata[1]} (mediana %{customdata[4]})"
                 "<br>Diferencia (Cobro − Pago): %{customdata[2]}"
                 "<br>Aplicaciones válidas — cobro: %{customdata[5]} · pago: %{customdata[6]}<extra></extra>")
    fig = go.Figure()
    for nombre, ys, color in (("Días de cobro", y_c, COLOR["Cobrado"]), ("Días de pago", y_p, "#E45756")):
        
        # Asignamos la posición del texto de forma dinámica si es anual para evitar que se encimen
        if anual:
            posicion_texto = "bottom right" if nombre == "Días de cobro" else "top right"
        else:
            posicion_texto = "bottom left"

        # Histórico anual: valor exacto (1 decimal) arriba/abajo de cada punto; Detalle mensual: sin texto (valores solo en el hover)
        fig.add_trace(go.Scatter(x=periodos, y=ys, name=nombre, mode="lines+markers+text" if anual else "lines+markers",
                                 connectgaps=True, line=dict(color=color, width=2.5, shape="spline", smoothing=0.3), marker=dict(size=8, color=color),
                                 text=[f"{x:.1f}" if x is not None else "" for x in ys] if anual else None,
                                 textposition=posicion_texto, textfont_size=11, cliponaxis=False,
                                 customdata=custom, hovertemplate=plantilla))
    
    if anual:
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=periodos, showgrid=False)
        
    else:
        # Tratamos el eje X como categoría para enlistar ordenadamente los meses de inicio a fin
        fig.update_xaxes(
            type="category", 
            categoryorder="array", 
            categoryarray=periodos, 
            showgrid=False,
            tickangle=-90,
            tickvals=[p for p in periodos if p.endswith(("-01","-06","-12"))], 
            ticktext=[p for p in periodos if p.endswith(("-01","-06","-12"))]
        )
        
    fig.update_yaxes(rangemode="tozero", showgrid=True, gridcolor="rgba(128,128,128,0.18)")
    fig = _layout_plotly(fig, y_titulo="Días promedio/mediana", altura=340)
    fig.update_layout(margin=dict(t=30, b=55, l=90, r=30), font=dict(size=12), hovermode="closest",
                      legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0))
    return fig


def _grafica_diferencia_cobros_pagos(periodos, cobros, pagos, diferencia, nombre_cobros: str = "Cobros",
                                     nombre_pagos: str = "Pagos considerados") -> go.Figure:
    """UNA barra por periodo con la diferencia Cobros − Pagos considerados (Pagos = proveedores + nómina). Verde si es
    positiva, rojo si es negativa y gris si es cero (a dos decimales); un periodo sin registros (NaN) no tiene barra.
    Línea de referencia en cero y etiqueta abreviada con dos decimales ("1.25 M", "325.40 mil") FUERA de la barra, con
    holgura en el eje para valores positivos y negativos. Tooltip: Periodo, Cobros, Pagos considerados y Diferencia,
    con el importe completo en MXN."""
    dif = [float("nan") if d is None or pd.isna(d) else float(d) for d in diferencia]   # exactas: su suma = el año
    colores = [COLOR_DIF_CERO if (not pd.isna(d) and round(d, 2) == 0) else COLOR_DIF_POSITIVA if (not pd.isna(d) and d > 0)
               else COLOR_DIF_NEGATIVA for d in dif]
    custom = [[str(p), _mxn_2d(c), _mxn_2d(pg), _mxn_2d(d)] for p, c, pg, d in zip(periodos, cobros, pagos, dif)]
    fig = go.Figure(go.Bar(
        x=list(periodos), y=dif, marker_color=colores, name="Diferencia entre cobros y pagos",
        text=[_importe_abreviado_2d(d) for d in dif], textposition="outside", textangle=0, textfont_size=11,
        cliponaxis=False, customdata=custom,
        hovertemplate=(f"Periodo: %{{customdata[0]}}<br>{nombre_cobros}: %{{customdata[1]}}<br>{nombre_pagos}: "
                       "%{customdata[2]}<br>Diferencia: %{customdata[3]}<extra></extra>")))
    fig.add_hline(y=0, line_width=1.5, line_color="#555555")
    validos = [d for d in dif if not pd.isna(d)]
    if validos:   # holgura para que la etiqueta (sobre la barra positiva o bajo la negativa) nunca quede recortada
        alto, bajo = max(0.0, max(validos)), min(0.0, min(validos))
        tramo = (alto - bajo) or 1.0
        fig.update_yaxes(range=[bajo - tramo * (0.16 if bajo < 0 else 0.04), alto + tramo * (0.16 if alto > 0 else 0.04)])
    fig.update_layout(showlegend=False, xaxis=dict(type="category", categoryorder="array",
                                                    categoryarray=list(periodos)))
    y_titulo = "Flujo Fiscal (MXN)"
    fig = _layout_plotly(fig, y_titulo=y_titulo)
    fig.update_layout(margin=dict(t=40, b=40, l=90, r=30), font=dict(size=12), hovermode="closest",
                      uniformtext_minsize=9, uniformtext_mode="show")
    return fig


def _grafica_ciclos_lineas(series_anio: dict, anios: list[int],
                            metricas: list[str] | None = None) -> go.Figure:
    """Flujo mensual de los años seleccionados. El color identifica el ejercicio fiscal; si se muestran ambas métricas,
    Cobros usa línea continua y Pagos discontinua. La leyenda agrupa los trazos por año y el hover identifica la métrica."""
    
    # Tu paleta fija de azules personalizada
    paleta_azules_fija = [
        "#0F2E85",  # Azul marino muy oscuro
        "#4775F7",  # Azul marino intermedio
        "#1D4ED8",  # Azul rey profundo
        "#83A3E7",  # Azul vivo principal
        "#14489C",  # Azul claro brillante pero sólido
        "#8EA9CA"   # Azul cielo
    ]
    
    metricas = METRICAS_VISUALIZAR if metricas is None else list(metricas)
    fig = go.Figure()
    anios = sorted(int(a) for a in anios)
    metricas_sel = [metrica for metrica in METRICAS_VISUALIZAR if metrica in metricas]
    estilos = {"Cobros": ("solid", "circle"), "Pagos": ("dash", "square")}
    
    for i, anio in enumerate(anios):
        # Asignamos el color de tu paleta de forma cíclica (usando el operador módulo % por si hay más años que colores)
        color = paleta_azules_fija[i % len(paleta_azules_fija)]
        
        for j, metrica in enumerate(metricas_sel):
            dash, simbolo = estilos[metrica]
            fig.add_trace(go.Scatter(
                x=MESES_ES, y=[None if pd.isna(x) else float(x) for x in series_anio[metrica][anio]],
                name=str(anio), legendgroup=str(anio), showlegend=(j == 0),
                mode="lines+markers", connectgaps=True,
                line=dict(
                    color=color, 
                    width=2, 
                    dash=dash,
                    shape="spline",     # Transforma las líneas rectas en curvas suaves
                    smoothing=0.5      # Nivel de suavizado (valores entre 0.0 y 1.3, por defecto es 0.5)
                ),
                marker=dict(size=6, color=color, symbol=simbolo),
                customdata=[anio] * len(MESES_ES),
                hovertemplate=("<b>Año: %{customdata}</b><br>Mes: %{x}<br>" + f"{metrica}: " +
                               "MXN %{y:,.2f}<extra></extra>")))
                               
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=MESES_ES, showgrid=False)
    fig.update_yaxes(tickformat=",.0f", showgrid=True, gridcolor="rgba(128,128,128,0.18)", zeroline=True, zerolinecolor="rgba(128,128,128,0.5)")
    fig = _layout_plotly(fig, y_titulo="Flujo mensual (MXN)", altura=420)
    fig.update_layout(margin=dict(t=20, b=60, l=90, r=30), font=dict(size=12), hovermode="closest",
                      legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0), showlegend=True)
    return fig



def _grafica_velas(ohlc: pd.DataFrame, nombre: str, promedio: pd.Series) -> go.Figure:
    """Combo chart por mes (Ene-Dic) de UNA serie: velas japonesas (`_ohlc_mensual`) + línea del Promedio Mensual (`go.Scatter`,
    `mode='lines'`, gris claro) con el promedio histórico de los años seleccionados (`_promedios_mensuales_historicos`).
    Vela verde si Close > Open y roja si Close < Open; la mecha va del mínimo al máximo histórico. Sin textos estáticos: el
    hover de cada vela indica en moneda el año base (Open), el año reciente (Close) y los máximo / mínimo históricos; un mes sin
    datos no dibuja vela ni punto de promedio."""
    def v(x):
        return None if pd.isna(x) else float(x)
    texto = [("Sin datos" if r.N_Anios == 0 else
              f"<b>{r.Mes}</b> · {nombre}<br>Año base (Open) {r.Anio_Open}: {_mxn_2d(r.Open)}"
              f"<br>Año reciente (Close) {r.Anio_Close}: {_mxn_2d(r.Close)}"
              f"<br>Máximo histórico: {_mxn_2d(r.High)}<br>Mínimo histórico: {_mxn_2d(r.Low)}<br>Años con datos: {r.N_Anios}")
             for r in ohlc.itertuples()]
    fig = go.Figure(go.Candlestick(
        x=list(ohlc["Mes"]), open=[v(x) for x in ohlc["Open"]], high=[v(x) for x in ohlc["High"]],
        low=[v(x) for x in ohlc["Low"]], close=[v(x) for x in ohlc["Close"]], name=nombre,
        increasing=dict(line=dict(color=COLOR_VELA_SUBE), fillcolor=COLOR_VELA_SUBE),
        decreasing=dict(line=dict(color=COLOR_VELA_BAJA), fillcolor=COLOR_VELA_BAJA),
        hovertext=texto, hoverinfo="text"))
    y_prom = [v(x) for x in promedio]
    fig.add_trace(go.Scatter(
        x=list(ohlc["Mes"]), y=y_prom, name="Promedio mensual", mode="lines", connectgaps=False,
        line=dict(color=COLOR_LINEA_PROMEDIO, width=1, dash="dot"),             # guía fina, punteada y gris: no compite con las velas
        customdata=[_mxn_2d(x) if x is not None else "Sin datos" for x in y_prom],
        hovertemplate="<b>%{x}</b> · Promedio mensual de " + nombre.lower() + ": %{customdata}<extra></extra>"))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=MESES_ES, showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(tickformat=",.0f", showgrid=True, gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    fig = _layout_plotly(fig, y_titulo=f"{nombre} (MXN)", altura=340)
    # Velas más anchas: `boxgap` es el gap que Plotly aplica a las velas (candlestick usa el layout de cajas); `bargap` se fija también
    # por si se mezclan barras, aunque no afecta a las velas.
    fig.update_layout(margin=dict(t=20, b=30, l=90, r=30), font=dict(size=12), hovermode="closest", showlegend=False,
                      bargap=0.1, boxgap=0.1)
    return fig


def _html_tabla_sin_facturacion(tabla: pd.DataFrame) -> str:
    """Tabla HTML de la sección 6 (columnas en % 30/17/13/23/17, mismas alturas de fila que `st.dataframe`: encabezado 38 px y filas de 35 px; sin desplazamiento
    horizontal ni letra reducida). RFC, fecha e importes siempre completos (importes como $2,400,000.00, total incluido; el '$' va como entidad porque dos '$' en un
    mismo Markdown se leerían como fórmula); un nombre largo se abrevia con puntos suspensivos y su nombre completo aparece al pasar el cursor. En UNA sola línea de HTML."""
    cols = list(tabla.columns)
    completos = tabla.attrs.get("nombres_completos") or [str(c) for c in tabla["Cliente"]]
    p = cols[3].split()[1]
    esc = lambda s: html.escape(str(s), quote=True)
    colgroup = "<colgroup>" + "".join(f'<col style="width:{w}%">' for w in ANCHOS_SIN_FACTURACION) + "</colgroup>"
    ayudas = {cols[4]: f"Participación en las ventas de {p}: % sobre la facturación TOTAL de {p}, no sobre el total de esta lista."}
    encabezado = "<thead><tr>" + "".join(
        f'<th class="sf-num" title="{esc(ayudas[c])}">{esc(c)}</th>' if c in ayudas else f'<th class="sf-num">{esc(c)}</th>' if i >= 3 else f"<th>{esc(c)}</th>"
        for i, c in enumerate(cols)) + "</tr></thead>"
    filas = []
    for i, r in enumerate(tabla.itertuples(index=False)):
        clase = ' class="sf-total"' if i == len(tabla) - 1 else ""
        filas.append(f'<tr{clase}><td class="sf-nombre" title="{esc(completos[i])}">{esc(r[0])}</td><td>{esc(r[1])}</td><td>{esc(r[2])}</td>'
                     f'<td class="sf-num">&#36;{float(r[3]):,.2f}</td><td class="sf-num">{float(r[4]):.1f}%</td></tr>')
    altura = min(38 + 35 * len(tabla), 460)
    return (f'{CSS_SIN_FACTURACION}<div class="sf-wrap" style="max-height:{altura}px"><table class="sf-tabla">{colgroup}{encabezado}'
            f"<tbody>{''.join(filas)}</tbody></table></div>")


def _html_detalle_anual(tabla: pd.DataFrame) -> str:
    """Tabla HTML del detalle anual (importes completos con miles y dos decimales, sin 'MXN' en cada celda). En
    UNA sola línea de HTML: un renglón vacío o una sangría de 4 espacios haría que Markdown lo trate como texto."""
    colgroup = "<colgroup>" + "".join(f'<col style="width:{w}%">' for w in ANCHOS_DETALLE_ANUAL) + "</colgroup>"
    encabezado = "<thead><tr>" + "".join(
        f'<th class="ppd-anio">{c}</th>' if i == 0 else f"<th>{c}</th>" for i, c in enumerate(tabla.columns)) + "</tr></thead>"
    filas = "".join(
        f'<tr><td class="ppd-anio">{int(r.iloc[0])}</td>' + "".join(
            f"<td>{_formatear_mxn(v).replace('$', '&#36;')}</td>" for v in r.iloc[1:]) + "</tr>"
        for _, r in tabla.iterrows())
    return (f'{CSS_DETALLE_ANUAL}<div class="ppd-detalle-wrap"><table class="ppd-detalle">{colgroup}{encabezado}'
            f"<tbody>{filas}</tbody></table></div>")


def _grafica_diferencia_anual(anual: pd.DataFrame, nombre_serie: str) -> go.Figure:
    """Una barra por año con la diferencia documental (Complementos − Facturación PPD; negativa = rezago).
    Etiqueta: importe abreviado y porcentaje sobre la facturación del año ('N/D' si ese total es 0). El hover trae
    año, facturación PPD, complementos, diferencia y porcentaje."""
    pct_txt = [f"{p:.1f}%" if p is not None and not pd.isna(p) else "N/D" for p in anual["Porcentaje"]]
    etiquetas = [f"{_abrev_monto(d)} · {p}" for d, p in zip(anual["Diferencia"], pct_txt)]
    custom = [[f"{f:,.2f}", f"{c:,.2f}", f"{d:,.2f}", p] for f, c, d, p in zip(
        anual["Facturación PPD"], anual["Complementos"], anual["Diferencia"], pct_txt)]
    colores = [COLOR_DIF_CERO if round(float(d), 2) == 0 else COLOR["PPD"] if d > 0 else COLOR_DIF_NEGATIVA
               for d in anual["Diferencia"]]      # > 0 naranja institucional · < 0 rojo de alerta · 0 gris
    fig = go.Figure(go.Bar(
        x=[str(a) for a in anual["Año"]], y=anual["Diferencia"], marker_color=colores, name=nombre_serie,
        text=etiquetas, textposition="outside", textfont_size=11, cliponaxis=False, customdata=custom,
        hovertemplate=("<b>Año %{x}</b><br>Facturación PPD: MXN %{customdata[0]}<br>Complementos: MXN %{customdata[1]}"
                       "<br>Diferencia: MXN %{customdata[2]}<br>Porcentaje: %{customdata[3]}<extra></extra>")))
    fig.update_layout(xaxis=dict(type="category", title="Año"), showlegend=False)
    fig = _layout_plotly(fig, y_titulo="Monto (MXN)", altura=360)
    fig.update_layout(margin=dict(t=30, b=30, l=90, r=30), font=dict(size=12), hovermode="closest")
    return fig


def _grafica_gauge_score(indice: float, color: str) -> go.Figure:
    """Velocímetro del índice (0–100) con franjas por dictamen: menos de 50 Débil, 50 a 70 Moderado, 70 a 85 Adecuado, 85 o más Sólido."""
    franjas = [(0, 50, "rgba(239,68,68,0.28)"), (50, 70, "rgba(245,158,11,0.28)"), (70, 85, "rgba(56,189,248,0.28)"), (85, 100, "rgba(16,185,129,0.28)")]
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(indice, 1), number=dict(suffix=" / 100", font=dict(size=34)),
        title=dict(text="Índice de desempeño documental", font=dict(size=14)),
        gauge=dict(axis=dict(range=[0, 100], tickvals=[0, 50, 70, 85, 100]), bar=dict(color=color, thickness=0.28),
                   steps=[dict(range=[a, b], color=c) for a, b, c in franjas],
                   threshold=dict(line=dict(color="#F8FAFC", width=3), thickness=0.8, value=round(indice, 1)))))
    fig.update_layout(height=270, margin=dict(l=45, r=25, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _grafica_pilares_score(pilares: list[dict]) -> go.Figure:
    """Barras horizontales (`orientation='h'`) con el puntaje de cada pilar (0–100). 'No aplica' y 'Datos insuficientes' se rotulan como tales (barra vacía, nunca un cero
    disfrazado); el tooltip trae el indicador real y la regla exacta de puntos."""
    nombres = [p["nombre"] for p in pilares]
    valores = [p["s"] if p["estado"] == "ok" else 0 for p in pilares]
    colores = [(_dictamen_indice(p["s"])[1] if p["estado"] == "ok" else "#9AA0A6") for p in pilares]
    textos = [(f"{p['s']:.0f}/100 · {p['pts']:.1f}/{p['peso']} pts" if p["estado"] == "ok" else "No aplica" if p["estado"] == "no_aplica" else "Datos insuficientes")
              for p in pilares]
    fig = go.Figure(go.Bar(
        y=nombres, x=valores, orientation="h", marker_color=colores, text=textos, textposition="outside", cliponaxis=False,
        customdata=[[p["real"], p["regla"], p["peso"]] for p in pilares],
        hovertemplate="<b>%{y}</b> (peso %{customdata[2]} pts)<br>%{customdata[0]}<br><i>Regla:</i> %{customdata[1]}<extra></extra>"))
    fig = _layout_plotly(fig, y_titulo="", altura=300)
    fig.update_layout(margin=dict(l=90, r=10, t=30, b=10), hovermode="closest", showlegend=False, xaxis_title="Puntaje del pilar (0–100)")
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=nombres, autorange="reversed")
    fig.update_xaxes(range=[0, 150])
    return fig


def _insight_html(texto: str, clase: str = "") -> None:
    st.markdown(f"<div class='eco-insight {clase}'>{texto}</div>", unsafe_allow_html=True)


def _grafica_ingresos_gastos(anios_str: list[str], ing: list, gas: list) -> go.Figure:
    fig = go.Figure()
    for nombre, vals, color in (("Ingresos (MDP)", ing, "#2563EB"), ("Gastos (MDP)", gas, "#DC2626")):
        fig.add_trace(go.Bar(x=anios_str, y=vals, name=nombre, marker_color=color, texttemplate="%{y:,.1f}", textposition="outside",
                             cliponaxis=False, customdata=[[_mxn_2d(v * 1e6)] for v in vals],
                             hovertemplate=f"<b>%{{x}}</b><br>{nombre}: %{{customdata[0]}}<extra></extra>"))
    fig.update_layout(barmode="group")
    fig = _layout_eco(fig, anios_str, "Millones MXN")
    fig.update_yaxes(range=[0, (max(ing + gas + [0.0]) * 1.2) or 1])
    return fig


def _fig_bump_top10(df: pd.DataFrame, monto_calc: str) -> go.Figure:
    """Bump Chart de los 10 mayores clientes del periodo: eje X = Año, eje Y = Rango 1-10 por año (`autorange='reversed'`: el 1 arriba) según la
    suma de `monto_calc` ('Subtotal' o 'Total'); una línea `spline` con marcadores por cliente y su monto como texto junto al marcador. Los
    clientes se unifican por RFC (`_normalizar_por_rfc`: una sola `Razon_Social_Limpia` por RFC) ANTES de agrupar por Año, para que un cliente
    con varias variantes de Razón Social sea UNA sola línea continua. El Top 10 es el histórico (suma de todos los años del df) y el rango se
    calcula entre esos 10; un año sin facturación del cliente queda como hueco."""
    d = _normalizar_por_rfc(df)
    top10 = d.groupby("Razon_Social_Limpia")[monto_calc].sum().sort_values(ascending=False).head(10).index.tolist()
    g = d[d["Razon_Social_Limpia"].isin(top10)].groupby(["Razon_Social_Limpia", "Año"], as_index=False)[monto_calc].sum()
    g = g[g[monto_calc] > 0]
    g["Rango"] = g.groupby("Año")[monto_calc].rank(method="first", ascending=False).astype(int)             # ranking 1-10 por año
    anios = [str(a) for a in sorted(g["Año"].unique())]
    fig = go.Figure()
    for color, razon in zip(PALETA_BUMP, top10):
        dd = g[g["Razon_Social_Limpia"] == razon].sort_values("Año")
        if dd.empty:
            continue
        fig.add_trace(go.Scatter(
            x=[str(a) for a in dd["Año"]], y=dd["Rango"], name=_nombre_abreviado(razon), mode="lines+markers+text", line_shape="spline",
            line=dict(color=color, width=3), marker=dict(size=10, color=color), text=[_abrev_signo(v) for v in dd[monto_calc]],
            textposition="top center", textfont=dict(size=10, color=color),
            customdata=[[razon, int(r), _mxn_2d(v)] for r, v in zip(dd["Rango"], dd[monto_calc])],
            hovertemplate="<b>%{customdata[0]}</b><br>Año: %{x}<br>Rango: %{customdata[1]}<br>" + monto_calc + ": %{customdata[2]}<extra></extra>"))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=anios, showgrid=False, zeroline=False)
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=list(range(1, 11)), showgrid=False, zeroline=False, title_text="Rango")
    fig.update_layout(height=460, margin=dict(l=90, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hovermode="closest", legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.01), legend_title_text=None)
    return fig




def _fig_lineas_por_anio(tabla: pd.DataFrame, rotulo: str) -> go.Figure:
    """Líneas comparativas mensuales por Año (`tabla` = 12 filas Mes x una columna por Año, monto NETO sin acumular): un `go.Scatter` por año
    (`lines+markers`, marcadores circulares), eje X = Ene-Dic, eje Y en millones (`$20M`), sin cuadrícula vertical, guías horizontales tenues y
    leyenda horizontal inferior. `rotulo` = texto del monto en el hover y en el título del eje Y."""
    fig = go.Figure()
    for i, anio in enumerate(tabla.columns):
        color = PALETA_BUMP_INGRESOS[i % len(PALETA_BUMP_INGRESOS)]
        y = [None if pd.isna(v) else float(v) for v in tabla[anio]]
        fig.add_trace(go.Scatter(
            x=MESES_ES, y=y, name=str(int(anio)), mode="lines+markers", connectgaps=True, line=dict(color=color, width=2,shape="spline",    
                    smoothing=0.5    
                ),
            marker=dict(symbol="circle", size=7, color=color), customdata=[[str(int(anio)), _mxn_2d(v) if v is not None else "Sin movimientos"] for v in y],
            hovertemplate="<b>Año %{customdata[0]}</b><br>Mes: %{x}<br>" + rotulo + ": %{customdata[1]}<extra></extra>"))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=MESES_ES, showgrid=False, zeroline=False, title_text=None, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)", zeroline=False, tickformat="$.2s", title_text=f"{rotulo} (MXN)")
    fig.update_layout(height=480, margin=dict(l=75, r=25, t=30, b=115), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hovermode="closest", legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0), legend_title_text=None)
    return fig


def _fig_ingresos_facturados(
    d: pd.DataFrame,
    col_monto: str,
    nomina_mensual: pd.Series | None = None,
) -> go.Figure:
    """Una línea por Año con facturación mensual y, cuando existe, nómina mensual sumada."""
    mensual = _serie_mensual_por_anio(d, col_monto)
    if nomina_mensual is not None:
        nomina = pd.DataFrame({
            "Mes": nomina_mensual.index.month,
            "Año": nomina_mensual.index.year,
            "Monto": nomina_mensual.to_numpy(),
        })
        nomina = nomina.pivot_table(index="Mes", columns="Año", values="Monto", aggfunc="sum")
        mensual = mensual.add(nomina, fill_value=0.0).reindex(range(1, 13))
    return _fig_lineas_por_anio(mensual, col_monto)



def _fig_pie_metodo_cobro(r: dict, realizado: str = "cobrado", paleta: dict | None = None) -> go.Figure:
    """Pie (`go.Pie`, hole=0.5, leyenda nativa oculta) de PUE, PPD cobrado (Egresos: pagado) y PPD pendiente sobre el mismo DataFrame del desglose. Solo
    se dibujan los sectores positivos: si la diferencia (PPD pendiente) es negativa porque los complementos superan la facturación PPD, el pastel
    completa la facturación con PUE + PPD y la diferencia se muestra fuera del gráfico (tabla lateral), con su importe sin alterar."""
    paleta = PALETA_ING if paleta is None else paleta
    cobrado, pendiente = r["cobrado"], r["pendiente"]
    if pendiente < 0:                                       # complementos > facturación PPD: el sector cobrado llega solo hasta el PPD facturado
        cobrado, pendiente = r["ppd"], 0.0
        
    filas = [("PUE", r["pue"], paleta["pue"]),
             (f"PPD {realizado}", cobrado, paleta["ppd"]),
             ("PPD pendiente", pendiente, paleta["pendiente"])]
    sectores = [(n, v, c) for n, v, c in filas if v > 0.005]
    nombres, valores, colores = ([s[i] for s in sectores] for i in range(3))
    
    # Determinamos dinámicamente el índice del valor más alto para ponerle texto blanco y a los demás negro
    if valores:
        max_idx = valores.index(max(valores))
        colores_texto = ["white" if i == max_idx else "black" for i in range(len(valores))]
    else:
        colores_texto = []

    fig = go.Figure(go.Pie(
        labels=nombres, 
        values=valores, 
        hole=0.5, 
        sort=False, 
        direction="clockwise", 
        textinfo="percent", 
        textposition="inside",
        marker=dict(colors=colores, line=dict(width=0, color='rgba(0,0,0,0)')),
        
        # Asignamos la lista de colores dinámica (blanco solo para el sector mayor, negro para el resto)
        textfont=dict(
            color=colores_texto,
            size=18
        ),
        customdata=[_mxn_2d(v) for v in valores],
        hovertemplate="<b>%{label}</b><br>Monto: %{customdata}<br>Participación: %{percent}<extra></extra>"
    ))
    fig.update_layout(
        height=320, 
        showlegend=False, 
        margin=dict(l=90, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig
    
    fig.update_layout(
        height=360, 
        showlegend=False, 
        margin=dict(l=90, r=10, t=30, b=10), 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def _html_resumen_metodo_cobro(
    r: dict,
    col_monto: str,
    lado: str = "ingresos",
    paleta: dict | None = None,
    rotular_base: bool = True,
    incluir_detalle_ppd: bool = True,
    formato_pdf: bool = False,
) -> str:
    """Tabla lateral (HTML): Monto total en la cabecera y debajo PUE, PPD Total (con sus dos viñetas, pendiente y cobrado), cada uno con monto y %
    sobre el total. Montos como 'MXN 1,234.00' (sin '$', que Streamlit podría interpretar como fórmula). `formato_pdf` genera etiquetas ReportLab;
    `incluir_detalle_ppd=False` omite el desglose de pagos cuando no se dispone de esa información."""
    tot = r["total"]
    paleta = PALETA_ING if paleta is None else paleta
    inmediato, plazo, realizado = (("Facturado PUE", "Facturado PPD", "PPD cobrado") if lado == "ingresos"
                                   else ("Pagos inmediatos (PUE)", "Pagos a plazos (PPD)", "PPD pagado"))
    pct = lambda v: f"{v / tot * 100:.1f}%" if tot else "n/a"
    if formato_pdf:
        fila_pdf = lambda color, nombre, v: (
            f'<font color="{color}">●</font> <b>{nombre}</b><br/>'
            f'<font color="#4B5563">{_mxn_2d(v)} · {pct(v)}</font>')
        filas = [
            f'<font size="8" color="#6B7280">Monto total</font><br/>'
            f'<b><font size="13" color="#1F2937">{_mxn_2d(tot)}</font></b>',
            fila_pdf(paleta["pue"], inmediato, r["pue"]),
            fila_pdf(paleta["ppd"], plazo, r["ppd"]),
        ]
        if incluir_detalle_ppd:
            filas.extend([
                fila_pdf(paleta["pendiente"], "PPD pendiente", r["pendiente"]),
                fila_pdf(paleta["ppd"], realizado, r["cobrado"]),
            ])
        return "<br/><br/>".join(filas)

    fila = lambda color, nombre, v, sangria=0, fuerte=True: (
        f'<div style="margin-left:{sangria}px;margin-top:8px;"><span style="color:{color}">●</span> '
        f'{"<b>" if fuerte else ""}{nombre}{"</b>" if fuerte else ""}<br>'
        f'<span style="margin-left:18px">{_mxn_2d(v)} · {pct(v)}</span></div>')
    return (f'<div style="padding:6px 4px"><div style="opacity:.75">Monto total{f" ({col_monto})" if rotular_base else ""}</div>'
            f'<div style="font-size:1.6rem;font-weight:700">{_mxn_2d(tot)}</div>'
            + fila(paleta["pue"], inmediato, r["pue"])
            + fila(paleta["ppd"], plazo, r["ppd"])
            + (fila(paleta["pendiente"], "PPD pendiente", r["pendiente"], sangria=28, fuerte=False)
               + fila(paleta["ppd"], realizado, r["cobrado"], sangria=28, fuerte=False)
               if incluir_detalle_ppd else "")
            + (f'<div style="margin-top:10px;opacity:.8;font-size:.85rem">Los Complementos de Pago Emitidos superan la facturación PPD: la diferencia '
               f'({_mxn_2d(r["pendiente"])}) se muestra fuera del gráfico.</div>' if r["pendiente"] < -0.005 else "") + "</div>")


def _fig_bump_anual(df: pd.DataFrame, col_monto: str) -> go.Figure:
    """Bump Chart «Top 10 clientes / proveedores de cada año» (Ingresos y Egresos): el ranking se calcula con TODOS los proveedores de cada año (`_ranking_anual`) y recién después se toma
    el Top 10 de ese año; se muestra la UNIÓN de los proveedores que aparecen en algún Top 10 anual, siempre con su posición real. En los años en que un
    proveedor queda fuera del Top 10 su línea se interrumpe (no se renumera ni se unen puntos a través de años omitidos). Tooltip: razón social completa, RFC,
    año, posición, Total en MXN y participación sobre toda la facturación recibida del año. El nombre abreviado es solo la etiqueta de la leyenda; leyenda y tooltip se muestran en MAYÚSCULAS (solo presentación).
    La leyenda puede traer más de 10 empresas: cada año tiene su propio Top 10."""
    r = _ranking_anual(df, col_monto)
    anios = [str(a) for a in sorted(r["Año"].unique())]
    top = r[r["En_Top"]]
    orden = top.groupby("Entidad")["Monto"].sum().sort_values(ascending=False).index.tolist()           # leyenda: mayor volumen en el Top primero
    paleta = PALETA_BUMP + px.colors.qualitative.Light24
    fig = go.Figure()
    for i, ent in enumerate(orden):
        color = paleta[i % len(paleta)]
        por_anio = top[top["Entidad"] == ent].set_index("Año")
        razon, rfc = str(por_anio["Razon_Social_Limpia"].iloc[0]).upper(), por_anio["RFC"].iloc[0]                 # presentación en MAYÚSCULAS (los datos no cambian)
        ys, textos, custom = [], [], []
        for a in anios:
            fila = por_anio.loc[int(a)] if int(a) in por_anio.index else None
            ys.append(None if fila is None else int(fila["Rango"]))                                    # fuera del Top 10 del año: hueco
            textos.append("" if fila is None else _abrev_signo(fila["Monto"]))
            custom.append([razon, rfc, a, "" if fila is None else int(fila["Rango"]), "" if fila is None else _mxn_2d(fila["Monto"]),
                           "" if fila is None else f"{fila['Participacion'] * 100:.1f}%"])
        fig.add_trace(go.Scatter(
            x=anios, y=ys, name=str(_nombre_abreviado(razon)).upper(), mode="lines+markers+text", line_shape="spline", connectgaps=False,
            line=dict(color=color, width=3), marker=dict(size=10, color=color), text=textos, textposition="top center", textfont=dict(size=10, color=color),
            customdata=custom,
            hovertemplate=("<b>%{customdata[0]}</b><br>RFC: %{customdata[1]}<br>Año: %{customdata[2]}<br>Posición: %{customdata[3]}"
                           "<br>Total: %{customdata[4]}<br>Participación del año: %{customdata[5]}<extra></extra>")))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=anios, showgrid=False, zeroline=False)
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=list(range(1, 11)), showgrid=False, zeroline=False, title_text="Rango")
    fig.update_layout(height=480, margin=dict(l=60, r=40, t=30, b=90),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hovermode="closest", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5), legend_title_text=None)
    return fig



def _fig_pie_nomina_gastos(r: dict, gastos_label: str = "Gastos") -> go.Figure:
    """Pie de la composición acumulada de gastos y nómina, con leyenda nativa oculta."""
    valores = [r["gastos"], r["nomina"]]
    labels = [gastos_label, NOMBRE_NOMINA]
    
    # Determinamos de forma dinámica cuál valor es el mayor para ponerle texto blanco y al menor negro
    # Si el gasto es mayor o igual a la nómina, el primer color es blanco y el segundo negro, y viceversa.
    if valores[0] >= valores[1]:
        colores_texto = ['white', 'black']
    else:
        colores_texto = ['black', 'white']

    fig = go.Figure(go.Pie(
        labels=labels, 
        values=valores, 
        hole=0.5, 
        sort=False, 
        direction="clockwise", 
        textinfo="percent", 
        textposition="inside",
        marker=dict(colors=[COLOR_GASTOS, COLOR_NOMINA], line=dict(width=0, color='rgba(0,0,0,0)')),
        
        # Asignamos la lista de colores al texto según el orden de los valores
        textfont=dict(
            color=colores_texto,
            size=18
        ), 
        customdata=[_mxn_2d(v) for v in valores],
        hovertemplate="<b>%{label}</b><br>Monto: %{customdata}<br>Participación: %{percent}<extra></extra>"
    ))
    fig.update_layout(
        height=320, 
        showlegend=False, 
        margin=dict(l=90, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig


def _html_resumen_nomina_gastos(r: dict, gastos_label: str = "Gastos (Proveedores)") -> str:
    """Tabla lateral: Monto total (Gastos + Nómina) en la cabecera y debajo el monto y % de Pagos a Nómina y de Gastos."""
    tot = r["total"]
    pct = lambda v: f"{v / tot * 100:.1f}%" if tot else "n/a"
    fila = lambda color, nombre, v: (f'<div style="margin-top:8px;"><span style="color:{color}">●</span> <b>{nombre}</b><br>'
                                     f'<span style="margin-left:18px">{_mxn_2d(v)} · {pct(v)}</span></div>')
    return (f'<div style="padding:6px 4px"><div style="opacity:.75">Monto total (Gastos + Nómina)</div>'
            f'<div style="font-size:1.4rem;font-weight:700">{_mxn_2d(tot)}</div>'
            + fila(COLOR_NOMINA, NOMBRE_NOMINA, r["nomina"]) + fila(COLOR_GASTOS, gastos_label, r["gastos"]) + "</div>")


def _fig_egresos_tiempo(mensual: pd.DataFrame) -> go.Figure:
    """Egresos en el tiempo: barras apiladas mensuales (`px.bar`, barmode='stack') con Egresos PUE (por mes de emisión), Egresos PPD (= Complementos, por
    mes de su Fecha Pago) y Pagos a Nómina (por Fecha Pago); su suma es el Egreso Total. `mensual` = esas 3 columnas indexadas por Periodo ('AAAA-MM')."""
    rubros = [NOMBRE_EGR_PUE, NOMBRE_EGR_PPD, NOMBRE_NOMINA]
    g = mensual.sort_index().reset_index(names="Periodo").melt(id_vars="Periodo", value_vars=rubros, var_name="Rubro", value_name="Monto")
    fig = px.bar(g, x="Periodo", y="Monto", color="Rubro", barmode="stack",
                 color_discrete_map={NOMBRE_EGR_PUE: COLOR_EGR_PUE, NOMBRE_EGR_PPD: COLOR_EGR_PPD, NOMBRE_NOMINA: COLOR_NOMINA},
                 category_orders={"Periodo": sorted(g["Periodo"].unique()), "Rubro": rubros})
    fig.update_traces(marker_line_width=0, hovertemplate="<b>%{x}</b><br>%{fullData.name}: MXN %{y:,.2f}<extra></extra>")
    fig.update_xaxes(type="category", showgrid=False, zeroline=False, tickangle=-90, title_text=None, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)", zeroline=False, tickformat=",.0f", title_text="Total (MXN)")
    
    fig.update_layout(
        height=500,  # Aumentamos un poco la altura total de la gráfica
        margin=dict(l=115, r=25, t=30, b=140),  # Aumentamos el margen inferior ('b') para dejar espacio a las fechas y la leyenda
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", 
        legend_title_text=None, 
        bargap=0.15,
        legend=dict(
            orientation="h",       # Leyenda horizontal
            yanchor="top",         # Anclada desde su parte superior
            y=-0.35,               # Posición vertical por debajo del eje X (puedes ajustarlo si lo quieres más arriba o abajo)
            xanchor="center",      # Centrada horizontalmente
            x=0.5
        )
    )
    return fig


# correcta
def _fig_facturacion_tiempo(
    d: pd.DataFrame,
    col_monto: str,
    nomina_mensual: pd.Series | None = None,
) -> go.Figure:
    """Facturación emitida en el tiempo: barras apiladas por mes (`px.bar`, barmode='stack'), PUE (`Monto_PUE`) y PPD (`Monto_PPD_Cobrado +
    Monto_PPD_Pendiente`); optionally includes payroll income as a separate monthly series."""
    g = d.assign(PPD=d["Monto_PPD_Cobrado"] + d["Monto_PPD_Pendiente"]).groupby("Periodo", as_index=False)[["Monto_PUE", "PPD"]].sum().sort_values("Periodo")
    g = g.rename(columns={"Monto_PUE": "PUE"}).melt(id_vars="Periodo", value_vars=["PUE", "PPD"], var_name="Método", value_name="Monto")
    if nomina_mensual is not None:
        nomina = nomina_mensual.rename_axis("Periodo").rename("Monto").reset_index()
        nomina["Periodo"] = nomina["Periodo"].astype(str)
        nomina["Método"] = "Nómina"
        g = pd.concat([g, nomina], ignore_index=True)
    fig = px.bar(g, x="Periodo", y="Monto", color="Método", barmode="stack", color_discrete_map={"PUE": PALETA_ING["pue"], "PPD": PALETA_ING["ppd"]},
                 category_orders={"Periodo": sorted(g["Periodo"].unique()), "Método": ["PUE", "PPD", "Nómina"]})
    fig.update_traces(marker_color="#F59E0B", selector={"name": "Nómina"})
    fig.update_traces(marker_line_width=0, hovertemplate="<b>%{x}</b><br>%{fullData.name}: MXN %{y:,.2f}<extra></extra>")
    fig.update_xaxes(type="category", showgrid=False, zeroline=False, tickangle=-90, title_text=None, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)", zeroline=False, tickformat=",.0f", title_text=f"{col_monto} (MXN)")
    
    fig.update_layout(
        height=520,  # Aumentamos la altura total de la gráfica
        margin=dict(l=115, r=25, t=30, b=140),  # Margen inferior más amplio ('b') para la leyenda horizontal
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", 
        legend_title_text=None, 
        bargap=0.15,
        legend=dict(
            orientation="h",   # Orientación horizontal
            yanchor="top",     # Anclada desde su parte superior
            y=-0.35,           # Posición vertical debajo del eje X
            xanchor="center",  # Centrada horizontalmente
            x=0.5
        )
    )
    return fig


def _fig_pie_metodo_pago(res: dict, paleta: dict | None = None) -> go.Figure:
    """Método de pago de gastos (`go.Pie`, hole=0, sin leyenda nativa). Con diferencia PPD >= 0: Egresos PUE, PPD pagado (= Complementos) y PPD pendiente
    (= Diferencia). Con diferencia NEGATIVA (los complementos superan la facturación PPD): solo la composición Egresos PUE / Egresos PPD de la facturación;
    los complementos y la diferencia firmada se presentan fuera del pastel (tabla), sin recortar ni alterar ningún importe."""
    paleta = {"pue": COLOR_EGR_PUE, "ppd": COLOR_EGR_PPD, "pendiente": "#2563EB"} if paleta is None else paleta
    if res["diferencia"] >= 0:
        filas = [(NOMBRE_EGR_PUE, res["pue"], paleta["pue"]), ("PPD pagado", res["complementos"], paleta["ppd"]), ("PPD pendiente", res["diferencia"], paleta["pendiente"])]
    else:
        filas = [(NOMBRE_EGR_PUE, res["pue"], paleta["pue"]), (NOMBRE_EGR_PPD, res["ppd"], paleta["ppd"])]
    sectores = [f for f in filas if f[1] > 0.005]
    nombres, valores, colores = ([s[i] for s in sectores] for i in range(3))
    
    fig = go.Figure(go.Pie(
        labels=nombres, 
        values=valores,
        hole=0.5, 
        sort=False, 
        direction="clockwise", 
        textinfo="percent", 
        textposition="inside",
        marker=dict(colors=colores, line=dict(width=0, color='rgba(0,0,0,0)')), 
        # Modificamos textfont para incluir tanto el color como el tamaño (size)
        textfont=dict(
            color=[TEXTO_SOBRE_ING[c] for c in colores],
            size=18
        ),
        customdata=[_mxn_2d(v) for v in valores],
        hovertemplate="<b>%{label}</b><br>Monto: %{customdata}<br>Participación: %{percent}<extra></extra>"
    ))
    
    fig.update_layout(height=320, showlegend=False, margin=dict(l=90, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _html_resumen_metodo_pago(
    res: dict,
    paleta: dict | None = None,
    incluir_detalle_ppd: bool = True,
    formato_pdf: bool = False,
) -> str:
    """Tabla lateral de Método de pago de gastos: Monto total (facturación recibida = PUE + PPD) en la cabecera, Egresos PUE, Egresos PPD y, si la
    diferencia es >= 0, sus viñetas PPD pendiente / PPD pagado; si es negativa, los Complementos y la Diferencia PPD (firmada) como importes separados.
    `formato_pdf` usa etiquetas compatibles con ReportLab y `incluir_detalle_ppd=False` omite el desglose si no hay base PAGO."""
    paleta = {"pue": COLOR_EGR_PUE, "ppd": COLOR_EGR_PPD, "pendiente": "#2563EB"} if paleta is None else paleta
    tot = res["facturacion"]
    pct = lambda v: f"{v / tot * 100:.1f}%" if tot else "n/a"
    if formato_pdf:
        fila_pdf = lambda color, nombre, v: (
            f'<font color="{color}">●</font> <b>{nombre}</b><br/>'
            f'<font color="#4B5563">{_mxn_2d(v)} · {pct(v)}</font>')
        filas = [
            f'<font size="8" color="#6B7280">Monto total</font><br/>'
            f'<b><font size="13" color="#1F2937">{_mxn_2d(tot)}</font></b>',
            fila_pdf(paleta["pue"], NOMBRE_EGR_PUE, res["pue"]),
            fila_pdf(paleta["ppd"], NOMBRE_EGR_PPD, res["ppd"]),
        ]
        if incluir_detalle_ppd:
            if res["diferencia"] >= 0:
                filas.extend([
                    fila_pdf(paleta["pendiente"], "PPD pendiente", res["diferencia"]),
                    fila_pdf(paleta["ppd"], "PPD pagado", res["complementos"]),
                ])
            else:
                filas.extend([
                    fila_pdf(paleta["ppd"], "Complementos de Pago Recibidos", res["complementos"]),
                    fila_pdf(paleta["pendiente"], "Diferencia PPD (Facturación PPD − Complementos de Pago Recibidos)", res["diferencia"]),
                ])
        return "<br/><br/>".join(filas)

    fila = lambda color, nombre, v, sangria=0, fuerte=True, con_pct=True: (
        f'<div style="margin-left:{sangria}px;margin-top:8px;"><span style="color:{color}">●</span> '
        f'{"<b>" if fuerte else ""}{nombre}{"</b>" if fuerte else ""}<br>'
        f'<span style="margin-left:18px">{_mxn_2d(v)}{" · " + pct(v) if con_pct else ""}</span></div>')
    html = (f'<div style="padding:6px 4px"><div style="opacity:.75">Monto total</div>'
            f'<div style="font-size:1.6rem;font-weight:700">{_mxn_2d(tot)}</div>'
            + fila(paleta["pue"], NOMBRE_EGR_PUE, res["pue"]) + fila(paleta["ppd"], NOMBRE_EGR_PPD, res["ppd"]))
    if incluir_detalle_ppd and res["diferencia"] >= 0:
        html += (fila(paleta["pendiente"], "PPD pendiente", res["diferencia"], sangria=28, fuerte=False)
                 + fila(paleta["ppd"], "PPD pagado", res["complementos"], sangria=28, fuerte=False))
    elif incluir_detalle_ppd:
        html += (fila(paleta["ppd"], "Complementos de Pago Recibidos", res["complementos"], con_pct=False)
                 + fila(paleta["pendiente"], "Diferencia PPD (Facturación PPD − Complementos de Pago Recibidos)", res["diferencia"], con_pct=False)
                 + '<div style="margin-top:10px;opacity:.8;font-size:.85rem">Los Complementos de Pago Recibidos superan la facturación PPD: la diferencia '
                   'se muestra fuera del gráfico.</div>')
    return html + "</div>"

def _fig_poder_adquisitivo(anios_str, idx_emp, idx_inpc):
    """Genera la gráfica de Poder Adquisitivo: Ingresos vs Inflación General (INPC) con etiquetas fijas."""
    fig = go.Figure()
    brecha = [ingreso - inflacion for ingreso, inflacion in zip(idx_emp, idx_inpc)]
    datos_hover_inpc = list(zip(idx_emp, brecha))
    datos_hover_ingresos = list(zip(idx_inpc, brecha))
    
    # Textos fijos para mostrar en la gráfica (ej. el valor numérico con 1 decimal)
    texto_inpc = [f"{val:.1f}" for val in idx_inpc]
    texto_ingresos = [f"{val:.1f}" for val in idx_emp]
    
    # Curva de Inflación General (INPC)
    fig.add_trace(go.Scatter(
        x=anios_str, y=idx_inpc, name="Inflación Consumidor (INPC)", 
        mode="lines+markers+text",  # <-- Añadido "+text" para mostrar etiquetas fijas
        text=texto_inpc,            # <-- Lista con el texto de cada punto
        textposition="top center",  # <-- Posición del texto respecto al marcador (top, bottom, middle, etc.)
        textfont=dict(color="#FA4A15", size=11), # Opcional: color a juego con la línea
        line=dict(color="#FA4A15", width=3), marker=dict(size=9, color="#FA4A15"),
        customdata=datos_hover_inpc,
        hovertemplate=("<b>%{x}</b><br>INPC: %{y:.1f}<br>Ingresos: %{customdata[0]:.1f}"
                       "<br>Brecha (Ingresos - INPC): %{customdata[1]:+.1f} puntos<extra></extra>")
    ))
    
    # Curva de Ingresos DPC (Base 100)
    fig.add_trace(go.Scatter(
        x=anios_str, y=idx_emp, name="Ingresos (Base 100)", 
        mode="lines+markers+text",  # <-- Añadido "+text"
        text=texto_ingresos,        # <-- Lista con el texto de cada punto
        textposition="bottom center", # <-- Posición para evitar que se encimen con los del INPC
        textfont=dict(color="#2563EB", size=11), # Opcional: color a juego
        line=dict(color="#2563EB", width=3), marker=dict(size=9, color="#2563EB"),
        customdata=datos_hover_ingresos,
        hovertemplate=("<b>%{x}</b><br>Ingresos: %{y:.1f}<br>INPC: %{customdata[0]:.1f}"
                       "<br>Brecha (Ingresos - INPC): %{customdata[1]:+.1f} puntos<extra></extra>")
    ))
    
    # Área de relleno sombreada (brecha entre ingresos e inflación)
    fig.add_trace(go.Scatter(
        x=anios_str + anios_str[::-1],
        y=idx_emp + idx_inpc[::-1],
        fill='toself',
        fillcolor='rgba(16, 185, 129, 0.2)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=False,
        name="Shaded Gap"
    ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=90, r=40, t=60, b=40), # Margen superior un poco más amplio por las etiquetas
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    )
    return fig

# Composición de Gasto Operativo Fijo
def _fig_eficiencia_operativa(anios_str, idx_emp, idx_inpp):
    """Genera la gráfica combinada de Eficiencia Operativa: Gastos Operativos (Barras) vs INPP (Línea)."""
    fig = go.Figure()
    
    # Barras de Gastos Operativos (Base 100)
    fig.add_trace(go.Bar(
        x=anios_str, y=idx_emp, name="Gastos Operativos (Base 100)",
        marker_color="#991B1B", texttemplate="%{y:.1f}", textposition="outside",
        cliponaxis=False, hovertemplate="<b>%{x}</b><br>Gastos Operativos: %{y:.1f}<extra></extra>"
    ))
    
    # Línea de Inflación Productor (INPP - Base 100)
    fig.add_trace(go.Scatter(
        x=anios_str, y=idx_inpp, name="Inflación Productor (INPP - Base 100)", mode="lines+markers",
        line=dict(color="#FF8000", width=3), marker=dict(size=9, color="#FF8000"),
        hovertemplate="<b>%{x}</b><br>INPP: %{y:.1f}<extra></extra>"
    ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=90, r=40, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    )
    return fig