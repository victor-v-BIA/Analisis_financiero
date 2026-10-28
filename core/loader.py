# Funciones de lectura, limpieza y caché (_cargar_base_cache, leer_facturas, etc.)
'''
Encargado de leer los archivos subidos (Excel/CSV), 
validar columnas, limpiar formatos de texto/fechas y gestionar la caché de Streamlit.
'''
import pandas as pd
import streamlit as st
from pyarrow import ArrowException
import io
import unicodedata
import re
import numpy as np
from pathlib import Path
from config import (CODIGO_VERSION, COLS_FACTURAS,
                    COLS_COMPLEMENTOS,COLS_COMPLEMENTOS_OPCIONALES,
                    COL_FECHA_REP,ANIOS_VENTANA, _MES_ABREV, DIAS_GRACIA_PPD,
                    RUTA_ITAEE_DEFAULT, RUTA_INPP_DEFAULT, RUTA_INPC_DEFAULT)

from utils import (_ArchivoMem, ContenidoArchivo, _norm, a_numero, a_fecha, buscar_columna)


def cargar_base(uploaded_file) -> pd.DataFrame:
    """Lector universal: Excel, CSV o Parquet, también para grupos de archivos homogéneos.

    La lectura vive en `_cargar_base_cache` (`st.cache_data`, indexada por nombre + contenido + versión del código): cada
    llamada devuelve una copia independiente del DataFrame y el archivo ya NO se vuelve a parsear en cada re-ejecución
    de la interfaz. Al leer del contenido en memoria no depende de la posición del cursor del archivo subido."""
    return _cargar_base_cache(uploaded_file.name, uploaded_file.getvalue(), CODIGO_VERSION)

def leer_archivo(nombre: str, contenido: ContenidoArchivo) -> pd.DataFrame:
    """Lee CSV, Excel o Parquet como texto; concatena grupos tras validar las columnas."""
    df = _leer_archivos_cache(nombre, contenido, True, CODIGO_VERSION)
    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.apply(lambda s: s.astype(str).str.strip())


def _partes_archivo(nombre: str, contenido: ContenidoArchivo) -> tuple[tuple[str, bytes], ...]:
    """Normaliza un archivo individual o el contenido serializable de un _ArchivoGrupo."""
    if (isinstance(contenido, tuple) and contenido
            and all(isinstance(parte, tuple) and len(parte) == 2 for parte in contenido)):
        return contenido
    return ((nombre, contenido),)


def _leer_csv(contenido: bytes, como_texto: bool) -> pd.DataFrame:
    if not como_texto:
        return pd.read_csv(io.BytesIO(contenido), encoding="utf-8")
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python",
                               encoding=codificacion)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo identificar la codificación del CSV.")


@st.cache_data(show_spinner=False)
def _leer_archivos_cache(nombre: str, contenido: ContenidoArchivo, como_texto: bool, version: str) -> pd.DataFrame:
    """Lee y concatena archivos con el mismo esquema, con caché compartida entre validación y procesamiento."""
    partes = _partes_archivo(nombre, contenido)
    tablas = []
    columnas_referencia = None
    nombre_referencia = None
    for nombre_parte, contenido_parte in partes:
        extension = Path(nombre_parte).suffix.lower()
        if extension == ".parquet":
            tabla = pd.read_parquet(io.BytesIO(contenido_parte), engine="pyarrow")
        elif extension in (".xlsx", ".xls", ".xlsb"):
            opciones = {"dtype": str} if como_texto else {}
            tabla = pd.read_excel(io.BytesIO(contenido_parte), engine="calamine", **opciones)
        else:
            tabla = _leer_csv(contenido_parte, como_texto)

        columnas = {_norm(col): col for col in tabla.columns}
        if len(columnas) != len(tabla.columns):
            raise ValueError(f"El archivo '{nombre_parte}' tiene encabezados repetidos o ambiguos.")
        if columnas_referencia is None:
            columnas_referencia = columnas
            nombre_referencia = nombre_parte
        elif columnas.keys() != columnas_referencia.keys():
            raise ValueError(
                f"El archivo '{nombre_parte}' no tiene las mismas columnas que '{nombre_referencia}'. "
                "Verifica que todas las partes pertenezcan a la misma base."
            )
        else:
            tabla = tabla.rename(columns={columna: columnas_referencia[normalizada]
                                          for normalizada, columna in columnas.items()})
        tablas.append(tabla)
    return pd.concat(tablas, ignore_index=True, sort=False)




