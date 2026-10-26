'''
Funciones de propósito general para formateo, normalización de textos, conversión de tipos de datos (números, fechas) y manejo de archivos en memoria.
'''
import unicodedata
import pandas as pd
import re
from config import (_PARENTESIS,_GRUPO_FINANCIERO_FINAL, _SUFIJOS_CORPORATIVOS, _CONECTORES_MINUSCULA, COL_FECHA_REP,MESES_ES)

#  Clase auxiliar
class _ArchivoMem:
    """Archivo en memoria con la interfaz mínima que usan los lectores (`name`, `getvalue()`, `seek`). Permite pasar los
    archivos subidos como (nombre, bytes) a funciones con `st.cache_data` (un archivo subido no es hasheable)."""

    def __init__(self, nombre: str, contenido: bytes):
        self.name, self._contenido = nombre, contenido

    def getvalue(self) -> bytes:
        return self._contenido

    def seek(self, *_args) -> int:
        return 0

def _norm(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())

def buscar_columna(columnas, nombre: str) -> str | None:
    """Nombre real en `columnas` que coincide con `nombre`, tolerando acentos, mayúsculas y espacios."""
    objetivo = _norm(nombre)
    return next((c for c in columnas if _norm(c) == objetivo), None)

def a_numero(serie: pd.Series) -> pd.Series:
    """'1,164,363.55 ' o '$1,000.00' -> float. También entiende negativos en formato contable:
    '(1,234.56)' o '1,234.56-' (comunes en notas de crédito). Lo no convertible queda NaN."""
    s = serie.astype(str).str.strip()
    negativo = s.str.match(r"^\(.*\)$") | s.str.endswith("-")
    limpio = (s.str.replace(r"^\((.*)\)$", r"\1", regex=True)  # (1,234.56) -> 1,234.56
               .str.replace(r"-$", "", regex=True)              # 1,234.56- -> 1,234.56
               .str.replace(r"[,$\s]", "", regex=True))
    num = pd.to_numeric(limpio, errors="coerce")
    return num.where(~negativo.fillna(False), -num.abs())


def a_fecha(serie: pd.Series) -> pd.Series:
    """Texto DD/MM/YYYY HH:MM (CSV) o YYYY-MM-DD HH:MM:SS (Excel) -> fecha sin hora."""
    s = serie.astype(str).str.strip()
    formatos = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    dt = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in formatos:
        if not dt.isna().any():
            break
        dt = dt.fillna(pd.to_datetime(s, format=fmt, errors="coerce").astype("datetime64[ns]"))
    return dt.dt.normalize()


def dinero(x: float) -> str:
    return f"${x:,.0f}"


def _formatear_mxn(x: float, decimales: int = 2) -> str:
    monto = float(x)
    return f"-${abs(monto):,.{decimales}f}" if monto < 0 else f"${monto:,.{decimales}f}"


def _abrev_signo(v: float) -> str:
    """'$4.65M' / '$325.4k' / '$950' con '-' para negativos."""
    a = abs(float(v))
    texto = f"${a / 1e6:.2f}M" if a >= 1e6 else f"${a / 1e3:.1f}k" if a >= 1e3 else f"${a:,.0f}"
    return ("-" if v < -0.005 else "") + texto


def _pesos(x: float) -> str:
    """Importe con signo delante del símbolo ("-$500"), para textos donde puede haber diferencias negativas."""
    return f"-${abs(x):,.0f}" if round(x) < 0 else f"${x:,.0f}"


def _mxn(x: float) -> str:
    """Importe para textos que Streamlit interpreta como Markdown: "MXN 7,172,647" / "-MXN 7,172,647". NO usa
    "$": dos "$" en un mismo st.info/st.caption se interpretan como fórmula LaTeX (cursivas, sin espacios)."""
    return f"-MXN {abs(x):,.0f}" if round(x) < 0 else f"MXN {x:,.0f}"



def _importe_abreviado_2d(x) -> str:
    """Importe abreviado con dos decimales y unidad clara para las etiquetas: "1.25 M", "-325.40 mil", "850.00"
    (conserva el signo; "" si NaN). Un valor que al redondear llega a 1,000 mil se muestra ya en M."""
    if x is None or pd.isna(x):
        return ""
    x = float(x)
    magnitud = abs(x)
    if round(magnitud / 1_000, 2) >= 1_000 or magnitud >= 1_000_000:
        texto = f"{magnitud / 1_000_000:,.2f} M"
    elif magnitud >= 1_000 and round(magnitud, 2) >= 1_000:
        texto = f"{magnitud / 1_000:,.2f} mil"
    else:
        texto = f"{magnitud:,.2f}"
    return f"-{texto}" if x < 0 and round(magnitud, 2) != 0 else texto


def _mxn_2d(x) -> str:
    """Importe completo para el tooltip: "MXN 1,234,567.89" / "-MXN 1,234.50" (miles y dos decimales)."""
    if x is None or pd.isna(x):
        return ""
    x = round(float(x), 2)
    return f"-MXN {abs(x):,.2f}" if x < 0 else f"MXN {x:,.2f}"


def _abrev_monto(x: float) -> str:
    """Importe abreviado para etiquetas: 1.2M, -350k, 80 (conserva el signo)."""
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if abs(x) >= 1_000:
        return f"{x / 1_000:.1f}k"
    return f"{x:.0f}"


def etiqueta_empresa(rfc: str, nombre: str) -> str:
    return f"{nombre} ({rfc})" if nombre else rfc


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=True if df.index.name else False).encode("utf-8-sig")


