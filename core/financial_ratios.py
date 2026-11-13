"""Lectura, normalización y evaluación de razones financieras."""

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
    "total debt ratio": "total_debt_ratio",
    "debt ratio": "total_debt_ratio",
    "endeudamiento total": "total_debt_ratio",
    "debt equity ratio": "debt_equity_ratio",
    "debt to equity": "debt_equity_ratio",
    "apalancamiento pasivo capital": "debt_equity_ratio",
    "gross profit margin": "gross_profit_margin",
    "gross margin": "gross_profit_margin",
    "margen bruto": "gross_profit_margin",
    "return on sales": "return_on_sales",
    "ros": "return_on_sales",
    "margen neto": "return_on_sales",
    "return on equity": "return_on_equity",
    "roe": "return_on_equity",
    "total asset turnover": "total_asset_turnover",
    "total assets turnover": "total_asset_turnover",
    "rotacion de activos totales": "total_asset_turnover",
    "equity": "equity",
    "total equity": "equity",
    "total stockholders equity": "equity",
    "shareholders equity": "equity",
    "stockholders equity": "equity",
    "capital contable": "equity",
}

_RAZONES_PORCENTAJE = {
    "total_debt_ratio",
    "gross_profit_margin",
    "return_on_sales",
    "return_on_equity",
}

