"""Obtención y cruce de tipos de cambio de referencia para operaciones en divisas."""

import os

import pandas as pd
import requests
import streamlit as st

from config import DIAS_MAX_FFILL_FIX, SERIES_FIX
from utils import a_fecha, a_numero, _norm

_BANXICO_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
_FRANKFURTER_URL = "https://api.frankfurter.app"
_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart"


def _token_banxico() -> str | None:
    token = os.environ.get("BANXICO_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("banxico_token")
    except (FileNotFoundError, KeyError):
        return None


def _serie_numerica(fechas, valores) -> pd.Series:
    fechas = a_fecha(pd.Series(fechas)).astype("datetime64[ns]")
    valores = a_numero(pd.Series(valores))
    serie = pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(fechas), dtype="float64")
    serie = serie.loc[serie.index.notna() & serie.notna()]
    serie = serie[~serie.index.duplicated(keep="last")].sort_index()
    serie.index.name = "Fecha"
    return serie


def fix_desde_respuesta_banxico(respuesta: dict) -> dict[str, pd.Series]:
    series = {}
    for item in respuesta.get("bmx", {}).get("series", []):
        moneda = SERIES_FIX.get(item.get("idSerie"))
        if moneda is None:
            continue
        datos = item.get("datos", [])
        if not datos:
            continue
        series[moneda] = _serie_numerica(
            [dato.get("fecha") for dato in datos],
            [dato.get("dato") for dato in datos],
        )
    return series


def leer_serie_fix(hojas: list[pd.DataFrame]) -> dict[str, pd.Series]:
    """Extrae series USD/MXN y EUR/MXN de exportaciones tabulares de Banxico."""
    series: dict[str, pd.Series] = {}
    for hoja in hojas:
        if hoja.empty:
            continue
        for fila_encabezado in range(min(len(hoja), 30)):
            encabezados = hoja.iloc[fila_encabezado].fillna("").astype(str).tolist()
            normalizados = [_norm(valor) for valor in encabezados]
            idx_fecha = next((i for i, valor in enumerate(normalizados) if "fecha" in valor), None)
            if idx_fecha is None:
                continue
            columnas = {}
            for idx, titulo in enumerate(normalizados):
                texto = titulo.replace(" ", "")
                for serie_id, moneda in SERIES_FIX.items():
                    if serie_id.lower() in texto:
                        columnas[moneda] = idx
                if "dolar" in titulo and ("fix" in titulo or "tipo de cambio" in titulo):
                    columnas.setdefault("USD", idx)
                if ("euro" in titulo or "eur" in titulo) and ("fix" in titulo or "tipo de cambio" in titulo):
                    columnas.setdefault("EUR", idx)
                if "fix" in titulo and "euro" not in titulo and "eur" not in titulo:
                    columnas.setdefault("USD", idx)
            if not columnas:
                continue
            datos = hoja.iloc[fila_encabezado + 1:].reset_index(drop=True)
            fechas = a_fecha(datos.iloc[:, idx_fecha])
            if fechas.notna().sum() == 0:
                continue
            for moneda, idx in columnas.items():
                valores = a_numero(datos.iloc[:, idx])
                serie = _serie_numerica(fechas, valores)
                if not serie.empty:
                    series[moneda] = serie
            if series:
                return series
    if not series:
        raise ValueError("No se encontraron columnas de fecha y tipo de cambio USD/EUR en el archivo FIX.")
    return series


@st.cache_data(ttl=86400, show_spinner=False)
def _fix_cache(archivos: tuple[tuple[str, bytes], ...], version: str) -> dict[str, pd.Series]:
    from core.loader import _hojas_crudas

    resultado: dict[str, pd.Series] = {}
    for nombre, contenido in archivos:
        series = leer_serie_fix(_hojas_crudas(nombre, contenido))
        for moneda, serie in series.items():
            resultado[moneda] = pd.concat([resultado.get(moneda, pd.Series(dtype=float)), serie])
            resultado[moneda] = resultado[moneda][~resultado[moneda].index.duplicated(keep="last")].sort_index()
    return resultado


@st.cache_data(ttl=86400, show_spinner=False)
def _consultar_fix_banxico(token: str, fecha_inicio: str, fecha_fin: str) -> dict[str, pd.Series]:
    ids = ",".join(SERIES_FIX)
    url = f"{_BANXICO_URL}/{ids}/datos/{fecha_inicio}/{fecha_fin}"
    respuesta = requests.get(url, headers={"Bmx-Token": token}, timeout=15)
    respuesta.raise_for_status()
    return fix_desde_respuesta_banxico(respuesta.json())


