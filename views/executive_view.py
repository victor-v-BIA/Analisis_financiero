# Módulo 1: Dashboard Ejecutivo (Riesgo y Viabilidad)

'''
Contiene la vista completa del Dashboard de Riesgo y Viabilidad.
'''
from html import escape

import streamlit as st
import pandas as pd
import plotly.express as px

from utils import _mxn, _formatear_mxn
from utils import (_nb, _nombre_abreviado,_rango_meses_texto, _limpiar_y_formatear)
from core.loader import (anios_5_archivos, _anual_ppd_cache,
                         _balance_cache, _tiempos_cache,_concentracion_cache,
                         _resumen_sf_cache,_res_sf_cache,_trazabilidad_cache)

from config import (CODIGO_VERSION, MESES_ES, VISTAS_CICLOS,
                    METRICAS_VISUALIZAR, PESOS_INDICE,BANDA_CONCENTRACION_ALTA,
                    BANDA_CONCENTRACION_BAJA,MOSTRAR_INDICE_DESEMPENO,
                    REGLAS_INDICE,PLAZO_DEFECTO_MESES,PERIODOS_EVALUACION, TASA_REFERENCIA_ANUAL,MARGEN_SEGURIDAD_PCT)

from components.charts import (_grafica_diferencia_anual, _html_detalle_anual, _grafica_diferencia_cobros_pagos,
                                _grafica_ciclos_lineas,_grafica_velas,_grafica_plazos_comparativa,
                                _layout_plotly,_html_tabla_sin_facturacion,_grafica_gauge_score,_grafica_pilares_score,
                                render_grafica)

from core.finance_logic import ( _tabla_detalle_anual, _anios_cobertura_completa,
                                 _flujo_bruto_mensual, _ohlc_mensual,
                                 _promedios_mensuales_historicos,
                                 _series_anuales_por_mes,_tabla_clientes_sin_facturacion,
                                 _trazabilidad_indicadores,_indice_desempeno,_periodo_evaluacion,_excedente_homologado,_dictamen_credito)

from components.pdf_generator import generate_modular_pdf


