"""Controles compartidos entre el punto de entrada y las vistas."""

import streamlit as st

from config import CSS_BARRA_CONTROL


def barra_control(anios, key_anios: str | None = None):
    """Muestra el selector de ejercicios fiscales y devuelve los años seleccionados."""
    st.markdown(CSS_BARRA_CONTROL, unsafe_allow_html=True)
    seleccion = st.pills("Ejercicios fiscales", options=anios, default=anios,
                         selection_mode="multi", key=key_anios)
    st.markdown("<hr style='margin: 0.5rem 0 1.2rem 0; border-color: rgba(255,255,255,0.08);'>",
                unsafe_allow_html=True)
    return sorted(int(a) for a in (seleccion or []))
