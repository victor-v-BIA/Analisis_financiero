# Módulo 3: Auditoría Operativa de Egresos
'''
Contiene la vista completa
de Facturación Recibida y Egresos
(incluyendo nómina, métodos de pago y su Vista Económica).
'''
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from core.loader import (anios_5_archivos,_columnas_archivo,validar_columnas,
                         _facturas_egresos_cache,excluir_años_incompletos,
                         cargar_base, buscar_columna,preparar_complementos_egresos,_preparar_nomina)

from config import (CODIGO_VERSION,COLUMNAS_FACTURAS_EGR_REQUERIDAS,VISTAS_MODULO,AYUDA_TOTAL,NOMBRE_EGR_PUE,NOMBRE_EGR_PPD,NOMBRE_NOMINA,COLOR_NOMINA,AYUDA_TOP10_ANUAL)
from core.finance_logic import (facturas_a_mxn,resumen_egresos,ncr_por_año_egresos,diferencia_ppd,matriz_anual_egresos,_preparar_concentracion,_resumen_nomina_gastos)
from utils import (dinero)
from components.charts import  render_notas_reporte
from views.income_view import _vista_economica
from components.charts import (_fig_egresos_tiempo,_fig_lineas_por_anio,_fig_pie_nomina_gastos,
                               _html_resumen_nomina_gastos,_fig_pie_metodo_pago,
                               _html_resumen_metodo_pago,_fig_bump_anual,render_grafica)
from views.controls import barra_control
from components.pdf_generator import generate_modular_pdf