def modulo_riesgo(f_ingresos_fac, f_ingresos_pago, f_egresos_fac, f_egresos_pago, f_nomina) -> None:
    """Dashboard Ejecutivo (Flujo de Efectivo): cruza Ingresos y Egresos para un vistazo de riesgo y viabilidad, antes de entrar
    al detalle operativo de cada módulo."""
    st.title("Dashboard Ejecutivo (Riesgo y Viabilidad)")

    if any(f is None for f in (f_ingresos_fac, f_ingresos_pago, f_egresos_fac, f_egresos_pago, f_nomina)):
        st.info("Para generar el análisis de riesgo y capacidad de pago, por favor arrastra tus "
                "5 reportes contables a la zona de carga.")
        st.stop()

    pdf_elements = []

    # ---------------------------------------------------------------
    # Módulo 1: Facturación PPD y complementos de pago
    # ---------------------------------------------------------------
    st.subheader("1. Facturación PPD y Complementos: Diferencias Anuales")
    st.caption("Años en los que los importes de los complementos fueron mayores o menores que la facturación PPD.")

    pdf_elements.append({"type": "heading", "text": "1. Facturación PPD y Complementos: Diferencias Anuales"})

    df_pagos_ingresos, df_pagos_egresos = f_ingresos_pago, f_egresos_pago

    a_fac_ing, a_pago_ing = _nb(f_ingresos_fac), _nb(df_pagos_ingresos)
    a_fac_egr, a_pago_egr = _nb(f_egresos_fac), _nb(df_pagos_egresos)
    a_nomina = _nb(f_nomina)
    anios_5 = anios_5_archivos(f_ingresos_fac, f_egresos_fac)

    anual_ing, motivo_ing = _anual_ppd_cache("clientes", a_fac_ing, a_pago_ing, anios_5, CODIGO_VERSION)
    anual_egr, motivo_egr = _anual_ppd_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, CODIGO_VERSION)

    def _bloque_anual(columna, titulo, anual, motivo, nombre_serie, lado, ayuda):
        with columna:
            st.markdown(f"**{titulo}**", help=ayuda)
            if anual is None or anual.empty:
                if anual is None:
                    st.warning(f"Información insuficiente: {motivo}.")
                else:
                    st.info("No hay facturas PPD vigentes en los años disponibles.")
                return

            # 1. Renderizamos únicamente la gráfica limpia en la vista
            fig_diff = _grafica_diferencia_anual(anual, nombre_serie)
            render_grafica(fig_diff, key=f"exec_diferencia_anual_{lado}")
            
            titulo_graf_pdf = "Clientes · Desfase entre Complementos y Facturación PPD" if lado == "clientes" else "Proveedores · Desfase entre Complementos y Compras PPD"
            
            # Agregamos la gráfica al PDF sin notas adjuntas
            pdf_elements.append({
                "type": "image", 
                "title": titulo_graf_pdf, 
                "fig": fig_diff
            })
            
            # 2. Generamos la tabla de detalle anual para la interfaz web y el PDF
            df_detalle = _tabla_detalle_anual(anual)
            df_detalle_pdf = df_detalle.copy()
            for col in df_detalle_pdf.columns:
                if col != "Año":
                    df_detalle_pdf[col] = df_detalle_pdf[col].apply(
                        lambda val: _formatear_mxn(val, decimales=1) if pd.notnull(val) else val)

            titulo_tabla_pdf = "Detalle Anual — Clientes" if lado == "clientes" else "Detalle Anual — Proveedores"
            
            # Visualización de la tabla en la interfaz web de Streamlit
            st.markdown(f"**Detalle anual — {'Clientes' if lado == 'clientes' else 'Proveedores'}**")
            st.markdown(_html_detalle_anual(df_detalle), unsafe_allow_html=True)

            # 3. El cuadro de texto de conclusiones ahora se ubica debajo de la tabla en la vista de Streamlit
            nota_key = f"note_graf_{lado}"
            nota_grafica = st.text_area(
                f"Insight para el detalle anual ({'Clientes' if lado == 'clientes' else 'Proveedores'})",
                max_chars=600,
                placeholder="Escribe tus conclusiones de la tabla (máx. 600 caracteres)...",
                key=nota_key
            )
            
            # Agregamos la tabla al PDF junto con su nota vinculada al pie de la misma
            pdf_elements.append({
                "type": "table", 
                "title": titulo_tabla_pdf, 
                "df": df_detalle_pdf,
                "note": nota_grafica if nota_grafica and nota_grafica.strip() else ""
            })
    col_g1, col_g2 = st.columns(2)
    _bloque_anual(col_g1, "Clientes · Desfase entre Complementos y Facturación PPD", anual_ing, motivo_ing,
                  "Complementos − Facturación PPD", "clientes",
                  "Mide la realidad fiscal ante el SAT. Negativo: aparenta cartera vencida (complementos no emitidos, mala relación de UUIDs entre factura y pago, etc.). Positivo: aparenta recuperación de cartera (cobros de facturas PPD de años anteriores, facturas PUE incluidas por error en un complemento, etc.).")
    _bloque_anual(col_g2, "Proveedores · Desfase entre Complementos y Facturación PPD", anual_egr, motivo_egr,
                  "Complementos − Compras PPD", "proveedores",
                   "Mide la realidad fiscal ante el SAT. Negativo: aparenta deudas vigentes (complementos no recibidos, mala relación de UUIDs entre factura y pago, etc.). Positivo: aparenta liquidación de deudas pasadas (pagos de facturas PPD de años anteriores, facturas PUE incluidas por error en un REP, etc.).")

    # ---------------------------------------------------------------
    # Indicador 4: Flujo Neto Fiscal
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("2. Flujo Neto Fiscal",
                 help="Mide el flujo de efectivo comprobable ante el SAT. Representa la diferencia entre los cobros (PUE + Complementos) y pagos ( PUE + Complementos + Nomina). ")
    

    balance = _balance_cache(a_fac_ing, a_pago_ing, a_fac_egr, a_pago_egr, a_nomina, anios_5, CODIGO_VERSION)
    nombre_cobros, nombre_pagos = "Cobros", "Pagos considerados"

    if not balance["disponible"]:
        detalle = "; ".join(f"{k}: {v}" for k, v in balance["motivos"].items())
        st.warning(f"No se pudo calcular por falta de información indispensable ({detalle}).")
    else:
        mensual = balance["mensual"]
        cobertura = balance["cobertura"]
        anios_ok = _anios_cobertura_completa(mensual, cobertura)
        anios_disp = sorted({int(a) for a in mensual.index.year}, reverse=True)
        anio_defecto = max(anios_ok) if anios_ok else anios_disp[0]

        if st.session_state.get("cp_anio_guardado") not in anios_disp:
            st.session_state["cp_anio_guardado"] = anio_defecto
        col_sel1, col_sel2 = st.columns([2, 1])
        with col_sel1:
            vista_graf = st.radio("Vista de la gráfica", ["Histórico anual", "Detalle mensual"], horizontal=True,
                                  key="cp_vista_graf")
        if vista_graf == "Detalle mensual":
            if st.session_state.get("cp_anio_sel") not in anios_disp:
                st.session_state["cp_anio_sel"] = st.session_state["cp_anio_guardado"]
            with col_sel2:
                anio_sel = int(st.selectbox("Año", anios_disp, key="cp_anio_sel"))
            st.session_state["cp_anio_guardado"] = anio_sel
        else:
            anio_sel = int(st.session_state["cp_anio_guardado"])

        datos_anio = mensual[mensual.index.year == anio_sel]

        if vista_graf == "Histórico anual":
            anual = mensual.groupby(mensual.index.year).agg(
                Cobros=("Cobros", "sum"), Proveedores=("Pagos", "sum"), Nomina=("Nomina", "sum"),
                Diferencia=("Balance", "sum"))
            etiquetas = [str(a) for a in anual.index]
            fig_cp = _grafica_diferencia_cobros_pagos(
                etiquetas, anual["Cobros"].tolist(), (anual["Proveedores"] + anual["Nomina"]).tolist(),
                anual["Diferencia"].tolist(), nombre_cobros, nombre_pagos)
            titulo_graf = "Flujo Neto Fiscal por Año"
            
            df_pdf_tabla = anual.reset_index().rename(columns={"index": "Año"})
        else:
            meses_ref = pd.period_range(f"{anio_sel}-01", periods=12, freq="M")
            d = datos_anio.reindex(meses_ref)
            etiquetas = [MESES_ES[p.month - 1] for p in meses_ref]
            fig_cp = _grafica_diferencia_cobros_pagos(
                etiquetas, d["Cobros"].tolist(), (d["Pagos"] + d["Nomina"]).tolist(), d["Balance"].tolist(),
                nombre_cobros, nombre_pagos)
            titulo_graf = "Flujo Neto Fiscal Mensual"
            
            df_pdf_tabla = d[["Cobros", "Pagos", "Nomina", "Balance"]].reset_index()
            df_pdf_tabla.columns = ["Periodo", "Cobros", "Pagos", "Nómina", "Diferencia"] # O Flujo Neto

        st.markdown(f"**{titulo_graf}**")
        render_grafica(fig_cp, key="exec_flujo_neto")
        
        nota_flujo = st.text_area(
            "Insight para la gráfica de Flujo Neto Fiscal",
            max_chars=600,
            placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
            key="note_graf_flujo"
        )

    
        pdf_elements.append({
                            "type": "image", 
                            "section_title": "2. Flujo Neto Fiscal",
                            "title": f"{titulo_graf}", 
                            "fig": fig_cp,
                            "note": nota_flujo
                        })
        

    # ---------------------------------------------------------------
    # Ciclos y Estacionalidad Operativa
    # ---------------------------------------------------------------
    st.divider()
    with st.container(key="exec_ciclos_titulo_pdf"):
        st.subheader("3. Ciclos y Estacionalidad Operativa",
                  help=("Analiza el comportamiento estructural del ciclo operativo. En la vista de Líneas, el espacio entre flujos identifica "
                       "meses con excedentes brutos (ideales para inversión) frente a meses de déficit (que requieren apalancamiento). En la "
                       "vista de Velas Japonesas, evalúa el riesgo histórico: cuerpos cortos indican alta certeza operativa, mientras que "
                       "mechas largas alertan sobre extrema volatilidad e incertidumbre en ese mes."))
  

    if not balance["disponible"]:
        st.info("Información insuficiente: no se pudo calcular el flujo mensual de la Sección 2.")
    else:
        flujo_bruto = _flujo_bruto_mensual(balance)
        anios_disponibles = sorted({int(a) for a in flujo_bruto["Año"].dropna()})
        anios_ritmo = anios_disponibles
        vista_ritmo = st.segmented_control("Vista", VISTAS_CICLOS, default=VISTAS_CICLOS[0], key="ritmo_vista") or VISTAS_CICLOS[0]
        ritmo_promedios = _promedios_mensuales_historicos(flujo_bruto, anios_disponibles)
        ritmo_ohlc = {"Cobros": _ohlc_mensual(flujo_bruto, anios_disponibles, "Cobros"),
                      "Pagos": _ohlc_mensual(flujo_bruto, anios_disponibles, "Pagos")}
        if not anios_disponibles:
            st.info("Sin años con datos para analizar.")
        elif vista_ritmo == VISTAS_CICLOS[0]:
            if "ritmo_ejercicios" not in st.session_state:
                seleccion_previa = st.session_state.get("ritmo_ejercicios_prev", anios_ritmo)
            else:
                seleccion_previa = st.session_state["ritmo_ejercicios"]
            seleccion_previa = list(seleccion_previa or [])
            seleccion_valida = [
                int(anio) for anio in seleccion_previa
                if str(anio).isdigit() and int(anio) in anios_ritmo
            ]
            if "ritmo_ejercicios" not in st.session_state:
                st.session_state["ritmo_ejercicios"] = seleccion_valida or anios_ritmo
            else:
                if len(seleccion_valida) != len(seleccion_previa) and not seleccion_valida:
                    seleccion_valida = anios_ritmo
                st.session_state["ritmo_ejercicios"] = seleccion_valida
            sel_ej = st.pills("Ejercicios fiscales", anios_ritmo, selection_mode="multi",
                              key="ritmo_ejercicios")
            sel_ej = sorted(int(anio) for anio in (sel_ej or []))
            sel_met = st.pills("Métricas a visualizar", METRICAS_VISUALIZAR, selection_mode="multi",
                               default=st.session_state.get("ritmo_metricas_prev", METRICAS_VISUALIZAR), key="ritmo_metricas")
            metricas_sel = [m for m in METRICAS_VISUALIZAR if m in (sel_met or [])]
            st.session_state["ritmo_metricas_prev"] = metricas_sel
            if sel_ej and metricas_sel:
                fig_ciclos = _grafica_ciclos_lineas(
                    _series_anuales_por_mes(flujo_bruto, sel_ej),
                    sel_ej,
                    metricas_sel,
                )
                render_grafica(fig_ciclos, key="exec_ciclos_lineas")
            elif not sel_ej:
                st.info("Selecciona al menos un ejercicio fiscal para mostrar la gráfica.")
            elif not metricas_sel:
                st.info("Selecciona al menos una métrica para mostrar la gráfica.")
        else:
            fig_velas_c = _grafica_velas(ritmo_ohlc["Cobros"], "Cobros", ritmo_promedios["Cobros_Promedio"])
            fig_velas_p = _grafica_velas(ritmo_ohlc["Pagos"], "Pagos Totales", ritmo_promedios["Pagos_Promedio"])
            
            st.markdown("**Cobros · Velas por Mes**")
            render_grafica(fig_velas_c, key="exec_velas_cobros")
            
            st.markdown("**Pagos Totales · Velas por Mes**")
            render_grafica(fig_velas_p, key="exec_velas_pagos")

        st.text_area(
            "Comentario para la vista de Tendencia (Líneas)",
            max_chars=600,
            placeholder="Escribe un comentario para la tendencia (máx. 600 caracteres)...",
            key="note_graf_ciclos_lineas_input",
        )
        st.text_area(
            "Comentario para la vista de Volatilidad (Velas Japonesas)",
            max_chars=600,
            placeholder="Escribe un comentario compartido para las gráficas de velas (máx. 600 caracteres)...",
            key="note_graf_ciclos_velas_input",
        )

        if anios_disponibles:
            ejercicios_pdf = sorted(
                int(anio) for anio in (st.session_state.get("ritmo_ejercicios", anios_ritmo) or [])
                if str(anio).isdigit() and int(anio) in anios_ritmo
            )
            fig_velas_c = _grafica_velas(
                ritmo_ohlc["Cobros"], "Cobros", ritmo_promedios["Cobros_Promedio"]
            )
            fig_velas_p = _grafica_velas(
                ritmo_ohlc["Pagos"], "Pagos Totales", ritmo_promedios["Pagos_Promedio"]
            )

            if ejercicios_pdf:
                series_pdf = _series_anuales_por_mes(flujo_bruto, ejercicios_pdf)
                for i, metrica in enumerate(METRICAS_VISUALIZAR):
                    fig_tendencia = _grafica_ciclos_lineas(
                        series_pdf,
                        ejercicios_pdf,
                        [metrica],
                    )
                    elemento_tendencia = {
                        "type": "image",
                        "title": (
                            f"{metrica} · Tendencia mensual · Ejercicios Fiscales: "
                            f"{', '.join(map(str, ejercicios_pdf))}"
                        ),
                        "fig": fig_tendencia,
                    }
                    if i == 0:
                        elemento_tendencia["section_title"] = "3. Ciclos y Estacionalidad Operativa"
                    if i == len(METRICAS_VISUALIZAR) - 1:
                        elemento_tendencia["note"] = st.session_state.get(
                            "note_graf_ciclos_lineas_input",
                            "",
                        ).strip()
                    pdf_elements.append(elemento_tendencia)

            elemento_velas_c = {
                "type": "image",
                "title": "Cobros · Velas por Mes",
                "fig": fig_velas_c,
            }
            if not ejercicios_pdf:
                elemento_velas_c["section_title"] = "3. Ciclos y Estacionalidad Operativa"
            pdf_elements.extend([
                elemento_velas_c,
                {
                    "type": "image",
                    "title": "Pagos Totales · Velas por Mes",
                    "fig": fig_velas_p,
                    "note": st.session_state.get(
                        "note_graf_ciclos_velas_input",
                        "",
                    ).strip(),
                },
            ])

    # ---------------------------------------------------------------
    # Indicador 2: Tiempos documentados
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("4. Tiempos Documentados de Cobro y Pago", help=('''
        Mide los días promedio fiscales transcurridos entre la emisión de las facturas diferidas (PPD) y sus complementos de pago
        (REP) relacionados. Una brecha donde los días de pago (rojo) superan a los cobros (verde) indica que la empresa usa el dinero 
        de sus proveedores para financiarse. Si ocurre lo contrario, la empresa asume el costo de financiar a sus clientes.'''))

    # --- Vistas Histórico Anual (Y) y Detalle Mensual (M) ---
    plazos_ing_y = _tiempos_cache("clientes", a_fac_ing, a_pago_ing, anios_5, "Y", CODIGO_VERSION)
    plazos_egr_y = _tiempos_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, "Y", CODIGO_VERSION)
    plazos_ing_m = _tiempos_cache("clientes", a_fac_ing, a_pago_ing, anios_5, "M", CODIGO_VERSION)
    plazos_egr_m = _tiempos_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, "M", CODIGO_VERSION)

    fig_plazos_y = None
    fig_plazos_m = None
    titulo_y = "Tiempos de cobro (Clientes) vs. pago (Proveedores) — Histórico Anual"
    titulo_m_base = "Tiempos de cobro (Clientes) vs. pago (Proveedores) — Detalle Mensual"
    titulo_m = f"{titulo_m_base} - Todos los años"
    fig_plazos_m_pdf = None

    if not (plazos_ing_y.empty and plazos_egr_y.empty):
        fig_plazos_y = _grafica_plazos_comparativa(plazos_ing_y, plazos_egr_y, anual=True)
    if not (plazos_ing_m.empty and plazos_egr_m.empty):
        fig_plazos_m = _grafica_plazos_comparativa(plazos_ing_m, plazos_egr_m, anual=False)
        fig_plazos_m_pdf = fig_plazos_m

    vistas_plazos = []
    if fig_plazos_y is not None:
        vistas_plazos.append("Histórico anual")
    if fig_plazos_m is not None:
        vistas_plazos.append("Detalle mensual")

    if vistas_plazos:
        vista_plazos = st.radio(
            "Vista de tiempos documentados",
            vistas_plazos,
            horizontal=True,
            key="exec_vista_plazos"
        )
        if vista_plazos == "Histórico anual":
            st.markdown(f"**{titulo_y}**")
            render_grafica(fig_plazos_y, key="exec_plazos_comparativa_y")
        else:
            anios_mensuales = sorted({
                str(periodo)[:4]
                for plazos in (plazos_ing_m, plazos_egr_m)
                for periodo in plazos.loc[plazos["n_validos"].notna()].index
            })
            anio_mensual = st.selectbox(
                "Año del detalle mensual",
                ["Todos los años", *anios_mensuales],
                key="exec_plazos_anio_mensual",
            )
            if anio_mensual != "Todos los años":
                ing_anio = plazos_ing_m.loc[
                    plazos_ing_m.index.astype(str).str.startswith(f"{anio_mensual}-")
                ]
                egr_anio = plazos_egr_m.loc[
                    plazos_egr_m.index.astype(str).str.startswith(f"{anio_mensual}-")
                ]
                fig_plazos_m_pdf = _grafica_plazos_comparativa(ing_anio, egr_anio, anual=False)
                titulo_m = f"{titulo_m_base} - {anio_mensual}"
            st.markdown(f"**{titulo_m}**")
            render_grafica(fig_plazos_m_pdf, key="exec_plazos_comparativa_m")

        nota_plazos = st.text_area(
            "Insight - Tiempos Documentados",
            max_chars=600,
            key="note_graf_plazos_m"
        )

        if fig_plazos_y is not None:
            pdf_elements.append({
                "type": "image",
                "section_title": "4. Tiempos Documentados de Cobro y Pago",
                "title": titulo_y,
                "fig": fig_plazos_y
            })
        if fig_plazos_m_pdf is not None:
            monthly_pdf_element = {
                "type": "image",
                "title": titulo_m,
                "fig": fig_plazos_m_pdf,
                "note": nota_plazos
            }
            if fig_plazos_y is None:
                monthly_pdf_element["section_title"] = "4. Tiempos Documentados de Cobro y Pago"
            pdf_elements.append(monthly_pdf_element)

    # ---------------------------------------------------------------
    # Indicador 3: Concentración de Ingresos
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("5. Índice de Concentración de Ingresos (Riesgo de Dependencia)",
                 help=('''Evalúa el Riesgo de Cliente Clave (Key Client Risk). Cuantifica qué porcentaje de la facturación histórica total 
                       depende de un solo comprador. Una alta concentración advierte vulnerabilidad estructural, donde la pérdida de la 
                       cuenta o el retraso en sus pagos compromete directamente la viabilidad operativa.'''))
    

    conc = _concentracion_cache(a_fac_ing, anios_5, CODIGO_VERSION)
    if conc["motivo"] is None and not conc["sin_cliente"]:
        por_cliente = conc["por_cliente"]
        total_general = conc["total_general"]
        if total_general > 0 and not por_cliente.empty:
            ALTURA_CONC = 400
            col_dona, col_tabla = st.columns([2, 3])
            top5 = por_cliente.head(5)
            otros = total_general - float(top5.sum())
            datos_dona = top5.copy()
            if otros > 1:
                datos_dona = pd.concat([datos_dona, pd.Series({"Otros": otros})])
            nombres_completos = [conc["nombre_por_id"].get(idx, idx) if idx != "Otros" else "Otros" for idx in datos_dona.index]
            etiquetas_dona = [_nombre_abreviado(n) if n != "Otros" else "Otros" for n in nombres_completos]
            
            # 1. Definimos la paleta de azules según la cantidad de sectores de la dona
            num_sectores = len(datos_dona)
            # Lista fija de tonos azules de oscuro a medio (sin llegar a blanco)
            paleta_azules_fija = [
                "#0F2E85",  # Azul marino muy oscuro
                "#4160B4",  # Azul marino muy oscuro
                "#1D4ED8",  # Azul rey profundo
                "#2563EB",  # Azul vivo principal
                "#3B82F6",  # Azul claro brillante pero sólido
                "#60A5FA"   # Azul cielo (último tono, pero aún legible)
            ]
            
            # Asignamos los colores según la cantidad de sectores (si hay más de 5, se repiten de forma segura)
            colores_azules = [paleta_azules_fija[i % len(paleta_azules_fija)] for i in range(num_sectores)]

            fig_dona = px.pie(
                names=etiquetas_dona, 
                values=datos_dona.values, 
                hole=0.5, 
                custom_data=[nombres_completos],
                template="plotly_white",
                color_discrete_sequence=colores_azules  # <-- Aplicamos la paleta de azules aquí
            )
            
            # 2. Configuramos el textinfo, posición y el tamaño de fuente (size=18)
            fig_dona.update_traces(
                textinfo="percent", 
                textposition="inside", 
                sort=False,
                textfont=dict(size=15,color="white")  # <-- Tamaño de fuente configurado en 18
            )
            
            fig_dona = _layout_plotly(fig_dona, altura=ALTURA_CONC)
            fig_dona.update_layout(
                margin=dict(l=20, r=20, t=30, b=80),
                legend=dict(font=dict(textcase="upper"))
            )
            
            with col_dona:
                render_grafica(fig_dona, key="exec_concentracion_clientes")
                nota_conc = st.text_area("Insight - Concentración de Ingresos", max_chars=600, key="note_graf_conc")

            tabla_conc = por_cliente.rename("Facturación Total").reset_index().rename(
                columns={"Cliente": "RFC" if conc["agrupa_por_rfc"] else "Razón Social"})
            if conc["agrupa_por_rfc"]:
                tabla_conc["Razón Social"] = tabla_conc["RFC"].map(conc["nombre_por_id"]).fillna(tabla_conc["RFC"])
            tabla_conc["%"] = tabla_conc["Facturación Total"] / total_general * 100
            # Reordenamos las columnas explícitamente en el orden deseado: RFC, Razón Social, Facturación Total, %
            columnas_ordenadas = ["RFC", "Razón Social", "Facturación Total", "%"]
            # Por si acaso el dataset original viniera sin RFC y solo con Razón Social, validamos las columnas existentes:
            columnas_existentes = [c for c in columnas_ordenadas if c in tabla_conc.columns]
            tabla_conc = tabla_conc[columnas_existentes]
            
            # Copia redondeada para el PDF en Concentración
            tabla_conc_pdf = tabla_conc.head(10).copy()
            if "Facturación Total" in tabla_conc_pdf.columns:
                tabla_conc_pdf["Facturación Total"] = tabla_conc_pdf["Facturación Total"].apply(
                    lambda val: _formatear_mxn(val) if pd.notnull(val) else val)
            if "%" in tabla_conc_pdf.columns:
                tabla_conc_pdf["%"] = tabla_conc_pdf["%"].apply(lambda x: f"{float(x):,.2f}%" if pd.notnull(x) else x)

            pdf_elements.append({
                "type": "image", 
                "section_title": "5. Índice de Concentración de Ingresos (Riesgo de Dependencia)",
                "title": "Distribución Top Clientes (Concentración)", 
                "fig": fig_dona,
                "preserve_textfont_size": True
            })
            pdf_elements.append({"type": "table", "title": "Detalle de Concentración por Cliente", "df": tabla_conc_pdf, 
                "note": nota_conc})
            col_tabla.dataframe(
                tabla_conc.head(10),
                hide_index=True,
                width='stretch',
                height=ALTURA_CONC,
                column_config={"Facturación Total": st.column_config.NumberColumn(format="$%.2f")}
            )

    # ---------------------------------------------------------------
    # Indicador 5 (Sección 6): Clientes sin facturación en el periodo
    # ---------------------------------------------------------------
    st.divider()
    ayuda_sf = ("Mide la deserción comercial y la fuga de ingresos. Identifica específicamente a los clientes que transaccionaron y generaron "
                "ingresos para la empresa durante el año inmediato anterior, pero que dejaron de facturar por completo en el año analizado.")

    st.subheader("6. Clientes sin facturación en el periodo", help=ayuda_sf)


    resumen_sf = _resumen_sf_cache(a_fac_ing, anios_5, CODIGO_VERSION)
    if resumen_sf["motivo"] is not None:
        st.warning(f"No se pudo calcular: {resumen_sf['motivo']}.")
    elif resumen_sf["vacia"]:
        st.warning("No hay facturas vigentes con fecha legible para identificar clientes sin facturación.")
    else:
        anios_sf = resumen_sf["anios"]
        if st.session_state.get("sf_anio_sel") not in anios_sf:
            st.session_state["sf_anio_sel"] = resumen_sf["defecto"]
        anio_sf = int(st.selectbox("Año de análisis", anios_sf, key="sf_anio_sel"))
        res_sf = _res_sf_cache(a_fac_ing, anio_sf, anios_5, CODIGO_VERSION)
        if not res_sf["disponible"]:
            st.info(f"Información insuficiente: {res_sf['motivo']}")
        elif res_sf["n"] == 0:
            st.info("No se identificaron clientes del periodo anterior sin facturación en el periodo seleccionado")
        else:
            st.markdown(f"Estos clientes registraron facturación en {res_sf['anio_prev']}, pero no en {anio_sf}.")
            df_sf_original = _tabla_clientes_sin_facturacion(res_sf)
            st.markdown(_html_tabla_sin_facturacion(df_sf_original), unsafe_allow_html=True)
            
           # Agregar tabla y nota de clientes sin facturación al PDF
            if df_sf_original is not None and not df_sf_original.empty:
                nota_no_fact = st.text_area("Insight - Clientes sin facturación en el periodo", max_chars=600, key="nota_no_fact")
                
                df_sf_pdf = df_sf_original.copy()
                col_facturado = f"Facturado {res_sf['anio_prev']} (MXN)"
                for col in df_sf_pdf.columns:
                    if col == col_facturado:
                        df_sf_pdf[col] = df_sf_pdf[col].apply(
                            lambda val: _formatear_mxn(val, decimales=1) if pd.notnull(val) else val)
                    elif col != "Año":
                        df_sf_pdf[col] = df_sf_pdf[col].apply(_limpiar_y_formatear)

                # 1. Agregamos la tabla con su respectivo título y título de sección
                pdf_elements.append({
                    "type": "table", 
                    "section_title": "6. Clientes sin facturación en el periodo",
                    "title": f"Clientes con facturación en {res_sf['anio_prev']} pero inactivos en {anio_sf}", 
                    "df": df_sf_pdf,
                    "note": nota_no_fact if nota_no_fact and nota_no_fact.strip() else ""
                })