# Each range is (state, minimum, includes minimum, maximum, includes maximum).
_RAZONES_REGLAS = {
    "current_ratio": (
        ("Crítico", None, False, 1.0, False),
        ("Vigilancia", 1.0, True, 1.2, False),
        ("Óptimo", 1.2, True, 2.5, True),
        ("Vigilancia", 2.5, False, 3.5, True),
        ("Atípico", 3.5, False, None, False),
    ),
    "quick_ratio": (
        ("Crítico", None, False, 0.7, False),
        ("Vigilancia", 0.7, True, 1.0, False),
        ("Óptimo", 1.0, True, 2.5, True),
        ("Atípico", 2.5, False, None, False),
    ),
    "total_debt_ratio": (
        ("Crítico", None, False, 0.0, False),
        ("Atípico", 0.0, True, 0.3, False),
        ("Óptimo", 0.3, True, 0.55, True),
        ("Vigilancia", 0.55, False, 0.75, True),
        ("Crítico", 0.75, False, None, False),
    ),
    "debt_equity_ratio": (
        ("Crítico", None, False, 0.0, False),
        ("Atípico", 0.0, True, 0.3, False),
        ("Óptimo", 0.3, True, 1.5, True),
        ("Vigilancia", 1.5, False, 3.0, True),
        ("Crítico", 3.0, False, None, False),
    ),
    "gross_profit_margin": (
        ("Crítico", None, False, 0.0, False),
        ("Vigilancia", 0.0, True, 0.2, False),
        ("Óptimo", 0.2, True, 0.8, True),
        ("Atípico", 0.8, False, None, False),
    ),
    "return_on_sales": (
        ("Crítico", None, False, 0.0, False),
        ("Vigilancia", 0.0, True, 0.05, False),
        ("Óptimo", 0.05, True, 0.2, True),
        ("Atípico", 0.2, False, None, False),
    ),
    "return_on_equity": (
        ("Crítico", None, False, 0.0, False),
        ("Vigilancia", 0.0, True, 0.08, False),
        ("Óptimo", 0.08, True, 0.25, True),
        ("Atípico", 0.25, False, None, False),
    ),
    "total_asset_turnover": (
        ("Crítico", None, False, 0.5, False),
        ("Vigilancia", 0.5, True, 1.0, False),
        ("Óptimo", 1.0, True, 5.0, True),
        ("Atípico", 5.0, False, None, False),
    ),
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
        (col for col in tabla.columns if _normalizar_clave_razon(col) in {"categoria", "category"}),
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
        raise ValueError("No se encontraron columnas de ejercicio con encabezados de cuatro dígitos, como 2025.")

    datos = {}
    for _, fila in tabla.iterrows():
        partes = _normalizar_clave_razon(fila[columna_categoria]).split(">")
        metrica = _RAZONES_ALIAS.get(partes[-1].strip())
        if metrica is None:
            continue
        valores = {
            anio: _numero_razon(fila[columna])
            for anio, columna in columnas_anio.items()
        }
        valores_previos = datos.get(metrica)
        if metrica != "equity" and valores_previos is not None:
            previo_util = any(pd.notna(valor) and valor != 0 for valor in valores_previos.values())
            actual_util = any(pd.notna(valor) and valor != 0 for valor in valores.values())
            if previo_util and not actual_util:
                continue
        datos[metrica] = valores

    if not datos:
        raise ValueError("No se reconocieron razones financieras en la columna «Categoría».")

    anios_utiles = [
        anio for anio in sorted(columnas_anio)
        if any(pd.notna(valores.get(anio)) for metrica, valores in datos.items() if metrica != "equity")
    ]
    if not anios_utiles:
        raise ValueError("Las columnas de ejercicios no contienen valores utilizables.")

    datos_utiles = {}
    for metrica, valores in datos.items():
        serie = pd.Series({anio: valores.get(anio, float("nan")) for anio in anios_utiles}, dtype=float)
        if metrica != "equity" and (serie.isna().all() or serie.fillna(0).eq(0).all()):
            continue
        datos_utiles[metrica] = serie

    if not set(datos_utiles).intersection(_RAZONES_REGLAS):
        raise ValueError("Las métricas reconocidas están vacías o son cero en todos los ejercicios.")
    resultado = pd.DataFrame(datos_utiles).T.reindex(columns=anios_utiles)
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
    if metrica == "return_on_equity" and "equity" in razones.index:
        capital = razones.at["equity", anio]
        if pd.notna(capital) and capital <= 0:
            return float("nan")
    return float(valor) if pd.notna(valor) else float("nan")


def _en_rango_razon(valor: float, rango: tuple) -> bool:
    _, minimo, incluye_minimo, maximo, incluye_maximo = rango
    if minimo is not None and (valor < minimo or (valor == minimo and not incluye_minimo)):
        return False
    if maximo is not None and (valor > maximo or (valor == maximo and not incluye_maximo)):
        return False
    return True


def _nivel_base_razon(metrica: str, valor: float) -> str | None:
    return next(
        (rango[0] for rango in _RAZONES_REGLAS.get(metrica, ()) if _en_rango_razon(valor, rango)),
        None,
    )


def _nivel_razon(razones: pd.DataFrame, metrica: str, anio: int) -> str | None:
    valor = _valor_razon(razones, metrica, anio)
    if metrica == "return_on_equity" and "equity" in razones.index:
        capital = razones.at["equity", anio]
        if pd.notna(capital) and capital <= 0:
            return "Crítico"
    if pd.isna(valor):
        return None

    nivel = _nivel_base_razon(metrica, valor)
    if nivel is None:
        return None
    if metrica == "quick_ratio" and "current_ratio" in razones.index:
        circulante = _nivel_razon(razones, "current_ratio", anio)
        orden = {"Crítico": 0, "Vigilancia": 1, "Óptimo": 2, "Atípico": 2}
        if circulante is not None and orden[nivel] > orden[circulante]:
            return circulante
    return nivel


def _formato_limite_razon(metrica: str, valor: float) -> str:
    return f"{valor * 100:g}%" if metrica in _RAZONES_PORCENTAJE else f"{valor:.2f}x"


def _texto_rango_razon(metrica: str, rango: tuple) -> str:
    _, minimo, incluye_minimo, maximo, incluye_maximo = rango
    if minimo is None:
        operador = "≤" if incluye_maximo else "<"
        return f"{operador}{_formato_limite_razon(metrica, maximo)}"
    if maximo is None:
        operador = "≥" if incluye_minimo else ">"
        return f"{operador}{_formato_limite_razon(metrica, minimo)}"

    inicio = _formato_limite_razon(metrica, minimo)
    fin = _formato_limite_razon(metrica, maximo)
    if not incluye_minimo:
        inicio = f">{inicio}"
    if not incluye_maximo:
        fin = f"<{fin}"
    return f"{inicio}–{fin}"


def criterios_razon(metrica: str) -> str:
    """Genera los criterios visibles directamente desde los rangos usados para clasificar."""
    orden_estados = ("Óptimo", "Vigilancia", "Crítico", "Atípico")
    rangos = _RAZONES_REGLAS.get(metrica, ())
    criterios = []
    for estado in orden_estados:
        intervalos = [
            _texto_rango_razon(metrica, rango)
            for rango in rangos
            if rango[0] == estado
        ]
        if intervalos:
            criterios.append(f"{estado}: {' o '.join(intervalos)}")
    return "; ".join(criterios)
