# Funciones de lectura, limpieza y caché (_cargar_base_cache, leer_facturas, etc.)
'''
Encargado de leer los archivos subidos (Excel/CSV), 
validar columnas, limpiar formatos de texto/fechas y gestionar la caché de Streamlit.
'''
import pandas as pd
import pyarrow as pa
import streamlit as st
import io
import re
import gc
import hashlib
import numpy as np
from pathlib import Path
from zipfile import ZipFile
from utils import (_ArchivoMem, _nb, _norm, a_numero, a_fecha, buscar_columna)
from config import (CODIGO_VERSION, COLS_FACTURAS,
                    COLS_COMPLEMENTOS,COLS_COMPLEMENTOS_OPCIONALES,
                    COL_FECHA_REP,ANIOS_VENTANA, MES_ABREV, DIAS_GRACIA_PPD,
                    RUTA_ITAEE_DEFAULT, RUTA_INPP_DEFAULT, RUTA_INPC_DEFAULT,
                    PREFIJO_DIVISAS, DIAS_DESFASE_ALERTA, COLUMNAS_OPERACIONES_DIVISAS,COLS_EMITIDOS_PRODUCTOS,
                    COLS_EMITIDOS_PRODUCTOS_OPC,ETIQUETA_CLAVE_GENERICA,CLASE_GENERICA_SAT)



def _datos_archivo_cache(archivo) -> tuple[str, bytes | tuple[tuple[str, bytes], ...]]:
    nombre, contenido = _nb(archivo)
    if isinstance(contenido, list):
        partes = []
        for parte in contenido:
            bytes_parte = parte.descargar() if hasattr(parte, "descargar") else parte.getvalue()
            partes.append((parte.name, bytes_parte))
        return nombre, tuple(partes)
    if hasattr(contenido, "descargar"):
        contenido = contenido.descargar()
    return nombre, contenido


def cargar_base(uploaded_file) -> pd.DataFrame:
    """Lector universal que delega a la función con caché."""
    return _cargar_base_cache(uploaded_file.name, uploaded_file.getvalue(), CODIGO_VERSION)



def leer_archivo(nombre: str, contenido) -> pd.DataFrame:
    """
    Lee archivos infiriendo tipos nativos para ahorrar memoria.
    FASE 3: Filtra columnas desde la lectura (usecols).
    DESCARGA PEREZOSA EXTREMA: Destruye los bytes tras la lectura.
    """
    # 0. MANEJO DE MÚLTIPLES ARCHIVOS (Grupos)
    if isinstance(contenido, list):
        dfs = []
        for cont in contenido:
            # Extraemos los bytes de forma segura y perezosa
            if hasattr(cont, 'descargar'):
                bytes_data = cont.descargar()
            elif hasattr(cont, 'getvalue'):
                bytes_data = cont.getvalue()
            else:
                bytes_data = cont
                
            nombre_archivo = cont.name if hasattr(cont, 'name') else nombre
            df_temp = leer_archivo(nombre_archivo, bytes_data)
            dfs.append(df_temp)
            
            # Liberamos RAM de esta fracción antes de descargar la siguiente
            del bytes_data
            gc.collect()
            
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    # 0.5 ARCHIVO INDIVIDUAL PEREZOSO (Cuando no vienen en grupo)
    if hasattr(contenido, 'descargar'):
        contenido = contenido.descargar()
    elif hasattr(contenido, 'getvalue') and not isinstance(contenido, bytes):
        try:
            contenido = contenido.getvalue()
        except Exception:
            pass

    nombre_lower = nombre.lower()
    
    # 1. EL PORTERO DE COLUMNAS
    COLUMNAS_UTILES = {
        "uuid", "fechayhora", "fecha", "fechadeemision", "fechaemision",
        "rfcemisor", "nombreemisor", "razonsocialemisor", "nombredelemisor", "razonsocial", 
        "estatus", "tipodocumento", "tipodedocumento", "tipodecomprobante", 
        "metododepago", "total", "importe", "clave", "saldoinicial", "saldofinal",
        "fechadepago", "fechapago", "documentorelacionado", "uuidrelacionado",
        "rfcreceptor", "nombrereceptor", "razonsocialreceptor", "razonsocialcliente", 
        "razonsocial1", "formadepago", "moneda", "tipodecambio", "serie", 
        "ivatrasladado", "tasaimpuestostrasladados", "importebase", "uuiddr", "subtotal", "montomxn", "descripcion",
        "cantidad", "valorunitario", "unidad", "unidaddemedida", "numeroorden", "numerodeorden",
        "numorden", "nodeorden", "orden", "ordencompra", "ordendecompra",
        "folio", "fechadeoperacion", "claveunidad", "codigosat", "descuento",
        "impuestostrasladados", "impuestosretenidos", "tipodecambiodof",
        "uuidcfdirecibido", "partida", "importelocaltrasladado",
        "importelocalretenido"
    }
    
    def es_columna_util(col_name):
        n_original = _norm(str(col_name))
        n_limpio = re.sub(r'[^a-z0-9]', '', n_original)
        return (n_limpio in COLUMNAS_UTILES) or ("iva" in n_original and "reten" not in n_original)

    def leer_excel_filtrado(bytes_excel: bytes, engine: str) -> pd.DataFrame:
        with pd.ExcelFile(io.BytesIO(bytes_excel), engine=engine) as xls:
            df_dummy = pd.read_excel(xls, nrows=0)
            cols_a_leer = [c for c in df_dummy.columns if es_columna_util(c)]
            return pd.read_excel(xls, usecols=cols_a_leer)

    # 2. LECTURA QUIRÚRGICA
    if nombre_lower.endswith((".parquet", ".pqt")):
        import pyarrow.parquet as pq
        esquema = pq.read_schema(io.BytesIO(contenido))
        cols_a_leer = [c for c in esquema.names if es_columna_util(c)]
        df = pd.read_parquet(io.BytesIO(contenido), columns=cols_a_leer)
        
    elif nombre_lower.endswith(".xlsb"):
        with pd.ExcelFile(io.BytesIO(contenido), engine="pyxlsb") as xls:
            df_dummy = pd.read_excel(xls, nrows=0)
            cols_a_leer = [c for c in df_dummy.columns if es_columna_util(c)]
            df = pd.read_excel(xls, usecols=cols_a_leer)
            
    elif nombre_lower.endswith((".xlsx", ".xls")):
        try:
            df = leer_excel_filtrado(contenido, "calamine")
        except ImportError as error_calamine:
            if not nombre_lower.endswith(".xlsx"):
                raise ImportError(
                    "No se pudo cargar python-calamine para leer archivos .xls."
                ) from error_calamine
            try:
                df = leer_excel_filtrado(contenido, "openpyxl")
            except TypeError as error_openpyxl:
                if "showZeroes" not in str(error_openpyxl):
                    raise
                normalizado = io.BytesIO()
                with ZipFile(io.BytesIO(contenido)) as origen, ZipFile(normalizado, "w") as destino:
                    for elemento in origen.infolist():
                        datos = origen.read(elemento.filename)
                        if elemento.filename.endswith(".xml"):
                            datos = datos.replace(b"showZeroes", b"showZeros")
                        destino.writestr(elemento, datos)
                df = leer_excel_filtrado(normalizado.getvalue(), "openpyxl")
            
    else:
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python", 
                                 encoding=codificacion, usecols=es_columna_util)
                break
            except UnicodeDecodeError:
                continue
            except ValueError:
                df = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python", encoding=codificacion)
                cols_ok = [c for c in df.columns if es_columna_util(c)]
                df = df[cols_ok]
                break

    # 2.5 Destruimos los megabytes crudos en cuanto Pandas crea la pequeña tabla útil
    if isinstance(contenido, bytes):
        del contenido
    gc.collect()

    # 3. Formateo final
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    cols_texto = df.select_dtypes(include=['object', 'string']).columns
    for col in cols_texto:
        df[col] = df[col].astype(str).str.strip()
        
    return df



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
        st.error(f"Error en el archivo de {etiqueta}: Faltan las siguientes columnas requeridas para el "
                 f"cálculo: {faltantes}")
        st.stop()