# ---------------------------------------------------------------
    # 6 (Sección 7). Dictamen de riesgo crediticio
    # ---------------------------------------------------------------
    st.divider()
    st.header("7.Estimación de Capacidad de Pago",
              help=('''Estimación documental con los CFDI de la ventana de 5 años; no es una oferta ni una opinión crediticia. El flujo mensual es EL MISMO resumen
                                  mensual de la sección 2 (Cobros − Pagos considerados − Nómina, en Flujo de Efectivo): esta sección no vuelve
                                  a extraer ni cruzar facturas. Un mes sin nómina vale 0 y se conservan los meses negativos.
                                  Se evalúan de forma independiente el mes más bajo, un mes intermedio y el mejor mes de los últimos 24 meses.'''))

    dictamen_res, plazo_sel = _simulador_financiamiento(balance)

    if dictamen_res is not None:
        cons = dictamen_res["conservador"]
        med = dictamen_res["medio"]
        opt = dictamen_res["optimista"]

        # Recuperamos los valores actuales ingresados en los number_input (vía st.session_state)
        # Streamlit asigna automáticamente el 'key' como el nombre de la variable en session_state
        plazo_val = st.session_state.get("sim_plazo", plazo_sel)
        tiie_val = st.session_state.get("sim_tiie", 0.0)
        margen_val = st.session_state.get("sim_margen", 0.0)
        tasa_total = dictamen_res["tasa"]

       

        # Funciones auxiliares seguras para extraer valores y viabilidad
        def _get_val_esc(e, tipo):
            if e is None:
                return "N/D", "Sin datos"
            if tipo == "flujo":
                return _mxn(e["flujo"]), f"Mes: {e['mes'].strftime('%b %Y')}"
            elif tipo == "cuota":
                if e["es_viable"]:
                    return _mxn(e["cuota"]), "30% del flujo libre"
                else:
                    return "No disponible", "Flujo insuficiente"
            elif tipo == "credito":
                if e["es_viable"]:
                    return _mxn(e["credito"]), f"{plazo_val} meses · tasa {tasa_total:.2f}%"
                else:
                    return "No viable", "No recomendado"
            return "", ""

        val_cons_f, sub_cons_f = _get_val_esc(cons, "flujo")
        val_cons_c, sub_cons_c = _get_val_esc(cons, "cuota")
        val_cons_l, sub_cons_l = _get_val_esc(cons, "credito")

        val_med_f, sub_med_f = _get_val_esc(med, "flujo")
        val_med_c, sub_med_c = _get_val_esc(med, "cuota")
        val_med_l, sub_med_l = _get_val_esc(med, "credito")

        val_opt_f, sub_opt_f = _get_val_esc(opt, "flujo")
        val_opt_c, sub_opt_c = _get_val_esc(opt, "cuota")
        val_opt_l, sub_opt_l = _get_val_esc(opt, "credito")

        # 2. Creamos la tabla estructurada verticalmente con los escenarios
        df_escenarios_pdf = pd.DataFrame([
            {
                "Concepto / Métrica": "<b>Flujo del Periodo</b>",
                "Mes Más Bajo (Conservador)": f"{val_cons_f}<br/><font size=7 color='#6B7280'>{sub_cons_f}</font>",
                "Mes Intermedio (Estimado)": f"{val_med_f}<br/><font size=7 color='#6B7280'>{sub_med_f}</font>",
                "Mejor Mes (Tope)": f"{val_opt_f}<br/><font size=7 color='#6B7280'>{sub_opt_f}</font>"
            },
            {
                "Concepto / Métrica": "<b>Capacidad de Pago (Cuota)</b>",
                "Mes Más Bajo (Conservador)": f"{val_cons_c}<br/><font size=7 color='#6B7280'>{sub_cons_c}</font>",
                "Mes Intermedio (Estimado)": f"{val_med_c}<br/><font size=7 color='#6B7280'>{sub_med_c}</font>",
                "Mejor Mes (Tope)": f"{val_opt_c}<br/><font size=7 color='#6B7280'>{sub_opt_c}</font>"
            },
            {
                "Concepto / Métrica": "<b>Línea de Financiamiento</b>",
                "Mes Más Bajo (Conservador)": f"{val_cons_l}<br/><font size=7 color='#6B7280'>{sub_cons_l}</font>",
                "Mes Intermedio (Estimado)": f"{val_med_l}<br/><font size=7 color='#6B7280'>{sub_med_l}</font>",
                "Mejor Mes (Tope)": f"{val_opt_l}<br/><font size=7 color='#6B7280'>{sub_opt_l}</font>"
            }
        ])