def resolver_columnas(df: pd.DataFrame, requeridas: dict[str, list[str]],
                      opcionales: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Renombra a nombres canónicos tolerando acentos/mayúsculas; error claro si falta alguna requerida."""
    por_norm = {_norm(c): c for c in df.columns}
    mapa, faltantes = {}, []
    for canonico, variantes in requeridas.items():
        origen = next((por_norm[_norm(v)] for v in [canonico, *variantes] if _norm(v) in por_norm), None)
        if origen is None:
            faltantes.append(canonico)
        else:
            mapa[origen] = canonico
    for canonico, variantes in (opcionales or {}).items():
        origen = next((por_norm[_norm(v)] for v in [canonico, *variantes] if _norm(v) in por_norm), None)
        if origen is not None:
            mapa[origen] = canonico
    if faltantes:
        raise KeyError(f"Faltan columnas: {faltantes}. Columnas encontradas: {list(df.columns)}")
    return df.rename(columns=mapa)


def validar_columnas(columnas, requeridas: dict[str, list[str]], etiqueta: str) -> None:
    """Hard stop explícito de columnas (por concepto, tolerante a variantes/acentos/mayúsculas vía _norm()).

    Comprobación de conjuntos: si NINGUNA variante de un concepto requerido está en `columnas`, se aborta de
    inmediato con un st.error() visual y st.stop() -antes de intentar cualquier cálculo-, en vez de dejar que
    el error aparezca más abajo como una excepción de Python o como tarjetas en $0.
    """
    normalizadas = {_norm(c) for c in columnas}
    faltantes = [concepto for concepto, variantes in requeridas.items()
                if not any(_norm(v) in normalizadas for v in [concepto, *variantes])]
    if faltantes:
        st.error(f"🚨 Error en el archivo de {etiqueta}: Faltan las siguientes columnas requeridas para el "
                 f"cálculo: {faltantes}")
        st.stop()

def leer_facturas(nombre: str, contenido: ContenidoArchivo) -> tuple[pd.DataFrame, list[str]]:
    """Facturas emitidas: Activo/Vigente + (Factura o NCR); Fecha sin hora; PUE/PPD; Total numérico (una fila por UUID).

    Se conservan las Notas de Crédito (Tipo Documento = 'NCR') con la bandera `Es_NCR`, para poder calcular el
    Ingreso Neto sin mezclarlas con la Facturación Total.
    """
    avisos: list[str] = []
    df = resolver_columnas(leer_archivo(nombre, contenido), COLS_FACTURAS)
    n0 = len(df)

    # contains() en vez de igualdad estricta: tolera variantes como "NCR", "01-NCR" o "Nota NCR", además de
    # espacios o mayúsculas distintas, que con una igualdad exacta habrían descartado la fila en silencio.
    tipo_crudo = df["Tipo Documento"].astype(str)
    es_ncr_crudo = tipo_crudo.str.contains("NCR", case=False, na=False)
    n_ncr_crudo = int(es_ncr_crudo.sum())
    es_factura = tipo_crudo.str.strip().str.upper() == "FACTURA"
    estatus = df["Estatus"].astype(str).str.strip().str.upper()
    df = df[estatus.isin(["ACTIVO", "VIGENTE"]) & (es_factura | es_ncr_crudo)]
    df = df.assign(Es_NCR=df["Tipo Documento"].astype(str).str.contains("NCR", case=False, na=False))
    avisos.append(f"Facturas: {n0} filas leídas, {len(df)} con Estatus 'Activo' y Tipo 'Factura' o 'NCR' "
                  f"({n_ncr_crudo} NCR detectadas en el archivo, {int(df['Es_NCR'].sum())} tras el filtro).")

    df = df.assign(Fecha=a_fecha(df["Fecha y Hora"]), Total=a_numero(df["Total"]),
                   Metodo_Pago=df["Metodo de Pago"].str.upper())

    ilegibles = df["Fecha"].isna() | df["Total"].isna()
    if ilegibles.any():
        n_ncr_perdidas = int((ilegibles & df["Es_NCR"]).sum())
        avisos.append(f"Facturas: {ilegibles.sum()} filas con fecha/total ilegible descartadas"
                      + (f" ({n_ncr_perdidas} de ellas eran NCR)." if n_ncr_perdidas else "."))
        df = df[~ilegibles]

    otro_metodo = ~df["Es_NCR"] & ~df["Metodo_Pago"].isin(["PUE", "PPD"])   # las NCR se conservan sin importar el método
    if otro_metodo.any():
        n_ncr_perdidas = int((otro_metodo & df["Es_NCR"]).sum())
        avisos.append(f"Facturas: {otro_metodo.sum()} filas con método distinto de PUE/PPD descartadas "
                      f"({df.loc[otro_metodo, 'Metodo_Pago'].unique().tolist()})"
                      + (f", {n_ncr_perdidas} de ellas NCR." if n_ncr_perdidas else "."))
        df = df[~otro_metodo]

    dup = df["UUID"].duplicated()
    if dup.any():
        n_ncr_perdidas = int((dup & df["Es_NCR"]).sum())
        avisos.append(f"Facturas: {dup.sum()} UUID duplicados eliminados"
                      + (f" ({n_ncr_perdidas} de ellos NCR)." if n_ncr_perdidas else "."))
        df = df[~dup]
    if df["Es_NCR"].any():
        avisos.append(f"Facturas: {int(df['Es_NCR'].sum())} Notas de Crédito (NCR) válidas para el análisis, "
                      f"por ${df.loc[df['Es_NCR'], 'Total'].abs().sum():,.2f} (magnitud absoluta).")

    # Si un mismo RFC trae varios nombres, la columna no es el nombre del emisor (p. ej. es el del cliente).
    n_nombres = df.groupby("RFC Emisor")["Nombre Emisor"].nunique()
    ambiguos = n_nombres[n_nombres > 1].index
    if len(ambiguos):
        avisos.append("Facturas: la columna de nombre trae varios valores para un mismo RFC Emisor "
                      "(parece ser el nombre del cliente, no el de la empresa); se identifica solo por RFC.")
        df = df.assign(**{"Nombre Emisor": df["Nombre Emisor"].where(~df["RFC Emisor"].isin(ambiguos), "")})

    # Cliente (receptor): columnas OPCIONALES que solo usa el Índice de Concentración del Dashboard Ejecutivo; el resto de
    # los consumidores ignora estas columnas extra. No altera filtros ni importes.
    col_rfc_receptor = buscar_columna(df.columns, "RFC Receptor")
    col_nombre_receptor = next((c for c in (buscar_columna(df.columns, n) for n in (
        "Razon Social Receptor", "Nombre Receptor", "Razon Social Cliente", "Razon Social.1")) if c), None)
    columnas = ["UUID", "Fecha", "RFC Emisor", "Nombre Emisor", "Metodo_Pago", "Total", "Es_NCR"]
    renombres = {"RFC Emisor": "RFC_Emisor", "Nombre Emisor": "Nombre_Emisor"}
    for col, nuevo in ((col_rfc_receptor, "RFC_Receptor"), (col_nombre_receptor, "Nombre_Receptor"),
                       (buscar_columna(df.columns, "Forma de Pago"), "Forma_Pago")):   # Forma de Pago: solo la usa la mezcla por forma de pago
        if col is not None and col not in columnas:
            columnas.append(col)
            renombres[col] = nuevo
    df = (df[columnas].rename(columns=renombres)
          .sort_values("Fecha", kind="stable").reset_index(drop=True))
    return df, avisos


def leer_facturas_egresos(nombre: str, contenido: ContenidoArchivo) -> tuple[pd.DataFrame, list[str]]:
    """Facturación recibida (Egresos): candados exactos confirmados por el usuario, sumatoria bruta (sin restas).

    Único criterio de vigencia: Estatus (limpio, en mayúsculas) igual a 'VIGENTE' o 'ACTIVO'. Único criterio de
    tipo: Tipo Documento (limpio, en mayúsculas) estrictamente igual a 'FACTURA' o 'NCR' -ya no se aceptan
    códigos SAT sueltos como 'I': la base real usa texto, y adivinar códigos de más solo arriesgaba excluir
    filas válidas-. Las NCR se conservan con la bandera `Es_NCR` (para el impacto de Notas de Crédito en
    Egresos) pero NO se exigen PUE/PPD válidos en esas filas, ya que muchas bases no lo llenan en un crédito.
    Temporalidad = Fecha y Hora (fecha de emisión del CFDI recibido). Total: se limpian '$' y ',' antes de
    convertir a numérico; lo no convertible se trata como 0 (no se descarta la fila completa, para no perder
    del conteo una fila por lo demás válida). Sin restas ni cruces adicionales aquí: es la sumatoria bruta de
    Total agrupable por Año (la resta de NCR se hace más arriba, en el módulo).
    """
    avisos: list[str] = []
    df = resolver_columnas(leer_archivo(nombre, contenido), COLS_FACTURAS)
    n0 = len(df)

    estatus_limpio = df["Estatus"].astype(str).str.strip().str.upper()
    vigente = estatus_limpio.isin(["VIGENTE", "ACTIVO"])
    if (~vigente).any():
        avisos.append(f"Facturación recibida: {int((~vigente).sum())} filas excluidas por Estatus distinto de "
                      f"'Vigente'/'Activo' {sorted(df.loc[~vigente, 'Estatus'].astype(str).unique().tolist())[:10]}.")
    df = df[vigente]

    tipo_limpio = df["Tipo Documento"].astype(str).str.strip().str.upper()
    es_factura = tipo_limpio == "FACTURA"
    es_ncr = tipo_limpio == "NCR"
    excluidos_tipo = ~(es_factura | es_ncr)
    if excluidos_tipo.any():
        avisos.append(f"Facturación recibida: {int(excluidos_tipo.sum())} filas excluidas por Tipo Documento "
                      f"distinto de 'Factura'/'NCR' "
                      f"{sorted(df.loc[excluidos_tipo, 'Tipo Documento'].astype(str).unique().tolist())[:10]}.")
    df = df.assign(Es_NCR=es_ncr)[~excluidos_tipo]
    avisos.append(f"Facturación recibida: {n0} filas leídas, {len(df)} vigentes de Tipo 'Factura'/'NCR' "
                  f"({int(df['Es_NCR'].sum())} NCR).")

    total_limpio = df["Total"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    df = df.assign(Fecha=a_fecha(df["Fecha y Hora"]),
                   Total=pd.to_numeric(total_limpio, errors="coerce").fillna(0.0),
                   Metodo_Pago=df["Metodo de Pago"].str.upper())

    fecha_ilegible = df["Fecha"].isna()
    if fecha_ilegible.any():
        avisos.append(f"Facturación recibida: {int(fecha_ilegible.sum())} filas con Fecha y Hora ilegible "
                      "descartadas (no se pueden ubicar en un ejercicio fiscal).")
        df = df[~fecha_ilegible]

    # Las NCR no se filtran por Método de Pago: muchas bases no lo llenan en un crédito y no deben perderse.
    otro_metodo = ~df["Es_NCR"] & ~df["Metodo_Pago"].isin(["PUE", "PPD"])
    if otro_metodo.any():
        avisos.append(f"Facturación recibida: {int(otro_metodo.sum())} filas con método distinto de PUE/PPD "
                      f"descartadas ({df.loc[otro_metodo, 'Metodo_Pago'].unique().tolist()}).")
        df = df[~otro_metodo]

    dup = df["UUID"].duplicated()
    if dup.any():
        avisos.append(f"Facturación recibida: {int(dup.sum())} UUID duplicados eliminados.")
        df = df[~dup]

    col_forma = buscar_columna(df.columns, "Forma de Pago")
    # Factor_MXN: 1 si la factura es en MXN (o no trae 'Moneda'); el Tipo de Cambio si es moneda extranjera; NaN si es extranjera sin Tipo de Cambio
    # válido (no se puede convertir). Solo lo usa `facturas_a_mxn` (Módulo de Egresos): el Total sigue en su moneda original para el resto del tablero.
    col_moneda, col_tc = buscar_columna(df.columns, "Moneda"), buscar_columna(df.columns, "Tipo de Cambio")
    moneda = df[col_moneda].astype(str).str.strip().str.upper() if col_moneda is not None else pd.Series("MXN", index=df.index)
    es_mxn = moneda.isin(["MXN", "PESOS", "PESO MEXICANO", "NAN", ""])
    tipo_cambio = a_numero(df[col_tc]) if col_tc is not None else pd.Series(1.0, index=df.index)
    df = df.assign(Factor_MXN=tipo_cambio.where(~es_mxn, 1.0).where(es_mxn | (tipo_cambio > 0)))
    col_serie = buscar_columna(df.columns, "Serie")
    df["Serie"] = df[col_serie].fillna("").astype(str).str.strip() if col_serie else ""
    col_iva_total = buscar_columna(df.columns, "IVA Trasladado")
    columnas_iva = ([col_iva_total] if col_iva_total is not None else [
        col for col in df.columns
        if "iva" in _norm(col) and "reten" not in _norm(col) and "retencion" not in _norm(col)
    ])
    if columnas_iva:
        df["IVA_Trasladado"] = df[columnas_iva].apply(
            lambda columna: a_numero(columna).fillna(0.0)
        ).sum(axis=1)
    columnas_salida = ["UUID", "Fecha", "RFC Emisor", "Nombre Emisor", "Metodo_Pago", "Total",
                       "Es_NCR", "Factor_MXN", "Serie"]
    if columnas_iva:
        columnas_salida.append("IVA_Trasladado")
    if col_forma is not None:
        columnas_salida.append(col_forma)
    df = (df[columnas_salida]
          .rename(columns={"RFC Emisor": "RFC_Emisor", "Nombre Emisor": "Nombre_Emisor", **({col_forma: "Forma_Pago"} if col_forma else {})})
          .sort_values("Fecha", kind="stable").reset_index(drop=True))
    return df, avisos


def leer_complementos(nombre: str, contenido: ContenidoArchivo) -> tuple[pd.DataFrame, list[str]]:
    """Complementos de pago: Fecha_Cobro (sin hora) y Cobro Efectivo = Saldo Inicial - Saldo Final.

    Fecha_Cobro = 'Fecha de Pago' del complemento.
    """
    avisos: list[str] = []
    etiqueta = f"Complementos de pago ({nombre})"
    df = resolver_columnas(leer_archivo(nombre, contenido), {**COLS_COMPLEMENTOS, **COL_FECHA_REP},
                           COLS_COMPLEMENTOS_OPCIONALES)
    n0 = len(df)
    if "Estatus" in df.columns:
        estatus = df["Estatus"].astype(str).str.strip().str.upper()
        df = df[estatus.isin(["ACTIVO", "VIGENTE"])]
        avisos.append(f"{etiqueta}: {n0 - len(df)} filas descartadas por Estatus distinto de "
                      "'Activo'/'Vigente'.")
    if "RFC Emisor" not in df.columns:
        df = df.assign(**{"RFC Emisor": ""})
        avisos.append(f"{etiqueta}: la base no trae 'RFC Emisor'; los cobros no se pueden filtrar por RFC.")
    if "UUID DR" not in df.columns:   # factura relacionada (opcional): solo la usa la depuración de complementos ligados a PUE
        df = df.assign(**{"UUID DR": ""})

    col_fecha = next(iter(COL_FECHA_REP))
    df = df.assign(Fecha_Cobro=a_fecha(df[col_fecha]),
                   Saldo_Inicial=a_numero(df["Saldo Inicial"]),
                   Saldo_Final=a_numero(df["Saldo Final"]))
    ilegibles = df["Fecha_Cobro"].isna() | df["Saldo_Inicial"].isna() | df["Saldo_Final"].isna()
    if ilegibles.any():
        avisos.append(f"{etiqueta}: {ilegibles.sum()} filas con '{col_fecha}' o saldos ilegibles descartadas.")
        df = df[~ilegibles]

    df = df.assign(Cobro_Efectivo=(df["Saldo_Inicial"] - df["Saldo_Final"]).round(2))
    negativos = df["Cobro_Efectivo"] < 0
    if negativos.any():
        avisos.append(f"{etiqueta}: {negativos.sum()} filas con Saldo Final mayor al Saldo Inicial "
                      f"(cobro negativo de ${df.loc[negativos, 'Cobro_Efectivo'].sum():,.2f}); se conservan.")
    avisos.append(f"{etiqueta}: {n0} filas leídas, {len(df)} válidas, {df['UUID'].nunique()} complementos únicos "
                  f"(fecha que rige: {col_fecha}).")

    col_forma = buscar_columna(df.columns, "Forma de Pago")
    df = df.assign(Forma_Pago=df[col_forma] if col_forma is not None else "")   # opcional: solo la usa la mezcla por forma de pago
    df = (df[["UUID", "RFC Emisor", "Fecha_Cobro", "Saldo_Inicial", "Saldo_Final", "Cobro_Efectivo", "UUID DR", "Forma_Pago"]]
          .rename(columns={"RFC Emisor": "RFC_Emisor", "UUID DR": "UUID_DR"})
          .assign(UUID_DR=lambda d: d["UUID_DR"].astype(str).str.strip().str.upper())
          .sort_values("Fecha_Cobro", kind="stable").reset_index(drop=True))
    return df, avisos


def preparar_complementos_egresos(df_rep: pd.DataFrame, col_monto: str, col_fecha: str) -> pd.DataFrame:
    """Complementos de Egresos (Base PAGO) con 'Monto_Num' (Monto MXN limpio, ya en MXN), 'Año' y 'Mes'
    de su PROPIA columna de fecha (Fecha Pago), con `a_fecha()`
    (DD/MM/YYYY o ISO). Es el cálculo ÚNICO de complementos anuales de Egresos: lo usan `modulo_egresos()` y la
    primera sección del Dashboard Ejecutivo, para que sus importes nunca diverjan."""
    df_rep = df_rep.copy()
    df_rep["Monto_Num"] = pd.to_numeric(
        df_rep[col_monto].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce").fillna(0)
    fechas = a_fecha(df_rep[col_fecha])
    df_rep["Año"] = fechas.dt.year
    df_rep["Mes"] = fechas.dt.to_period("M")
    return df_rep

def obtener_anios_analisis(df_emitidos=None, df_recibidos=None) -> list[int]:
    """Ventana móvil estándar de 5 años consecutivos: `list(range(anio_max - 4, anio_max + 1))`, donde `anio_max` es el
    año máximo de emisión de las facturas activas de Emitidos (Ingresos) y Recibidos (Egresos). Acepta las salidas de
    `leer_facturas` / `leer_facturas_egresos` (columna `Fecha`, ya filtradas a Activo/Vigente) o las bases crudas
    (`Fecha y Hora`, con `Estatus` si existe). Cualquiera de las dos puede ser None; sin facturas devuelve []."""
    maximos = []
    for df in (df_emitidos, df_recibidos):
        if df is None or len(df) == 0:
            continue
        if "Fecha" in df.columns:
            fechas = df["Fecha"]
        elif "Fecha y Hora" in df.columns:
            activas = df
            if "Estatus" in df.columns:
                activas = df[df["Estatus"].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])]
            fechas = a_fecha(activas["Fecha y Hora"])
        else:
            continue
        if fechas.notna().any():
            maximos.append(int(fechas.dt.year.max()))
    if not maximos:
        return []
    anio_max = max(maximos)
    return list(range(anio_max - (ANIOS_VENTANA - 1), anio_max + 1))


def excluir_años_incompletos(df: pd.DataFrame, col_fecha: str, etiqueta: str,
                             anios: list[int] | tuple[int, ...] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Conserva SOLO los registros cuyo año en `col_fecha` pertenece a la ventana de análisis `anios` (`anios_5`) y
    descarta el resto: p. ej. un complemento pagado en dic-2020 o en ene-2026 no crea barras fuera de los 5 años.
    Sin `anios` usa los 5 años que terminan en el año máximo de `col_fecha` (uso directo); con `anios` vacío no filtra."""
    if anios is None:
        mx = df[col_fecha].dt.year.max() if len(df) else None
        anios = [] if mx is None or pd.isna(mx) else list(range(int(mx) - (ANIOS_VENTANA - 1), int(mx) + 1))
    if not len(anios):
        return df, []
    fuera = ~df[col_fecha].dt.year.isin([int(a) for a in anios])
    if not fuera.any():
        return df, []
    monto = next(c for c in ("Total", "Importe", "Cobro_Efectivo") if c in df.columns)
    return df[~fuera].reset_index(drop=True), [
        f"{etiqueta}: {int(fuera.sum())} filas (${df.loc[fuera, monto].sum():,.2f}) fuera de la ventana de análisis "
        f"{min(anios)}–{max(anios)} descartadas."]

def anios_5_archivos(f_emitidos, f_recibidos) -> tuple:
    """`anios_5` (ventana móvil de 5 años) a partir de los archivos subidos de facturas emitidas y recibidas (o None)."""
    return _anios_analisis_cache(None if f_emitidos is None else (f_emitidos.name, f_emitidos.getvalue()),
                                 None if f_recibidos is None else (f_recibidos.name, f_recibidos.getvalue()),
                                 CODIGO_VERSION)


def _preparar_nomina(df_nomina: pd.DataFrame) -> pd.DataFrame | None:
    """Nómina: comprobantes activos/vigentes; fecha = Pago, Pago alternativo o Certificación; monto = 'Total'.
    Devuelve Año, Mes (1-12), Periodo ('AAAA-MM') y Monto, o `None` si faltan la fecha o la columna Total."""
    c_est = buscar_columna(df_nomina.columns, "Estatus")
    c_fecha = (buscar_columna(df_nomina.columns, "Fecha Pago")
               or buscar_columna(df_nomina.columns, "Fecha de Pago")
               or buscar_columna(df_nomina.columns, "Fecha de Certificación"))
    c_monto = buscar_columna(df_nomina.columns, "Total")
    if c_fecha is None or c_monto is None:
        return None
    d = df_nomina
    if c_est is not None:
        d = d[d[c_est].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])]
    f = a_fecha(d[c_fecha])
    out = pd.DataFrame({"Año": f.dt.year, "Mes": f.dt.month, "Periodo": f.dt.strftime("%Y-%m"), "Monto": a_numero(d[c_monto]).fillna(0.0)}).dropna(subset=["Año"])
    return out.astype({"Año": int, "Mes": int})


