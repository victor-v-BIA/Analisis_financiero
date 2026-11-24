"""Consulta y normalización de series económicas del INEGI (API BIE-BISE 2.0)."""

import math
import os
import re

import requests
import streamlit as st

from config import ESTADOS_INEGI, INDICADORES_ITAEE, INDICADOR_INPC_NACIONAL

_INEGI_URL = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR"
_TAMANO_LOTE_INEGI = 3


def _token_inegi() -> str | None:
    token = os.environ.get("INEGI_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("inegi_token")
    except (FileNotFoundError, KeyError):
        return None


def _ids_indicador(valor: str | tuple[str, ...]) -> tuple[str, ...]:
    return (valor,) if isinstance(valor, str) else tuple(str(i).strip() for i in valor)


def parsear_respuesta_itaee(
    respuesta: dict,
    mapa_indicadores: dict[str, tuple[str, ...]],
) -> dict[str, dict[str, dict[int, float]]]:
    """Convierte el JSON de BIE-BISE en {clave_estado: {sector: {año: índice_anual}}}."""
    id_a_sector = {
        ind_id: nombre
        for nombre, ids in mapa_indicadores.items()
        for ind_id in _ids_indicador(ids)
    }
    # Indexa por periodo (AAAA/TT) para evitar promediar dos veces un mismo trimestre
    acumulado: dict[str, dict[str, dict[int, dict[str, float]]]] = {}

    for serie in respuesta.get("Series", []):
        indicador = str(serie.get("INDICADOR", "")).strip()
        sector = id_a_sector.get(indicador)
        if sector is None:
            continue

        for obs in serie.get("OBSERVATIONS", []):
            cober_raw = str(obs.get("COBER_GEO", "")).strip()
            clave_estado = cober_raw.zfill(2) if cober_raw.isdigit() else cober_raw
            if clave_estado not in ESTADOS_INEGI:
                continue

            periodo = str(obs.get("TIME_PERIOD", "")).strip()
            coincidencia = re.match(r"^(\d{4})(?:/\d{1,2})?$", periodo)
            if coincidencia is None:
                continue
            anio = int(coincidencia.group(1))

            valor_raw = obs.get("OBS_VALUE")
            if valor_raw is None or str(valor_raw).strip() == "":
                continue
            try:
                valor = float(valor_raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(valor):
                continue

            (
                acumulado.setdefault(clave_estado, {})
                .setdefault(sector, {})
                .setdefault(anio, {})[periodo]
            ) = valor

    orden_sectores = list(mapa_indicadores.keys())
    resultado: dict[str, dict[str, dict[int, float]]] = {}
    for clave_estado, sectores in acumulado.items():
        sectores_ordenados: dict[str, dict[int, float]] = {}
        for sector in orden_sectores:
            anios = sectores.get(sector)
            if anios:
                sectores_ordenados[sector] = {
                    anio: sum(periodos.values()) / len(periodos)
                    for anio, periodos in sorted(anios.items())
                }
        if sectores_ordenados:
            resultado[clave_estado] = sectores_ordenados
    return resultado


def _peticion_inegi(
    session: requests.Session,
    ids: list[str],
    token: str,
    area: str = "0",
) -> dict:
    url = f"{_INEGI_URL}/{','.join(ids)}/es/{area}/false/BIE-BISE/2.0/{token}"
    respuesta = session.get(url, params={"type": "json"}, timeout=25)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise ValueError("Respuesta inesperada de la API del INEGI.")
    return datos


@st.cache_data(ttl=86400, show_spinner="Consultando ITAEE en INEGI...")
def _consultar_itaee_cache(
    token: str,
    indicadores: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, dict[str, dict[int, float]]]:
    mapa = {nombre: _ids_indicador(ids) for nombre, ids in indicadores}
    todos_ids = [ind_id for ids in mapa.values() for ind_id in ids]
    series_combinadas: list[dict] = []

    with requests.Session() as session:
        for i in range(0, len(todos_ids), _TAMANO_LOTE_INEGI):
            lote = todos_ids[i:i + _TAMANO_LOTE_INEGI]
            try:
                datos = _peticion_inegi(session, lote, token)
                series_combinadas.extend(datos.get("Series", []))
            except (requests.RequestException, ValueError):
                for ind_id in lote:
                    try:
                        parcial = _peticion_inegi(session, [ind_id], token)
                        series_combinadas.extend(parcial.get("Series", []))
                    except (requests.RequestException, ValueError):
                        continue

    if not series_combinadas:
        raise ValueError("No se obtuvieron series válidas desde la API del INEGI.")
    return parsear_respuesta_itaee({"Series": series_combinadas}, mapa)


def obtener_itaee_por_estado() -> tuple[dict[str, dict[str, dict[int, float]]], str | None]:
    """Devuelve ({clave_estado: {sector: {año: índice}}}, aviso_error)."""
    token = _token_inegi()
    if not token:
        return {}, "No se encontró el token del INEGI (INEGI_TOKEN o st.secrets['inegi_token'])."
    if not INDICADORES_ITAEE:
        return {}, "No hay indicadores ITAEE configurados en INDICADORES_ITAEE."
    clave_cache = tuple((nombre, _ids_indicador(ids)) for nombre, ids in INDICADORES_ITAEE.items())
    try:
        datos = _consultar_itaee_cache(token, clave_cache)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {}, f"No se pudo consultar el ITAEE desde la API del INEGI ({exc})."
    if not datos:
        return {}, "La API del INEGI respondió sin observaciones válidas para los estados."
    return datos, None


def parsear_respuesta_inpc(respuesta: dict, indicador_id: str) -> dict[str, dict[int, float]]:
    """Convierte el JSON mensual del INPC Nacional en {'INPC Nacional': {año: promedio_anual}}."""
    acumulado: dict[int, dict[str, float]] = {}

    for serie in respuesta.get("Series", []):
        if str(serie.get("INDICADOR", "")).strip() != str(indicador_id).strip():
            continue
        for obs in serie.get("OBSERVATIONS", []):
            periodo = str(obs.get("TIME_PERIOD", "")).strip()
            coincidencia = re.match(r"^(\d{4})(?:/\d{1,2})?$", periodo)
            if coincidencia is None:
                continue
            anio = int(coincidencia.group(1))

            valor_raw = obs.get("OBS_VALUE")
            if valor_raw is None or str(valor_raw).strip() == "":
                continue
            try:
                valor = float(valor_raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(valor):
                continue

            acumulado.setdefault(anio, {})[periodo] = valor

    promedios = {
        anio: sum(periodos.values()) / len(periodos)
        for anio, periodos in sorted(acumulado.items())
        if periodos
    }
    return {"INPC Nacional": promedios} if promedios else {}


@st.cache_data(ttl=86400, show_spinner="Consultando INPC en INEGI...")
def _consultar_inpc_cache(token: str, indicador_id: str) -> dict[str, dict[int, float]]:
    with requests.Session() as session:
        datos = _peticion_inegi(session, [indicador_id], token, area="00")
    return parsear_respuesta_inpc(datos, indicador_id)


def obtener_inpc_nacional() -> tuple[dict[str, dict[int, float]], str | None]:
    """Devuelve ({'INPC Nacional': {año: promedio_anual}}, aviso_error)."""
    token = _token_inegi()
    if not token:
        return {}, "No se encontró el token del INEGI (INEGI_TOKEN o st.secrets['inegi_token'])."
    try:
        datos = _consultar_inpc_cache(token, INDICADOR_INPC_NACIONAL)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {}, f"error de conexión o lectura con la API del INEGI ({exc})"
    if not datos:
        return {}, "la API del INEGI respondió sin observaciones válidas para el INPC"
    return datos, None