# 1. El título se agrega como elemento independiente porque los callouts no renderizan section_title
        pdf_elements.append({
            "type": "heading",
            "text": "7. Estimación de Capacidad de Pago"
        })

        pdf_elements.append({
            "type": "callout", 
            "text": f"<b>Parámetros de Simulación Aplicados:</b><br/>"
                    f"• Plazo del financiamiento: <b>{plazo_val} meses</b><br/>"
                    f"• TIIE Base: <b>{tiie_val:.2f}%</b> | Puntos adicionales sobre TIIE (%): <b>{margen_val:.2f}%</b> (Tasa Anual Total: <b>{tasa_total:.2f}%</b>)"
        })

        # 2. La tabla de escenarios se anexa inmediatamente debajo
        pdf_elements.append({
            "type": "table",
            "title": "Comparativa Vertical de Escenarios de Financiamiento",
            "df": df_escenarios_pdf,
            "cell_scale": 1.15
        })
        pdf_elements.append({
            "type": "callout", # O "paragraph" según lo que soporte tu generador
            "text": """<b>Nota:</b> La capacidad de pago mostrada es una estimación basada en la información fiscal histórica de la empresa y 
                      no equivale al monto que un banco podría otorgarle, ya que cada institución aplica sus propias métricas y 
                      criterios de evaluación. Si desea obtener un financiamiento, podemos asesorarle para que pueda acceder 
                      a un crédito que se ajuste a sus necesidades."""
        })
    # ---------------------------------------------------------------
    # SECCIÓN DE DESCARGA DE REPORTES EN PDF
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("Exportación de Reporte Ejecutivo")
    
    col_pdf_desc, col_pdf_info = st.columns([1, 2])
    with col_pdf_info:
        '''exec_notes = st.text_area(
            "Notas / Observaciones Generales del Analista para el PDF:",
            placeholder="Agrega tus conclusiones ejecutivas generales aquí...",
            key="exec_notes_general"
        )'''
    
    with col_pdf_desc:
        st.write("Genera un PDF con las gráficas, sus conclusiones individuales, tablas e información financiera de esta vista.")
        
        # texto_notas = exec_notes
        if dictamen_res is not None:
            cons_viabilidad = "VIABLE" if dictamen_res["conservador"] and dictamen_res["conservador"]["es_viable"] else "NO VIABLE"
            # texto_notas =  exec_notes

        if st.button("Generar Reporte PDF", key="btn_generar_pdf"):
            with st.spinner("Construyendo estructura modular y maquetando PDF..."):
                
                elementos_finales = []
                # if texto_notas and texto_notas.strip():
                # elementos_finales.append({"type": "heading", "text": "Notas y Observaciones Ejecutivas"})
                # elementos_finales.append({"type": "callout"})
                
                elementos_finales.extend(pdf_elements)

                pdf_data = generate_modular_pdf(
                    title="Reporte Ejecutivo de Riesgo y Viabilidad",
                    subtitle="",
                    elements=elementos_finales
                )
                
                st.download_button(
                    label="Descargar reporte PDF",
                    data=pdf_data,
                    file_name="Reporte_Ejecutivo_Detallado.pdf",
                    mime="application/pdf",
                    key="btn_download_pdf"
                )
