from html import escape

import pandas as pd
import streamlit as st
from components.pdf_generator import generate_modular_pdf
from utils import _ArchivoMem

from components.charts import (
    _html_tabla_clase_sat,
    fig_barra_distribucion_100,
    fig_donut_declarado,
    fig_donut_facturado,
    html_barra_distribucion_100,
)

from config import CODIGO_VERSION, NOTA_METODOLOGICA_CLASE_SAT, TOP_FILAS_CLASE_SAT
from core.loader import (
    _actividades_constancia_sat,
    _clasificar_base_clase_sat,
    _datos_archivo_cache,
    _egresos_productos_cache,
    _emitidos_productos_cache,
    anios_5_archivos,
    cargar_catalogo_sat,
    descripciones_clase_sat,
)

_TIPOS_ARCHIVO_CLASE_SAT = {
    "csv", "xlsx", "xls", "xlsb", "parquet", "pqt",
}


def _archivo_en_memoria(archivo) -> _ArchivoMem | None:
    if archivo is None:
        return None
    nombre, contenido = _datos_archivo_cache(archivo)
    return _ArchivoMem(nombre, contenido)


def _cargar_archivos_clase_sat() -> tuple[
    _ArchivoMem | None, _ArchivoMem | None, _ArchivoMem | None, _ArchivoMem | None]:
    version_key = "clase_sat_archivos_uploader_version"
    version = int(st.session_state.get(version_key, 0))
    archivos_subidos = st.file_uploader(
        "Sube aquí las bases que falten. Los archivos cargados en este módulo tienen "
        "prioridad; si falta una base, se reutiliza la correspondiente de la barra "
        "lateral. También puedes cargar la Constancia de Situación Fiscal (PDF).",
        type=sorted(_TIPOS_ARCHIVO_CLASE_SAT | {"pdf"}),
        accept_multiple_files=True,
        key=f"clase_sat_archivos_uploader_{version}",)

    bases = {"emitidos": [], "egresos": [], "encabezados": []}
    constancias = []
    no_reconocidos = []
    for archivo in archivos_subidos or []:
        extension = archivo.name.rsplit(".", 1)[-1].casefold()
        if extension == "pdf":
            constancias.append(archivo)
        elif extension in _TIPOS_ARCHIVO_CLASE_SAT:
            tipo_base = _clasificar_base_clase_sat(
                archivo.name, archivo.getvalue(), CODIGO_VERSION
            )
            if tipo_base in bases:
                bases[tipo_base].append(archivo)
            else:
                no_reconocidos.append(archivo.name)
        else:
            no_reconocidos.append(archivo.name)

    if no_reconocidos:
        st.error(
            "No se pudo identificar por sus columnas el tipo de base de: "
            + ", ".join(no_reconocidos)
        )
    elif any(len(archivos) > 1 for archivos in bases.values()) or len(constancias) > 1:
        st.warning(
            "Carga como máximo una base de CFDIs emitidos, una de recibidos por "
            "producto, una de encabezados SAT y una Constancia. Los archivos "
            "guardados anteriormente se conservaron."
        )
    else:
        if bases["emitidos"]:
            st.session_state["clase_sat_emitidos_productos_archivo_guardado"] = (
                bases["emitidos"][0].name, bases["emitidos"][0].getvalue()
            )
        if bases["egresos"]:
            st.session_state["clase_sat_egresos_productos_archivo_guardado"] = (
                bases["egresos"][0].name, bases["egresos"][0].getvalue()
            )
        if bases["encabezados"]:
            st.session_state["clase_sat_egresos_encabezados_archivo_guardado"] = (
                bases["encabezados"][0].name, bases["encabezados"][0].getvalue()
            )
        if constancias:
            st.session_state["csf_pdf_archivo_guardado"] = (
                constancias[0].name, constancias[0].getvalue()
            )

    emitidos_guardados = st.session_state.get(
        "clase_sat_emitidos_productos_archivo_guardado"
    )
    egresos_guardados = st.session_state.get(
        "clase_sat_egresos_productos_archivo_guardado"
    )
    encabezados_guardados = st.session_state.get(
        "clase_sat_egresos_encabezados_archivo_guardado"
    )
    constancia_guardada = st.session_state.get("csf_pdf_archivo_guardado")
    for state_key, archivo_guardado, nombre in (
        (
            "clase_sat_emitidos_productos_archivo_guardado",
            emitidos_guardados,
            "Base CFDIs Emitidos Productos",
        ),
        (
            "clase_sat_egresos_productos_archivo_guardado",
            egresos_guardados,
            "Base CFDIs Recibidos Productos",
        ),
        (
            "clase_sat_egresos_encabezados_archivo_guardado",
            encabezados_guardados,
            "Base SAT CFDIs Recibidos (encabezados)",
        ),
        ("csf_pdf_archivo_guardado", constancia_guardada, "Constancia de Situación Fiscal"),
    ):
        if archivo_guardado is None:
            continue
        columna_archivo, columna_quitar = st.columns([5, 1])
        columna_archivo.caption(f"{nombre} guardada: {archivo_guardado[0]}")
        if columna_quitar.button(
            "Quitar", key=f"clase_sat_{state_key}_quitar"
        ):
            st.session_state.pop(state_key, None)
            st.session_state[version_key] = version + 1
            st.rerun()

    emitidos = (
        _ArchivoMem(*emitidos_guardados) if emitidos_guardados is not None else None
    )
    egresos = (
        _ArchivoMem(*egresos_guardados) if egresos_guardados is not None else None
    )
    encabezados = (
        _ArchivoMem(*encabezados_guardados)
        if encabezados_guardados is not None
        else None
    )
    constancia = (
        _ArchivoMem(*constancia_guardada)
        if constancia_guardada is not None
        else None
    )
    return emitidos, egresos, encabezados, constancia