def _hojas_crudas(nombre: str, contenido: bytes) -> list[pd.DataFrame]:
    """Tablas de un Excel, Parquet o CSV para inspeccionar bases económicas."""
    if nombre.lower().endswith(".parquet"):
        return [pd.read_parquet(io.BytesIO(contenido), engine="pyarrow")]
    try:
        if nombre.lower().endswith(".csv"):
            for codificacion in ("utf-8-sig", "latin-1"):
                try:
                    return [pd.read_csv(io.BytesIO(contenido), header=None, dtype=str, sep=None, engine="python",
                                        encoding=codificacion)]
                except UnicodeDecodeError:
                    continue
            return []
        try:
            libro = pd.ExcelFile(io.BytesIO(contenido), engine="calamine")
            return [libro.parse(h, header=None) for h in libro.sheet_names]
        except Exception:
            return pd.read_html(io.BytesIO(contenido), header=None)
    except Exception:
        return []


def _texto_col0(df: pd.DataFrame) -> pd.Series:
    return df.iloc[:, 0].fillna("").astype(str).str.strip()


def _leer_itaee(df: pd.DataFrame) -> dict | None:
    """ITAEE (tabulado del INEGI): ubica la fila de periodos con 'Anual' y, en el bloque «Índice de volumen físico», toma por cada fila (sector)
    las columnas anuales con el año de la fila de encabezado (sin sufijos R / P). Devuelve {sector: {año: índice}} | None si no es un ITAEE."""
    etiquetas = _texto_col0(df)
    ini = next((i for i in range(len(df)) if "ndice de volumen f" in etiquetas.iloc[i]), None)
    fila_per = next((i for i in range(len(df)) if (df.iloc[i].fillna("").astype(str).str.strip() == "Anual").any()), None)
    if ini is None or fila_per is None or fila_per < 1:
        return None
    anios = df.iloc[fila_per - 1].ffill()
    cols = {}
    for c in range(1, df.shape[1]):
        if str(df.iloc[fila_per, c]).strip() == "Anual":
            m = re.search(r"(\d{4})", str(anios.iloc[c]))
            if m:
                cols[c] = int(m.group(1))
    fin = next((i for i in range(ini + 1, len(df)) if etiquetas.iloc[i].lower().startswith("variaci")), len(df))
    salida = {}
    for r in range(ini + 1, fin):
        valores = {a: float(v) for c, a in cols.items() if pd.notna(v := pd.to_numeric(df.iloc[r, c], errors="coerce"))}
        if valores and etiquetas.iloc[r]:
            salida[etiquetas.iloc[r]] = valores
    return salida or None