'''
MOVER TODAS ESTAS VARIABLE AL ARCHIVO DE CONFIG.PY. POR EL MOMENTO, SE QUEDAN AQUI HASTA VALIDAR

'''

# Evaluación INDEPENDIENTE de cada escenario: proporción del flujo del mes frente al mejor mes de la ventana -> viabilidad y porcentaje del flujo libre.
PROPORCION_MINIMA = 0.05        # flujo del mes < 5 % del mejor mes: flujo marginal, no viable
CREDITO_MINIMO = 50_000.0       # línea comercial mínima (MXN): si al 30 % el crédito queda por debajo, el escenario no es viable
PCT_CAPACIDAD = 0.30            # porcentaje ESTANDARIZADO del flujo libre que se compromete en todo escenario viable (mes bajo, intermedio o mejor mes)
PLAZO_DEFECTO_MESES, PLAZO_MIN_MESES, PLAZO_MAX_MESES = 36, 12, 60
MARGEN_COMERCIAL_DEFECTO = 5.0  # puntos porcentuales que el banco suma a la TIIE (editable)
VENTANA_DICTAMEN_MESES = 24     # el dictamen evalúa estrictamente los últimos 24 meses históricos disponibles
TIIE_DEFECTO = 6.79             # último dato conocido de la TIIE a 28 días de Banxico (corte al 25/09/2026); el analista la actualiza a mano según el mercado del momento


