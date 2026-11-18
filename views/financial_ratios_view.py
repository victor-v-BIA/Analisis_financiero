"""Vista de salud financiera y razones financieras del Dashboard Ejecutivo."""

from html import escape

import pandas as pd
import streamlit as st

from components.financial_ratios import (
    _fig_estructura_razones,
    _fig_liquidez_razones,
    _html_matriz_razones,
    _html_tarjetas_razones,
)
from config import CODIGO_VERSION
from core.financial_ratios import _RAZONES_CODE_VERSION, _razones_cache
from core.loader import _datos_archivo_cache


def _seccion_razones(f_razones, pdf_elements=None) -> None:
    st.header(
        "9. Posición Financiera: Liquidez, Endeudamiento y Rentabilidad",
    )
    if pdf_elements is not None:
        pdf_elements.append({"type": "heading", "text": "9. Posición Financiera: Liquidez, Endeudamiento y Rentabilidad"})
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
    ultimo = next(
        (
            anio
            for anio in reversed(anios)
            if any(
                metrica in razones.index and pd.notna(razones.at[metrica, anio])
                for metrica in (
                    "current_ratio",
                    "quick_ratio",
                    "total_debt_ratio",
                    "debt_equity_ratio",
                    "gross_profit_margin",
                    "return_on_sales",
                    "return_on_equity",
                    "total_asset_turnover",
                )
            )
        ),
        anios[-1],
    )
    previo = next((anio for anio in reversed(anios) if anio < ultimo), None)

    tarjetas_html, pdf_kpis = _html_tarjetas_razones(razones, ultimo, previo)
    st.markdown(tarjetas_html, unsafe_allow_html=True)
    if pdf_elements is not None:
        pdf_elements.append({"type": "metrics", "title": f"Indicadores — {ultimo}", "data": pdf_kpis})

    st.markdown("**Evolución de razones financieras de los últimos cinco ejercicios fiscales**")
    matriz_html, matriz_pdf = _html_matriz_razones(razones, anios)
    st.markdown(matriz_html, unsafe_allow_html=True)
    if pdf_elements is not None and not matriz_pdf.empty:
        pdf_elements.append({
            "type": "table",
            "title": "Evolución de razones financieras de los últimos cinco ejercicios fiscales",
            "df": matriz_pdf,
            "status_badges": True,
        })

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
            st.markdown(
                '<div style="text-align:center;font-weight:600;margin-bottom:.35rem">'
                'Liquidez de Corto Plazo vs. Umbral Mínimo '
                '<span title="Indica si la empresa puede pagar sus deudas de corto plazo con los recursos '
                'que tiene disponibles en ese mismo plazo. Arriba de la línea punteada (1.00x) le alcanza '
                'para pagar; abajo, no le alcanza. La prueba ácida es la medida más estricta porque no cuenta '
                'los inventarios.">ⓘ</span></div>',
                unsafe_allow_html=True,
            )
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
    comentario_salud = st.text_area(
            "Insight para Salud Financiera y Razones Financieras",
            max_chars=600,
            placeholder="Escribe un comentario (máx. 600 caracteres)...",
            key="note_secc9",
        )
    fig_estructura = None
    if disponibles_estructura:
        fig_estructura = _fig_estructura_razones(razones)
        with col_estructura:
            if fig_estructura is None:
                st.info("No hay valores no atípicos para graficar en estructura patrimonial y márgenes.")
            else:
                st.markdown(
                    '<div style="text-align:center;font-weight:600;margin-bottom:.35rem">'
                    'Estructura Patrimonial vs. Márgenes Declarados % '
                    '<span title="Indica qué parte de lo que tiene la empresa está financiada con deuda y cuánto '
                    'le queda de cada peso que vende, antes y después de todos sus gastos (margen bruto y margen '
                    'neto). Sirve para ver si la deuda se traduce en mejores resultados o si la empresa debe más '
                    'sin ganar más. El margen bruto no se muestra en los ejercicios donde es atípico.">ⓘ</span></div>',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(fig_estructura, width="stretch", key="razones_fig_estructura")
        if pdf_elements is not None and fig_estructura is not None:
            pdf_elements.append({
                "type": "image",
                "title": "Estructura patrimonial vs Márgenes Declarados %",
                "fig": fig_estructura,
                "note":comentario_salud
            })
    else:
        with col_estructura:
            st.info("El archivo no contiene endeudamiento ni márgenes para graficar.")

    
    