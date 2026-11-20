from html import escape

import pandas as pd
import streamlit as st

from components.charts import (
    _html_tabla_clase_sat,
    fig_donut_declarado,
    fig_donut_facturado,
)
from components.pdf_generator import generate_modular_pdf
from config import CODIGO_VERSION, NOTA_METODOLOGICA_CLASE_SAT, TOP_FILAS_CLASE_SAT
from core.loader import (
    _actividades_constancia_sat,
    _clasificar_base_clase_sat,
    _egresos_productos_cache,
    _emitidos_productos_cache,
    anios_5_archivos,
    cargar_catalogo_sat,
    descripciones_clase_sat,
)
from utils import _ArchivoMem


_TIPOS_ARCHIVO_CLASE_SAT = {
    "csv", "xlsx", "xls", "xlsb", "parquet", "pqt",
}


def _cargar_archivos_clase_sat() -> tuple[
    _ArchivoMem | None, _ArchivoMem | None, _ArchivoMem | None
]:
    version_key = "clase_sat_archivos_uploader_version"
    version = int(st.session_state.get(version_key, 0))
    archivos_subidos = st.file_uploader(
        "Sube aquí las bases de CFDIs emitidos/recibidos y/o la Constancia de Situación "
        "Fiscal (PDF). Puedes seleccionar los tres archivos.",
        type=sorted(_TIPOS_ARCHIVO_CLASE_SAT | {"pdf"}),
        accept_multiple_files=True,
        key=f"clase_sat_archivos_uploader_{version}",
    )

    bases = {"emitidos": [], "egresos": []}
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
            "Carga como máximo una base de CFDIs emitidos, una de recibidos y una "
            "Constancia. Los archivos guardados anteriormente se conservaron."
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
    constancia = (
        _ArchivoMem(*constancia_guardada)
        if constancia_guardada is not None
        else None
    )
    return emitidos, egresos, constancia


def modulo_ingresos_sat(file_ingresos, file_egresos) -> None:
    anios_5 = anios_5_archivos(file_ingresos, file_egresos)
    pdf_elements = []

    st.title("Barrido y Visoría")

    f_emitidos, f_egresos, f_constancia = _cargar_archivos_clase_sat()
    actividades = _actividades_constancia_sat(f_constancia)
    _seccion_clave_sat(
        anios_5=anios_5,
        pdf_elements=pdf_elements,
        f_emitidos_productos=f_emitidos,
        actividades=actividades,
    )
    st.divider()
    _seccion_egresos_sat(
        f_egresos_productos=f_egresos,
        actividades=actividades,
        pdf_elements=pdf_elements,
    )

    st.divider()
    st.subheader("Exportación de Reporte - Barrido y visoría")
    st.write("Genera un PDF con las gráficas, la tabla y las notas de esta sección.")
    if st.button("Generar Reporte PDF", key="btn_generar_pdf_clase_sat", type="primary"):
        with st.spinner("Construyendo y maquetando el PDF..."):
            pdf_data = generate_modular_pdf(
                title="Reporte de Barrido y Visoría",
                subtitle="",
                elements=pdf_elements,
            )
        st.download_button(
            label="Descargar reporte PDF",
            data=pdf_data,
            file_name="Reporte_Barrido_Visoria.pdf",
            mime="application/pdf",
            key="btn_download_pdf_clase_sat",
            type="secondary",
        )

def tabla_clase_sat(
    d: pd.DataFrame,
    descripciones: dict | None = None,
    top: int = TOP_FILAS_CLASE_SAT,
) -> pd.DataFrame:
    """Construye la matriz acumulada por Clase SAT de las partidas del periodo."""
    descripciones = descripciones or {}
    cols = ["Clase", "Descripcion", "Total", "Pct", "Tipo"]
    if d.empty:
        return pd.DataFrame(columns=cols)

    g = (
        d.groupby("Clase")["Monto"]
        .sum()
        .reset_index()
        .sort_values(["Monto", "Clase"], ascending=[False, True])
        .reset_index(drop=True)
    )
    total = float(g["Monto"].sum())
    pct = lambda value: value / total * 100 if total else float("nan")
    filas = [
        {
            "Clase": row["Clase"],
            "Descripcion": descripciones.get(row["Clase"], "Sin catálogo"),
            "Total": float(row["Monto"]),
            "Pct": pct(float(row["Monto"])),
            "Tipo": "fila",
        }
        for _, row in g.head(top).iterrows()
    ]
    if len(g) > top:
        resto = float(g["Monto"].iloc[top:].sum())
        filas.append({
            "Clase": "Resto de Clases",
            "Descripcion": f"{len(g) - top:,} clases más",
            "Total": resto,
            "Pct": pct(resto),
            "Tipo": "resto",
        })
    filas.append({
        "Clase": "Total",
        "Descripcion": "",
        "Total": total,
        "Pct": pct(total),
        "Tipo": "total",
    })
    return pd.DataFrame(filas, columns=cols)


