"""Vista de razones financieras del Dashboard Ejecutivo."""

from html import escape

import streamlit as st

from components.financial_ratios import (
    NOTA_RAZONES,
    _matriz_razones,
    _tarjetas_razones,
    _ultimo_ejercicio_con_informacion,
)
from config import CODIGO_VERSION
from core.financial_ratios import _RAZONES_CODE_VERSION, _razones_cache
from core.loader import _datos_archivo_cache


_TITULO_SECCION = "9. Posición Financiera: Liquidez, Endeudamiento y Rentabilidad"
_TITULO_MATRIZ = "Evolución de razones financieras de los últimos cinco ejercicios fiscales"


def _agregar_encabezado_pdf(pdf_elements) -> None:
    if pdf_elements is not None:
        pdf_elements.append({"type": "heading", "text": _TITULO_SECCION})


def _seccion_razones(f_razones, pdf_elements=None) -> None:
    st.header(_TITULO_SECCION)
    if f_razones is None:
        mensaje = (
            "Para mostrar esta sección, carga un archivo llamado «financial-ratios», "
            "«financial_ratios» o «razones financieras»."
        )
        st.info(mensaje)
        _agregar_encabezado_pdf(pdf_elements)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return

    nombre, contenido = _datos_archivo_cache(f_razones)
    if isinstance(contenido, tuple):
        mensaje = (
            "Se detectaron varios archivos de razones financieras. Deja solo un archivo "
            "para evitar mezclar ejercicios o empresas."
        )
        st.error(mensaje)
        _agregar_encabezado_pdf(pdf_elements)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return
    try:
        razones = _razones_cache(
            nombre,
            contenido,
            f"{CODIGO_VERSION}:{_RAZONES_CODE_VERSION}",
        )
    except (ValueError, KeyError) as error:
        mensaje = f"No se pudo procesar «{nombre}»: {error}"
        st.error(mensaje)
        _agregar_encabezado_pdf(pdf_elements)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return

    ultimo = _ultimo_ejercicio_con_informacion(razones)
    if ultimo is None:
        mensaje = "No hay razones financieras con información para mostrar."
        st.info(mensaje)
        _agregar_encabezado_pdf(pdf_elements)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return

    tarjetas_html, tarjetas_pdf = _tarjetas_razones(razones, ultimo)
    titulo_tarjetas = f"Indicadores de evaluación crediticia — Ejercicio {ultimo}"
    st.markdown(f"**{titulo_tarjetas}**")
    st.markdown(tarjetas_html, unsafe_allow_html=True)
    st.info(NOTA_RAZONES)

    st.markdown(f"**{_TITULO_MATRIZ}**")
    matriz_html, matriz_pdf, notas = _matriz_razones(razones)
    st.markdown(matriz_html, unsafe_allow_html=True)
    for nota in notas:
        st.caption(nota)

    comentario_salud = st.text_area(
        "Insight sobre la posición financiera",
        max_chars=600,
        placeholder="Escribe un comentario (máx. 600 caracteres)...",
        key="note_secc9",
    )
    if pdf_elements is not None:
        pdf_elements.append({
            "type": "financial_ratios",
            "section_title": _TITULO_SECCION,
            "cards_title": titulo_tarjetas,
            "cards": tarjetas_pdf,
            "matrix_title": _TITULO_MATRIZ,
            "df": matriz_pdf,
            "footnotes": notas,
            "insight": comentario_salud,
            "note": NOTA_RAZONES,
        })