def modulo_ingresos_sat(
    file_ingresos,
    file_egresos,
    file_egresos_productos=None,
    file_emitidos_productos=None,
) -> None:
    anios_5 = anios_5_archivos(file_ingresos, file_egresos)
    pdf_elements = []

    st.title("Barrido y Visoría")

    f_emitidos_local, f_egresos_local, f_encabezados_local, f_constancia = (
        _cargar_archivos_clase_sat()
    )
    f_emitidos = (
        f_emitidos_local or _archivo_en_memoria(file_emitidos_productos)
    )
    f_egresos = (
        f_egresos_local or _archivo_en_memoria(file_egresos_productos)
    )
    f_encabezados = f_encabezados_local or _archivo_en_memoria(file_egresos)
    if f_egresos_local is None and file_egresos_productos is not None:
        st.caption(
            f"CFDIs Recibidos Productos reutilizados desde la barra lateral: "
            f"{f_egresos.name}."
        )
    if f_emitidos_local is None and file_emitidos_productos is not None:
        st.caption(
            f"CFDIs Emitidos Productos reutilizados desde la barra lateral: "
            f"{f_emitidos.name}."
        )

    actividades = _actividades_constancia_sat(f_constancia)
    anios_ingresos = _seccion_clave_sat(
        anios_5=anios_5,
        pdf_elements=pdf_elements,
        f_emitidos_productos=f_emitidos,
        f_encabezados_emitidos=_archivo_en_memoria(file_ingresos),
        actividades=actividades,)
    st.divider()
    _seccion_egresos_sat(
        f_egresos_productos=f_egresos,
        f_encabezados=f_encabezados,
        pdf_elements=pdf_elements,
        anios_ingresos=anios_ingresos,)

    st.divider()
    st.subheader("Exportación de Reporte - Barrido y visoría")
    st.write("Genera un PDF con las gráficas, la tabla y las notas de esta sección.")
    if st.button("Generar Reporte PDF", key="btn_generar_pdf_clase_sat", type="primary"):
        with st.spinner("Construyendo y maquetando el PDF..."):
            pdf_data = generate_modular_pdf(
                title="",
                subtitle="",
                elements=pdf_elements,)
        st.download_button(
            label="Descargar reporte PDF",
            data=pdf_data,
            file_name="Reporte_Barrido_Visoria.pdf",
            mime="application/pdf",
            key="btn_download_pdf_clase_sat",
            type="secondary",)