def _monto_por_cuota(cuota: float, tasa_m: float, plazo: int) -> float:
    """Monto de crédito estimado (ingeniería inversa, valor actual de la anualidad): cuota = 0 -> 0; tasa 0 -> cuota * plazo; tasa > 0 ->
    cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)."""
    if cuota <= 0 or plazo <= 0:
        return 0.0
    return cuota * plazo if tasa_m <= 0 else cuota * ((1 - (1 + tasa_m) ** -plazo) / tasa_m)


def evaluar_escenario(flujo_mes: float, flujo_max: float, tasa_mensual: float, plazo: int) -> dict:
    """Evalúa UN escenario de forma independiente. `proporcion = flujo_mes / flujo_max` (0 si flujo_max <= 0). NO viable (porcentaje, cuota y crédito = 0) si `flujo_mes <= 0`,
    `proporcion < PROPORCION_MINIMA` (5 %: flujo marginal) o el crédito calculado al 30 % es menor a `CREDITO_MINIMO` (MXN 50,000). Todo escenario viable compromete el mismo
    `PCT_CAPACIDAD` (30 % del flujo libre): `cuota = flujo_mes × 0.30` y `credito` = valor presente de la anualidad ordinaria (`_monto_por_cuota`, que también cubre tasa 0)."""
    proporcion = flujo_mes / flujo_max if flujo_max > 0 else 0.0
    credito = _monto_por_cuota(max(0.0, flujo_mes) * PCT_CAPACIDAD, tasa_mensual, plazo)
    if flujo_mes <= 0 or proporcion < PROPORCION_MINIMA or credito < CREDITO_MINIMO:
        return {"es_viable": False, "estatus_texto": "No viable para financiamiento", "motivo_badge": "Flujo libre insuficiente / marginal",
                "porcentaje": 0.0, "cuota": 0.0, "credito": 0.0, "proporcion": proporcion}
    return {"es_viable": True, "estatus_texto": "Viable para financiamiento", "motivo_badge": None, "porcentaje": PCT_CAPACIDAD, "cuota": flujo_mes * PCT_CAPACIDAD,
            "credito": credito, "proporcion": proporcion}