def _leer_inpp(df: pd.DataFrame) -> dict | None:
    """INPP (consulta del INEGI): fila 'Fecha' con el código de cada serie, fila 'Título' con su nombre y filas 'Mes Año'. Si la información es
    'Inflación mensual' (variaciones %), cada serie se convierte en un índice compuesto (`cumprod` de 1 + var/100); si ya son índices se
    usan tal cual. Se promedia por año. Devuelve {nombre de la serie: {año: índice}} | None si no es un INPP."""
    primera = _texto_col0(df)
    fila_cod = next((i for i in range(len(df)) if primera.iloc[i] == "Fecha"), None)
    if fila_cod is None:
        return None
    cuerpo = df.iloc[fila_cod + 1:]
    fechas = cuerpo.iloc[:, 0].fillna("").astype(str).str.strip().str.extract(r"^([A-Za-zñÑ]{3})\w*\.?\s+(\d{4})$")
    valido = fechas[0].notna() & fechas[0].str.lower().isin(_MES_ABREV)
    if int(valido.sum()) < 3:
        return None
    mes = fechas.loc[valido, 0].str.lower().map(_MES_ABREV)
    anio = fechas.loc[valido, 1].astype(int)
    orden = (anio * 100 + mes).sort_values().index
    fila_tit = next((i for i in range(len(df)) if primera.iloc[i].lower().startswith("t") and "tulo" in primera.iloc[i].lower()), None)
    fila_tipo = next((i for i in range(len(df)) if primera.iloc[i].lower().startswith("tipo de informaci")), None)
    mensual = fila_tipo is not None and "mensual" in str(df.iloc[fila_tipo, 1]).lower()
    marca = "según actividad económica,"
    salida = {}
    for c in range(1, df.shape[1]):
        codigo = str(df.iloc[fila_cod, c]).strip()
        titulo = str(df.iloc[fila_tit, c]).strip() if fila_tit is not None else ""
        nombre = titulo.split(marca, 1)[1].strip() if marca in titulo else (titulo or codigo)
        nombre = nombre if nombre not in salida else f"{nombre} ({codigo})"
        valores = pd.to_numeric(cuerpo.loc[orden, c], errors="coerce")
        indice = (1 + valores / 100).cumprod() if mensual else valores
        promedio = indice.groupby(anio.loc[orden].to_numpy()).mean()
        serie = {int(a): float(v) for a, v in promedio.items() if pd.notna(v)}
        if serie:
            salida[nombre] = serie
    return salida or None