def tabla_clase_sat(
    d: pd.DataFrame,
    descripciones: dict | None = None,
    top: int = TOP_FILAS_CLASE_SAT) -> pd.DataFrame:
    """Construye la matriz acumulada por ClaVe SAT de las partidas del periodo."""
    descripciones = descripciones or {}
    tiene_subtotal = "SubTotal_Neto_MXN" in d.columns
    cols = ["Clase", "Descripcion"]
    if tiene_subtotal:
        cols.append("Subtotal")
    cols.extend(["Total", "Pct", "Tipo"])
    if d.empty:
        return pd.DataFrame(columns=cols)

    columna_monto = "Monto_MXN" if "Monto_MXN" in d.columns else "Monto"
    columnas_suma = [columna_monto]
    if tiene_subtotal:
        columnas_suma.append("SubTotal_Neto_MXN")
    g = d.groupby("Clase")[columnas_suma].sum().reset_index()
    g = g.rename(columns={columna_monto: "Monto"})
    g = g.sort_values(["Monto", "Clase"], ascending=[False, True]).reset_index(drop=True)
    total = float(g["Monto"].sum())
    pct = lambda value: value / total * 100 if total else float("nan")
    filas = []
    for _, row in g.head(top).iterrows():
        fila = {
            "Clase": row["Clase"],
            "Descripcion": descripciones.get(row["Clase"], "Sin catálogo"),
            "Total": float(row["Monto"]),
            "Pct": pct(float(row["Monto"])),
            "Tipo": "fila",
        }
        if tiene_subtotal:
            fila["Subtotal"] = float(row["SubTotal_Neto_MXN"])
        filas.append(fila)
    if len(g) > top:
        resto = float(g["Monto"].iloc[top:].sum())
        fila_resto = {
            "Clase": "Resto de Clases",
            "Descripcion": f"{len(g) - top:,} clases más",
            "Total": resto,
            "Pct": pct(resto),
            "Tipo": "resto",
        }
        if tiene_subtotal:
            fila_resto["Subtotal"] = float(g["SubTotal_Neto_MXN"].iloc[top:].sum())
        filas.append(fila_resto)
    fila_total = {
        "Clase": "Total",
        "Descripcion": "",
        "Total": total,
        "Pct": pct(total),
        "Tipo": "total",
    }
    if tiene_subtotal:
        fila_total["Subtotal"] = float(g["SubTotal_Neto_MXN"].sum())
    filas.append(fila_total)
    return pd.DataFrame(filas, columns=cols)


def _filtrar_actividades_csf_por_anio(
    actividades: pd.DataFrame,
    anios_seleccionados: list[int],
    anios_disponibles: list[int],) -> pd.DataFrame:
    """Conserva el histórico anterior al primer año seleccionado y los años elegidos."""
    if set(anios_seleccionados) == set(anios_disponibles):
        return actividades
    anios_inicio = pd.to_datetime(
        actividades["Fecha de inicio"], format="%d/%m/%Y", errors="coerce").dt.year
    historicas = anios_inicio < min(anios_seleccionados)
    seleccionadas = anios_inicio.isin(anios_seleccionados)
    return actividades.loc[historicas | seleccionadas].copy()


def _sufijo_periodo_clase_sat(
    anios_seleccionados: list[int], anios_disponibles: list[int]) -> str:
    if set(anios_seleccionados) == set(anios_disponibles):
        return " - Acumulado"
    return " - " + ", ".join(str(anio) for anio in sorted(anios_seleccionados))


def _algun_anio_actividad_fuera_periodo(
    actividades: pd.DataFrame, anios_periodo: list[int] | tuple) -> bool:
    """Indica si alguna actividad inició fuera de la ventana de análisis."""
    if actividades is None or actividades.empty or not anios_periodo:
        return False
    fechas = pd.to_datetime(
        actividades["Fecha de inicio"], format="%d/%m/%Y", errors="coerce")
    periodo = {int(anio) for anio in anios_periodo}
    anios_actividad = fechas.dt.year
    fuera_periodo = anios_actividad.notna() & ~anios_actividad.isin(periodo)
    return bool(periodo) and fuera_periodo.any()