def _filtrar_actividades_csf_por_anio(
    actividades: pd.DataFrame,
    anios_seleccionados: list[int],
    anios_disponibles: list[int],
) -> pd.DataFrame:
    """Conserva el histórico anterior al primer año seleccionado y los años elegidos."""
    if set(anios_seleccionados) == set(anios_disponibles):
        return actividades
    anios_inicio = pd.to_datetime(
        actividades["Fecha de inicio"], format="%d/%m/%Y", errors="coerce"
    ).dt.year
    historicas = anios_inicio < min(anios_seleccionados)
    seleccionadas = anios_inicio.isin(anios_seleccionados)
    return actividades.loc[historicas | seleccionadas].copy()


def _sufijo_periodo_clase_sat(
    anios_seleccionados: list[int], anios_disponibles: list[int]
) -> str:
    if set(anios_seleccionados) == set(anios_disponibles):
        return " - Acumulado"
    return " - " + ", ".join(str(anio) for anio in sorted(anios_seleccionados))


def _algun_anio_actividad_en_periodo(
    actividades: pd.DataFrame, anios_periodo: list[int] | tuple
) -> bool:
    """Indica si alguna actividad inició dentro de la ventana de análisis."""
    if actividades is None or actividades.empty or not anios_periodo:
        return False
    fechas = pd.to_datetime(
        actividades["Fecha de inicio"], format="%d/%m/%Y", errors="coerce"
    )
    periodo = {int(anio) for anio in anios_periodo}
    return bool(periodo) and fechas.dt.year.isin(periodo).any()