def _consultar_frankfurter(moneda: str, fecha_inicio: str, fecha_fin: str) -> pd.Series:
    respuesta = requests.get(
        f"{_FRANKFURTER_URL}/{fecha_inicio}..{fecha_fin}",
        params={"from": moneda, "to": "MXN"},
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json().get("rates", {})
    return _serie_numerica(
        list(datos.keys()),
        [valores.get("MXN") for valores in datos.values()],
    )


def fix_desde_respuesta_frankfurter(respuesta: dict) -> pd.Series:
    datos = respuesta.get("rates", {})
    return _serie_numerica(
        list(datos.keys()),
        [valores.get("MXN") for valores in datos.values()],
    )


@st.cache_data(ttl=86400, show_spinner=False)
def _frankfurter_cache(moneda: str, fecha_inicio: str, fecha_fin: str) -> pd.Series:
    return _consultar_frankfurter(moneda, fecha_inicio, fecha_fin)


@st.cache_data(ttl=86400, show_spinner=False)
def _consultar_yfinance(moneda: str, fecha_inicio: str, fecha_fin: str) -> pd.Series:
    ticker = {"USD": "USDMXN=X", "EUR": "EURMXN=X"}.get(moneda)
    if ticker is None:
        return pd.Series(dtype=float)
    inicio = int(pd.Timestamp(fecha_inicio, tz="UTC").timestamp())
    fin = int((pd.Timestamp(fecha_fin, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    respuesta = requests.get(
        f"{_YAHOO_URL}/{ticker}",
        params={"period1": inicio, "period2": fin, "interval": "1d", "events": "history"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    respuesta.raise_for_status()
    resultado = respuesta.json().get("chart", {}).get("result") or []
    if not resultado:
        return pd.Series(dtype=float)
    registro = resultado[0]
    marcas = registro.get("timestamp", [])
    precios = registro.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    fechas = pd.to_datetime(marcas, unit="s", utc=True).tz_convert(None).normalize()
    return _serie_numerica(fechas, precios)


def _archivos_fix(archivo) -> tuple[tuple[str, bytes], ...]:
    if archivo is None:
        return ()
    contenido = archivo.getvalue() if hasattr(archivo, "getvalue") else archivo
    partes = contenido if isinstance(contenido, (list, tuple)) else [contenido]
    archivos = []
    for parte in partes:
        nombre = getattr(parte, "name", getattr(archivo, "name", "fix.csv"))
        if hasattr(parte, "descargar"):
            bytes_archivo = parte.descargar()
        elif hasattr(parte, "getvalue"):
            bytes_archivo = parte.getvalue()
        else:
            bytes_archivo = parte
        if not isinstance(bytes_archivo, bytes):
            raise TypeError("El archivo FIX debe contener datos binarios.")
        archivos.append((nombre, bytes_archivo))
    return tuple(archivos)


def _referencia_completa(operaciones: pd.DataFrame, serie: pd.Series | None) -> bool:
    if serie is None or serie.empty:
        return False
    indice = pd.DatetimeIndex(pd.to_datetime(serie.index)).astype("datetime64[ns]").sort_values()
    fechas = pd.DatetimeIndex(pd.to_datetime(operaciones["Fecha_Operacion"])).astype("datetime64[ns]")
    posiciones = indice.searchsorted(fechas, side="right") - 1
    cubiertas = posiciones >= 0
    if cubiertas.any():
        diferencia = fechas[cubiertas] - indice.take(posiciones[cubiertas])
        cubiertas[cubiertas] = diferencia <= pd.Timedelta(days=DIAS_MAX_FFILL_FIX)
    return bool(cubiertas.all())


def _combinar_referencias(
    existente: pd.Series | None,
    nueva: pd.Series,
    fuente_existente: str | None,
    fuente_nueva: str,
) -> tuple[pd.Series, str]:
    if existente is None or existente.empty:
        return nueva, fuente_nueva
    combinado = pd.concat([nueva, existente]).sort_index()
    combinado = combinado[~combinado.index.duplicated(keep="last")]
    fuente = fuente_existente if fuente_nueva in fuente_existente else f"{fuente_existente} + {fuente_nueva}"
    return combinado, fuente


def _obtener_fix(ops_df: pd.DataFrame, f_fix=None) -> tuple[dict[str, pd.Series], str, str]:
    """Busca referencias en orden: archivo, Banxico, Frankfurter y Yahoo Finance."""
    if ops_df.empty:
        return {}, "Ninguna", "Sin operaciones"

    fecha_inicio = pd.Timestamp(ops_df["Fecha_Operacion"].min()).strftime("%Y-%m-%d")
    fecha_fin = pd.Timestamp(ops_df["Fecha_Operacion"].max()).strftime("%Y-%m-%d")
    monedas = sorted(set(ops_df["Divisa"].dropna()).intersection(SERIES_FIX.values()))
    fix_data: dict[str, pd.Series] = {}
    fuentes: dict[str, str] = {}
    avisos = []

    if f_fix is not None:
        try:
            fix_data.update(_fix_cache(_archivos_fix(f_fix), "seccion-divisas-v2"))
            fuentes.update({moneda: "Archivo FIX cargado" for moneda in fix_data})
        except (KeyError, TypeError, ValueError, OSError) as exc:
            avisos.append(f"No se pudo leer el archivo FIX ({exc})")

    faltantes = [
        moneda for moneda in monedas
        if not _referencia_completa(ops_df.loc[ops_df["Divisa"].eq(moneda)], fix_data.get(moneda))
    ]
    token = _token_banxico()
    if faltantes and token:
        try:
            series_banxico = _consultar_fix_banxico(token, fecha_inicio, fecha_fin)
            for moneda in faltantes:
                serie = series_banxico.get(moneda)
                if serie is not None and not serie.empty:
                    fix_data[moneda], fuentes[moneda] = _combinar_referencias(
                        fix_data.get(moneda), serie, fuentes.get(moneda), "Banxico SIE (FIX oficial)"
                    )
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            avisos.append(f"Falló la consulta al SIE de Banxico ({exc})")

    faltantes = [
        moneda for moneda in monedas
        if not _referencia_completa(ops_df.loc[ops_df["Divisa"].eq(moneda)], fix_data.get(moneda))
    ]
    for moneda in faltantes:
        try:
            serie = _frankfurter_cache(moneda, fecha_inicio, fecha_fin)
            if not serie.empty:
                fix_data[moneda], fuentes[moneda] = _combinar_referencias(
                    fix_data.get(moneda), serie, fuentes.get(moneda), "Frankfurter (referencia de mercado)"
                )
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            avisos.append(f"Falló Frankfurter para {moneda} ({exc})")

    faltantes = [
        moneda for moneda in monedas
        if not _referencia_completa(ops_df.loc[ops_df["Divisa"].eq(moneda)], fix_data.get(moneda))
    ]
    for moneda in faltantes:
        try:
            serie = _consultar_yfinance(moneda, fecha_inicio, fecha_fin)
            if not serie.empty:
                fix_data[moneda], fuentes[moneda] = _combinar_referencias(
                    fix_data.get(moneda), serie, fuentes.get(moneda), "Yahoo Finance (referencia de mercado)"
                )
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            avisos.append(f"Falló Yahoo Finance para {moneda} ({exc})")

    fuentes_usadas = list(dict.fromkeys(fuentes.values()))
    fuente = ", ".join(fuentes_usadas) if fuentes_usadas else "Sin referencia disponible"
    return fix_data, fuente, "; ".join(avisos)


def cruzar_fix(ops_df: pd.DataFrame, fix_data: dict[str, pd.Series]) -> pd.DataFrame:
    """Agrega TC_FIX, spread y costo cambiario, usando el valor previo hasta siete días."""
    if ops_df.empty:
        return ops_df.copy()
    partes = []
    for moneda, operaciones in ops_df.groupby("Divisa", sort=False, dropna=False):
        operaciones = operaciones.copy()
        serie_fix = fix_data.get(moneda)
        if serie_fix is None or serie_fix.empty:
            operaciones["TC_FIX"] = float("nan")
            partes.append(operaciones)
            continue
        serie_fix = pd.to_numeric(serie_fix, errors="coerce").dropna().sort_index()
        serie_fix.index = pd.DatetimeIndex(serie_fix.index).astype("datetime64[ns]")
        serie_fix = serie_fix.loc[~serie_fix.index.duplicated(keep="last")]
        if serie_fix.empty:
            operaciones["TC_FIX"] = float("nan")
            partes.append(operaciones)
            continue
        operaciones["Fecha_Operacion"] = pd.to_datetime(operaciones["Fecha_Operacion"]).astype("datetime64[ns]")
        cruzadas = pd.merge_asof(
            operaciones.sort_values("Fecha_Operacion"),
            serie_fix.rename("TC_FIX"),
            left_on="Fecha_Operacion",
            right_index=True,
            direction="backward",
            tolerance=pd.Timedelta(days=DIAS_MAX_FFILL_FIX),
        )
        partes.append(cruzadas)
    resultado = pd.concat(partes, ignore_index=True).sort_values("Fecha_Operacion", kind="stable").reset_index(drop=True)
    resultado["Spread_MXN"] = resultado["TC_Facturado"] - resultado["TC_FIX"]
    resultado["Spread_Pct"] = resultado["Spread_MXN"].div(resultado["TC_FIX"]).mul(100)
    resultado["Sobreprecio_Total_MXN"] = resultado["Monto_Divisa"] * resultado["Spread_MXN"]
    return resultado