def _datos_desde_donut(fig) -> tuple[list[str], list[float]]:
    """Extrae etiquetas, valores y colores directamente de la traza de la dona."""
    if not fig.data:
        return [], []
    traza = fig.data[0]
    raw_labels = getattr(traza, "labels", None)
    raw_values = getattr(traza, "values", None)
    raw_colors = getattr(getattr(traza, "marker", None), "colors", None)
    labels = [str(x) for x in raw_labels] if raw_labels is not None else []
    values = [float(x) if pd.notna(x) else 0.0 for x in raw_values] if raw_values is not None else []
    return labels, values



def _calcular_n_clases_corte(
    d: pd.DataFrame,
    modo: str,
    top_default: int = TOP_FILAS_CLASE_SAT,
) -> int:
    """Devuelve el número N de clases principales según el corte ('Top', '50%', '80%')."""
    if d.empty or modo not in ("50%", "80%"):
        return top_default

    columna_monto = "Monto_MXN" if "Monto_MXN" in d.columns else "Monto"
    g = (
        d.groupby("Clase", as_index=False)[columna_monto]
        .sum()
        .rename(columns={columna_monto: "Monto"})
        .sort_values(["Monto", "Clase"], ascending=[False, True])
        .reset_index(drop=True)
    )
    total = float(g["Monto"].sum())
    if total <= 0:
        return top_default

    umbral = 50.0 if modo == "50%" else 80.0
    pct = (g["Monto"] / total) * 100.0
    # Regla inclusiva: incluye las clases necesarias hasta alcanzar o cruzar el umbral
    n = int((pct.cumsum().shift(fill_value=0.0) < umbral).sum())
    return max(1, n)


def _seleccionar_corte_clases(d: pd.DataFrame, key: str) -> tuple[int, str]:
    """Renderiza el selector de cobertura y devuelve (N clases, modo elegido)."""
    opcion_top = f"Top {TOP_FILAS_CLASE_SAT}"
    modo = (
        st.pills(
            "Cobertura de Clases SAT",
            options=[opcion_top, "50%", "80%"],
            default=opcion_top,
            selection_mode="single",
            key=key,
        )
        or opcion_top
    )
    n_clases = _calcular_n_clases_corte(d, modo, TOP_FILAS_CLASE_SAT)
    return n_clases, modo


