"""Lectura y normalización de razones financieras reportadas por ejercicio."""

import hashlib
import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from utils import _norm


_RAZONES_ALIAS = {
    "current ratio": "current_ratio",
    "razon circulante": "current_ratio",
    "quick ratio": "quick_ratio",
    "acid test": "quick_ratio",
    "prueba acida": "quick_ratio",
    "cash to assets": "cash_to_assets",
    "cash to total assets": "cash_to_assets",
    "efectivo a activo total": "cash_to_assets",
    "net working capital to sales": "net_working_capital_to_sales",
    "working capital to sales": "net_working_capital_to_sales",
    "capital de trabajo a ventas": "net_working_capital_to_sales",
    "total debt ratio": "total_debt_ratio",
    "debt ratio": "total_debt_ratio",
    "endeudamiento total": "total_debt_ratio",
    "debt equity ratio": "debt_equity_ratio",
    "debt to equity": "debt_equity_ratio",
    "apalancamiento": "debt_equity_ratio",
    "coverage": "coverage",
    "interest coverage": "coverage",
    "interest coverage ratio": "coverage",
    "cobertura de intereses": "coverage",
    "gross profit margin": "gross_profit_margin",
    "gross margin": "gross_profit_margin",
    "margen bruto": "gross_profit_margin",
    "return on sales": "return_on_sales",
    "ros": "return_on_sales",
    "margen neto": "return_on_sales",
    "return on equity": "return_on_equity",
    "roe": "return_on_equity",
    "rendimiento sobre capital": "return_on_equity",
    "total asset turnover": "total_asset_turnover",
    "total assets turnover": "total_asset_turnover",
    "rotacion de activos totales": "total_asset_turnover",
}

_RAZONES_PORCENTAJE = {
    "cash_to_assets",
    "net_working_capital_to_sales",
    "total_debt_ratio",
    "gross_profit_margin",
    "return_on_sales",
    "return_on_equity",
}

_RAZONES_CODE_VERSION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _normalizar_clave_razon(valor: object) -> str:
    return _norm(str(valor).replace("_", " "))


def _numero_razon(valor: object) -> float:
    if pd.isna(valor):
        return float("nan")
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("$", "").replace(" ", "")
    if not texto:
        return float("nan")
    porcentaje = texto.endswith("%")
    if porcentaje:
        texto = texto[:-1]
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    else:
        texto = texto.replace(",", "")
    numero = pd.to_numeric(texto, errors="coerce")
    if pd.isna(numero):
        return float("nan")
    return float(numero) / 100 if porcentaje else float(numero)


def _normalizar_tabla_razones(tabla: pd.DataFrame) -> pd.DataFrame:
    columna_categoria = next(
        (
            col for col in tabla.columns
            if _normalizar_clave_razon(col) in {"categoria", "category"}
        ),
        None,
    )
    if columna_categoria is None:
        raise ValueError("Falta la columna «Categoría» (o «category»).")

    columnas_anio = {}
    for columna in tabla.columns:
        coincidencia = re.fullmatch(r"(19|20|21)\d{2}", str(columna).strip())
        if coincidencia:
            columnas_anio[int(str(columna).strip())] = columna
    if not columnas_anio:
        raise ValueError(
            "No se encontraron columnas de ejercicio con encabezados de cuatro dígitos, como 2025."
        )

    anios = sorted(columnas_anio)[-5:]
    datos: dict[str, dict[int, float]] = {}
    for _, fila in tabla.iterrows():
        partes = _normalizar_clave_razon(fila[columna_categoria]).split(">")
        metrica = _RAZONES_ALIAS.get(partes[-1].strip())
        if metrica is None:
            continue
        valores = {
            anio: _numero_razon(fila[columnas_anio[anio]])
            for anio in anios
        }
        anteriores = datos.get(metrica, {})
        datos[metrica] = {
            anio: valor if pd.notna(valor) else anteriores.get(anio, float("nan"))
            for anio, valor in valores.items()
        }

    if not datos:
        raise ValueError("No se reconocieron razones financieras en la columna «Categoría».")

    datos_con_informacion = {
        metrica: valores
        for metrica, valores in datos.items()
        if any(pd.notna(valor) for valor in valores.values())
    }
    resultado = pd.DataFrame(
        {
            metrica: pd.Series(valores, dtype=float)
            for metrica, valores in datos_con_informacion.items()
        },
        index=anios,
        dtype=float,
    ).T.reindex(columns=anios)
    resultado.index.name = "metrica"
    return resultado


@st.cache_data(show_spinner=False, max_entries=4)
def _razones_cache(nombre: str, contenido: bytes, version: str) -> pd.DataFrame:
    extension = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if extension == "csv":
        tabla = None
        errores = []
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                tabla = pd.read_csv(
                    io.BytesIO(contenido),
                    dtype=object,
                    sep=None,
                    engine="python",
                    encoding=codificacion,
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError) as error:
                errores.append(str(error))
        if tabla is None:
            detalle = errores[-1] if errores else "formato CSV no reconocido"
            raise ValueError(f"No se pudo leer el CSV: {detalle}")
    elif extension in {"xlsx", "xls"}:
        try:
            tabla = pd.read_excel(io.BytesIO(contenido), dtype=object)
        except (ImportError, OSError, ValueError) as error:
            raise ValueError(f"No se pudo leer el archivo Excel: {error}") from error
    else:
        raise ValueError("El archivo de razones financieras debe ser CSV o Excel (.csv, .xlsx, .xls).")
    if tabla.empty:
        raise ValueError("El archivo de razones financieras no contiene filas.")
    return _normalizar_tabla_razones(tabla)


def _valor_razon(razones: pd.DataFrame, metrica: str, anio: int) -> float:
    if metrica not in razones.index or anio not in razones.columns:
        return float("nan")
    valor = razones.at[metrica, anio]
    return float(valor) if pd.notna(valor) else float("nan")