def _escenarios_credito(flujo: pd.Series, plazo: int, tasa_anual: float) -> dict:
    """Motor de la Sección 7 sobre el Flujo Neto mensual de la Sección 2: filtra estrictamente los últimos `VENTANA_DICTAMEN_MESES` (24) meses y ubica TRES MESES REALES: el más bajo
    (`flujo_min`), el más alto (`flujo_max`) y el intermedio = el mes (sin contar los dos extremos) cuyo flujo queda más cerca de `punto_medio_ref = (flujo_min + flujo_max) / 2`
    (sin promedios; `medio` es None si no hay un tercer mes). Cada escenario se evalúa con `evaluar_escenario` (viabilidad y porcentaje propios), tomando el mejor mes como techo."""
    ventana = flujo.sort_index().tail(VENTANA_DICTAMEN_MESES)
    flujo_min, flujo_max = float(ventana.min()), float(ventana.max())
    tasa_mensual = tasa_anual / 12 / 100
    idx_min, idx_max = ventana.idxmin(), ventana.idxmax()
    punto_medio_ref = (flujo_min + flujo_max) / 2
    candidatos = ventana.drop(index=list({idx_min, idx_max}))                       # el mes intermedio no puede ser ninguno de los dos extremos
    idx_intermedio = (candidatos - punto_medio_ref).abs().idxmin() if len(candidatos) else None

    def escenario(flujo_mes, mes):
        return {"flujo": flujo_mes, "mes": mes, **evaluar_escenario(flujo_mes, flujo_max, tasa_mensual, plazo)}

    return {"ventana": ventana, "meses": len(ventana), "tasa_anual": tasa_anual, "plazo": plazo, "flujo_min": flujo_min, "flujo_max": flujo_max, "punto_medio_ref": punto_medio_ref,
            "conservador": escenario(flujo_min, idx_min),
            "medio": escenario(float(ventana.loc[idx_intermedio]), idx_intermedio) if idx_intermedio is not None else None,
            "optimista": escenario(flujo_max, idx_max)}






