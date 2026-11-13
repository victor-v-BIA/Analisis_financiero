"""Vista de salud financiera y razones financieras del Dashboard Ejecutivo."""

from html import escape

import streamlit as st

from components.financial_ratios import (
    _fig_estructura_razones,
    _fig_liquidez_razones,
    _html_matriz_razones,
    _html_tarjetas_razones,
)
from config import CODIGO_VERSION
from core.financial_ratios import _RAZONES_CODE_VERSION, _razones_cache, criterios_razon
from core.loader import _datos_archivo_cache


def _seccion_razones(f_razones, pdf_elements=None) -> None:
    st.header(
        "9. Salud Financiera y Razones Financieras",
        help=(
            "Razones financieras de las declaraciones anuales del SAT. Cada razón se evalúa contra su propio "
            "rango de referencia en cuatro niveles (óptimo, vigilancia, crítico y atípico): un valor positivo "
            "no es necesariamente favorable."
        ),
    )
    if pdf_elements is not None:
        pdf_elements.append({"type": "heading", "text": "9. Salud Financiera y Razones Financieras"})
    if f_razones is None:
        mensaje = (
            "Para mostrar esta sección, carga un archivo llamado «financial-ratios», "
            "«financial_ratios» o «razones financieras»."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return

    nombre, contenido = _datos_archivo_cache(f_razones)
    if isinstance(contenido, tuple):
        mensaje = "Se detectaron varios archivos de razones financieras. Deja solo un archivo para evitar mezclar ejercicios o empresas."
        st.error(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return
    try:
        razones = _razones_cache(nombre, contenido, f"{CODIGO_VERSION}:{_RAZONES_CODE_VERSION}")
    except (ValueError, KeyError) as error:
        mensaje = f"No se pudo procesar «{nombre}»: {error}"
        st.error(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return

    anios = list(razones.columns)
    ultimo, previo = anios[-1], anios[-2] if len(anios) > 1 else None
    st.caption(f"Archivo: {nombre} · Periodo disponible: {anios[0]}–{ultimo}")

    tarjetas_html, pdf_kpis = _html_tarjetas_razones(razones, ultimo, previo)
    st.markdown(tarjetas_html, unsafe_allow_html=True)
    if pdf_elements is not None:
        pdf_elements.append({"type": "metrics", "title": f"Indicadores — {ultimo}", "data": pdf_kpis})

    st.markdown("**Matriz histórica con semáforo por pilar**")
    matriz_html, matriz_pdf = _html_matriz_razones(razones, anios)
    st.markdown(matriz_html, unsafe_allow_html=True)
    if pdf_elements is not None and not matriz_pdf.empty:
        pdf_elements.append({
            "type": "table",
            "title": "Matriz histórica con semáforo por pilar",
            "df": matriz_pdf,
        })

    st.caption(
        f"Umbrales de referencia — Liquidez: {criterios_razon('current_ratio')} · "
        f"Endeudamiento: {criterios_razon('total_debt_ratio')}"
    )

    disponibles_liquidez = any(
        metrica in razones.index for metrica in ("current_ratio", "quick_ratio")
    )
    disponibles_estructura = any(
        metrica in razones.index
        for metrica in ("total_debt_ratio", "gross_profit_margin", "return_on_sales")
    )
    col_liquidez, col_estructura = st.columns(2)
    if disponibles_liquidez:
        fig_liquidez = _fig_liquidez_razones(razones)
        with col_liquidez:
            st.plotly_chart(fig_liquidez, width="stretch", key="razones_fig_liquidez")
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "title": "Liquidez de Corto Plazo vs Umbral Mínimo",
                "fig": fig_liquidez,
            })
    else:
        with col_liquidez:
            st.info("El archivo no contiene razones de liquidez.")

    fig_estructura = None
    if disponibles_estructura:
        fig_estructura = _fig_estructura_razones(razones)
        with col_estructura:
            if fig_estructura is None:
                st.info("No hay valores no atípicos para graficar en estructura patrimonial y márgenes.")
            else:
                st.plotly_chart(fig_estructura, width="stretch", key="razones_fig_estructura")
        if pdf_elements is not None and fig_estructura is not None:
            pdf_elements.append({
                "type": "image",
                "title": "Estructura patrimonial vs Márgenes Declarados %",
                "fig": fig_estructura,
            })
    else:
        with col_estructura:
            st.info("El archivo no contiene endeudamiento ni márgenes para graficar.")

    comentario_salud = st.text_area(
        "Comentario para Salud Financiera y Razones Financieras",
        max_chars=600,
        placeholder="Escribe un comentario (máx. 600 caracteres)...",
        key="note_secc9",
    )
    if pdf_elements is not None and comentario_salud.strip():
        comentario_pdf = escape(comentario_salud.strip()).replace("\n", "<br/>")
        pdf_elements.append({"type": "callout", "text": f"<b>Comentario:</b> {comentario_pdf}"})