def leer_facturas(nombre: str, contenido: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Facturas emitidas: activas, con fecha, método y total válidos; conserva Razón Social como receptor si falta ese campo."""
    avisos: list[str] = []
    base = leer_archivo(nombre, contenido)
    columnas_nombre_receptor = (
        "Razon Social Receptor", "Nombre Receptor", "Razon Social Cliente", "Razon Social.1",
        "Razon Social",
    )
    columnas_disponibles = []
    for nombre_columna in columnas_nombre_receptor:
        columna = buscar_columna(base.columns, nombre_columna)
        if columna is not None and columna not in columnas_disponibles:
            columnas_disponibles.append(columna)
    if columnas_disponibles:
        nombre_receptor = pd.Series("", index=base.index, dtype="object")
        for columna in columnas_disponibles:
            valores = base[columna].fillna("").astype(str).str.strip()
            presentes = ~valores.str.casefold().isin({"", "nan", "none", "null", "<na>"})
            nombre_receptor = nombre_receptor.mask(nombre_receptor.eq("") & presentes, valores)
        base["_Nombre_Receptor_Archivo"] = nombre_receptor
    df = resolver_columnas(base, COLS_FACTURAS)
    n0 = len(df)

    tipo_crudo = df["Tipo Documento"].astype(str)
    es_ncr_crudo = tipo_crudo.str.contains("NCR", case=False, na=False)
    n_ncr_crudo = int(es_ncr_crudo.sum())
    es_factura = tipo_crudo.str.strip().str.upper() == "FACTURA"
    estatus = df["Estatus"].astype(str).str.strip().str.upper()
    df = df[estatus.isin(["ACTIVO", "VIGENTE"]) & (es_factura | es_ncr_crudo)].copy()
    
    # Asegurar booleanos estrictos
    df["Es_NCR"] = df["Tipo Documento"].astype(str).str.contains("NCR", case=False, na=False).astype(bool)
    
    avisos.append(f"Facturas: {n0} filas leídas, {len(df)} con Estatus 'Activo' y Tipo 'Factura' o 'NCR' "
                  f"({n_ncr_crudo} NCR detectadas en el archivo, {int(df['Es_NCR'].sum())} tras el filtro).")

    # Asignación optimizada con categorías
    df = df.assign(Fecha=a_fecha(df["Fecha y Hora"]), 
                   Total=a_numero(df["Total"]),
                   Metodo_Pago=df["Metodo de Pago"].astype(str).str.upper().astype("category"))

    # Convertir las columnas originales a categorías para ahorrar RAM
    if "Estatus" in df.columns:
        df["Estatus"] = df["Estatus"].astype("category")
    if "Tipo Documento" in df.columns:
        df["Tipo Documento"] = df["Tipo Documento"].astype("category")

    ilegibles = df["Fecha"].isna() | df["Total"].isna()
    if ilegibles.any():
        n_ncr_perdidas = int((ilegibles & df["Es_NCR"]).sum())
        avisos.append(f"Facturas: {ilegibles.sum()} filas con fecha/total ilegible descartadas"
                      + (f" ({n_ncr_perdidas} de ellas eran NCR)." if n_ncr_perdidas else "."))
        df = df[~ilegibles]

    otro_metodo = ~df["Es_NCR"] & ~df["Metodo_Pago"].isin(["PUE", "PPD"])
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

    n_nombres = df.groupby("RFC Emisor")["Nombre Emisor"].nunique()
    ambiguos = n_nombres[n_nombres > 1].index
    if len(ambiguos):
        avisos.append("Facturas: la columna de nombre trae varios valores para un mismo RFC Emisor "
                      "(parece ser el nombre del cliente, no el de la empresa); se identifica solo por RFC.")
        df = df.assign(**{"Nombre Emisor": df["Nombre Emisor"].where(~df["RFC Emisor"].isin(ambiguos), "")})

    col_rfc_receptor = buscar_columna(df.columns, "RFC Receptor")
    col_nombre_receptor = ("_Nombre_Receptor_Archivo"
                           if "_Nombre_Receptor_Archivo" in df.columns else
                           next((c for c in (buscar_columna(df.columns, n) for n in (
                               "Razon Social Receptor", "Nombre Receptor", "Razon Social Cliente",
                               "Razon Social.1")) if c), None))
    
    columnas = ["UUID", "Fecha", "RFC Emisor", "Nombre Emisor", "Metodo_Pago", "Total", "Es_NCR"]
    renombres = {"RFC Emisor": "RFC_Emisor", "Nombre Emisor": "Nombre_Emisor"}
    for col, nuevo in ((col_rfc_receptor, "RFC_Receptor"), (col_nombre_receptor, "Nombre_Receptor"),
                       (buscar_columna(df.columns, "Forma de Pago"), "Forma_Pago")):
        if col is not None and col not in columnas:
            columnas.append(col)
            renombres[col] = nuevo
            
    df = (df[columnas].rename(columns=renombres)
          .sort_values("Fecha", kind="stable").reset_index(drop=True))
    return df, avisos


def leer_facturas_egresos(nombre: str, contenido: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Facturación recibida (Egresos): candados exactos confirmados por el usuario, sumatoria bruta."""
    avisos: list[str] = []
    df = resolver_columnas(leer_archivo(nombre, contenido), COLS_FACTURAS)
    n0 = len(df)

    estatus_limpio = df["Estatus"].astype(str).str.strip().str.upper()
    vigente = estatus_limpio.isin(["VIGENTE", "ACTIVO"])
    if (~vigente).any():
        avisos.append(f"Facturación recibida: {int((~vigente).sum())} filas excluidas por Estatus distinto de "
                      f"'Vigente'/'Activo'.")
    df = df[vigente].copy()

    tipo_limpio = df["Tipo Documento"].astype(str).str.strip().str.upper()
    es_factura = tipo_limpio == "FACTURA"
    es_ncr = tipo_limpio == "NCR"
    excluidos_tipo = ~(es_factura | es_ncr)
    if excluidos_tipo.any():
        avisos.append(f"Facturación recibida: {int(excluidos_tipo.sum())} filas excluidas por Tipo Documento "
                      f"distinto de 'Factura'/'NCR'.")
    
    df["Es_NCR"] = es_ncr.astype(bool)
    df = df[~excluidos_tipo]
    
    avisos.append(f"Facturación recibida: {n0} filas leídas, {len(df)} vigentes de Tipo 'Factura'/'NCR' "
                  f"({int(df['Es_NCR'].sum())} NCR).")

    total_limpio = df["Total"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    
    # Asignación optimizada con categorías
    df = df.assign(Fecha=a_fecha(df["Fecha y Hora"]),
                   Total=pd.to_numeric(total_limpio, errors="coerce").fillna(0.0),
                   Metodo_Pago=df["Metodo de Pago"].astype(str).str.upper().astype("category"))

    if "Estatus" in df.columns:
        df["Estatus"] = df["Estatus"].astype("category")
    if "Tipo Documento" in df.columns:
        df["Tipo Documento"] = df["Tipo Documento"].astype("category")

    fecha_ilegible = df["Fecha"].isna()
    if fecha_ilegible.any():
        avisos.append(f"Facturación recibida: {int(fecha_ilegible.sum())} filas con Fecha y Hora ilegible descartadas.")
        df = df[~fecha_ilegible]

    otro_metodo = ~df["Es_NCR"] & ~df["Metodo_Pago"].isin(["PUE", "PPD"])
    if otro_metodo.any():
        avisos.append(f"Facturación recibida: {int(otro_metodo.sum())} filas con método distinto de PUE/PPD descartadas.")
        df = df[~otro_metodo]

    dup = df["UUID"].duplicated()
    if dup.any():
        avisos.append(f"Facturación recibida: {int(dup.sum())} UUID duplicados eliminados.")
        df = df[~dup]

    col_forma = buscar_columna(df.columns, "Forma de Pago")
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

def leer_complementos(nombre: str, contenido: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Complementos de pago: Fecha_Cobro (sin hora) y Cobro Efectivo = Saldo Inicial - Saldo Final."""
    avisos: list[str] = []
    etiqueta = f"Complementos de pago ({nombre})"
    df = resolver_columnas(leer_archivo(nombre, contenido), {**COLS_COMPLEMENTOS, **COL_FECHA_REP},
                           COLS_COMPLEMENTOS_OPCIONALES)
    n0 = len(df)
    
    if "Estatus" in df.columns:
        estatus = df["Estatus"].astype(str).str.strip().str.upper()
        df = df[estatus.isin(["ACTIVO", "VIGENTE"])].copy()
        # Optimización de RAM
        df["Estatus"] = df["Estatus"].astype("category")
        avisos.append(f"{etiqueta}: {n0 - len(df)} filas descartadas por Estatus distinto de 'Activo'/'Vigente'.")
        
    if "RFC Emisor" not in df.columns:
        df = df.assign(**{"RFC Emisor": ""})
        avisos.append(f"{etiqueta}: la base no trae 'RFC Emisor'; los cobros no se pueden filtrar por RFC.")
        
    if "UUID DR" not in df.columns:
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
    # Convertimos Forma de Pago a categoría porque se repiten mucho los códigos (03, 01, etc.)
    df = df.assign(Forma_Pago=df[col_forma].astype("category") if col_forma is not None else "")
    
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
    """Nómina de egresos: comprobantes activos/vigentes; fecha de pago; monto = 'Total'.
    Devuelve Año, Mes (1-12), Periodo ('AAAA-MM') y Monto; el formato con Fecha de Certificación se reserva a Ingresos."""
    c_est = buscar_columna(df_nomina.columns, "Estatus")
    if buscar_columna(df_nomina.columns, "Fecha de Certificación") is not None:
        return None
    c_fecha = (buscar_columna(df_nomina.columns, "Fecha Pago")
               or buscar_columna(df_nomina.columns, "Fecha de Pago"))
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
    if nombre.lower().endswith((".parquet", ".pqt")):
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
    valido = fechas[0].notna() & fechas[0].str.lower().isin(MES_ABREV)
    if int(valido.sum()) < 3:
        return None
    mes = fechas.loc[valido, 0].str.lower().map(MES_ABREV)
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
        mes = MES_ABREV.get(mes_txt[:3])
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




def _cargar_bases_economicas(lado: str) -> dict:
    """Carga las bases económicas subidas; para ITAEE consulta la API del INEGI con respaldo en `data/`."""
    if lado not in ("ingresos", "egresos"):
        raise ValueError(f"El lado debe ser 'ingresos' o 'egresos', no {lado!r}.")

    pertinentes = ("itaee", "inpc", "tiie") if lado == "ingresos" else ("inpp", "inpc")
    texto = "ITAEE, INPC y/o TIIE" if lado == "ingresos" else "INPP y/o INPC"
    archivos = st.file_uploader(
        f"Carga las bases externas ({texto}) · Excel, CSV o Parquet",
        type=["xlsx", "xls", "xlsb", "csv", "parquet"],
        accept_multiple_files=True,
        key=f"eco_up_{lado}",
    )

    series: dict = {}
    base_proyecto = Path(__file__).resolve().parent.parent

    def _procesar_entradas(entradas: list[tuple[str, bytes]]) -> None:
        for nombre, contenido in entradas:
            try:
                r = _procesar_archivo_economico(nombre, contenido, CODIGO_VERSION)
            except (pa.ArrowException, OSError, ValueError) as exc:
                st.error(f"No se pudo leer la base económica «{nombre}»: {exc}")
                continue
            if r["tipo"] is None:
                st.warning(
                    f"No se reconoció el formato de «{nombre}» (se esperan una base de ITAEE, INPP, INPC "
                    "o una serie fecha-valor como la TIIE)."
                )
            elif r["tipo"] not in pertinentes:
                st.info(
                    f"«{nombre}» es una base de {r['tipo'].upper()}: cárgala en el módulo "
                    f"{'de Egresos' if lado == 'ingresos' else 'de Ingresos'}."
                )
            else:
                series.setdefault(r["tipo"], {}).update(r["series"])

    entradas_subidas = [(f.name, f.getvalue()) for f in archivos or []]
    if entradas_subidas:
        _procesar_entradas(entradas_subidas)

    if lado == "ingresos":
        if "itaee" not in series:
            from core.api_inegi import obtener_itaee_por_estado

            itaee_estados, aviso_api = obtener_itaee_por_estado()
            if itaee_estados:
                series["itaee_estados"] = itaee_estados
                st.caption(
                    "ITAEE obtenido en línea desde la API del INEGI (BIE-BISE). "
                    "Si cargas un archivo manual de ITAEE, sustituirá estos datos."
                )
            else:
                st.warning(f"{aviso_api} Se utilizará el archivo local predeterminado.")
                archivo_itaee = base_proyecto / RUTA_ITAEE_DEFAULT
                try:
                    _procesar_entradas([(archivo_itaee.name, archivo_itaee.read_bytes())])
                except OSError as exc:
                    st.error(f"No se pudo leer la base económica predeterminada {archivo_itaee}: {exc}")

        if "inpc" not in series and not entradas_subidas:
            archivo_inpc = base_proyecto / RUTA_INPC_DEFAULT
            try:
                _procesar_entradas([(archivo_inpc.name, archivo_inpc.read_bytes())])
            except OSError as exc:
                st.error(f"No se pudo leer la base económica predeterminada {archivo_inpc}: {exc}")
    elif not entradas_subidas:
        st.caption(
            "Si no cargas archivos, se utilizan las bases predeterminadas. "
            "Los archivos que subas sustituyen esas bases para esta vista."
        )
        archivo_inpp = base_proyecto / RUTA_INPP_DEFAULT
        try:
            _procesar_entradas([(archivo_inpp.name, archivo_inpp.read_bytes())])
        except OSError as exc:
            st.error(f"No se pudo leer la base económica predeterminada {archivo_inpp}: {exc}")

    return series


# ============================================
# FUNCIONES CON @st.cache_data
# ============================================

@st.cache_data(show_spinner="Leyendo base...")
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

@st.cache_data(show_spinner="Procesando facturas…", max_entries=2)
def _facturas_cache_procesar(nombre: str, _contenido, version: str, huella_contenido: str):
    return leer_facturas(nombre, _contenido)


def _facturas_cache(nombre: str, contenido, version: str):
    if isinstance(contenido, list):
        partes = []
        huella = hashlib.sha256()
        for archivo in contenido:
            if hasattr(archivo, "descargar"):
                bytes_archivo = archivo.descargar()
            elif hasattr(archivo, "getvalue"):
                bytes_archivo = archivo.getvalue()
            else:
                bytes_archivo = archivo
            nombre_archivo = archivo.name if hasattr(archivo, "name") else nombre
            huella.update(nombre_archivo.encode("utf-8"))
            huella.update(hashlib.sha256(bytes_archivo).digest())
            partes.append(_ArchivoMem(nombre_archivo, bytes_archivo))
        contenido = partes
        huella_contenido = huella.hexdigest()
    else:
        huella_contenido = hashlib.sha256(contenido).hexdigest()

    return _facturas_cache_procesar(nombre, contenido, version, huella_contenido)

@st.cache_data(show_spinner="Procesando facturación recibida…", max_entries=2)
def _facturas_egresos_cache(nombre: str, _contenido: bytes, version: str):
    return leer_facturas_egresos(nombre, _contenido)

@st.cache_data(show_spinner="Procesando complementos de pago…", max_entries=2)
def _complementos_cache(nombre: str, _contenido: bytes, version: str):
    return leer_complementos(nombre, _contenido)

@st.cache_data(show_spinner=False, max_entries=5)
def _columnas_archivo(nombre: str, _contenido: bytes, version: str) -> list[str]:
    return list(leer_archivo(nombre, _contenido).columns)

@st.cache_data(show_spinner="Procesando bases CFDI...", max_entries=2)
def _cargar_base_cache(nombre: str, _contenido: bytes, version: str) -> pd.DataFrame:
    return leer_archivo(nombre, _contenido)

@st.cache_data(show_spinner=False)
def _anios_analisis_cache(_fac_ing, _fac_egr, version: str) -> tuple:
    """`obtener_anios_analisis` sobre las facturas de Emitidos (Ingresos) y Recibidos (Egresos), en caché."""
    def leer(lector, archivo):
        if archivo is None:
            return None
        try:
            return lector(archivo[0], archivo[1], version)[0]
        except KeyError:
            return None
    return tuple(obtener_anios_analisis(leer(_facturas_cache, _fac_ing), leer(_facturas_egresos_cache, _fac_egr)))

@st.cache_data(show_spinner="Procesando bases CFDI...")
def _anual_ppd_cache(lado: str, _fac: tuple, _rep: tuple, anios: tuple, version: str):
    """Sección 1: `anual_ppd_clientes` / `anual_ppd_proveedores` en caché -> (DataFrame | None, motivo | None)."""
    from core.finance_logic import anual_ppd_clientes, anual_ppd_proveedores

    calculo = anual_ppd_clientes if lado == "clientes" else anual_ppd_proveedores
    try:
        return calculo(_ArchivoMem(*_fac), _ArchivoMem(*_rep), anios), None
    except KeyError as e:
        return None, e.args[0]


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _balance_cache(_fac_ing: tuple, _pago_ing: tuple, _fac_egr: tuple, _pago_egr: tuple, _nomina: tuple,
                   _productos: tuple | None, productos_cache_key: tuple | None,
                   anios: tuple, version: str) -> dict:
    """Sección 2: carga de las 5 bases, complementos mensuales (`rep_mensual_*`) y `_balance_documental_mensual`, todo
    en caché (el cambio de radio/selector no recalcula nada)."""
    from core.finance_logic import (excluir_cfdis_divisas, rep_mensual_clientes, rep_mensual_proveedores,
                                    _balance_documental_mensual)

    f_fi, f_pi, f_fe, f_pe = (_ArchivoMem(*a) for a in (_fac_ing, _pago_ing, _fac_egr, _pago_egr))
    df_fac_ing, df_pago_ing = cargar_base(f_fi), cargar_base(f_pi)
    df_fac_egr = cargar_base(f_fe).rename(columns={"Fecha": "Fecha y Hora"})
    df_pago_egr = cargar_base(f_pe).rename(columns={"Documento Relacionado": "UUID DR"})
    uuids_divisas: set[str] = set()
    estadisticas_divisas = None
    pagos_divisas_excluidos = 0
    relacion_pago_disponible = True
    if _productos is not None:
        facturas_egr, _ = leer_facturas_egresos(f_fe.name, f_fe.getvalue())
        nombre_productos, contenido_productos = _productos
        if isinstance(contenido_productos, tuple):
            productos = pd.concat(
                [leer_archivo(nombre, contenido) for nombre, contenido in contenido_productos],
                ignore_index=True,
            )
        else:
            productos = leer_archivo(nombre_productos, contenido_productos)
        _, uuids_divisas, estadisticas_divisas = excluir_cfdis_divisas(facturas_egr, productos)
        if uuids_divisas:
            columna_uuid = buscar_columna(df_fac_egr.columns, "UUID")
            if columna_uuid is None:
                raise KeyError("La Facturación Recibida no incluye la columna 'UUID'.")
            uuid_facturas = df_fac_egr[columna_uuid].fillna("").astype(str).str.strip().str.upper()
            df_fac_egr = df_fac_egr.loc[~uuid_facturas.isin(uuids_divisas)]

            columna_relacion = (buscar_columna(df_pago_egr.columns, "UUID DR")
                                or buscar_columna(df_pago_egr.columns, "Documento Relacionado"))
            if columna_relacion is None:
                relacion_pago_disponible = False
            else:
                uuid_relacionados = df_pago_egr[columna_relacion].fillna("").astype(str).str.strip().str.upper()
                excluir_pagos = uuid_relacionados.isin(uuids_divisas)
                pagos_divisas_excluidos = int(excluir_pagos.sum())
                df_pago_egr = df_pago_egr.loc[~excluir_pagos]
    rep_ing = rep_mensual_clientes(f_fi, f_pi, anios)
    rep_egr = rep_mensual_proveedores(f_fe, f_pe, anios, uuids_excluir_divisas=uuids_divisas)
    balance = _balance_documental_mensual(
        df_fac_ing, df_pago_ing, df_fac_egr, df_pago_egr, cargar_base(_ArchivoMem(*_nomina)),
        rep_ing=rep_ing, rep_egr=rep_egr, anios=anios)
    if estadisticas_divisas is not None:
        balance["divisas"] = {
            **estadisticas_divisas,
            "cfdis_excluidos": len(uuids_divisas),
            "uuids_divisas": uuids_divisas,
            "complementos_excluidos": pagos_divisas_excluidos,
            "relacion_pago_disponible": relacion_pago_disponible,
        }
    return balance


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _tiempos_cache(lado: str, _fac: tuple, _pagos: tuple, anios: tuple, freq: str, version: str) -> pd.DataFrame:
    """Sección 4: `_tiempos_por_periodo` en caché (Egresos con los nombres canónicos de columna, como antes), por Año (`freq='Y'`) o
    por Año-Mes (`freq='M'`), limitado a los años de la ventana `anios` y con la línea de tiempo CONTINUA (del primer al último
    periodo con datos; los intermedios sin aplicaciones quedan con NaN, nunca con 0)."""
    from core.finance_logic import _tiempos_por_periodo

    df_fac, df_pagos = cargar_base(_ArchivoMem(*_fac)), cargar_base(_ArchivoMem(*_pagos))
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
def _concentracion_cache(_fac: tuple, anios: tuple, version: str) -> dict:
    """Sección 5: importes por cliente (RFC Receptor) de la Facturación Emitida Total, en caché. Devuelve un dict con
    `motivo` (str | None), `sin_cliente` (bool) y, si hay datos, `agrupa_por_rfc`, `por_cliente` (Serie descendente),
    `total_general`, `fact_emitida_total` y `nombre_por_id`."""
    try:
        facturas, _ = _facturas_cache(_fac[0], _fac[1], version)
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
            # = tarjeta "Facturación Emitida Total" de Ingresos
            "fact_emitida_total": float(base_conc["Total"].sum()),
            "nombre_por_id": nombre_por_id}


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _resumen_sf_cache(_fac: tuple, anios: tuple, version: str) -> dict:
    """Sección 6: base de facturación emitida y años analizables, en caché. `motivo` (str | None; no se pudo leer la
    base), `vacia`, `anios` (descendente) y `defecto` (último año con periodo anterior comparable)."""
    from core.finance_logic import _base_facturacion_emitida, _clientes_sin_facturacion

    base, motivo = _base_facturacion_emitida(_ArchivoMem(*_fac), anios)
    if base is None:
        return {"motivo": motivo, "vacia": False, "anios": [], "defecto": None}
    if base.empty:
        return {"motivo": None, "vacia": True, "anios": [], "defecto": None}
    anios = sorted({int(a) for a in base["Fecha"].dt.year}, reverse=True)
    defecto = next((a for a in anios if _clientes_sin_facturacion(base, a)["disponible"]), anios[0])
    return {"motivo": None, "vacia": False, "anios": anios, "defecto": defecto}


@st.cache_data(show_spinner="Procesando bases CFDI...")
def _res_sf_cache(_fac: tuple, anio: int, anios: tuple, version: str) -> dict:
    """Sección 6: `_clientes_sin_facturacion` del año elegido, en caché."""
    from core.finance_logic import _base_facturacion_emitida, _clientes_sin_facturacion

    base, _ = _base_facturacion_emitida(_ArchivoMem(*_fac), anios)
    return _clientes_sin_facturacion(base, anio)

@st.cache_data(show_spinner="Procesando bases CFDI...")
def _trazabilidad_cache(_fac_ing: tuple, _pago_ing: tuple, anios: tuple, version: str) -> dict:
    """Insumos de facturación a crédito, complementos y notas de crédito de CLIENTES para el Índice (ventana `anios`): facturación anual (PUE + PPD, sin NCR);
    PPD con su importe aplicado por REP hasta la fecha de corte (= último REP de la ventana; pagos parciales sumados y con tope en el total de cada factura) solo para facturas
    emitidas con más de `DIAS_GRACIA_PPD` días de antigüedad; PPD sin ningún REP; REP cuyo UUID relacionado no está en la base de facturas; facturas PUE con REP asociado;
    y notas de crédito (total y emitidas con método PPD)."""
    try:
        fi_all, _ = _facturas_cache(_fac_ing[0], _fac_ing[1], version)
        rep_all, _ = _complementos_cache(_pago_ing[0], _pago_ing[1], version)
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
def _facturacion_anual_cache(_fac: tuple, lado: str, anios: tuple, version: str) -> dict:
    """Facturación Total (Tipo Factura, PUE + PPD, columna Total, sin NCR) por año de emisión sobre `anios`: {año: MXN} | {'motivo': str}."""
    lector, etiqueta = (_facturas_cache, "Facturas") if lado == "ingresos" else (_facturas_egresos_cache, "Facturación recibida")
    try:
        f, _ = lector(_fac[0], _fac[1], version)
        f, _ = excluir_años_incompletos(f, "Fecha", etiqueta, anios)
    except KeyError as e:
        return {"motivo": e.args[0]}
    f = f[~f["Es_NCR"]]
    por_anio = f.groupby(f["Fecha"].dt.year)["Total"].sum().reindex([int(a) for a in anios], fill_value=0.0)
    return {int(a): float(v) for a, v in por_anio.items()}


@st.cache_data(show_spinner="Procesando base de productos...", max_entries=2)
def _operaciones_divisas_cache(nombre: str, _contenido, version: str) -> pd.DataFrame:
    """Devuelve conceptos 841216 USD/EUR normalizados; marca duplicados solo con orden explícita y filas idénticas."""
    df = leer_archivo(nombre, _contenido)
    if isinstance(df, pd.DataFrame) and df.empty and not len(df.columns):
        return pd.DataFrame(columns=COLUMNAS_OPERACIONES_DIVISAS)

    requeridas = {
        "Clave": [],
        "Descripcion": ["Descripción"],
        "Fecha": ["Fecha y Hora", "Fecha de emisión", "Fecha de Emision"],
        "RFC Emisor": [],
        "Razon Social Emisor": ["Razón Social Emisor", "Nombre Emisor", "Nombre del Emisor"],
        "Cantidad": [],
        "Valor Unitario": ["Precio Unitario"],
        "Importe": ["Monto", "Importe MXN"],
    }
    opcionales = {
        "Orden": ["Número de orden", "No. de orden", "No Orden", "Num Orden", "Orden de compra"],
        "Unidad": ["Unidad de medida"],
        "Clave Unidad": [],
        "Moneda": ["Divisa"],
    }
    df = resolver_columnas(df, requeridas, opcionales)
    clave = df["Clave"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df = df.loc[clave.str.startswith(PREFIJO_DIVISAS, na=False)].copy()
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_OPERACIONES_DIVISAS)

    descripcion = df["Descripcion"].fillna("").astype(str)
    texto_divisa = descripcion.copy()
    for columna in ("Unidad", "Clave Unidad", "Moneda"):
        if columna in df.columns:
            texto_divisa = texto_divisa.str.cat(df[columna].fillna("").astype(str), sep=" ")
    desc_norm = texto_divisa.map(_norm)
    divisa = pd.Series(pd.NA, index=df.index, dtype="string")
    es_usd = desc_norm.str.contains(
        r"\b(?:usd|dls?|dlls?|dollars?|(?:us\s*)?dolares?|(?:us\s*)?dolar(?:es)?|us\s*dollar)\b",
        regex=True, na=False,
    )
    es_eur = desc_norm.str.contains(r"\b(?:eur|euros?)\b", regex=True, na=False)
    divisa.loc[es_usd & ~es_eur] = "USD"
    divisa.loc[es_eur & ~es_usd] = "EUR"

    patron_fecha = r"(?:operaci[oó]n|liquidaci[oó]n|fecha)\D{0,30}(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    fecha_texto = descripcion.str.extract(patron_fecha, flags=re.IGNORECASE)[0]
    fecha_operacion = a_fecha(fecha_texto)
    fecha_cfdi = a_fecha(df["Fecha"])
    fecha_operacion = fecha_operacion.fillna(fecha_cfdi)

    cantidad = a_numero(df["Cantidad"])
    tc_facturado = a_numero(df["Valor Unitario"])
    importe_mxn = a_numero(df["Importe"])
    orden = df.get("Orden", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    rfc = df["RFC Emisor"].fillna("").astype(str).str.strip().str.upper()
    institucion = df["Razon Social Emisor"].fillna("").astype(str).str.strip()
    institucion = institucion.mask(institucion.eq(""), rfc)

    salida = pd.DataFrame({
        "Clave": clave.loc[df.index],
        "Descripcion": descripcion,
        "Divisa": divisa,
        "Fecha_Operacion": fecha_operacion,
        "Fecha_CFDI": fecha_cfdi,
        "Cantidad": cantidad,
        "Monto_Divisa": cantidad,
        "TC_Facturado": tc_facturado,
        "Importe_MXN": importe_mxn,
        "RFC_Emisor": rfc,
        "Institucion": institucion,
        "Num_Orden": orden,
        "Orden_Duplicada": False,
        "Desfase_Alerta": False,
    }, index=df.index)
    valida = (
        salida["Divisa"].notna()
        & salida["Fecha_Operacion"].notna()
        & salida["Cantidad"].gt(0)
        & salida["TC_Facturado"].gt(0)
        & salida["Importe_MXN"].gt(0)
        & salida["RFC_Emisor"].ne("")
    )
    salida = salida.loc[valida].copy()

    # Marcar únicamente filas idénticas que comparten un identificador explícito de orden.
    tiene_orden = salida["Num_Orden"].ne("")
    clave_orden = ["RFC_Emisor", "Divisa", "Num_Orden", "Fecha_Operacion", "Cantidad", "TC_Facturado", "Importe_MXN"]
    repetida = salida.loc[tiene_orden].duplicated(clave_orden, keep=False)
    salida.loc[repetida.index[repetida], "Orden_Duplicada"] = True
    desfase = (salida["Fecha_CFDI"] - salida["Fecha_Operacion"]).dt.days
    salida["Desfase_Alerta"] = desfase.gt(DIAS_DESFASE_ALERTA).fillna(False)
    return salida.reset_index(drop=True)


def validar_congruencia_fiscal(tipos_archivo: dict, regimen_seleccionado: str) -> list[str]:
    """
    QUÉ HACE: Analiza una muestra utilizable de cada categoría cargada, extrae el RFC de la empresa
    y compara su longitud con el régimen seleccionado. También busca señales de mala clasificación (ej. Nómina en Egresos).
    
    POR QUÉ SE IMPLEMENTA: Para evitar que el usuario procese por error archivos de una Persona Moral 
    en el módulo de Persona Física (o viceversa), lo cual corrompería las métricas financieras sin lanzar un error técnico.
    Es una advertencia "no destructiva": avisa, pero no bloquea.
    """
    import re
    import gc
    
    advertencias = []
    archivos_verificados = 0
    errores_lectura = []
    
    # MAPEO ESTRATÉGICO: 
    # En facturas emitidas, la empresa es el "Emisor". En recibidas, la empresa es el "Receptor".
    reglas_busqueda = {
        "ingresos_facturas": "rfcemisor",
        "egresos_facturas": "rfcreceptor",
        "nomina": "rfcemisor"
    }
    
    for tipo, archivos in tipos_archivo.items():
        if not archivos or tipo not in reglas_busqueda:
            continue
        col_objetivo = reglas_busqueda[tipo]
        for archivo in archivos:
            nombre_archivo = archivo.name if hasattr(archivo, "name") else "muestra"
            try:
                bytes_data = (
                    archivo.descargar()
                    if hasattr(archivo, "descargar")
                    else archivo.getvalue()
                    if hasattr(archivo, "getvalue")
                    else archivo
                )
                df = leer_archivo(nombre_archivo, bytes_data)
            except (ImportError, OSError, ValueError, TypeError, KeyError, pd.errors.ParserError) as error:
                errores_lectura.append(
                    f"**{nombre_archivo}**: No se pudo leer para verificar el régimen ({error})."
                )
                continue

            cols_norm = {
                re.sub(r"[^a-z0-9]", "", _norm(str(col))): col
                for col in df.columns
            }
            if tipo == "egresos_facturas" and "fechadecertificacion" in cols_norm:
                advertencias.append(
                    f"**{nombre_archivo}**: Se clasificó en Egresos, pero contiene formato de Nómina."
                )

            col_real = cols_norm.get(col_objetivo)
            if col_real is None:
                del df
                gc.collect()
                continue

            rfcs = df[col_real].dropna().astype(str).str.strip()
            rfc_empresa = next((rfc for rfc in rfcs.unique() if len(rfc) in (12, 13)), None)
            del df
            gc.collect()
            if rfc_empresa is None:
                continue

            archivos_verificados += 1
            regimen_detectado = "Persona Moral" if len(rfc_empresa) == 12 else "Persona Física"
            if regimen_detectado != regimen_seleccionado:
                advertencias.append(
                    f"**{nombre_archivo}**: El RFC ({rfc_empresa}) indica que es de **{regimen_detectado}**, "
                    f"pero elegiste **{regimen_seleccionado}**."
                )
            break

    # Si no fue posible leer archivos ni localizar un RFC en las columnas esperadas, se explica por qué.
    if archivos_verificados == 0:
        advertencias.extend(errores_lectura)
        advertencias.append("Los datos no bastan para verificar automáticamente el régimen.")
        
    return advertencias


def parsear_actividades_csf(texto: str) -> list[dict]:
    """Tabla «Actividades Económicas» (Orden · Actividad Económica · Porcentaje · Fecha Inicio · Fecha Fin) del texto de una Constancia de Situación Fiscal -> lista de
    {'Actividad Económica', 'Porcentaje (%)', 'Fecha de inicio'}. Une los renglones partidos de un nombre largo y omite el encabezado y los «Página [n] de [m]». [] si no hay tabla."""
    m = re.search(r"Actividades\s+Econ[oó]micas\s*:?", texto, flags=re.I)
    if not m:
        return []
    cuerpo = texto[m.end():]
    fin = re.search(r"\n\s*(?:Reg[ií]menes|Obligaciones)\s*:?", cuerpo, flags=re.I)
    cuerpo = cuerpo[:fin.start()] if fin else cuerpo
    lineas = [
        t for linea in cuerpo.splitlines()
        if (t := linea.strip())
        and not re.match(r"P[aá]gina\s*\[?\d+\]?\s*de\s*\[?\d+\]?", t, flags=re.I)
        and not re.match(r"Orden\s+Actividad", t, flags=re.I)
    ]
    inicios = [i for i, t in enumerate(lineas) if re.match(r"^\d{1,2}\s+[^\d\s]", t)]
    filas = []
    for j, inicio in enumerate(inicios):
        fin_fila = inicios[j + 1] if j + 1 < len(inicios) else len(lineas)
        bloque = " ".join(lineas[inicio:fin_fila])
        contenido = re.sub(r"^\d{1,2}\s+", "", bloque, count=1)
        fecha = re.search(r"\d{2}/\d{2}/\d{4}", contenido)
        contenido_actividad = contenido[:fecha.start()] if fecha else ""
        porcentajes = list(re.finditer(r"(?<!\S)(\d{1,3}(?:[.,]\d+)?)\s*%?(?!\S)", contenido_actividad))
        if fecha and porcentajes:
            porcentaje = porcentajes[-1]
            nombre = re.sub(
                r"\s+",
                " ",
                contenido_actividad[:porcentaje.start()] + contenido_actividad[porcentaje.end():],
            ).strip()
            filas.append({
                "Actividad Económica": nombre,
                "Porcentaje (%)": float(porcentaje.group(1).replace(",", ".")),
                "Fecha de inicio": fecha.group(0),
            })
    return filas


VERSION_PARSEADOR_ACTIVIDADES_CSF = "2"


@st.cache_data(show_spinner="Leyendo la Constancia de Situación Fiscal…")
def _constancia_cache(contenido: bytes, version: str) -> list[dict]:
    """PDF de la Constancia de Situación Fiscal -> actividades económicas (`parsear_actividades_csf`). ImportError si falta `pypdf`."""
    from pypdf import PdfReader
    return parsear_actividades_csf("\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(contenido)).pages))


def _file_uploader_persistente(etiqueta: str, tipos: list[str], clave: str) -> _ArchivoMem | None:
    version_key = f"{clave}_uploader_version"
    archivo_key = f"{clave}_archivo_guardado"
    version = int(st.session_state.get(version_key, 0))
    archivo_subido = st.file_uploader(etiqueta, type=tipos, key=f"{clave}_uploader_{version}")
    if archivo_subido is not None:
        st.session_state[archivo_key] = (archivo_subido.name, archivo_subido.getvalue())

    guardado = st.session_state.get(archivo_key)
    if guardado is None:
        return None

    columna_archivo, columna_quitar = st.columns([5, 1])
    columna_archivo.caption(f"Archivo guardado en esta sesión: {guardado[0]}")
    if columna_quitar.button("Quitar", key=f"{clave}_quitar"):
        st.session_state.pop(archivo_key, None)
        st.session_state[version_key] = version + 1
        st.rerun()

    return _ArchivoMem(*guardado)


def _actividades_constancia_sat(pdf: _ArchivoMem | None) -> pd.DataFrame:
    """Lee las actividades económicas de un PDF de Constancia, si se proporcionó."""
    filas = []
    if pdf is not None:
        try:
            filas = _constancia_cache(pdf.getvalue(), f"{CODIGO_VERSION}:{VERSION_PARSEADOR_ACTIVIDADES_CSF}")
        except ImportError:
            st.warning("Falta la biblioteca `pypdf` para leer el PDF (pip install pypdf).")
        except Exception as e:                                       # PDF dañado, cifrado o escaneado
            st.warning(f"No se pudo leer «{pdf.name}»: {e}.")
        else:
            if not filas:
                st.warning(f"No se encontró la tabla «Actividades Económicas» en «{pdf.name}».")
    return pd.DataFrame({"Actividad Económica": pd.Series([f["Actividad Económica"] for f in filas], dtype="object"),
                         "Porcentaje (%)": pd.Series([f["Porcentaje (%)"] for f in filas], dtype="float"),
                         "Fecha de inicio": pd.Series([f["Fecha de inicio"] for f in filas], dtype="object")})


def _bloque_constancia_sat() -> pd.DataFrame:
    """Carga la Constancia con su uploader persistente y devuelve sus actividades."""
    pdf = _file_uploader_persistente(
        "Sube la Constancia de Situación Fiscal (PDF)", ["pdf"], "csf_pdf"
    )
    return _actividades_constancia_sat(pdf)


def _normalizar_clave_sat(serie: pd.Series) -> pd.Series:
    """Clave de producto/servicio como texto de 8 dígitos: sin decimales «.0» de Excel y con ceros a la izquierda (1010101 -> 01010101)."""
    return serie.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(8)



def tasa_impuesto_sat(serie: pd.Series) -> pd.Series:
    """`Tasa Impuestos Trasladados` como fracción: numérica, nulos o ilegibles = 0.0 y, si el valor viene en formato porcentual (> 1, p. ej. 16 o «16%»), entre 100."""
    t = a_numero(serie.astype(str).str.replace("%", "", regex=False)).fillna(0.0)
    return t.where(t <= 1, t / 100)


def monto_con_iva_partida(d: pd.DataFrame) -> tuple[pd.Series, str]:
    """Calcula el monto de cada partida con IVA, sin redondear antes de sumar:
    `Importe + (Importe Base.fillna(0) × tasa)` si existe la base, `Importe × (1 + tasa)` si no existe; sin tasa, conserva `Importe`."""
    if "Tasa Impuestos Trasladados" not in d.columns:
        return d["Importe"].astype(float), "sin_tasa"
    tasa = tasa_impuesto_sat(d["Tasa Impuestos Trasladados"])
    if "Importe Base" in d.columns:
        return d["Importe"] + a_numero(d["Importe Base"]).fillna(0.0) * tasa, "importe_base"
    return d["Importe"] * (1 + tasa), "importe"


def emitidos_productos_sat(df: pd.DataFrame) -> pd.DataFrame:
    """Base `CFDIs Emitidos Productos` (texto crudo) -> partidas ACTIVAS de tipo FACTURA (sin canceladas ni notas de crédito) con `Importe` (SubTotal sin IVA de la partida) numérico,
    `Monto` (el monto con IVA calculado por partida: la cifra que usa la sección 10; `attrs['regla_iva']` indica la regla), `Clave` de 8 dígitos, `Clase` (sus primeros 6 dígitos),
    `Fecha` y `Anio`. Descarta lo que no tenga fecha, importe o clave de 8 dígitos legibles
    (`attrs['descartadas']`). KeyError con las columnas faltantes si no es esa base."""
    df = resolver_columnas(df, COLS_EMITIDOS_PRODUCTOS, COLS_EMITIDOS_PRODUCTOS_OPC)
    vigente = (df["Estatus"].astype(str).str.strip().str.casefold() == "activo") & (df["Tipo Documento"].astype(str).str.strip().str.upper() == "FACTURA")
    d = df[vigente].copy()
    d["Fecha"], d["Importe"], d["Clave"] = a_fecha(d["Fecha"]), a_numero(d["Importe"]), _normalizar_clave_sat(d["Clave"])
    ilegible = d["Fecha"].isna() | d["Importe"].isna() | ~d["Clave"].str.fullmatch(r"\d{8}")
    d = d[~ilegible].copy()
    if "Descripcion" not in d.columns:
        d["Descripcion"] = ""
    d["Anio"] = d["Fecha"].dt.year.astype(int)
    d["Clase"] = d["Clave"].str[:6]
    d["Monto"], regla = monto_con_iva_partida(d)
    d.attrs["descartadas"], d.attrs["regla_iva"] = int(ilegible.sum()), regla
    return d.reset_index(drop=True)


@st.cache_data(show_spinner="Leyendo los productos emitidos…")
def _emitidos_productos_cache(nombre: str, contenido: bytes, version: str) -> pd.DataFrame:
    return emitidos_productos_sat(leer_archivo(nombre, contenido))


def _normalizar_uuid_clase_sat(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.upper()
        .str.replace(r"\s+", "", regex=True)
        .replace({"NAN": "", "NONE": ""})
    )


def _tipo_documento_es_ncr(valor) -> bool:
    tipo = _norm(valor)
    return (
        tipo == "e"
        or "egreso" in tipo
        or "ncr" in tipo
        or "nota de credito" in tipo
        or "nota credito" in tipo
    )


def _puntaje_bloque_ncr(grupo: pd.DataFrame) -> int:
    puntaje = int(grupo["Clave"].eq("84111506").any())
    descripciones = grupo["Descripcion"].map(_norm)
    terminos = (
        ("anticipo",),
        ("nota de credito", "nota credito"),
        ("devolucion",),
        ("bonificacion",),
    )
    for variantes in terminos:
        puntaje += int(
            descripciones.map(
                lambda texto: any(termino in texto for termino in variantes)
            ).any()
        )
    return puntaje


def _emparejar_bloques_egresos(
    bloques: list[dict], encabezados: pd.DataFrame
) -> dict[int, int]:
    """Cruza bloques y encabezados por huella exacta y luego con tolerancia de dos centavos."""
    bloques_por_huella = {}
    encabezados_por_huella = {}
    for bloque in bloques:
        bloques_por_huella.setdefault(bloque["huella"], []).append(bloque)
    for indice, encabezado in encabezados.iterrows():
        huella = encabezado["huella"]
        if huella is not None:
            encabezados_por_huella.setdefault(huella, []).append(indice)

    asignaciones = {}
    bloques_usados = set()
    encabezados_usados = set()
    for huella in bloques_por_huella.keys() & encabezados_por_huella.keys():
        bloques_iguales = sorted(
            bloques_por_huella[huella],
            key=lambda bloque: (-bloque["puntaje_ncr"], bloque["id"]),
        )
        encabezados_iguales = sorted(
            encabezados_por_huella[huella],
            key=lambda indice: (
                not encabezados.at[indice, "es_ncr"],
                indice,
            ),
        )
        for bloque, indice in zip(bloques_iguales, encabezados_iguales):
            asignaciones[bloque["id"]] = indice
            bloques_usados.add(bloque["id"])
            encabezados_usados.add(indice)

    candidatos = []
    bloques_restantes = [
        bloque for bloque in bloques if bloque["id"] not in bloques_usados
    ]
    encabezados_restantes = [
        indice for indice in encabezados.index if indice not in encabezados_usados
    ]
    for indice in encabezados_restantes:
        huella_encabezado = encabezados.at[indice, "huella"]
        if huella_encabezado is None:
            continue
        fecha, rfc, moneda, subtotal, total = huella_encabezado
        for bloque in bloques_restantes:
            if bloque["huella"] is None:
                continue
            b_fecha, b_rfc, b_moneda, b_subtotal, b_total = bloque["huella"]
            if (fecha, rfc, moneda) != (b_fecha, b_rfc, b_moneda):
                continue
            diferencia_subtotal = abs(subtotal - b_subtotal)
            diferencia_total = abs(total - b_total)
            if diferencia_subtotal <= 0.02 and diferencia_total <= 0.02:
                candidatos.append((
                    not encabezados.at[indice, "es_ncr"],
                    -bloque["puntaje_ncr"],
                    diferencia_subtotal + diferencia_total,
                    diferencia_subtotal,
                    diferencia_total,
                    indice,
                    bloque["id"],
                ))

    for _, _, _, _, _, indice, bloque_id in sorted(candidatos):
        if indice in encabezados_usados or bloque_id in bloques_usados:
            continue
        asignaciones[bloque_id] = indice
        encabezados_usados.add(indice)
        bloques_usados.add(bloque_id)
    return asignaciones


def egresos_productos_sat(
    df: pd.DataFrame, df_encabezados: pd.DataFrame
) -> pd.DataFrame:
    """Cruza CFDIs recibidos con encabezados, limpia comprobantes y calcula importes MXN por partida."""
    columna_clave = buscar_columna(df.columns, "Codigo SAT") or buscar_columna(
        df.columns, "Clave"
    )
    columnas = {
        "Fecha": buscar_columna(df.columns, "Fecha y Hora")
        or buscar_columna(df.columns, "Fecha de Emision")
        or buscar_columna(df.columns, "Fecha Emision")
        or buscar_columna(df.columns, "Fecha"),
        "Importe": buscar_columna(df.columns, "Importe"),
        "Descuento": buscar_columna(df.columns, "Descuento"),
        "Moneda": buscar_columna(df.columns, "Moneda"),
        "Tipo de Cambio": buscar_columna(df.columns, "Tipo de Cambio"),
        "Impuestos Trasladados": buscar_columna(df.columns, "Impuestos Trasladados"),
        "Impuestos Retenidos": buscar_columna(df.columns, "Impuestos Retenidos"),
    }
    faltantes = [
        nombre for nombre, columna in columnas.items()
        if columna is None and nombre != "Descuento"
    ]
    if columna_clave is None:
        faltantes.insert(0, "Codigo SAT o Clave")
    if faltantes:
        raise KeyError("Faltan columnas requeridas: " + ", ".join(faltantes))
    if df_encabezados is None or df_encabezados.empty:
        raise KeyError("Falta la base SAT CFDIs Recibidos con los encabezados de comprobantes.")

    columnas_encabezado = {
        "UUID": buscar_columna(df_encabezados.columns, "UUID"),
        "Estatus": buscar_columna(df_encabezados.columns, "Estatus"),
        "Tipo Documento": (
            buscar_columna(df_encabezados.columns, "Tipo Documento")
            or buscar_columna(df_encabezados.columns, "Tipo de Documento")
            or buscar_columna(df_encabezados.columns, "Tipo de Comprobante")
        ),
    }
    faltantes_encabezado = [
        nombre for nombre, columna in columnas_encabezado.items() if columna is None
    ]
    if faltantes_encabezado:
        raise KeyError(
            "La base SAT CFDIs Recibidos requiere las columnas: "
            + ", ".join(faltantes_encabezado)
        )

    indice = pd.RangeIndex(len(df))
    descripcion_col = buscar_columna(df.columns, "Descripcion")
    uuid_col = buscar_columna(df.columns, "UUID CFDI Recibido")
    partida_col = buscar_columna(df.columns, "Partida")
    tipo_cambio_dof_col = buscar_columna(df.columns, "Tipo de Cambio DOF")
    local_trasladado_col = buscar_columna(df.columns, "Importe Local Trasladado")
    local_retenido_col = buscar_columna(df.columns, "Importe Local Retenido")

    def numero_opcional(columna):
        if columna is None:
            return pd.Series(0.0, index=indice)
        numeros = a_numero(df[columna])
        return numeros.where(np.isfinite(numeros), 0.0).fillna(0.0).reset_index(drop=True)

    base = pd.DataFrame({
        "Clave": _normalizar_clave_sat(df[columna_clave]).reset_index(drop=True),
        "Fecha": a_fecha(df[columnas["Fecha"]]).reset_index(drop=True),
        "RFC_Emisor": (
            (
                df[buscar_columna(df.columns, "RFC Emisor")]
                .fillna("").astype(str).str.strip().str.upper()
                if buscar_columna(df.columns, "RFC Emisor") is not None
                else pd.Series("", index=indice)
            )
            .reset_index(drop=True)
        ),
        "Importe": a_numero(df[columnas["Importe"]]).reset_index(drop=True),
        "Descuento": numero_opcional(columnas["Descuento"]),
        "Moneda": (
            df[columnas["Moneda"]].fillna("").astype(str).str.strip().str.upper()
            .reset_index(drop=True)
        ),
        "Tipo_Cambio": a_numero(df[columnas["Tipo de Cambio"]]).reset_index(drop=True),
        "Tipo_Cambio_DOF": (
            a_numero(df[tipo_cambio_dof_col]).reset_index(drop=True)
            if tipo_cambio_dof_col is not None
            else pd.Series(np.nan, index=indice)
        ),
        "Impuestos_Trasladados": numero_opcional(
            columnas["Impuestos Trasladados"]
        ),
        "Impuestos_Retenidos": numero_opcional(
            columnas["Impuestos Retenidos"]
        ),
        "ImpLocalTras_Original": numero_opcional(local_trasladado_col),
        "ImpLocalRet_Original": numero_opcional(local_retenido_col),
        "Descripcion": (
            df[descripcion_col].fillna("").astype(str).reset_index(drop=True)
            if descripcion_col is not None
            else pd.Series("", index=indice)
        ),
        "_Orden": np.arange(len(df)),
    })
    clave_producto = _normalizar_uuid_clase_sat(
        df[uuid_col] if uuid_col is not None else pd.Series("", index=indice)
    ).reset_index(drop=True)
    excluidas_divisas = base["Clave"].str.startswith("841216", na=False)

    moneda_mxn = base["Moneda"].isin(
        ["MXN", "PESO", "PESOS", "PESO MEXICANO", "PESOS MEXICANOS"]
    )
    tc_valido = np.isfinite(base["Tipo_Cambio"]) & base["Tipo_Cambio"].gt(0)
    tc_dof_valido = (
        np.isfinite(base["Tipo_Cambio_DOF"]) & base["Tipo_Cambio_DOF"].gt(0)
    )
    usa_tc_dof = ~moneda_mxn & ~tc_valido & tc_dof_valido
    factor_mxn = base["Tipo_Cambio"].where(tc_valido)
    factor_mxn = factor_mxn.fillna(base["Tipo_Cambio_DOF"].where(tc_dof_valido))
    factor_mxn = factor_mxn.where(~moneda_mxn, 1.0)
    sin_tipo_cambio = ~moneda_mxn & factor_mxn.isna()
    base["Tipo_Cambio_Aplicado"] = factor_mxn

    encabezados = pd.DataFrame({
        "UUID": _normalizar_uuid_clase_sat(
            df_encabezados[columnas_encabezado["UUID"]]
        ).reset_index(drop=True),
        "Estatus": (
            df_encabezados[columnas_encabezado["Estatus"]]
            .fillna("").astype(str).str.strip().reset_index(drop=True)
        ),
        "Tipo Documento": (
            df_encabezados[columnas_encabezado["Tipo Documento"]]
            .fillna("").astype(str).str.strip().reset_index(drop=True)
        ),
    })
    encabezados["_Orden_Encabezado"] = np.arange(len(encabezados))
    encabezados["es_ncr"] = encabezados["Tipo Documento"].map(_tipo_documento_es_ncr)
    modo_uuid = uuid_col is not None

    if modo_uuid:
        encabezados_validos = encabezados.loc[encabezados["UUID"].ne("")].drop_duplicates(
            "UUID", keep="first"
        )
        encabezados_por_uuid = encabezados_validos.set_index("UUID")
        base["UUID"] = clave_producto
        base["_TieneCruce"] = base["UUID"].isin(encabezados_por_uuid.index)
        base["Documento_ID"] = base["UUID"].where(base["UUID"].ne(""), "")
        for nombre in ("Estatus", "Tipo Documento"):
            base[nombre] = base["UUID"].map(encabezados_por_uuid[nombre])
        modo_cruce = "UUID CFDI Recibido"
        base["ImpLocalTras_Dedup"] = 0.0
        base["ImpLocalRet_Dedup"] = 0.0
        fila_valida_local = (
            base["Clave"].str.fullmatch(r"\d{8}")
            & base["Fecha"].notna()
            & base["Importe"].notna()
            & np.isfinite(base["Importe"])
            & ~sin_tipo_cambio
            & ~excluidas_divisas
            & base["UUID"].ne("")
        )
        filas_validas = base.loc[fila_valida_local].sort_values("_Orden")
        primeras_filas = filas_validas.drop_duplicates("UUID", keep="first")["_Orden"]
        primera_fila_documento = base["_Orden"].isin(primeras_filas)
        base.loc[primera_fila_documento, "ImpLocalTras_Dedup"] = base.loc[
            primera_fila_documento, "ImpLocalTras_Original"
        ]
        base.loc[primera_fila_documento, "ImpLocalRet_Dedup"] = base.loc[
            primera_fila_documento, "ImpLocalRet_Original"
        ]
    else:
        if partida_col is None:
            raise KeyError(
                "Sin la columna «UUID CFDI Recibido», se requiere «Partida» para reconstruir comprobantes."
            )
        if buscar_columna(df.columns, "RFC Emisor") is None:
            raise KeyError(
                "Sin la columna «UUID CFDI Recibido», se requiere «RFC Emisor» para reconstruir comprobantes."
            )
        campos_huella = {
            "Fecha": buscar_columna(df_encabezados.columns, "Fecha y Hora")
            or buscar_columna(df_encabezados.columns, "Fecha de Emision")
            or buscar_columna(df_encabezados.columns, "Fecha Emision")
            or buscar_columna(df_encabezados.columns, "Fecha"),
            "RFC Emisor": buscar_columna(df_encabezados.columns, "RFC Emisor"),
            "Moneda": buscar_columna(df_encabezados.columns, "Moneda"),
            "SubTotal": buscar_columna(df_encabezados.columns, "SubTotal"),
            "Total": buscar_columna(df_encabezados.columns, "Total"),
        }
        faltantes_huella = [
            nombre for nombre, columna in campos_huella.items() if columna is None
        ]
        if faltantes_huella:
            raise KeyError(
                "El cruce por Partida requiere en la base de encabezados: "
                + ", ".join(faltantes_huella)
            )

        partida = a_numero(df[partida_col]).reset_index(drop=True)
        if (
            partida.empty
            or partida.isna().any()
            or not np.isfinite(partida).all()
            or not np.isclose(
                partida.to_numpy(), np.round(partida.to_numpy())
            ).all()
        ):
            raise ValueError("La columna Partida contiene valores vacíos o no enteros.")
        empieza_bloque = partida.eq(1)
        if not empieza_bloque.iloc[0]:
            raise ValueError(
                "El archivo parece reordenado: la primera fila de productos no inicia con Partida 1."
            )
        block_ids = empieza_bloque.cumsum().astype(int)
        esperado = block_ids.groupby(block_ids, sort=False).cumcount() + 1
        if not partida.astype(int).eq(esperado).all():
            raise ValueError(
                "El archivo parece reordenado: Partida no conserva secuencias consecutivas 1..N."
            )
        base["Block_ID"] = block_ids
        base["Documento_ID"] = "BLOCK-" + block_ids.astype(str)
        base["ImpLocalTras_Dedup"] = base["ImpLocalTras_Original"].where(
            empieza_bloque, 0.0
        )
        base["ImpLocalRet_Dedup"] = base["ImpLocalRet_Original"].where(
            empieza_bloque, 0.0
        )

        encabezados["Fecha_Huella"] = a_fecha(
            df_encabezados[campos_huella["Fecha"]]
        ).reset_index(drop=True)
        encabezados["RFC_Huella"] = (
            df_encabezados[campos_huella["RFC Emisor"]]
            .fillna("").astype(str).str.strip().str.upper().reset_index(drop=True)
        )
        encabezados["Moneda_Huella"] = (
            df_encabezados[campos_huella["Moneda"]]
            .fillna("").astype(str).str.strip().str.upper().reset_index(drop=True)
        )
        encabezados["SubTotal_Huella"] = a_numero(
            df_encabezados[campos_huella["SubTotal"]]
        ).reset_index(drop=True)
        encabezados["Total_Huella"] = a_numero(
            df_encabezados[campos_huella["Total"]]
        ).reset_index(drop=True)

        def crear_huella(fecha, rfc, moneda, subtotal, total):
            if (
                pd.isna(fecha) or not rfc or not moneda
                or pd.isna(subtotal) or pd.isna(total)
                or not np.isfinite(float(subtotal))
                or not np.isfinite(float(total))
            ):
                return None
            return (fecha, rfc, moneda, round(float(subtotal), 2), round(float(total), 2))

        encabezados["huella"] = [
            crear_huella(fecha, rfc, moneda, subtotal, total)
            for fecha, rfc, moneda, subtotal, total in zip(
                encabezados["Fecha_Huella"],
                encabezados["RFC_Huella"],
                encabezados["Moneda_Huella"],
                encabezados["SubTotal_Huella"],
                encabezados["Total_Huella"],
            )
        ]
        bloques = []
        for block_id, grupo in base.groupby("Block_ID", sort=True):
            fechas = grupo["Fecha"].dropna().unique()
            rfcs = grupo["RFC_Emisor"].dropna().unique()
            monedas = grupo["Moneda"].dropna().unique()
            bloque_valido = (
                len(fechas) == 1
                and len(rfcs) == 1
                and len(monedas) == 1
                and grupo["Importe"].notna().all()
                and np.isfinite(grupo["Importe"]).all()
                and bool(rfcs[0])
                and bool(monedas[0])
            )
            huella = None
            if bloque_valido:
                subtotal = grupo["Importe"].sum()
                total_original = (
                    grupo["Importe"]
                    - grupo["Descuento"]
                    + grupo["Impuestos_Trasladados"]
                    + grupo["ImpLocalTras_Dedup"]
                    - grupo["Impuestos_Retenidos"]
                    - grupo["ImpLocalRet_Dedup"]
                ).sum()
                huella = crear_huella(
                    fechas[0], rfcs[0], monedas[0], subtotal, total_original
                )
            bloques.append({
                "id": int(block_id),
                "huella": huella,
                "puntaje_ncr": _puntaje_bloque_ncr(grupo),
            })
        asignaciones = _emparejar_bloques_egresos(bloques, encabezados)
        encabezados_por_indice = encabezados.set_index("_Orden_Encabezado")
        por_bloque = {
            int(block_id): int(indice_encabezado)
            for block_id, indice_encabezado in asignaciones.items()
        }
        base["_Indice_Encabezado"] = base["Block_ID"].map(por_bloque)
        base["_TieneCruce"] = base["_Indice_Encabezado"].notna()
        for nombre in ("UUID", "Estatus", "Tipo Documento"):
            mapa = encabezados_por_indice[nombre]
            base[nombre] = base["_Indice_Encabezado"].map(mapa)
        modo_cruce = "reconstrucción por Partida"

    base["Estatus_Normalizado"] = base["Estatus"].fillna("").map(_norm)
    base["Tipo_Normalizado"] = base["Tipo Documento"].fillna("").map(_norm)
    estatus_cancelado = base["Estatus_Normalizado"].str.contains("cancel", regex=False)
    ncr = base["Tipo Documento"].map(_tipo_documento_es_ncr)
    tipo_valido = base["Tipo_Normalizado"].isin({"factura", "ingreso", "i"})
    estatus_valido = base["Estatus_Normalizado"].isin({"activo", "vigente"})
    tiene_cruce = base["_TieneCruce"]

    def contar_exclusion(mascara):
        filas = base.loc[mascara]
        documentos = filas.loc[filas["Documento_ID"].ne(""), "Documento_ID"].nunique()
        return int(mascara.sum()), int(documentos)

    filas_divisas, comprobantes_divisas = contar_exclusion(excluidas_divisas)
    filas_ncr, comprobantes_ncr = contar_exclusion(tiene_cruce & ncr)
    filas_cancelados, comprobantes_cancelados = contar_exclusion(
        tiene_cruce & estatus_cancelado
    )
    filas_sin_cruce, comprobantes_sin_cruce = contar_exclusion(~tiene_cruce)
    documento_admisible = tiene_cruce & estatus_valido & tipo_valido
    base_valida = (
        base["Clave"].str.fullmatch(r"\d{8}")
        & base["Fecha"].notna()
        & base["Importe"].notna()
        & np.isfinite(base["Importe"])
        & ~sin_tipo_cambio
    )
    descartadas = int((documento_admisible & ~excluidas_divisas & ~base_valida).sum())
    sin_tipo_cambio_validas = int(
        (documento_admisible & ~excluidas_divisas & sin_tipo_cambio).sum()
    )
    registros_validos = (
        documento_admisible
        & ~excluidas_divisas
        & base_valida
    )
    filas_tc_dof = int((registros_validos & usa_tc_dof).sum())
    base = base.loc[registros_validos].copy()

    base["Anio"] = base["Fecha"].dt.year.astype(int)
    base["Clase"] = base["Clave"].str[:6]
    base["SubTotal_Neto_MXN"] = (
        base["Importe"] - base["Descuento"]
    ) * base["Tipo_Cambio_Aplicado"]
    base["Imp_Trasladados_MXN"] = (
        base["Impuestos_Trasladados"] + base["ImpLocalTras_Dedup"]
    ) * base["Tipo_Cambio_Aplicado"]
    base["Imp_Retenidos_MXN"] = (
        base["Impuestos_Retenidos"] + base["ImpLocalRet_Dedup"]
    ) * base["Tipo_Cambio_Aplicado"]
    base["Monto_MXN"] = (
        base["SubTotal_Neto_MXN"]
        + base["Imp_Trasladados_MXN"]
        - base["Imp_Retenidos_MXN"]
    )
    base["Monto"] = base["Monto_MXN"]

    salida = base.reset_index(drop=True)
    salida.attrs.update({
        "modo_cruce": modo_cruce,
        "filas_divisas_excluidas": filas_divisas,
        "comprobantes_divisas_excluidos": comprobantes_divisas,
        "filas_ncr_excluidas": filas_ncr,
        "comprobantes_ncr_excluidos": comprobantes_ncr,
        "filas_cancelados_excluidas": filas_cancelados,
        "comprobantes_cancelados_excluidos": comprobantes_cancelados,
        "filas_sin_cruce": filas_sin_cruce,
        "comprobantes_sin_cruce": comprobantes_sin_cruce,
        "filas_sin_tipo_cambio": sin_tipo_cambio_validas,
        "filas_tc_dof": filas_tc_dof,
        "filas_descartadas": descartadas,
    })
    return salida


def _leer_archivo_clase_sat(nombre: str, contenido) -> pd.DataFrame:
    if isinstance(contenido, tuple):
        dfs = [
            leer_archivo(nombre_parte, bytes_parte)
            for nombre_parte, bytes_parte in contenido
        ]
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return leer_archivo(nombre, contenido)


@st.cache_data(show_spinner="Procesando productos recibidos…", max_entries=2)
def _egresos_productos_cache(
    nombre: str,
    contenido,
    nombre_encabezados: str,
    contenido_encabezados,
    version: str,
) -> pd.DataFrame:
    return egresos_productos_sat(
        _leer_archivo_clase_sat(nombre, contenido),
        _leer_archivo_clase_sat(nombre_encabezados, contenido_encabezados),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _clasificar_base_clase_sat(
    nombre: str, contenido: bytes, version: str
) -> str | None:
    columnas = {_norm(str(columna)) for columna in leer_archivo(nombre, contenido).columns}
    es_encabezados = (
        {"uuid", "estatus", "total"}.issubset(columnas)
        and bool({"tipo documento", "tipo de documento", "tipo de comprobante"} & columnas)
    )
    es_emitidos = {
        "clave", "fecha", "estatus", "tipo documento", "importe"
    }.issubset(columnas)
    es_egresos = (
        bool({"codigo sat", "clave"} & columnas)
        and {
            "fecha", "importe", "moneda", "tipo de cambio",
            "impuestos trasladados", "impuestos retenidos",
        }.issubset(columnas)
    )
    if es_encabezados:
        return "encabezados"
    if es_emitidos == es_egresos:
        return "ambiguo" if es_emitidos else None
    return "emitidos" if es_emitidos else "egresos"


@st.cache_data(show_spinner="Leyendo el catálogo oficial del SAT…")
def _leer_catalogo_sat(ruta: str, firma: int, version: str) -> dict:
    """Hoja `c_ClaveProdServ` (encabezado en la fila 5: `skiprows=4`) -> {'claves': {clave_8: Descripción}, 'archivo': nombre}. `firma` (fecha de modificación del archivo) invalida la
    caché si se reemplaza el catálogo. KeyError si la hoja no trae las columnas esperadas."""
    df = pd.read_excel(ruta, sheet_name="c_ClaveProdServ", skiprows=4, dtype=str, engine="calamine")
    col_clave, col_desc = buscar_columna(df.columns, "c_ClaveProdServ"), buscar_columna(df.columns, "Descripcion")
    if col_clave is None or col_desc is None:
        raise KeyError(f"La hoja c_ClaveProdServ no trae las columnas c_ClaveProdServ y Descripción. Columnas encontradas: {list(df.columns)}")
    claves = _normalizar_clave_sat(df[col_clave])
    valida = claves.str.fullmatch(r"\d{8}")
    return {"claves": dict(zip(claves[valida], df.loc[valida, col_desc].fillna("").astype(str).str.strip())), "archivo": Path(ruta).name}



def _ruta_catalogo_sat() -> Path | None:
    """Busca el catálogo SAT primero en `data/` y luego en la raíz y carpeta del módulo."""
    base = Path(__file__).resolve().parent
    carpetas = (base.parent / "data", base.parent, base)
    nombres = ("catCFDI_V_4_20261106.xls", "catCFDI_V_4_20261106.xlsx")
    for nombre in nombres:
        for carpeta in carpetas:
            ruta = carpeta / nombre
            if ruta.is_file():
                return ruta
    for carpeta in carpetas:
        otros = sorted((p for p in carpeta.glob("catCFDI*.xls*") if p.is_file()), key=lambda p: p.name, reverse=True)
        if otros:
            return otros[0]
    return None

def cargar_catalogo_sat() -> dict | None:
    """Catálogo SAT de la carpeta del proyecto (en caché); None si no está o no se puede leer."""
    ruta = _ruta_catalogo_sat()
    if ruta is None:
        return None
    try:
        return _leer_catalogo_sat(str(ruta), ruta.stat().st_mtime_ns, CODIGO_VERSION)
    except (KeyError, ValueError, OSError):
        return None

def descripciones_clase_sat(d: pd.DataFrame, catalogo: dict | None) -> dict:
    """{Clase de 6 dígitos: descripción oficial}. La descripción de una clase es la de la fila `Clase + "00"` del catálogo; si no existe (p. ej. 851215), el respaldo es la descripción
    de la clave de 8 dígitos de mayor Monto de esa clase; 010101 es «No existe en el catálogo». Sin catálogo: «Sin catálogo»."""
    claves = (catalogo or {}).get("claves", {})
    if not claves:
        return {c: (ETIQUETA_CLAVE_GENERICA if c == CLASE_GENERICA_SAT else "Sin catálogo") for c in d["Clase"].unique()}
    rep = (d.groupby(["Clase", "Clave"])["Monto"].sum().reset_index().sort_values(["Clase", "Monto", "Clave"], ascending=[True, False, True])
             .drop_duplicates("Clase").set_index("Clase")["Clave"])
    salida = {}
    for clase, clave in rep.items():
        salida[clase] = (ETIQUETA_CLAVE_GENERICA if clase == CLASE_GENERICA_SAT else claves.get(clase + "00") or claves.get(clave) or "Clave no encontrada en el catálogo")
    return salida

def descripciones_clase_sat(d: pd.DataFrame, catalogo: dict | None) -> dict:
    """{Clase de 6 dígitos: descripción oficial}. La descripción de una clase es la de la fila `Clase + "00"` del catálogo; si no existe (p. ej. 851215), el respaldo es la descripción
    de la clave de 8 dígitos de mayor Monto de esa clase; 010101 es «No existe en el catálogo». Sin catálogo: «Sin catálogo»."""
    claves = (catalogo or {}).get("claves", {})
    if not claves:
        return {c: (ETIQUETA_CLAVE_GENERICA if c == CLASE_GENERICA_SAT else "Sin catálogo") for c in d["Clase"].unique()}
    rep = (d.groupby(["Clase", "Clave"])["Monto"].sum().reset_index().sort_values(["Clase", "Monto", "Clave"], ascending=[True, False, True])
             .drop_duplicates("Clase").set_index("Clase")["Clave"])
    salida = {}
    for clase, clave in rep.items():
        salida[clase] = (ETIQUETA_CLAVE_GENERICA if clase == CLASE_GENERICA_SAT else claves.get(clase + "00") or claves.get(clave) or "Clave no encontrada en el catálogo")
    return salida

def actividades_declaradas_csf(actividades) -> list[tuple[str, float]]:
    """[(actividad, porcentaje)] de la tabla de la Constancia (DataFrame con `Actividad Económica` y `Porcentaje (%)`, o None), de mayor a menor porcentaje. Se omiten los renglones sin
    actividad, sin porcentaje legible o con 0%."""
    filas = []
    if actividades is not None:
        for _, r in actividades.iterrows():
            v = r.get("Actividad Económica")
            nombre = "" if v is None or pd.isna(v) else str(v).strip()
            pct = pd.to_numeric(r.get("Porcentaje (%)"), errors="coerce")
            if nombre and pd.notna(pct) and pct > 0:
                filas.append((nombre, float(pct)))
    return sorted(filas, key=lambda f: -f[1])