def modulo_egresos(file_egresos_facturas, file_egresos_pago, file_nomina, anios_5=None,
                   file_ingresos_facturas=None) -> None:
    """Módulo de Egresos: facturación recibida (candados estrictos, sin alterar) + complementos pagados.

    Revelación progresiva: el hard stop de Facturación Recibida se evalúa ANTES de dibujar cualquier otro
    control, así que nada de este módulo aparece hasta que esa base exista. Los complementos de pago salen de la
    Base PAGO (Flujo de Efectivo) y se leen y limpian en línea (Monto MXN + su columna de fecha), independiente
    de la lectura de Facturas Recibidas.
    """
    st.title("Facturación Recibida y Egresos")

    if file_egresos_facturas is None:
        st.info("👋 Para iniciar el análisis de Egresos, arrastra tu base de Facturación Recibida en la zona "
                "de carga.")
        st.stop()
    if anios_5 is None:   # ventana móvil de 5 años (main() la deduce de Emitidos y Recibidos)
        anios_5 = anios_5_archivos(None, file_egresos_facturas)

    # -- Facturas Recibidas: regla de oro, sin alterar (Estatus Vigente/Activo, Tipo Factura, sin NCR) --
    columnas_facturas = _columnas_archivo(file_egresos_facturas.name, file_egresos_facturas.getvalue(),
                                          CODIGO_VERSION)
    validar_columnas(columnas_facturas, COLUMNAS_FACTURAS_EGR_REQUERIDAS, "Facturas Recibidas")
    try:
        facturas, _ = _facturas_egresos_cache(file_egresos_facturas.name, file_egresos_facturas.getvalue(),
                                              CODIGO_VERSION)
        facturas, _ = excluir_años_incompletos(facturas, "Fecha", "Facturación recibida", anios_5)
        facturas, n_sin_tc = facturas_a_mxn(facturas)       # importes en moneda extranjera -> MXN antes de agregarlos
    except KeyError as e:
        st.error(f"'{file_egresos_facturas.name}' no tiene el formato esperado de facturación recibida. "
                 f"{e.args[0]}")
        st.stop()
    if n_sin_tc:
        st.warning(f"{n_sin_tc} factura(s) recibida(s) en moneda extranjera sin Tipo de Cambio válido se excluyeron: no se pueden convertir a MXN.")
    if facturas.empty:
        st.warning("No quedaron facturas recibidas tras aplicar los filtros (Estatus 'Vigente'/'Activo', Tipo "
                   f"Documento = 'Factura' y la ventana de análisis {anios_5[0] if anios_5 else ''}–"
                   f"{anios_5[-1] if anios_5 else ''}).")
        st.stop()

    vista_modulo = st.radio("Vista", VISTAS_MODULO, horizontal=True, key="egr_vista_modulo", label_visibility="collapsed")
    econ = vista_modulo == "Vista Económica"   # Vista Económica: filtro de ejercicios + desglose + 4 gráficas
    ejercicios = barra_control(
        [int(a) for a in anios_5],   # eje canónico: los 5 años de la ventana (uno sin movimientos queda en 0)
        key_anios="egr_ejercicios")

    if not ejercicios:
        st.warning("Selecciona al menos un ejercicio fiscal en la barra de filtros.")
        st.stop()

    if file_egresos_pago is None:
        st.info("Falta la base de PAGOS (Flujo)")
        st.stop()
    if file_nomina is None:
        st.info("Sube la base de Nómina para calcular el egreso total")
        st.stop()

    fac = facturas[facturas["Fecha"].dt.year.isin(ejercicios)]
    if fac.empty:
        st.warning("No hay facturas recibidas para los ejercicios seleccionados.")
        st.stop()

    # -- Complementos de Pago (Base PAGO, Flujo de Efectivo) --
    archivo_rep, etiqueta_base = file_egresos_pago, "Base de PAGO"
    nombre_monto, nombre_fecha = "Monto MXN", "Fecha Pago"

    df_rep = cargar_base(archivo_rep)
    col_monto = buscar_columna(df_rep.columns, nombre_monto)
    col_fecha = buscar_columna(df_rep.columns, nombre_fecha)
    faltantes = [c for c, col in ((nombre_monto, col_monto), (nombre_fecha, col_fecha)) if col is None]
    if faltantes:
        st.error(f"🚨 Faltan columnas en la {etiqueta_base}: {faltantes}")
        st.stop()

    col_est_rep = buscar_columna(df_rep.columns, "Estatus")        # complementos vigentes únicamente (suma global, sin cruce por UUID)
    if col_est_rep is not None:
        df_rep = df_rep[df_rep[col_est_rep].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])]
    df_rep = preparar_complementos_egresos(df_rep, col_monto, col_fecha)

    df_rep_f = df_rep[df_rep["Año"].isin(ejercicios)]
    total_rep = float(df_rep_f["Monto_Num"].sum())
    rep_por_año = df_rep_f.groupby("Año")["Monto_Num"].sum()
    col_uuid = buscar_columna(df_rep_f.columns, "UUID")
    n_rep = int(df_rep_f[col_uuid].nunique()) if col_uuid else len(df_rep_f)

    # -- Nómina: Estatus Vigente/Activo, Total limpio ($/,), Año por 'Fecha de Pago' / 'Fecha Pago' --
    df_nomina = cargar_base(file_nomina)
    col_estatus_nom = buscar_columna(df_nomina.columns, "Estatus")
    col_total_nom = buscar_columna(df_nomina.columns, "Total")
    col_fecha_nom = (buscar_columna(df_nomina.columns, "Fecha de Pago")
                     or buscar_columna(df_nomina.columns, "Fecha Pago"))
    faltantes_nom = [c for c, col in (("Estatus", col_estatus_nom), ("Total", col_total_nom),
                                      ("Fecha de Pago", col_fecha_nom)) if col is None]
    if faltantes_nom:
        st.error(f"🚨 Faltan columnas en la Base de Nómina: {faltantes_nom}")
        st.stop()

    estatus_nom_limpio = df_nomina[col_estatus_nom].astype(str).str.strip().str.upper()
    df_nomina = df_nomina[estatus_nom_limpio.isin(["VIGENTE", "ACTIVO"])].copy()
    df_nomina["Total_Num"] = pd.to_numeric(
        df_nomina[col_total_nom].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce").fillna(0)
    df_nomina["Año"] = pd.to_datetime(df_nomina[col_fecha_nom], errors="coerce").dt.year

    df_nomina_f = df_nomina[df_nomina["Año"].isin(ejercicios)]
    nomina_total = float(df_nomina_f["Total_Num"].sum())
    nomina_por_año = df_nomina_f.groupby("Año")["Total_Num"].sum()

    # Facturación/Pagado se calculan SOLO con Factura -las NCR se excluyen aquí y se manejan aparte-.
    fac_factura = fac[~fac["Es_NCR"]]
    fact_pue = fac_factura.loc[fac_factura["Metodo_Pago"] == "PUE", "Total"].sum()
    fact_ppd = fac_factura.loc[fac_factura["Metodo_Pago"] == "PPD", "Total"].sum()
    pagado_ppd = total_rep
    cifras = resumen_egresos(fact_pue, fact_ppd, pagado_ppd, nomina_total)      # única función: tarjetas, desglose anual y gráficas
    fact_total, pagado_total, saldo_ppd, egreso_total = cifras["facturacion"], cifras["pagado_total"], cifras["diferencia"], cifras["egreso_total"]
    pct_saldo_ppd = (saldo_ppd / fact_ppd * 100) if fact_ppd else 0.0

    ncr_anual_egr = ncr_por_año_egresos(fac)
    ncr_total = ncr_anual_egr["NCR_Total"].reindex(ejercicios, fill_value=0.0).sum()    # NCR vigentes: se presentan aparte, no se descuentan del Egreso Total

    # Saldo global (ventana de 5 años, sin filtrar por Ejercicios fiscales): Facturación PPD vigente (Total en MXN) − Complementos vigentes, con la MISMA
    # fórmula `diferencia_ppd`; sin cruce por UUID.
    total_ppd_facturado = float(facturas.loc[~facturas["Es_NCR"] & (facturas["Metodo_Pago"] == "PPD"), "Total"].sum())
    total_pagado_rep = float(df_rep.loc[df_rep["Año"].isin([int(a_) for a_ in anios_5]), "Monto_Num"].sum())
    saldo_ppd_macro = dinero(diferencia_ppd(total_ppd_facturado, total_pagado_rep))

    # Inicialización del acumulador para PDF
    pdf_elements = []

    if not econ:   # las tarjetas de KPI solo van en la Vista Financiera (la Vista Económica no las muestra)
        with st.container(key="egr_kpis_facturacion_pdf"):
            k = st.columns(3)
            k[0].metric("**Facturación Recibida Total**", dinero(fact_total),
                       f"{fac_factura['UUID'].nunique()} facturas recibidas", delta_color="off", delta_arrow="off",
                       help=AYUDA_TOTAL)
            k[1].metric("Facturación Recibida PUE", dinero(fact_pue),
                       f"{fact_pue / fact_total:.1%} del total" if fact_total else "n/a",
                       delta_color="off", delta_arrow="off", help=AYUDA_TOTAL)
            k[2].metric("Facturación Recibida PPD", dinero(fact_ppd),
                       f"{fact_ppd / fact_total:.1%} del total" if fact_total else "n/a",
                       delta_color="off", delta_arrow="off", help=AYUDA_TOTAL)

        with st.container(key="egr_kpis_cobranza_pdf"):
            k = st.columns(4)
            k[0].metric("Pagado Total (PUE + Complementos)", dinero(pagado_total),
                       f"{pagado_total / fact_total:.1%} de lo facturado" if fact_total else "n/a",
                       delta_color="off", delta_arrow="off",
                       help="PUE (pagado al recibir la factura) más el Pago Efectivo de los Complementos de Pago Recibidos "
                            "(por su fecha de pago).")
            k[1].metric("Complementos de Pago Recibidos", dinero(pagado_ppd),
                       f"{n_rep} complementos de pago", delta_color="off", delta_arrow="off",
                       help=f"Monto MXN de la {etiqueta_base} cuya {nombre_fecha} cae en los ejercicios seleccionados.")
            k[2].metric("Saldo PPD por Pagar", saldo_ppd_macro,
                       help="Diferencia PPD global: Facturación Recibida PPD vigente (Total en MXN) menos el Total de los "
                            "Complementos de Pago Recibidos vigentes (por su fecha de pago, Flujo de Efectivo), sin cruce por UUID. "
                            "No se filtra por los Ejercicios fiscales seleccionados arriba; puede ser negativa.")
            k[3].metric("% Saldo PPD por Pagar", f"{pct_saldo_ppd:.1f}%",
                       help="Saldo PPD por Pagar entre Facturación Recibida PPD, de los ejercicios seleccionados.")

        with st.container(key="egr_kpis_cierre_pdf"):
            k = st.columns(3)
            k[0].metric("Pagos a Nómina", dinero(nomina_total),
                       help="Suma del Total (limpio) de la Base de Nómina cuya Fecha de Pago cae en los ejercicios "
                            "seleccionados (Estatus 'Vigente'/'Activo').")
            k[1].metric("**Egreso Total (Operación + Nómina)**", dinero(egreso_total),
                       help="PUE + Complementos de Pago Recibidos + Pagos a Nómina, de los ejercicios seleccionados. Las Notas de "
                            "Crédito se presentan aparte y no se descuentan de este indicador.")
            k[2].metric("Total Notas de Crédito", dinero(ncr_total),
                        help="Suma de las Notas de Crédito (Tipo Documento = 'NCR') de Facturas Recibidas en los "
                             "ejercicios seleccionados. Se muestra solo el total.")

        # Registro de KPIs en el PDF con formato de 3 elementos por tupla
        metrics_kpis_finan = [
            ("Facturación Recibida Total", dinero(fact_total), f"{fac_factura['UUID'].nunique()} facturas recibidas"),
            ("Facturación Recibida PUE", dinero(fact_pue), f"{fact_pue / fact_total:.1%} del total" if fact_total else "n/a"),
            ("Facturación Recibida PPD", dinero(fact_ppd), f"{fact_ppd / fact_total:.1%} del total" if fact_total else "n/a"),
            
            ("Pagado Total (PUE + Complementos)", dinero(pagado_total),  f"{pagado_total / fact_total:.1%} de lo facturado" if fact_total else "n/a"),
            ("Complementos Recibidos", dinero(pagado_ppd), f"{n_rep} complementos de pago"),
            ("Saldo PPD por Pagar", saldo_ppd_macro, ""),
            ("% Saldo PPD por Pagar", f"{pct_saldo_ppd:.1f}%", ""),

            ("Pagos a Nómina", dinero(nomina_total), ""),
            ("Egreso Total", dinero(egreso_total), ""),
            ("Total Notas de Crédito", dinero(ncr_total), "")
        ]
        
        for i in range(0, len(metrics_kpis_finan), 3):
            bloque_tres = metrics_kpis_finan[i:i+3]
            titulo_bloque = "Facturación Recibida y Egresos" if i == 0 else ""
            
            pdf_elements.append({
                "type": "metrics", 
                "title": titulo_bloque, 
                "data": bloque_tres
            })


    matriz = matriz_anual_egresos(fac, rep_por_año, ncr_anual_egr, nomina_por_año, ejercicios)

    texto = matriz.apply(lambda col: col.map(
        lambda v: "n/a" if pd.isna(v) else (f"{v:.1f}%" if col.name.startswith("%") else f"${v:,.2f}")))
    try:
        columna_texto = st.column_config.TextColumn(alignment="right")
    except TypeError:
        columna_texto = st.column_config.TextColumn()
    tabla = texto.T.rename_axis(index="Concepto").reset_index()

    def _mostrar_desglose():
        with st.container(key="egr_desglose_anual_pdf", width="stretch"):
            st.markdown("**Desglose año con año**")
            st.dataframe(tabla, hide_index=True, key="egr_desglose_anual", width="stretch",
                         column_config={año: columna_texto for año in texto.index})

    st.divider()
    if econ:   # Vista Económica: tabla anual y luego sus gráficas macro
        _mostrar_desglose()
        
        # Agregar tabla de desglose a la vista económica en PDF
        pdf_elements.append({
            "type": "table",
            "section_title": "Evolución Económica de Egresos",
            "title": "Desglose Año con Año Egresos",
            "df": tabla
        })
        
        st.divider()
        _vista_economica("egresos", file_ingresos_facturas, file_egresos_facturas, ejercicios, anios_5, pdf_elements=pdf_elements)
        return

    _bloque_egresos(_preparar_concentracion(fac_factura, "Nombre_Emisor", "RFC_Emisor"), cargar_base(file_nomina), df_rep_f, ejercicios,
                    desglose=_mostrar_desglose, tabla_pdf=tabla, pdf_elements=pdf_elements)

    st.divider()
    st.subheader("Exportación de Reporte - Vista Financiera")
    col_pdf_desc, col_pdf_info = st.columns([1, 2])

    with col_pdf_desc:
        st.write("Genera un PDF con las gráficas, conclusiones, tablas y desglose de este módulo.")
    if pdf_elements:
        if st.button("Generar PDF Vista Financiera", key="btn_generar_pdf_egresos_financiera"):
            with st.spinner("Generando reporte financiero en PDF..."):
                pdf_data = generate_modular_pdf(
                    title="Reporte de Auditoría Operativa de Egresos",
                    subtitle="Vista Financiera, Operación y Egresos",
                    elements=pdf_elements
                )
                st.download_button(
                    label="📄 Descargar Reporte PDF (Vista Financiera)",
                    data=pdf_data,
                    file_name="Reporte_Egresos_Vista_Financiera.pdf",
                    mime="application/pdf",
                    key="btn_pdf_egresos_financiera"
                )


def _bloque_egresos(df_prov: pd.DataFrame, nomina_raw: pd.DataFrame, comp_df: pd.DataFrame, ejercicios, desglose=None, tabla_pdf=None, pdf_elements=None) -> None:
    """Cuerpo de la Vista Financiera de Egresos con la lógica global (sin cruce por UUID), SIEMPRE sobre Total. `df_prov` = `_preparar_concentracion` de
    facturas recibidas vigentes sin NCR, con el Total ya en MXN y filtradas por ejercicios; `nomina_raw` = base de nómina cruda (Total de comprobantes
    activos por Fecha Pago); `comp_df` = complementos vigentes de los ejercicios (`Monto_Num` = Monto MXN, no se reconvierte; `Mes`). Todo sale de
    `resumen_egresos` (la misma función de tarjetas y desglose anual): Egreso Total = PUE + Complementos + Nómina. Orden: (2) Evolución de los egresos año
    con año: la tabla «Desglose año con año» (`desglose`) junto a «Egresos en el tiempo» y «Egresos facturados por mes»; (3) Método de pago y composición
    de gastos frente a nómina (los dos pies con sus tablas, en dos columnas); (4) Análisis de proveedores: Bump Chart Top 10 normalizado por RFC. (El
    bloque 1, resumen y tarjetas, lo dibuja `modulo_egresos` antes.) Verifica al centavo que todo cuadra."""
    col_monto = "Total"
    if desglose is not None:
        desglose()
        if tabla_pdf is not None and pdf_elements is not None:
            pdf_elements.append({
                "type": "table",
                "section_title": "1. Evolución de Egresos y Desglose Anual",
                "title": "Desglose Año con Año Egresos",
                "df": tabla_pdf
            })

    nom = _preparar_nomina(nomina_raw)
    if nom is None:
        st.subheader("Egresos y Riesgo de Dependencia")
        st.info("La base de nómina no trae 'Total' y 'Fecha Pago'; no se pueden graficar los egresos.")
        return
    nom = nom[nom["Año"].isin([int(e) for e in ejercicios])]
    es_pue, es_ppd = df_prov["Metodo_Pago"].eq("PUE"), df_prov["Metodo_Pago"].eq("PPD")
    pue_t, ppd_t = float(df_prov.loc[es_pue, col_monto].sum()), float(df_prov.loc[es_ppd, col_monto].sum())
    comp_mes = comp_df.assign(Periodo=comp_df["Mes"].dt.strftime("%Y-%m")).groupby("Periodo")["Monto_Num"].sum()
    res = resumen_egresos(pue_t, ppd_t, float(comp_df["Monto_Num"].sum()), float(nom["Monto"].sum()))
    mensual = pd.DataFrame({NOMBRE_EGR_PUE: df_prov[es_pue].groupby("Periodo")[col_monto].sum(), NOMBRE_EGR_PPD: comp_mes,
                            NOMBRE_NOMINA: nom.groupby("Periodo")["Monto"].sum()}).fillna(0.0)
    total_mes = mensual.sum(axis=1).rename_axis("Periodo").reset_index(name="Monto")
    total_mes["Año"], total_mes["Mes"] = total_mes["Periodo"].str[:4].astype(int), total_mes["Periodo"].str[5:7].astype(int)
    tabla_mes = total_mes.pivot_table(index="Mes", columns="Año", values="Monto", aggfunc="sum").reindex(range(1, 13)).sort_index(axis=1)
    res_nom = _resumen_nomina_gastos(res)

    for nombre, diferencia in (("Las barras de egresos en el tiempo", float(mensual.to_numpy().sum() - res["egreso_total"])),
                               ("Los egresos por mes", float(np.nansum(tabla_mes.to_numpy()) - res["egreso_total"])),
                               ("Nómina vs. Gastos", float(res_nom["gastos"] + res_nom["nomina"] - res["egreso_total"]))):
        if abs(diferencia) > 0.005:
            st.error(f"{nombre} no cuadra con el Egreso Total; diferencia {diferencia:,.2f}. Revisa los datos.")

    st.divider()
    st.markdown("**Egresos en el tiempo**")
    fig_tiempo = _fig_egresos_tiempo(mensual)
    with st.container(key="egr_tiempo_pdf", width="stretch"):
        render_grafica(fig_tiempo, key="egr_tiempo")
    # nota_tiempo = st.text_area("Conclusión - Egresos en el Tiempo", max_chars=600, key="note_egr_tiempo")

    if pdf_elements is not None:
        pdf_elements.append({
            "type": "image",
            # "section_title": "2. Evolución de los Egresos",
            "title": "Egresos en el Tiempo",
            "fig": fig_tiempo,
            "custom_height": 240
        })
    st.divider()
    st.markdown("**Egresos facturados por mes**")
    fig_fact_mes = _fig_lineas_por_anio(tabla_mes, "Egreso total")
    with st.container(key="egr_facturado_por_mes_pdf", width="stretch"):
        render_grafica(fig_fact_mes, key="egr_facturado_por_mes")
    # nota_fact_mes = st.text_area("Conclusión - Egresos Facturados por Mes", max_chars=600, key="note_egr_fact_mes")

    if pdf_elements is not None:
        pdf_elements.append({
            "type": "image",
            "title": "Egresos Facturados por Mes",
            "fig": fig_fact_mes,
            "custom_height": 270
        })

    st.divider()
    c1, c2 = st.columns([1, 1])

    # Secciones cuadradas: Nómina vs. Gastos
    fig_nom_gastos = _fig_pie_nomina_gastos(res_nom)
    with c1:
        st.markdown("**Nómina vs. Gastos**")
        with st.container(key="egr_nomina_vs_gastos_layout"):
            p1, t1 = st.columns([1, 1])
            with p1:
                with st.container(key="egr_nomina_vs_gastos_pdf", width="stretch"):
                    render_grafica(fig_nom_gastos, key="egr_nomina_vs_gastos", incluir_notas=False)
            with t1:
                st.markdown(_html_resumen_nomina_gastos(res_nom), unsafe_allow_html=True)
        # nota_nom_gastos = st.text_area("Conclusión - Nómina vs. Gastos", max_chars=600, key="note_egr_nom_gastos")

    # Secciones cuadradas: Método de Pago de Gastos
    fig_metodo_pago = _fig_pie_metodo_pago(res)
    with c2:
        st.markdown("**Método de pago de gastos**")
        with st.container(key="egr_metodo_pago_layout"):
            p2, t2 = st.columns([1, 1])
            with p2:
                with st.container(key="egr_metodo_pago_pdf", width="stretch"):
                    render_grafica(fig_metodo_pago, key="egr_metodo_pago", incluir_notas=False)
            with t2:
                st.markdown(_html_resumen_metodo_pago(res), unsafe_allow_html=True)
        # nota_metodo_pago = st.text_area("Conclusión - Método de Pago", max_chars=600, key="note_egr_metodo_pago")

    # Registro en PDF para Nómina vs. Gastos y Método de Pago
    if pdf_elements is not None:
        # 1. Nómina vs. Gastos
        pdf_elements.append({
            "type": "image",
            "section_title": "3. Composición y Métodos de Pago",
            "title": "Nómina vs. Gastos",
            "fig": fig_nom_gastos,
            "preserve_textfont_size": True,
            # "note": nota_nom_gastos
        })
        try:
            total_egr_nom = float(res_nom.get("gastos", 0) + res_nom.get("nomina", 0))
            gastos_val = float(res_nom.get("gastos", 0))
            nomina_val = float(res_nom.get("nomina", 0))
            pct_gastos = (gastos_val / total_egr_nom * 100) if total_egr_nom > 0 else 0
            pct_nomina = (nomina_val / total_egr_nom * 100) if total_egr_nom > 0 else 0

            df_nom_pdf = pd.DataFrame([
                {"Concepto": f"<font size=8 color='#6B7280'>Monto Total</font><br/><b><font size=13 color='#1F2937'>MXN {total_egr_nom:,.2f}</font></b>"},
                {"Concepto": f"<font color='#7dd3fc'>●</font> <b><font color='#1F2937'>Gastos (Proveedores)</font></b><br/><font color='#4B5563'>MXN {gastos_val:,.2f} · {pct_gastos:.1f}%</font>"},
                {"Concepto": f"<font color='{COLOR_NOMINA}'>●</font> <b><font color='#1F2937'>Pagos a Nómina</font></b><br/><font color='#4B5563'>MXN {nomina_val:,.2f} · {pct_nomina:.1f}%</font>"}
            ])[["Concepto"]]

            pdf_elements.append({
                "type": "table",
                "title": "Resumen — Nómina vs. Gastos",
                "df": df_nom_pdf,
                "white_background": True
            })
        except Exception:
            pass

        # 2. Método de Pago de Gastos
        pdf_elements.append({
            "type": "image",
            "title": "Método de Pago de Gastos",
            "fig": fig_metodo_pago,
            "preserve_textfont_size": True,
            # "note": nota_metodo_pago
        })
        try:
            pue_g = float(res.get("pue", 0))
            ppd_g = float(res.get("ppd", 0))
            ppd_pendiente_g = float(res.get("diferencia", 0))
            ppd_pagado_g = float(res.get("complementos", 0))
            total_g = float(res.get("facturacion", pue_g + ppd_g))
            pct_pago = lambda monto: f"{monto / total_g * 100:.1f}%" if total_g else "n/a"

            filas_pago_pdf = [
                {"Concepto": f"<font size=8 color='#6B7280'>Monto total</font><br/><b><font size=13 color='#1F2937'>MXN {total_g:,.2f}</font></b>"},
                {"Concepto": f"<font color='#2563EB'>●</font> <b><font color='#1F2937'>Egresos PUE</font></b><br/><font color='#4B5563'>MXN {pue_g:,.2f} · {pct_pago(pue_g)}</font>"},
                {"Concepto": f"<font color='#60A5FA'>●</font> <b><font color='#1F2937'>Egresos PPD</font></b><br/><font color='#4B5563'>MXN {ppd_g:,.2f} · {pct_pago(ppd_g)}</font>"}
            ]
            if ppd_pendiente_g >= 0:
                filas_pago_pdf.extend([
                    {"Concepto": f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#2563EB'>●</font> <b><font color='#1F2937'>PPD pendiente</font></b><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#4B5563'>MXN {ppd_pendiente_g:,.2f} · {pct_pago(ppd_pendiente_g)}</font>"},
                    {"Concepto": f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#60A5FA'>●</font> <b><font color='#1F2937'>PPD pagado</font></b><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#4B5563'>MXN {ppd_pagado_g:,.2f} · {pct_pago(ppd_pagado_g)}</font>"}
                ])
            else:
                filas_pago_pdf.extend([
                    {"Concepto": f"<font color='#60A5FA'>●</font> <b><font color='#1F2937'>Complementos de Pago Recibidos</font></b><br/><font color='#4B5563'>MXN {ppd_pagado_g:,.2f}</font>"},
                    {"Concepto": f"<font color='#2563EB'>●</font> <b><font color='#1F2937'>Diferencia PPD (Facturación PPD − Complementos de Pago Recibidos)</font></b><br/><font color='#4B5563'>MXN {ppd_pendiente_g:,.2f}</font>"}
                ])

            df_pago_pdf = pd.DataFrame(filas_pago_pdf)[["Concepto"]]

            pdf_elements.append({
                "type": "table",
                "title": "Resumen — Método de Pago de Gastos",
                "df": df_pago_pdf,
                "white_background": True
            })
        except Exception:
            pass

    st.divider()
    st.subheader("Egresos y Riesgo de Dependencia")
    st.markdown("**Top 10 proveedores de cada año**", help=AYUDA_TOP10_ANUAL)
    if df_prov["Año"].nunique() < 2:
        st.info("El Bump Chart compara posiciones entre años: selecciona al menos dos ejercicios.")
    else:
        fig_bump = _fig_bump_anual(df_prov, col_monto)
        with st.container(key="egr_bump_anual_pdf", width="stretch"):
            render_grafica(fig_bump, key="egr_bump_anual")
        # nota_bump = st.text_area("Conclusión - Top 10 Proveedores", max_chars=600, key="note_egr_bump")

        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "section_title": "4. Egresos y Riesgo de Dependencia",
                "title": "Top 10 Proveedores de Cada Año",
                "fig": fig_bump,
                # "note": nota_bump,
                "custom_height": 320  # Alto extendido para evitar corte de ejes X
            })