def _leer_inpc(df: pd.DataFrame) -> dict | None:
    """Lee el índice nacional del INPC desde una tabla mensual del INEGI y devuelve promedios por año."""
    if df.empty or df.shape[1] < 2:
        return None
    primera = _texto_col0(df)
    fila_fecha = next((i for i, valor in enumerate(primera) if valor.casefold() == "fecha"), None)
    if fila_fecha is None:
        return None

    filas = []
    for i in range(fila_fecha + 1, len(df)):
        periodo = str(df.iloc[i, 0]).strip().lower()
        coincidencia = re.match(r"^([a-zñ]{3,})[-\s/](\d{2}|\d{4})$", periodo)
        if coincidencia is None:
            continue
        mes_txt, anio_txt = coincidencia.groups()
        mes = _MES_ABREV.get(mes_txt[:3])
        if mes is None:
            continue
        anio = int(anio_txt)
        if len(anio_txt) == 2:
            anio += 2000
        valor = pd.to_numeric(df.iloc[i, 1], errors="coerce")
        if pd.notna(valor):
            filas.append((anio, float(valor)))

    if not filas:
        return None
    promedios = pd.DataFrame(filas, columns=["Año", "INPC"]).groupby("Año")["INPC"].mean()
    return {"INPC Nacional": {int(anio): float(valor) for anio, valor in promedios.items()}}