def _simulador_financiamiento(balance: dict):
    """Sección 7: capacidad de pago y límite de endeudamiento alimentados EXACTAMENTE con el resumen mensual de la Sección 2 (`balance`)."""
    if not balance["disponible"]:
        st.info("Información insuficiente: " + "; ".join(f"{k}: {v}" for k, v in balance["motivos"].items()))
        return None, None  
        
    c1, c2, c3 = st.columns(3)
    with c1:
        plazo = int(st.number_input("Plazo del financiamiento (meses)", min_value=PLAZO_MIN_MESES, max_value=PLAZO_MAX_MESES, value=PLAZO_DEFECTO_MESES, step=1, key="sim_plazo",
                                     help="Supuesto editable de simulación (no es un dato bancario ni sale del Excel): meses en que se pagaría el crédito."))
    with c2:
        tiie_actual = float(st.number_input("TIIE Actual / Base (%)", min_value=0.0, max_value=100.0, value=TIIE_DEFECTO, step=0.05, format="%.2f", key="sim_tiie",
                                            help=f"TIIE a 28 días de Banxico. Se precarga con el último dato conocido ({TIIE_DEFECTO:.2f}%, corte al 25/09/2026); tú eres responsable de "
                                                                                             "actualizarla según las condiciones del mercado al momento del análisis (también sirve para simular una TIIE futura)."))
    with c3:
        margen_comercial = float(st.number_input("Puntos adicionales sobre TIIE (%)", min_value=0.0, value=MARGEN_COMERCIAL_DEFECTO, step=0.5, format="%.2f", key="sim_margen",
                                               help="Puntos porcentuales adicionales que cobra el banco sobre la TIIE (por ejemplo 5.0 o 10.0). Supuesto editable de simulación."))
    
    tasa_anual = tiie_actual + margen_comercial
    esc = _escenarios_credito(_excedente_homologado(balance)["Excedente_Mensual_Homologado"], plazo, tasa_anual)
    
    if esc["meses"] == 0:
        st.info("Información insuficiente: el resumen mensual de la Sección 2 no tiene meses para evaluar.")
        return None, None  
        
    mes_txt = lambda p: f"{MESES_ES[p.month - 1]} {p.year}"
    columnas = st.columns(3)
    
    # Renderizado visual de los 3 escenarios en Streamlit
    for col, titulo, e, flujo_lbl, linea_lbl, flujo_help, linea_help in (
        (
            columnas[0], 
            "Escenario Mes Más Bajo", 
            esc["conservador"], 
            "Flujo del mes más bajo", 
            "Financiamiento viable",
            f"Menor Flujo Neto mensual (Cobros − Pagos − Nómina, Sección 2) de los últimos {esc['meses']} meses; puede ser negativo.",
            "Valor presente de la cuota de este escenario con la Tasa Anual Total y el plazo elegido. No viable si el flujo es negativo, marginal o no respalda una línea mínima de MXN 50,000."
        ),
        (
            columnas[1], 
            "Escenario Mes Intermedio", 
            esc["medio"], 
            "Flujo del mes intermedio", 
            "Financiamiento estimado",
            f"Mes real, distinto del más bajo y del más alto, cuyo Flujo Neto mensual queda más cerca del punto medio entre ambos extremos ({_mxn(esc['punto_medio_ref'])}).",
            "Valor presente de la cuota del mes intermedio con la Tasa Anual Total y el plazo elegido."
        ),
        (
            columnas[2], 
            "Escenario Mejor Mes", 
            esc["optimista"], 
            "Flujo del mejor mes", 
            "Financiamiento tope",
            f"Mayor Flujo Neto mensual (Cobros − Pagos − Nómina, Sección 2) de los últimos {esc['meses']} meses.",
            "Valor presente de la cuota con la Tasa Anual Total y el plazo elegido, suponiendo que todos los meses fueran como el mejor."
        )
    ):
        with col:
            badge = ""
            if e is not None:
                color, texto = (("#09ab3b", "rgba(33, 195, 84, 0.16)"), "Viable para crédito") if e["es_viable"] else (("#ff4b4b", "rgba(255, 75, 75, 0.16)"), "No viable para crédito")
                badge = (f'<span style="color: {color[0]}; background: {color[1]}; border-radius: 0.5rem; padding: 0.1rem 0.55rem; font-size: 0.8rem; '
                         f'font-weight: 600; white-space: nowrap;">{texto}</span>')
            
            st.markdown(f'<div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 12px;">'
                        f'<span style="font-size: 1.25rem; font-weight: 600;">{titulo}</span>{badge}</div>', unsafe_allow_html=True)
            
            if e is None:
                st.info("Se necesitan al menos 3 meses con información para identificar un mes intermedio.")
                continue
                
            if not e["es_viable"]:
                flujo_help += f" {e['motivo_badge']}."
                
            st.metric(flujo_lbl, _mxn(e["flujo"]), mes_txt(e["mes"]), delta_color="off", delta_arrow="off", help=flujo_help)
            
            if e["es_viable"]:
                st.metric("Capacidad de pago", f"MXN {e['cuota']:,.0f}", "30% del flujo libre", delta_color="off", delta_arrow="off",
                          help=f"El flujo de este mes equivale al {e['proporcion'] * 100:.0f}% del mejor mes de la ventana; cuota = flujo del mes × 30%.")
                st.metric(linea_lbl, f"MXN {e['credito']:,.0f}", f"{plazo} meses · tasa {tasa_anual:.2f}% anual", delta_color="off", delta_arrow="off", help=linea_help)
            else:
                st.metric("Capacidad de pago", "No disponible", "Flujo insuficiente para cuota", delta_color="off", delta_arrow="off",
                          help=f"{e['estatus_texto']}: el flujo del mes es negativo, menor al 5% del mejor mes o no respalda una línea comercial mínima.")
                st.metric(linea_lbl, "No viable", "No se recomienda endeudamiento en este nivel de flujo", delta_color="off", delta_arrow="off", help=linea_help)

    # Explicaciones metodológicas en la interfaz
    st.markdown(
        '''
            ⚠️ **Nota:** La capacidad de pago mostrada es una **estimación** basada en la información fiscal histórica de la empresa y 
            no equivale al monto que un banco podría otorgarle, ya que cada institución aplica sus propias métricas y 
            criterios de evaluación. Si desea obtener un financiamiento, podemos asesorarle para que pueda acceder 
            a un crédito que se ajuste a sus necesitades
        '''
    )
    st.caption("Evaluación paramétrica basada en el flujo neto documental. Es orientativa y no constituye una opinión crediticia.")

    # Empaquetamos y retornamos los resultados para el reporte PDF y el desempaquetado de la vista
    resultado_dictamen = {
        "plazo": plazo,
        "tasa": tasa_anual,
        "conservador": esc["conservador"],
        "medio": esc["medio"],
        "optimista": esc["optimista"]
    }

    return resultado_dictamen, plazo