def _nombre_abreviado(nombre, max_len: int = 30) -> str:
    """Nombre corto SOLO para presentación (gráfica/tabla de la Sección 5) -el nombre completo se conserva
    siempre en los datos subyacentes y en el hover de la gráfica-. Quita paréntesis (p. ej. "(MEXICO)"),
    sufijos corporativos comunes ("S.A. DE C.V.", "S.A.", "S. DE R.L. DE C.V.", "S.C.") y una repetición
    final tipo "GRUPO FINANCIERO <marca>", recorta a `max_len` caracteres, y castellaniza a Título (conserva
    en mayúsculas las siglas de 3 letras o menos, p. ej. "IOS"; minúsculas los conectores "de/la/los/y/...").
    Es una heurística de legibilidad, no una normalización legal -nombres con estructuras poco comunes
    pueden no acortarse de forma perfecta; en ese caso simplemente se truncan-.
    """
    if not isinstance(nombre, str) or not nombre.strip():
        return nombre
    limpio = _PARENTESIS.sub("", nombre)
    limpio = _GRUPO_FINANCIERO_FINAL.sub("", limpio)
    limpio = _SUFIJOS_CORPORATIVOS.sub("", limpio)
    limpio = re.sub(r"\s{2,}", " ", limpio).strip(" .,-")
    if not limpio:
        limpio = nombre.strip()

    palabras = []
    for i, palabra in enumerate(limpio.split(" ")):
        minuscula = palabra.lower()
        if len(palabra) <= 3 and palabra.isalpha() and palabra.isupper() and minuscula not in _CONECTORES_MINUSCULA:
            palabras.append(palabra)
        elif minuscula in _CONECTORES_MINUSCULA and i != 0:
            palabras.append(minuscula)
        else:
            palabras.append(palabra.capitalize())
    resultado = " ".join(palabras)
    if len(resultado) > max_len:
        resultado = resultado[:max_len - 1].rstrip() + "…"
    return resultado


def _columna_unica(df: pd.DataFrame, nombre: str) -> pd.Series:
    """Devuelve una única Serie para `nombre`, incluso si `df` trae más de una columna con ese nombre exacto.

    El origen típico no es el CSV/Excel en sí -pandas ya renombra encabezados duplicados al leer (`UUID DR`,
    `UUID DR.1`, ...)-, sino un renombrado nuestro que colisiona con una columna que ya existía con ese nombre
    (p. ej. si la base de Egresos ya trae una 'UUID DR' propia además de 'Documento Relacionado', renombrar
    esta última crea el duplicado). En vez de truncar por posición (`~columns.duplicated()`, que puede quedarse
    con la columna equivocada según el orden), se combinan por fila tomando el primer valor no nulo/no vacío
    (coalesce) entre todas las columnas con ese nombre.
    """
    coincidencias = df.loc[:, df.columns == nombre]
    if coincidencias.shape[1] <= 1:
        return coincidencias.iloc[:, 0] if coincidencias.shape[1] == 1 else pd.Series(index=df.index, dtype=object)
    limpio = coincidencias.replace(r"^\s*$", pd.NA, regex=True)
    return limpio.bfill(axis=1).iloc[:, 0]

def _resolver_fecha_pagos(columnas) -> str | None:
    """Nombre real de la columna de fecha de pago del archivo de pagos ('Fecha de Pago' o 'Fecha Pago'), la misma
    convención que `COL_FECHA_REP` usa en `leer_complementos()`."""
    (canonico, variantes), = COL_FECHA_REP.items()
    for candidato in [canonico, *variantes]:
        col = buscar_columna(columnas, candidato)
        if col:
            return col
    return None


def _rango_meses_texto(tabla: pd.DataFrame) -> str:
    """'ene 2025 a dic 2025' del rango cronológico de la tabla."""
    p0, p1 = tabla.index.min(), tabla.index.max()
    return f"{MESES_ES[p0.month - 1].lower()} {p0.year} a {MESES_ES[p1.month - 1].lower()} {p1.year}"


def _lista_anios(anios) -> str:
    return ", ".join(str(a) for a in anios) if anios else "ningún año"


def _anios_txt(anios: list[int]) -> str:
    """'2022–2025' si los años son consecutivos (2 o más); si no, la lista separada por comas."""
    anios = sorted(anios)
    return f"{anios[0]}–{anios[-1]}" if len(anios) >= 2 and anios == list(range(anios[0], anios[-1] + 1)) else ", ".join(map(str, anios))

def _nb(archivo) -> tuple[str, bytes]:
    """(nombre, contenido) de un archivo subido: la llave de los cálculos en caché del Dashboard Ejecutivo."""
    return archivo.name, archivo.getvalue()

def _rango_base100(*series) -> list[float]:
    vals = [v for s in series for v in s if pd.notna(v)]
    return [min(vals) - 10, max(vals) + 10]

def _limpiar_y_formatear(val, sufijo=""):
            if pd.isnull(val):
                return val
            try:
                num = float(val)
                return f"{num:,.1f}{sufijo}"
            except (ValueError, TypeError):
                return val

def _monto_por_cuota(cuota: float, tasa_m: float, plazo: int) -> float:
    """Monto de crédito estimado (ingeniería inversa, valor actual de la anualidad): cuota = 0 -> 0; tasa 0 -> cuota * plazo; tasa > 0 ->
    cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)."""
    if cuota <= 0 or plazo <= 0:
        return 0.0
    return cuota * plazo if tasa_m <= 0 else cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)