def _anio_de_celda(v) -> int | None:
    """Año de una celda con fecha: número 1990–2100, 'aaaa', 'aaaa-mm-dd', 'dd/mm/aaaa', 'Mes aaaa' o fecha de Excel; None si no lo es."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year"):
        return int(v.year)
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() and 1990 <= int(v) <= 2100 else None
    s = str(v).strip()
    for patron in (r"^(\d{4})(?:\.0)?$", r"^(\d{4})[-/]\d{1,2}(?:[-/]\d{1,2})?", r"^\d{1,2}[/-]\d{1,2}[/-](\d{4})",
                   r"^[A-Za-zñÑ]{3}\w*\.?\s+(\d{4})$"):
        m = re.match(patron, s)
        if m and 1990 <= int(m.group(1)) <= 2100:
            return int(m.group(1))
    return None




def _leer_tabla_fecha_valor(df: pd.DataFrame) -> dict | None:
    """Serie económica genérica (p. ej. TIIE de Banxico): busca la columna de fechas y, en las demás columnas numéricas, promedia por año. Devuelve
    {nombre de la columna: {año: promedio}} | None si no hay una columna de fechas con valores numéricos. Es deliberadamente estricta para no
    confundir un reporte contable con una serie económica: tabla angosta (≤ 8 columnas) y valores tipo tasa (entre 0 y 100)."""
    if df.shape[1] > 8:
        return None
    for c_fecha in range(min(3, df.shape[1])):
        anios = df.iloc[:, c_fecha].map(_anio_de_celda)
        filas = anios.dropna().index
        if len(filas) < 2:
            continue
        r0 = filas[0]
        salida = {}
        for c in range(df.shape[1]):
            if c == c_fecha:
                continue
            vals = pd.to_numeric(df.iloc[filas, c].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False),
                                 errors="coerce")
            if vals.notna().mean() < 0.7 or not vals.dropna().between(0, 100).all():
                continue
            nombre = str(df.iloc[r0 - 1, c]).strip() if r0 >= 1 and pd.notna(df.iloc[r0 - 1, c]) else f"Serie {c + 1}"
            prom = vals.groupby(anios.loc[filas].astype(int).to_numpy()).mean()
            salida[nombre if nombre not in salida else f"{nombre} ({c + 1})"] = {int(a): float(v) for a, v in prom.items() if pd.notna(v)}
        if salida:
            return salida
    return None


@st.cache_data(show_spinner="Leyendo base económica...")
def _procesar_archivo_economico(nombre: str, contenido: bytes, version: str) -> dict:
    """Clasifica por contenido un archivo económico como ITAEE, INPP, INPC o TIIE.
    Devuelve {'tipo': str | None, 'series': {nombre de la serie: {año: valor}}}."""
    for df in _hojas_crudas(nombre, contenido):
        for tipo, lector in (("itaee", _leer_itaee), ("inpp", _leer_inpp), ("inpc", _leer_inpc),
                             ("tiie", _leer_tabla_fecha_valor)):
            try:
                series = lector(df)
            except Exception:
                series = None
            if series:
                return {"tipo": tipo, "series": series}
    return {"tipo": None, "series": {}}


def _cargar_bases_economicas(lado: str) -> dict:
    """Carga las bases económicas subidas o, si no hay ninguna, las predeterminadas de `data/`."""
    if lado not in ("ingresos", "egresos"):
        raise ValueError(f"El lado debe ser 'ingresos' o 'egresos', no {lado!r}.")

    pertinentes = ("itaee", "inpc", "tiie") if lado == "ingresos" else ("inpp", "inpc")
    texto = "ITAEE, INPC y/o TIIE" if lado == "ingresos" else "INPP y/o INPC"
    archivos = st.file_uploader(f"Carga las bases externas ({texto}) · Excel, CSV o Parquet",
                                type=["xlsx", "xls", "xlsb", "csv", "parquet"],
                                accept_multiple_files=True, key=f"eco_up_{lado}")
    entradas = [(f.name, f.getvalue()) for f in archivos or []]
    if not entradas:
        st.caption("Si no cargas archivos, se utilizan las bases predeterminadas. "
                   "Los archivos que subas sustituyen esas bases para esta vista.")
        base_proyecto = Path(__file__).resolve().parent.parent
        predeterminados = (
            (("itaee", RUTA_ITAEE_DEFAULT), ("inpc", RUTA_INPC_DEFAULT))
            if lado == "ingresos" else (("inpp", RUTA_INPP_DEFAULT),)
        )
        for tipo, ruta in predeterminados:
            archivo = base_proyecto / ruta
            try:
                entradas.append((archivo.name, archivo.read_bytes()))
            except OSError as exc:
                st.error(f"No se pudo leer la base económica predeterminada {archivo}: {exc}")

    series: dict = {}
    for nombre, contenido in entradas:
        try:
            r = _procesar_archivo_economico(nombre, contenido, CODIGO_VERSION)
        except (ArrowException, OSError, ValueError) as exc:
            st.error(f"No se pudo leer la base económica «{nombre}»: {exc}")
            continue
        if r["tipo"] is None:
            st.warning(f"No se reconoció el formato de «{nombre}» (se esperan una base de ITAEE, INPP, INPC o una serie "
                       "fecha-valor como la TIIE).")
        elif r["tipo"] not in pertinentes:
            st.info(f"«{nombre}» es una base de {r['tipo'].upper()}: cárgala en el módulo {'de Egresos' if lado == 'ingresos' else 'de Ingresos'}.")
        else:
            series.setdefault(r["tipo"], {}).update(r["series"])
    return series


# =============== FUNCIONES CON @st.cache_data

@st.cache_data(show_spinner="Procesando facturas…")
def _facturas_cache(nombre: str, contenido: ContenidoArchivo, version: str):
    return leer_facturas(nombre, contenido)


@st.cache_data(show_spinner="Procesando facturación recibida…")
def _facturas_egresos_cache(nombre: str, contenido: ContenidoArchivo, version: str):
    return leer_facturas_egresos(nombre, contenido)


@st.cache_data(show_spinner="Procesando complementos de pago…")
def _complementos_cache(nombre: str, contenido: ContenidoArchivo, version: str):
    return leer_complementos(nombre, contenido)


@st.cache_data(show_spinner=False)
def _columnas_archivo(nombre: str, contenido: ContenidoArchivo, version: str) -> list[str]:
    return list(leer_archivo(nombre, contenido).columns)


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _cargar_base_cache(nombre: str, contenido: ContenidoArchivo, version: str) -> pd.DataFrame:
    """Lectura cruda (Excel o CSV) de uno o varios archivos subidos, en caché."""
    return _leer_archivos_cache(nombre, contenido, False, version)


@st.cache_data(show_spinner=False)
def _anios_analisis_cache(fac_ing, fac_egr, version: str) -> tuple:
    """`obtener_anios_analisis` sobre las facturas de Emitidos (Ingresos) y Recibidos (Egresos), en caché."""
    def leer(lector, archivo):
        if archivo is None:
            return None
        try:
            return lector(archivo[0], archivo[1], version)[0]
        except KeyError:
            return None
    return tuple(obtener_anios_analisis(leer(_facturas_cache, fac_ing), leer(_facturas_egresos_cache, fac_egr)))

@st.cache_data(show_spinner="Procesando bases CFDI...")
def _anual_ppd_cache(lado: str, fac: tuple, rep: tuple, anios: tuple, version: str):
    """Sección 1: `anual_ppd_clientes` / `anual_ppd_proveedores` en caché -> (DataFrame | None, motivo | None)."""
    from core.finance_logic import anual_ppd_clientes, anual_ppd_proveedores

    calculo = anual_ppd_clientes if lado == "clientes" else anual_ppd_proveedores
    try:
        return calculo(_ArchivoMem(*fac), _ArchivoMem(*rep), anios), None
    except KeyError as e:
        return None, e.args[0]


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _balance_cache(fac_ing: tuple, pago_ing: tuple, fac_egr: tuple, pago_egr: tuple, nomina: tuple,
                   anios: tuple, version: str) -> dict:
    """Sección 2: carga de las 5 bases, complementos mensuales (`rep_mensual_*`) y `_balance_documental_mensual`, todo
    en caché (el cambio de radio/selector no recalcula nada)."""
    from core.finance_logic import (rep_mensual_clientes, rep_mensual_proveedores,
                                    _balance_documental_mensual)

    f_fi, f_pi, f_fe, f_pe = (_ArchivoMem(*a) for a in (fac_ing, pago_ing, fac_egr, pago_egr))
    df_fac_ing, df_pago_ing = cargar_base(f_fi), cargar_base(f_pi)
    df_fac_egr = cargar_base(f_fe).rename(columns={"Fecha": "Fecha y Hora"})
    df_pago_egr = cargar_base(f_pe).rename(columns={"Documento Relacionado": "UUID DR"})
    rep_ing = rep_mensual_clientes(f_fi, f_pi, anios)
    rep_egr = rep_mensual_proveedores(f_fe, f_pe, anios)
    return _balance_documental_mensual(df_fac_ing, df_pago_ing, df_fac_egr, df_pago_egr, cargar_base(_ArchivoMem(*nomina)),
                                       rep_ing=rep_ing, rep_egr=rep_egr, anios=anios)


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _tiempos_cache(lado: str, fac: tuple, pagos: tuple, anios: tuple, freq: str, version: str) -> pd.DataFrame:
    """Sección 4: `_tiempos_por_periodo` en caché (Egresos con los nombres canónicos de columna, como antes), por Año (`freq='Y'`) o
    por Año-Mes (`freq='M'`), limitado a los años de la ventana `anios` y con la línea de tiempo CONTINUA (del primer al último
    periodo con datos; los intermedios sin aplicaciones quedan con NaN, nunca con 0)."""
    from core.finance_logic import _tiempos_por_periodo

    df_fac, df_pagos = cargar_base(_ArchivoMem(*fac)), cargar_base(_ArchivoMem(*pagos))
    if lado == "proveedores":
        df_fac = df_fac.rename(columns={"Fecha": "Fecha y Hora"})
        df_pagos = df_pagos.rename(columns={"Documento Relacionado": "UUID DR"})
    res = _tiempos_por_periodo(df_fac, df_pagos, freq)
    filtrado = res.loc[np.array([int(m[:4]) in {int(a) for a in anios} for m in res.index], dtype=bool)]   # solo los 5 años de la ventana
    if not filtrado.empty:
        continuo = pd.period_range(filtrado.index.min(), filtrado.index.max(), freq=freq).astype(str)
        filtrado = filtrado.reindex(pd.Index(continuo, name="Periodo"))
    filtrado.attrs.update(res.attrs)
    return filtrado


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _concentracion_cache(fac: tuple, anios: tuple, version: str) -> dict:
    """Sección 5: importes por cliente (RFC Receptor) de la Facturación Emitida Total, en caché. Devuelve un dict con
    `motivo` (str | None), `sin_cliente` (bool) y, si hay datos, `agrupa_por_rfc`, `por_cliente` (Serie descendente),
    `total_general`, `fact_emitida_total` y `nombre_por_id`."""
    try:
        facturas, _ = _facturas_cache(fac[0], fac[1], version)
        facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturas", anios)
    except KeyError as e:
        return {"motivo": e.args[0], "sin_cliente": False}
    base_conc = facturas[~facturas["Es_NCR"]]
    agrupa_por_rfc = "RFC_Receptor" in base_conc.columns
    if not agrupa_por_rfc and "Nombre_Receptor" not in base_conc.columns:
        return {"motivo": None, "sin_cliente": True}
    # Normaliza el identificador (strip + mayúsculas en el RFC) ANTES de agrupar: un mismo cliente capturado con
    # variantes de espacios/mayúsculas no debe fragmentarse (se diluiría en "Otros"). Un receptor sin RFC se agrupa
    # como "Sin RFC" para que la suma por cliente coincida SIEMPRE con la Facturación Emitida Total.
    crudo = base_conc["RFC_Receptor" if agrupa_por_rfc else "Nombre_Receptor"].fillna("").astype(str).str.strip()
    id_cliente = crudo.str.upper() if agrupa_por_rfc else crudo
    id_cliente = id_cliente.where(~id_cliente.isin(["", "NAN"]), "Sin RFC" if agrupa_por_rfc else "Sin nombre")
    por_cliente = base_conc.groupby(id_cliente)["Total"].sum().sort_values(ascending=False).rename_axis("Cliente")
    # Razón Social de cada RFC (solo para mostrarla; el agrupamiento siempre usa el RFC).
    if agrupa_por_rfc and "Nombre_Receptor" in base_conc.columns:
        nombre_por_id = (pd.DataFrame({"id": id_cliente, "nombre": base_conc["Nombre_Receptor"]})
                         .dropna().query("nombre != ''").groupby("id")["nombre"].first().to_dict())
    else:
        nombre_por_id = {}
    return {"motivo": None, "sin_cliente": False, "agrupa_por_rfc": agrupa_por_rfc, "por_cliente": por_cliente,
            "total_general": float(por_cliente.sum()),
            "fact_emitida_total": float(base_conc["Total"].sum()),   # = tarjeta "Facturación Emitida Total" de Ingresos
            "nombre_por_id": nombre_por_id}


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _resumen_sf_cache(fac: tuple, anios: tuple, version: str) -> dict:
    """Sección 6: base de facturación emitida y años analizables, en caché. `motivo` (str | None; no se pudo leer la
    base), `vacia`, `anios` (descendente) y `defecto` (último año con periodo anterior comparable)."""
    from core.finance_logic import _base_facturacion_emitida, _clientes_sin_facturacion

    base, motivo = _base_facturacion_emitida(_ArchivoMem(*fac), anios)
    if base is None:
        return {"motivo": motivo, "vacia": False, "anios": [], "defecto": None}
    if base.empty:
        return {"motivo": None, "vacia": True, "anios": [], "defecto": None}
    anios = sorted({int(a) for a in base["Fecha"].dt.year}, reverse=True)
    defecto = next((a for a in anios if _clientes_sin_facturacion(base, a)["disponible"]), anios[0])
    return {"motivo": None, "vacia": False, "anios": anios, "defecto": defecto}


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _res_sf_cache(fac: tuple, anio: int, anios: tuple, version: str) -> dict:
    """Sección 6: `_clientes_sin_facturacion` del año elegido, en caché."""
    from core.finance_logic import _base_facturacion_emitida, _clientes_sin_facturacion

    base, _ = _base_facturacion_emitida(_ArchivoMem(*fac), anios)
    return _clientes_sin_facturacion(base, anio)

@st.cache_data(show_spinner="Procesando bases CFDI...")
def _trazabilidad_cache(fac_ing: tuple, pago_ing: tuple, anios: tuple, version: str) -> dict:
    """Insumos de facturación a crédito, complementos y notas de crédito de CLIENTES para el Índice (ventana `anios`): facturación anual (PUE + PPD, sin NCR);
    PPD con su importe aplicado por REP hasta la fecha de corte (= último REP de la ventana; pagos parciales sumados y con tope en el total de cada factura) solo para facturas
    emitidas con más de `DIAS_GRACIA_PPD` días de antigüedad; PPD sin ningún REP; REP cuyo UUID relacionado no está en la base de facturas; facturas PUE con REP asociado;
    y notas de crédito (total y emitidas con método PPD)."""
    try:
        fi_all, _ = _facturas_cache(fac_ing[0], fac_ing[1], version)
        rep_all, _ = _complementos_cache(pago_ing[0], pago_ing[1], version)
    except KeyError as e:
        return {"motivo": e.args[0]}
    norm = lambda s: s.fillna("").astype(str).str.strip().str.upper()
    anios = [int(a) for a in anios]
    uuids_fac = set(norm(fi_all["UUID"]))
    fi, _ = excluir_años_incompletos(fi_all, "Fecha", "Facturas", anios)
    rep, _ = excluir_años_incompletos(rep_all, "Fecha_Cobro", "Complementos de pago", anios)
    fi = fi.assign(U=norm(fi["UUID"]))
    rep = rep.assign(U=norm(rep["UUID_DR"]))
    ventas = fi[~fi["Es_NCR"] & fi["Metodo_Pago"].isin(["PUE", "PPD"])]
    fact_anual = ventas.groupby(ventas["Fecha"].dt.year)["Total"].sum().reindex(anios, fill_value=0.0)
    ppd = ventas[ventas["Metodo_Pago"] == "PPD"]
    corte = rep["Fecha_Cobro"].max() if len(rep) else pd.NaT
    elegibles = ppd.iloc[0:0] if pd.isna(corte) else ppd[ppd["Fecha"] <= corte - pd.Timedelta(days=DIAS_GRACIA_PPD)]
    aplicado_uuid = rep.groupby("U")["Cobro_Efectivo"].sum()
    aplicado = np.minimum(np.maximum(elegibles["U"].map(aplicado_uuid).fillna(0.0), 0.0), elegibles["Total"]) if len(elegibles) else pd.Series(dtype=float)
    sin_rep = elegibles[~elegibles["U"].isin(set(rep["U"]))]
    rep_sin_fac = rep[(rep["U"] == "") | ~rep["U"].isin(uuids_fac)]
    pue = ventas[ventas["Metodo_Pago"] == "PUE"]
    ncr = fi[fi["Es_NCR"]]
    ncr_m = ncr["Total"].abs()
    return {"motivo": None, "corte": None if pd.isna(corte) else corte, "facturacion_anual": {int(a): float(v) for a, v in fact_anual.items()},
            "ppd_total": int(len(ppd)), "ppd_n_elegibles": int(len(elegibles)), "ppd_monto_elegible": float(elegibles["Total"].sum()),
            "ppd_aplicado": float(aplicado.sum()), "ppd_n_sin_rep": int(len(sin_rep)), "ppd_monto_sin_rep": float(sin_rep["Total"].sum()),
            "rep_n": int(len(rep)), "rep_n_sin_factura": int(len(rep_sin_fac)), "rep_monto_sin_factura": float(rep_sin_fac["Cobro_Efectivo"].sum()),
            "pue_con_rep": int(pue["U"].isin(set(rep["U"])).sum()),
            "ncr_n": int(len(ncr)), "ncr_n_ppd": int((ncr["Metodo_Pago"] == "PPD").sum()), "ncr_monto": float(ncr_m.sum()),
            "ncr_monto_ppd": float(ncr_m[ncr["Metodo_Pago"] == "PPD"].sum()), "ventas_total": float(ventas["Total"].sum())}



@st.cache_data(show_spinner=False)
def _facturacion_anual_cache(fac: tuple, lado: str, anios: tuple, version: str) -> dict:
    """Facturación Total (Tipo Factura, PUE + PPD, columna Total, sin NCR) por año de emisión sobre `anios`: {año: MXN} | {'motivo': str}."""
    lector, etiqueta = (_facturas_cache, "Facturas") if lado == "ingresos" else (_facturas_egresos_cache, "Facturación recibida")
    try:
        f, _ = lector(fac[0], fac[1], version)
        f, _ = excluir_años_incompletos(f, "Fecha", etiqueta, anios)
    except KeyError as e:
        return {"motivo": e.args[0]}
    f = f[~f["Es_NCR"]]
    por_anio = f.groupby(f["Fecha"].dt.year)["Total"].sum().reindex([int(a) for a in anios], fill_value=0.0)
    return {int(a): float(v) for a, v in por_anio.items()}