def _seccion_clave_sat(
    anios_5: list[int] | tuple,
    pdf_elements: list | None,
    f_emitidos_productos: _ArchivoMem | None,
    actividades: pd.DataFrame,) -> None:
    """Muestra el perfil fiscal y agrega sus visualizaciones y notas al PDF."""
    subtitulo_seccion = "Perfil Fiscal Declarado y Estructura de Ingresos Facturados"
    st.subheader(
        subtitulo_seccion,
        help=(
            "Pone lo declarado en la Constancia de Situación Fiscal (CSF) frente a lo "
            "facturado, agrupado por Clase SAT (los 6 primeros dígitos de la clave de "
            "producto o servicio, según el catálogo oficial del SAT). La clave genérica "
            "010101 («No existe en el catálogo») no identifica qué se vendió. El anillo "
            "de actividades conserva el histórico anterior al primer año seleccionado y "
            "las actividades de los años elegidos; al seleccionar todos los años, muestra "
            "todas las actividades. El filtro también recalcula el anillo facturado y la "
            "tabla. Solo partidas Activas de tipo Factura. El monto por partida incluye "
            "el IVA trasladado según Importe, Importe Base y Tasa Impuestos Trasladados; "
            "no usa el Total repetido por renglón."
        ),
    )
    if pdf_elements is not None:
        pdf_elements.append({"type": "heading",
                             "text": "Perfil Fiscal Declarado y Estructura de Ingresos Facturados"})

    if f_emitidos_productos is None:
        mensaje = "Carga la base «CFDIs Emitidos Productos» para analizar la facturación por clave SAT."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    try:
        d = _emitidos_productos_cache(
            f_emitidos_productos.name, f_emitidos_productos.getvalue(), CODIGO_VERSION
        )
    except KeyError as e:
        mensaje = (
            f"Información insuficiente: «{f_emitidos_productos.name}» no trae las "
            f"columnas esperadas de conceptos de CFDI emitidos. {e.args[0]}"
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return
    if d.empty:
        mensaje = (
            f"La base «{f_emitidos_productos.name}» no trae partidas Activas de tipo Factura."
        )
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    catalogo = cargar_catalogo_sat()
    if catalogo is None:
        st.warning(
            "No se encontró el catálogo oficial del SAT (catCFDI_V_4_….xls, hoja "
            "c_ClaveProdServ) en la carpeta data/ del proyecto: las descripciones "
            "oficiales no están disponibles."
        )
    descripciones = descripciones_clase_sat(d, catalogo)
    disponibles = sorted(int(anio) for anio in d["Anio"].unique())
    elegidos = st.pills(
        "Años",
        disponibles,
        selection_mode="multi",
        default=disponibles,
        key=f"clase_sat_anios_{'_'.join(map(str, disponibles))}",
    )
    if not elegidos:
        mensaje = "Selecciona al menos un año para ver el resumen y la matriz."
        st.info(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    anios_seleccionados = [int(anio) for anio in elegidos]
    d_sel = d[d["Anio"].isin(anios_seleccionados)]
    actividades_grafica = _filtrar_actividades_csf_por_anio(
        actividades, anios_seleccionados, disponibles
    )
    sufijo_periodo = _sufijo_periodo_clase_sat(anios_seleccionados, disponibles)
    fig_declarado = fig_donut_declarado(actividades_grafica)
    fig_facturado = fig_donut_facturado(d_sel, descripciones)
    for figura in (fig_declarado, fig_facturado):
        figura.update_layout(title_text=f"{figura.layout.title.text}{sufijo_periodo}")

    fig_col1, fig_col2 = st.columns(2)
    with fig_col1:
        st.plotly_chart(fig_declarado, width="stretch", key="clase_sat_donut_declarado")
    with fig_col2:
        st.plotly_chart(fig_facturado, width="stretch", key="clase_sat_donut_facturado")
    st.markdown("#### Detalle de Facturación por Clase SAT")
    tabla = tabla_clase_sat(d_sel, descripciones)
    st.markdown(_html_tabla_clase_sat(tabla), unsafe_allow_html=True)
    st.caption("Nota" + NOTA_METODOLOGICA_CLASE_SAT)

    nota_dos_texto = (
        "2.- La gráfica Distribución de Actividades Económicas Declaradas muestra las "
        "actividades y porcentajes registrados en la Constancia de Situación Fiscal "
        "actual. Si la empresa registró una nueva actividad dentro del periodo "
        "analizado, los años anteriores a ese registro podrían no sumar 100%, ya que "
        "se desconoce cómo estaban distribuidas las actividades antes del cambio."
    )
    mostrar_nota_dos = _algun_anio_actividad_en_periodo(actividades, anios_5)
    if mostrar_nota_dos:
        st.caption(nota_dos_texto)

    comentario = st.text_area(
        "Insight para Estructura de Ingresos Facturados",
        max_chars=600,
        placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
        key="clase_sat_insight",
    )

    if pdf_elements is not None:
        tabla_pdf = tabla.drop(columns="Tipo").rename(columns={
            "Clase": "Clase SAT",
            "Descripcion": "Descripción oficial SAT",
            "Total": "Total facturado (MXN)",
            "Pct": "% del total",
        })
        tabla_pdf["Descripción oficial SAT"] = tabla_pdf["Descripción oficial SAT"].map(
            lambda valor: escape(str(valor))
        )
        tabla_pdf["Total facturado (MXN)"] = tabla_pdf["Total facturado (MXN)"].map(
            lambda valor: f"${valor:,.0f}"
        )
        tabla_pdf["% del total"] = tabla_pdf["% del total"].map(
            lambda valor: f"{valor:.2f}%"
        )
        pdf_elements.extend([
            {"type": "image",
             "fig": fig_declarado, "preserve_textfont_size": True},
            {"type": "image",
             "fig": fig_facturado, "preserve_textfont_size": True},
            {
                "type": "table",
                "title": "Detalle de Facturación por Clase SAT",
                "df": tabla_pdf,
                "column_widths_pct": [12, 54, 22, 12],
                "note": comentario.strip() if comentario and comentario.strip() else "",
            },
        ])
        nota_metodologica = escape(NOTA_METODOLOGICA_CLASE_SAT).replace("\n", "<br/>")
        if mostrar_nota_dos:
            nota_metodologica += (
                "<br/><br/>" + escape(nota_dos_texto).replace("\n", "<br/>")
            )
            texto_nota = "<b>Nota</b> " + nota_metodologica
        else:
            texto_nota = nota_metodologica
        pdf_elements.append({"type": "callout",
                             "text": texto_nota})


def _seccion_egresos_sat(
    f_egresos_productos: _ArchivoMem | None,
    actividades: pd.DataFrame,
    pdf_elements: list | None,
) -> None:
    titulo = "Estructura de Egresos Facturados"
    st.subheader(
        titulo,
        help=(
            "Compara las actividades declaradas en la Constancia de Situación Fiscal "
            "con los egresos recibidos, agrupados por Clase SAT. Los importes se "
            "convierten a MXN por partida; se excluyen las claves de divisas 841216."
        ),
    )
    if f_egresos_productos is None:
        mensaje = "Carga la base «CFDIs Recibidos Productos» para analizar los egresos por Clase SAT."
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
            CODIGO_VERSION,
        )
    except KeyError as e:
        mensaje = (
            f"Información insuficiente: «{f_egresos_productos.name}» no contiene las "
            f"columnas necesarias para calcular los egresos. {e.args[0]}"
        )
        st.error(mensaje)
        if pdf_elements is not None:
            pdf_elements.append({"type": "heading",
                                 "text": titulo})
            pdf_elements.append({"type": "callout",
                                 "text": escape(mensaje)})
        return

    filas_divisas = d.attrs.get("filas_divisas_excluidas", 0)
    filas_sin_tc = d.attrs.get("filas_sin_tipo_cambio", 0)
    filas_tc_dof = d.attrs.get("filas_tc_dof", 0)
    filas_descartadas = d.attrs.get("filas_descartadas", 0)
    st.info(
        f"Se excluyeron {filas_divisas:,} partidas de divisas con clave SAT que "
        "empieza con 841216."
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
    nota_calculo = (
        f"Se excluyeron {filas_divisas:,} partidas de divisas con clave SAT iniciada "
        "en 841216. "
        f"El Tipo de Cambio DOF se usó en {filas_tc_dof:,} partidas; "
        f"{filas_descartadas:,} partidas inválidas se descartaron. "
        "Por partida: (Importe − Descuento) × tipo de cambio; al subtotal se suman "
        "los impuestos trasladados en MXN y se restan los retenidos en MXN."
    )

    if d.empty:
        mensaje = "No hay partidas válidas para mostrar después de aplicar los filtros."
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
            "no están disponibles."
        )
    descripciones = descripciones_clase_sat(d, catalogo)
    disponibles = sorted(int(anio) for anio in d["Anio"].unique())
    elegidos = st.pills(
        "Años de egresos",
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
    d_sel = d[d["Anio"].isin(anios_seleccionados)]
    actividades_grafica = _filtrar_actividades_csf_por_anio(
        actividades, anios_seleccionados, disponibles
    )
    sufijo_periodo = _sufijo_periodo_clase_sat(anios_seleccionados, disponibles)
    fig_declarado = fig_donut_declarado(actividades_grafica)
    fig_egresos = fig_donut_facturado(
        d_sel,
        descripciones,
        titulo="Distribución de Facturación Recibida (CFDIs)",
        nombre_serie="Egresos recibidos",
    )
    for figura in (fig_declarado, fig_egresos):
        figura.update_layout(title_text=f"{figura.layout.title.text}{sufijo_periodo}")

    col_declarado, col_egresos = st.columns(2)
    with col_declarado:
        st.plotly_chart(
            fig_declarado, width="stretch", key="egresos_sat_donut_declarado"
        )
    with col_egresos:
        st.plotly_chart(
            fig_egresos, width="stretch", key="egresos_sat_donut_recibido"
        )

    st.markdown("#### Detalle de Facturación por Clase SAT")
    tabla = tabla_clase_sat(d_sel, descripciones)
    st.markdown(_html_tabla_clase_sat(tabla), unsafe_allow_html=True)
    st.caption("Nota" + NOTA_METODOLOGICA_CLASE_SAT)

    nota_csf = (
        "2.- La gráfica de actividades declaradas usa la Constancia de Situación Fiscal "
        "actual.")
    mostrar_nota_csf = _algun_anio_actividad_en_periodo(
        actividades, anios_seleccionados
    )
    if mostrar_nota_csf:
        st.caption(nota_csf)

    comentario = st.text_area(
        "Conclusiones para Estructura de Egresos Facturados",
        max_chars=600,
        placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
        key="egresos_clase_sat_insight",
    )

    if pdf_elements is not None:
        tabla_pdf = tabla.drop(columns="Tipo").rename(columns={
            "Clase": "Clase SAT",
            "Descripcion": "Descripción oficial SAT",
            "Total": "Total facturado (MXN)",
            "Pct": "% del total",
        })
        tabla_pdf["Descripción oficial SAT"] = tabla_pdf["Descripción oficial SAT"].map(
            lambda valor: escape(str(valor))
        )
        tabla_pdf["Total facturado (MXN)"] = tabla_pdf["Total facturado (MXN)"].map(
            lambda valor: f"${valor:,.0f}"
        )
        tabla_pdf["% del total"] = tabla_pdf["% del total"].map(
            lambda valor: f"{valor:.2f}%"
        )
        pdf_elements.extend([
            {
                "type": "image",
                "section_title": titulo,
                "fig": fig_declarado,
                "preserve_textfont_size": True,
            },
            {"type": "image",
             "fig": fig_egresos,
             "preserve_textfont_size": True},
            {
                "type": "table",
                "title": "Detalle de Facturación Recibida por Clase SAT",
                "df": tabla_pdf,
                "column_widths_pct": [12, 54, 22, 12],
                "note": comentario.strip() if comentario and comentario.strip() else "",
            },
        ])
    