def _seccion_clave_sat(
    anios_5: list[int] | tuple,
    pdf_elements: list | None,
    f_emitidos_productos: _ArchivoMem | None,
    f_encabezados_emitidos: _ArchivoMem | None,
    actividades: pd.DataFrame,) -> list[int]:
    """Muestra el perfil fiscal y agrega sus visualizaciones y notas al PDF."""
    subtitulo_seccion = "Estructura de Ingresos Facturados"
    st.subheader(
        subtitulo_seccion,
        help=(
            "Pone lo declarado en la Constancia de Situación Fiscal (CSF) frente a lo "
            "facturado, agrupado por la clave SAT completa de 8 dígitos de cada "
            "producto o servicio, según el catálogo oficial del SAT. La clave genérica "
            "01010101 no identifica qué se vendió. El anillo "
            "de actividades conserva el histórico anterior al primer año seleccionado y "
            "las actividades de los años elegidos; al seleccionar todos los años, muestra "
            "todas las actividades. El filtro también recalcula el anillo facturado y la "
            "tabla. Solo partidas asociadas por UUID a facturas activas; subtotal y total "
            "por partida se convierten a MXN usando la jerarquía de tipo de cambio."
        ),
    )

    encabezado_pdf: dict[str, str] | None = None
    if pdf_elements is not None:
        encabezado_pdf = {
            "type": "heading",
            "text": "Estructura de Ingresos Facturados",
        }
        pdf_elements.append(encabezado_pdf)

    if f_emitidos_productos is None:
        mensaje = "Carga la base «CFDIs Emitidos Productos» para analizar la facturación por clave SAT."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return []
    if f_encabezados_emitidos is None:
        mensaje = (
            "Para cruzar las partidas emitidas por UUID, carga la base "
            "«SAT CFDIs Emitidos» en la barra lateral."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return []

    try:
        d = _emitidos_productos_cache(
            f_emitidos_productos.name,
            f_emitidos_productos.getvalue(),
            f_encabezados_emitidos.name,
            f_encabezados_emitidos.getvalue(),
            CODIGO_VERSION,
        )
    except (KeyError, ValueError) as e:
        mensaje = (
            f"Información insuficiente: «{f_emitidos_productos.name}» no trae las "
            f"columnas esperadas de conceptos de CFDI emitidos. {e.args[0]}"
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return []


    if d.empty:
        mensaje = (
            f"La base «{f_emitidos_productos.name}» no trae partidas asociadas por UUID "
            "a facturas emitidas activas de tipo Factura con importes convertibles a MXN."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return []
    if d.attrs.get("filas_sin_tipo_cambio"):
        st.warning(
            f"{d.attrs['filas_sin_tipo_cambio']:,} partidas extranjeras sin tipo de "
            "cambio válido se excluyeron."
        )

    catalogo = cargar_catalogo_sat()
    if catalogo is None:
        st.warning(
            "No se encontró el catálogo oficial del SAT (catCFDI.xls, hoja "
            "c_ClaveProdServ) en la carpeta data/ del proyecto: las descripciones "
            "oficiales no están disponibles.")
    descripciones = descripciones_clase_sat(d, catalogo)
    disponibles = sorted({int(anio) for anio in anios_5}) or sorted(
        int(anio) for anio in d["Anio"].unique())
    elegidos = st.pills(
        "Años de Ingresos",
        disponibles,
        selection_mode="multi",
        default=disponibles,
        key=f"clase_sat_anios_{'_'.join(map(str, disponibles))}",)
    if not elegidos:
        mensaje = "Selecciona al menos un año para ver el resumen y la matriz."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return disponibles

    anios_seleccionados = [int(anio) for anio in elegidos]
    d_sel = d[d["Anio"].isin(anios_seleccionados)]
    if d_sel.empty:
        mensaje = "No hay partidas emitidas para los años seleccionados."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return disponibles

    n_clases_ingresos, modo = _seleccionar_corte_clases(
        d_sel, key="clase_sat_corte_ingresos"
    )
    if encabezado_pdf is not None:
        encabezado_pdf["text"] = f"Estructura de Ingresos Facturados - {modo}"

    actividades_grafica = _filtrar_actividades_csf_por_anio(
        actividades, anios_seleccionados, disponibles)
    sufijo_periodo = _sufijo_periodo_clase_sat(anios_seleccionados, disponibles)
    fig_declarado = fig_donut_declarado(actividades_grafica)
    fig_facturado = fig_donut_facturado(d_sel, descripciones, top=5)
    for figura in (fig_declarado, fig_facturado):
        figura.update_layout(title_text=f"{figura.layout.title.text}{sufijo_periodo}")

    tipo_vista = (
        st.pills(
            "Formato de visualización",
            options=["Donas", "Barras 100%"],
            default="Donas",
            selection_mode="single",
            key="barrida_pills_tipo_perfil_fiscal",
            label_visibility="visible",
        )
        or "Donas"
    )
    fig_declarado_pdf = fig_declarado
    fig_facturado_pdf = fig_facturado

    if tipo_vista == "Donas":
        st.plotly_chart(fig_declarado, width="stretch", key="clase_sat_donut_declarado")
        st.plotly_chart(fig_facturado, width="stretch", key="clase_sat_donut_facturado")
    else:
        labels_dec, values_dec = _datos_desde_donut(fig_declarado)
        fig_facturado_barras = fig_donut_facturado(d_sel, descripciones)
        labels_fac, values_fac = _datos_desde_donut(fig_facturado_barras)
        titulo_dec = fig_declarado.layout.title.text or f"Distribución de actividades económicas declaradas{sufijo_periodo}"
        titulo_fac = fig_facturado.layout.title.text or f"Distribución real facturada (CFDIs emitidos){sufijo_periodo}"
        fig_declarado_pdf = fig_barra_distribucion_100(
            titulo=titulo_dec,
            labels=labels_dec,
            values=values_dec,
        )
        fig_facturado_pdf = fig_barra_distribucion_100(
            titulo=titulo_fac,
            labels=labels_fac,
            values=values_fac,
            bar_width=0.52,
        )
        st.markdown(
            html_barra_distribucion_100(
                titulo=titulo_dec,
                labels=labels_dec,
                values=values_dec,
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            html_barra_distribucion_100(
                titulo=titulo_fac,
                labels=labels_fac,
                values=values_fac,
            ),
            unsafe_allow_html=True,
        )

    st.markdown("#### Detalle de Facturación")
    tabla = tabla_clase_sat(d_sel, descripciones, top=n_clases_ingresos)
    st.markdown(_html_tabla_clase_sat(tabla), unsafe_allow_html=True)
   
    nota_dos_texto = (
        "La gráfica Distribución de Actividades Económicas Declaradas muestra las "
        "actividades y porcentajes registrados en la Constancia de Situación Fiscal "
        "actual. Si la empresa registró una nueva actividad dentro del periodo "
        "analizado, los años anteriores a ese registro podrían no sumar 100%, ya que "
        "se desconoce cómo estaban distribuidas las actividades antes del cambio.")

    mostrar_nota_dos = _algun_anio_actividad_fuera_periodo(
        actividades, anios_seleccionados)
    if mostrar_nota_dos:
        st.caption(nota_dos_texto)

    comentario = st.text_area(
        "Insight para Estructura de Ingresos Facturados",
        max_chars=600,
        placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
        key="clase_sat_insight",)

    if pdf_elements is not None:
        tabla_pdf = tabla.drop(columns="Tipo").rename(columns={
            "Clase": "Clave SAT",
            "Descripcion": "Descripción oficial SAT",
            "Subtotal": "Subtotal neto (MXN)",
            "Total": "Total facturado (MXN)",
            "Pct": "% del total",})
        tabla_pdf["Descripción oficial SAT"] = tabla_pdf["Descripción oficial SAT"].map(
            lambda valor: escape(str(valor))
        )
        tabla_pdf["Total facturado (MXN)"] = tabla_pdf["Total facturado (MXN)"].map(
            lambda valor: f"${valor:,.0f}"
        )
        anchos_pdf = [12, 54, 22, 12]
        if "Subtotal neto (MXN)" in tabla_pdf.columns:
            tabla_pdf["Subtotal neto (MXN)"] = tabla_pdf[
                "Subtotal neto (MXN)"
            ].map(lambda valor: f"${valor:,.0f}")
            anchos_pdf = [10, 42, 18, 18, 12]
        tabla_pdf["% del total"] = tabla_pdf["% del total"].map(
            lambda valor: f"{valor:.2f}%"
        )
        pdf_elements.extend([
            {"type": "image",
             "fig": fig_declarado_pdf,
             "preserve_textfont_size": tipo_vista == "Donas",
             "width_pt": 500 if tipo_vista == "Barras 100%" else 400,
             "render_height": 450 if tipo_vista == "Barras 100%" else 600,},
            {"type": "image",
             "fig": fig_facturado_pdf,
             "preserve_textfont_size": tipo_vista == "Donas",
             "width_pt": 500 if tipo_vista == "Barras 100%" else 400,
             "render_height": 450 if tipo_vista == "Barras 100%" else 600,},
            {
                "type": "table",
                "title": "Detalle de Facturación Emitida",
                "df": tabla_pdf,
                "column_widths_pct": anchos_pdf,
                "note": comentario.strip() if comentario and comentario.strip() else "",
            },
        ])
  
        if mostrar_nota_dos:
            pdf_elements.append({
                "type": "callout",
                "text": "<b>Nota: </b> " + escape(nota_dos_texto).replace("\n", "<br/>"),
            })
    return disponibles


def _seccion_egresos_sat(
    f_egresos_productos: _ArchivoMem | None,
    f_encabezados: _ArchivoMem | None,
    pdf_elements: list | None,
    anios_ingresos: list[int] | tuple = (),) -> None:
    titulo = "Estructura de Egresos Facturados"
    st.subheader(
        titulo,
        help=(
            "Compara las actividades declaradas en la Constancia de Situación Fiscal "
            "con los egresos recibidos, agrupados por la clave SAT completa de 8 "
            "dígitos. Los importes se "
            "convierten a MXN por partida: tipo de cambio de la partida, luego el del "
            "encabezado por UUID y finalmente el DOF. Se muestran subtotal y total; "
            "se excluyen las claves de divisas 841216."
        ),
    )
    if f_egresos_productos is None:
        mensaje = "Carga la base «CFDIs Recibidos Productos» para analizar los egresos por Clave SAT."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return
    if f_encabezados is None:
        mensaje = (
            f"«{f_egresos_productos.name}» se identificó como base de productos, "
            "pero falta la base de encabezados «SAT CFDIs Recibidos» con UUID, "
            "Estatus y Tipo Documento. Si los productos no incluyen «UUID CFDI "
            "Recibido», el cruce por Partida también necesita Fecha, RFC Emisor, "
            "Moneda, SubTotal y Total en los encabezados."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    try:
        d = _egresos_productos_cache(
            f_egresos_productos.name,
            f_egresos_productos.getvalue(),
            f_encabezados.name,
            f_encabezados.getvalue(),
            CODIGO_VERSION,
        )
    except (KeyError, ValueError) as e:
        mensaje = (
            f"No se pudieron preparar los egresos con «{f_egresos_productos.name}» "
            f"y «{f_encabezados.name}»: {e}"
        )
        st.error(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    filas_sin_cruce = d.attrs.get("filas_sin_cruce", 0)
    comprobantes_sin_cruce = d.attrs.get("comprobantes_sin_cruce", 0)
    filas_sin_tc = d.attrs.get("filas_sin_tipo_cambio", 0)
    filas_tc_dof = d.attrs.get("filas_tc_dof", 0)
    filas_descartadas = d.attrs.get("filas_descartadas", 0)

    if filas_sin_cruce:
        st.warning(
            f"Sin coincidencia con encabezados: {filas_sin_cruce:,} partidas de "
            f"{comprobantes_sin_cruce:,} comprobantes; se excluyeron."
        )
    if filas_tc_dof:
        st.caption(
            f"{filas_tc_dof:,} partidas usaron Tipo de Cambio DOF porque el Tipo de "
            "Cambio original no era válido."
        )
    if filas_sin_tc or filas_descartadas:
        st.warning(
            f"Se descartaron {filas_descartadas:,} partidas con clave, fecha, importe "
            f"o conversión inválida; {filas_sin_tc:,} no tenían un tipo de cambio "
            "válido ni en la columna original ni en la DOF."
        )

    disponibles = sorted({int(anio) for anio in anios_ingresos})
    if not disponibles:
        mensaje = (
            "No hay años disponibles en «Estructura de Ingresos Facturados» para "
            "filtrar los egresos."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading", "text": titulo})
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})
        return
    elegidos = st.pills(
        "Años de Egresos",
        disponibles,
        selection_mode="multi",
        default=disponibles,
        key=f"egresos_clase_sat_anios_{'_'.join(map(str, disponibles))}",
    )
    if not elegidos:
        mensaje = "Selecciona al menos un año para ver los egresos."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    anios_seleccionados = [int(anio) for anio in elegidos]
    if d.empty:
        mensaje = "No hay partidas válidas de egresos; se muestran los años disponibles de ingresos."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    d_sel = d[d["Anio"].isin(anios_seleccionados)]
    if d_sel.empty:
        mensaje = "No hay partidas de egresos para los años seleccionados."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return
    catalogo = cargar_catalogo_sat()
    if catalogo is None:
        st.warning(
            "No se encontró el catálogo oficial del SAT; las descripciones oficiales "
            "no están disponibles.")
    descripciones = descripciones_clase_sat(d, catalogo)
    sufijo_periodo = _sufijo_periodo_clase_sat(anios_seleccionados, disponibles)

    n_clases_egresos, modo_egresos = _seleccionar_corte_clases(
        d_sel, key="clase_sat_corte_egresos"
    )

    fig_egresos = fig_donut_facturado(
        d_sel,
        descripciones,
        titulo="Distribución de Facturación Recibida (CFDIs)",
        nombre_serie="Egresos recibidos",
        top=5,
    )

    fig_egresos.update_layout(title_text=f"{fig_egresos.layout.title.text}{sufijo_periodo}")

    tipo_vista_egresos = (
        st.pills(
            "Formato de visualización",
            options=["Donas", "Barras 100%"],
            default="Donas",
            selection_mode="single",
            key="barrida_pills_tipo_egresos",
            label_visibility="visible",
        )
        or "Donas"
    )
    fig_egresos_pdf = fig_egresos

    if tipo_vista_egresos == "Donas":
        st.plotly_chart(
            fig_egresos,
            width="stretch",
            key="egresos_sat_donut_recibido",
        )
    else:
        fig_egresos_barras = fig_donut_facturado(
            d_sel,
            descripciones,
            titulo="Distribución de Facturación Recibida (CFDIs)",
            nombre_serie="Egresos recibidos",
            top=n_clases_egresos,
        )
        labels_egr, values_egr = _datos_desde_donut(fig_egresos_barras)
        titulo_egr = (
            fig_egresos.layout.title.text
            or f"Distribución de Facturación Recibida (CFDIs){sufijo_periodo}"
        )
        fig_egresos_pdf = fig_barra_distribucion_100(
            titulo=titulo_egr,
            labels=labels_egr,
            values=values_egr,
            bar_width=0.52,
        )
        st.markdown(
            html_barra_distribucion_100(
                titulo=titulo_egr,
                labels=labels_egr,
                values=values_egr,
            ),
            unsafe_allow_html=True,
        )

    st.markdown("#### Detalle de Facturación")
    tabla = tabla_clase_sat(d_sel, descripciones, top=n_clases_egresos)
    st.markdown(_html_tabla_clase_sat(tabla), unsafe_allow_html=True)

    comentario = st.text_area(
        "Conclusiones para Estructura de Egresos Facturados",
        max_chars=600,
        placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
        key="egresos_clase_sat_insight",
    )

    if pdf_elements is not None:
        tabla_pdf = tabla.drop(columns="Tipo").rename(columns={
            "Clase": "Clave SAT",
            "Descripcion": "Descripción oficial SAT",
            "Subtotal": "Subtotal neto (MXN)",
            "Total": "Total facturado (MXN)",
            "Pct": "% del total",
        })
        tabla_pdf["Descripción oficial SAT"] = tabla_pdf["Descripción oficial SAT"].map(
            lambda valor: escape(str(valor))
        )
        tabla_pdf["Total facturado (MXN)"] = tabla_pdf["Total facturado (MXN)"].map(
            lambda valor: f"${valor:,.0f}"
        )
        if "Subtotal neto (MXN)" in tabla_pdf.columns:
            tabla_pdf["Subtotal neto (MXN)"] = tabla_pdf[
                "Subtotal neto (MXN)"
            ].map(lambda valor: f"${valor:,.0f}")
        tabla_pdf["% del total"] = tabla_pdf["% del total"].map(
            lambda valor: f"{valor:.2f}%"
        )
        pdf_elements.extend([
            {
                "type": "image",
                "section_title": f"{titulo} - {modo_egresos}",
                "title": "",
                "fig": fig_egresos_pdf,
                "preserve_textfont_size": tipo_vista_egresos == "Donas",
                "width_pt": 500 if tipo_vista_egresos == "Barras 100%" else 400,
                "render_height": 400 if tipo_vista_egresos == "Barras 100%" else 600,
            },
            {
                "type": "table",
                "title": "Detalle de Facturación Recibida",
                "df": tabla_pdf,
                "column_widths_pct": [12, 42, 18, 18, 12],
                "note": comentario.strip() if comentario and comentario.strip() else "",
            },
        ])
       