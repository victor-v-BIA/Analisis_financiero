# Módulo 1: Dashboard Ejecutivo (Riesgo y Viabilidad)

'''
Contiene la vista completa del Dashboard de Riesgo y Viabilidad.
'''
from html import escape

import streamlit as st
import pandas as pd
import plotly.express as px

from utils import _mxn, _formatear_mxn
from utils import (_nb, _nombre_abreviado,_rango_meses_texto, _limpiar_y_formatear, _monto_por_cuota)
from core.loader import (anios_5_archivos, _anual_ppd_cache,
                         _balance_cache, _tiempos_cache,_concentracion_cache,
                         _resumen_sf_cache,_res_sf_cache,_trazabilidad_cache,_operaciones_divisas_cache)
from core.api_rates import _obtener_fix, cruzar_fix

from config import (CODIGO_VERSION, MESES_ES, VISTAS_CICLOS,
                    METRICAS_VISUALIZAR, PESOS_INDICE,BANDA_CONCENTRACION_ALTA,
                    BANDA_CONCENTRACION_BAJA,MOSTRAR_INDICE_DESEMPENO,
                    REGLAS_INDICE,PLAZO_DEFECTO_MESES,PERIODOS_EVALUACION, TASA_REFERENCIA_ANUAL,MARGEN_SEGURIDAD_PCT,
                    PROPORCION_MINIMA, CREDITO_MINIMO, PCT_CAPACIDAD, PLAZO_DEFECTO_MESES, PLAZO_MIN_MESES, PLAZO_MAX_MESES,
                    MARGEN_COMERCIAL_DEFECTO, VENTANA_DICTAMEN_MESES, TIIE_DEFECTO,PREFIJO_DIVISAS)

from components.charts import (_grafica_diferencia_anual, _html_detalle_anual, _grafica_diferencia_cobros_pagos,
                                _grafica_ciclos_lineas,_grafica_velas,_grafica_plazos_comparativa,
                                _layout_plotly,_html_tabla_sin_facturacion,_grafica_gauge_score,_grafica_pilares_score,
                                render_grafica,fig_tc_fix_vs_facturado,_html_tabla_intermediarios,_html_tabla_benchmark, _html_kpis_divisas)

from core.finance_logic import ( _tabla_detalle_anual, _anios_cobertura_completa,
                                 _flujo_bruto_mensual, _ohlc_mensual,
                                 _promedios_mensuales_historicos,
                                 _series_anuales_por_mes,_tabla_clientes_sin_facturacion,
                                 _trazabilidad_indicadores,_indice_desempeno,_periodo_evaluacion,
                                 _excedente_homologado,_dictamen_credito,_escenarios_credito,
                                 kpis_divisas, tabla_intermediarios, benchmark_mercado)

from components.pdf_generator import generate_modular_pdf


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


def modulo_riesgo(f_ingresos_fac, f_ingresos_pago, f_egresos_fac, f_egresos_pago, f_nomina,
                  file_egresos_productos=None, file_fix=None) -> None:
    """Dashboard Ejecutivo (Flujo de Efectivo): cruza Ingresos y Egresos para un vistazo de riesgo y viabilidad, antes de entrar
    al detalle operativo de cada módulo."""
    st.title("Dashboard Ejecutivo (Riesgo y Viabilidad)")

    pdf_elements = []

    # ---------------------------------------------------------------
    # Módulo 1: Facturación PPD y complementos de pago
    # ---------------------------------------------------------------
    st.subheader("1. Facturación PPD y Complementos: Diferencias Anuales")
    st.caption("Años en los que los importes de los complementos fueron mayores o menores que la facturación PPD.")

    pdf_elements.append({"type": "heading", "text": "1. Facturación PPD y Complementos: Diferencias Anuales"})

    df_pagos_ingresos, df_pagos_egresos = f_ingresos_pago, f_egresos_pago

    a_fac_ing = _nb(f_ingresos_fac) if f_ingresos_fac is not None else None
    a_pago_ing = _nb(df_pagos_ingresos) if df_pagos_ingresos is not None else None
    a_fac_egr = _nb(f_egresos_fac) if f_egresos_fac is not None else None
    a_pago_egr = _nb(df_pagos_egresos) if df_pagos_egresos is not None else None
    a_nomina = _nb(f_nomina) if f_nomina is not None else None
    anios_5 = anios_5_archivos(f_ingresos_fac, f_egresos_fac)

    if a_fac_ing is not None and a_pago_ing is not None:
        anual_ing, motivo_ing = _anual_ppd_cache("clientes", a_fac_ing, a_pago_ing, anios_5, CODIGO_VERSION)
    else:
        faltantes_ing = [
            nombre for nombre, archivo in (
                ("Facturación Emitida", a_fac_ing),
                ("Complementos de Pago de Ingresos", a_pago_ing),
            ) if archivo is None
        ]
        anual_ing, motivo_ing = None, "**Archivos faltantes:** " + ", ".join(faltantes_ing)
    if a_fac_egr is not None and a_pago_egr is not None:
        anual_egr, motivo_egr = _anual_ppd_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, CODIGO_VERSION)
    else:
        faltantes_egr = [
            nombre for nombre, archivo in (
                ("Facturación Recibida", a_fac_egr),
                ("Complementos de Pago de Egresos", a_pago_egr),
            ) if archivo is None
        ]
        anual_egr, motivo_egr = None, "**Archivos faltantes:** " + ", ".join(faltantes_egr)

    def _bloque_anual(columna, titulo, anual, motivo, nombre_serie, lado, ayuda):
        with columna:
            st.markdown(f"**{titulo}**", help=ayuda)
            if anual is None or anual.empty:
                if anual is None:
                    st.info(f"{motivo}.")
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
                placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
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
    

    faltantes_balance = [
        nombre for nombre, archivo in (
            ("Facturación Emitida", a_fac_ing),
            ("Complementos de Pago de Ingresos", a_pago_ing),
            ("Facturación Recibida", a_fac_egr),
            ("Complementos de Pago de Egresos", a_pago_egr),
            ("Nómina", a_nomina),
        ) if archivo is None
    ]
    if faltantes_balance:
        balance = {"disponible": False, "motivos": {"**Archivos faltantes**": ", ".join(faltantes_balance)}}
    else:
        a_productos = _datos_archivo_cache(file_egresos_productos) if file_egresos_productos is not None else None
        try:
            balance = _balance_cache(a_fac_ing, a_pago_ing, a_fac_egr, a_pago_egr, a_nomina,
                                     a_productos, a_productos, anios_5, CODIGO_VERSION)
        except (KeyError, ValueError) as e:
            if file_egresos_productos is not None:
                st.error(f"'{file_egresos_productos.name}' no tiene la estructura esperada para detectar compras "
                         f"de divisas. {e}")
            else:
                st.error(f"No se pudo calcular el flujo ejecutivo: {e}")
            st.stop()
        if a_productos is not None:
            divisas = balance["divisas"]
            st.info(
                f"Filtro de divisas: {divisas['coincidencias']} concepto(s) 841216 coincidieron exactamente "
                f"con CFDI por RFC, fecha e importe; se excluyeron {divisas['cfdis_excluidos']} CFDI."
            )
            if divisas["uuids_divisas"] and not divisas["relacion_pago_disponible"]:
                st.warning("No se pudieron excluir pagos relacionados con CFDI de divisas: la Base de PAGO no "
                           "incluye UUID DR o Documento Relacionado.")
            elif divisas["complementos_excluidos"]:
                st.info(f"Se excluyeron {divisas['complementos_excluidos']} pago(s) relacionado(s) con CFDI de divisas.")
    nombre_cobros, nombre_pagos = "Cobros", "Pagos considerados"

    if not balance["disponible"]:
        detalle = "; ".join(f"{k}: {v}" for k, v in balance["motivos"].items())
        st.info(f"{detalle}.")
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
            titulo_graf = f"Flujo Neto Fiscal Mensual Año {anio_sel}"
            
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
            placeholder="Escribe un comentario para las gráficas de velas (máx. 600 caracteres)...",
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
                            f"{metrica} · Tendencia por Año"),
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
    faltantes_plazos = [
        nombre for nombre, archivo in (
            ("Facturación Emitida", a_fac_ing),
            ("Complementos de Pago de Ingresos", a_pago_ing),
            ("Facturación Recibida", a_fac_egr),
            ("Complementos de Pago de Egresos", a_pago_egr),
        ) if archivo is None
    ]
    if faltantes_plazos:
        plazos_ing_y = plazos_egr_y = plazos_ing_m = plazos_egr_m = pd.DataFrame()
    else:
        plazos_ing_y = _tiempos_cache("clientes", a_fac_ing, a_pago_ing, anios_5, "Y", CODIGO_VERSION)
        plazos_egr_y = _tiempos_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, "Y", CODIGO_VERSION)
        plazos_ing_m = _tiempos_cache("clientes", a_fac_ing, a_pago_ing, anios_5, "M", CODIGO_VERSION)
        plazos_egr_m = _tiempos_cache("proveedores", a_fac_egr, a_pago_egr, anios_5, "M", CODIGO_VERSION)

    fig_plazos_y = None
    fig_plazos_m = None
    titulo_y = "Tiempos de cobro vs. Pago  — Histórico Anual"
    titulo_m_base = "Tiempos de cobro vs. Pago  — Detalle Mensual"
    titulo_m = f"{titulo_m_base}"
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
            key="note_graf_plazos_m",
            placeholder="Escríbe tus conslusiones (máx. 600 caracteres)..."
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
    elif faltantes_plazos:
        st.info("No se muestran estas gráficas porque faltan: " + ", ".join(faltantes_plazos) + ".")

    # ---------------------------------------------------------------
    # Indicador 3: Concentración de Ingresos
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("5. Índice de Concentración de Ingresos (Riesgo de Dependencia)",
                 help=('''Evalúa el Riesgo de Cliente Clave (Key Client Risk). Cuantifica qué porcentaje de la facturación histórica total 
                       depende de un solo comprador. Una alta concentración advierte vulnerabilidad estructural, donde la pérdida de la 
                       cuenta o el retraso en sus pagos compromete directamente la viabilidad operativa.'''))
    

    if a_fac_ing is None:
        conc = {"motivo": "Falta Facturación Emitida", "sin_cliente": False}
    else:
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
                "#60A5FA"   # Azul cielo
            ]
            
            # Asignamos los colores según la cantidad de sectores (si hay más de 5, se repiten de forma segura)
            colores_azules = [paleta_azules_fija[i % len(paleta_azules_fija)] for i in range(num_sectores)]

            fig_dona = px.pie(
                names=etiquetas_dona, 
                values=datos_dona.values, 
                hole=0.5, 
                custom_data=[nombres_completos],
                template="plotly_white",
                color_discrete_sequence=colores_azules  # <-- paleta de azules
            )
            
            # 2. Configuramos el textinfo, posición y el tamaño de fuente 
            fig_dona.update_traces(
                textinfo="percent", 
                textposition="inside", 
                sort=False,
                textfont=dict(size=15,color="white")  # <-- Tamaño de fuente configurado
            )
            
            fig_dona = _layout_plotly(fig_dona, altura=ALTURA_CONC)
            fig_dona.update_layout(
                margin=dict(l=20, r=20, t=30, b=80),
                legend=dict(font=dict(textcase="upper"))
            )
            
            with col_dona:
                render_grafica(fig_dona, key="exec_concentracion_clientes")
            nota_conc = st.text_area("Insight - Concentración de Ingresos",
                                      max_chars=600, 
                                      key="note_graf_conc",
                                      placeholder="Escríbe tus conslusiones (máx. 600 caracteres)...")
            
            tabla_conc = por_cliente.rename("Facturación Total").reset_index().rename(
                columns={"Cliente": "RFC" if conc["agrupa_por_rfc"] else "Razón Social"})
            
            if conc["agrupa_por_rfc"]:
                tabla_conc["Razón Social"] = tabla_conc["RFC"].map(conc["nombre_por_id"]).fillna(tabla_conc["RFC"])
            
            tabla_conc["%"] = tabla_conc["Facturación Total"] / total_general * 100
            
            # Reordenamos las columnas explícitamente
            columnas_ordenadas = ["RFC", "Razón Social", "Facturación Total", "%"]
            columnas_existentes = [c for c in columnas_ordenadas if c in tabla_conc.columns]
            tabla_conc = tabla_conc[columnas_existentes]

            # -----------------------------------------------------------------
            # NUEVO: CREAR LA FILA DE TOTALES
            # -----------------------------------------------------------------
            # 1. Preparamos un diccionario con los totales
            fila_total = {
                "Facturación Total": tabla_conc["Facturación Total"].sum(),
                "%": tabla_conc["%"].sum()
            }
            
            # 2. Asignamos la etiqueta "TOTAL" a la columna que exista (RFC o Razón Social)
            if "Razón Social" in tabla_conc.columns:
                fila_total["Razón Social"] = "TOTAL GENERAL"
                if "RFC" in tabla_conc.columns:
                    fila_total["RFC"] = "" # Dejamos el RFC vacío
            elif "RFC" in tabla_conc.columns:
                fila_total["RFC"] = "TOTAL GENERAL"

            # 3. Concatenamos la fila al DataFrame original
            df_total = pd.DataFrame([fila_total])
            tabla_conc = pd.concat([tabla_conc, df_total], ignore_index=True)

            tabla_conc_app = tabla_conc.iloc[:-1].head(10).copy()
            fila_total_app = df_total.copy()
            fila_total_app.loc[0, "Facturación Total"] = tabla_conc_app["Facturación Total"].sum()
            fila_total_app.loc[0, "%"] = tabla_conc_app["%"].sum()
            tabla_conc_app = pd.concat([tabla_conc_app, fila_total_app], ignore_index=True)

            # Copia redondeada para el PDF en Concentración
            tabla_conc_pdf = tabla_conc_app.copy()
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
                tabla_conc_app.style.format({
                    "Facturación Total": lambda val: _formatear_mxn(val) if pd.notnull(val) else val,
                    "%": lambda val: f"{val:,.2f}%" if pd.notnull(val) else val,
                }),
                hide_index=True,
                width='stretch',
                height=ALTURA_CONC,
            )
    elif conc["motivo"] is not None:
        st.info(f"No se muestra esta sección: {conc['motivo']}.")

    # ---------------------------------------------------------------
    # Indicador 5 (Sección 6): Clientes sin facturación en el periodo
    # ---------------------------------------------------------------
    st.divider()
    ayuda_sf = ("Mide la deserción comercial y la fuga de ingresos. Identifica específicamente a los clientes que transaccionaron y generaron "
                "ingresos para la empresa durante el año inmediato anterior, pero que dejaron de facturar por completo en el año analizado.")

    st.subheader("6. Clientes sin facturación en el periodo", help=ayuda_sf)


    if a_fac_ing is None:
        resumen_sf = {
            "motivo": "Falta Facturación Emitida",
            "vacia": False,
            "anios": [],
            "defecto": None,
        }
    else:
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
                nota_no_fact = st.text_area("Insight - Clientes sin facturación en el periodo",
                                            max_chars=600,
                                            key="nota_no_fact",
                                            placeholder="Escríbe tus conslusiones (máx. 600 caracteres)...")
                
                df_sf_pdf = df_sf_original.copy()
                col_facturado = f"Facturado {res_sf['anio_prev']} (MXN)"
                for col in df_sf_pdf.columns:
                    if col == col_facturado:
                        df_sf_pdf[col] = df_sf_pdf[col].apply(
                            lambda val: _formatear_mxn(val, decimales=1) if pd.notnull(val) else val)
                    elif col == "Participación (%)":
                        df_sf_pdf[col] = df_sf_pdf[col].apply(
                            lambda val: _limpiar_y_formatear(val, sufijo="%"))
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
            
            # Lista de meses abreviados en español (el índice 0 se deja vacío para que coincida con el número de mes)
            meses_es = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            
            if tipo == "flujo":
                # Extraemos el mes y año usando el número de mes para asegurar el español
                mes_formateado = f"{meses_es[e['mes'].month]} {e['mes'].year}"
                return _mxn(e["flujo"]), f"Mes: {mes_formateado}"
                
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
    # SECCIÓN 8: Operaciones en divisas
    # ---------------------------------------------------------------
    st.divider()
    _seccion_divisas(file_egresos_productos, f_fix=file_fix, anios=anios_5, pdf_elements=pdf_elements)

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


# ___________________________
# SECCION 7
# ___________________________


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
    st.caption(
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


#===================================
# SECCION 8
#===================================

def _seccion_divisas(f_productos, f_fix=None, anios=None, pdf_elements=None) -> None:
    """Sección «8. Eficiencia Cambiaria y Operaciones en Divisas» del Dashboard Ejecutivo, 100% automática para cualquier empresa cargada: conceptos de CFDI recibidos con
    clave 841216 (base de Productos Recibidos, ruteada desde la barra lateral; sin cargadores aquí) frente al tipo de cambio de referencia consultado por `_obtener_fix`
    (archivo FIX, Banxico SIE, Frankfurter o Yahoo Finance). El contraste es contra el tipo de cambio del DÍA de la operación (`Fecha de operación`). `anios` es la
    ventana de ejercicios de los CFDI cargados (`anios_5`, p. ej. 2021-2025): operaciones y gráfica quedan dentro de ella (nada de meses posteriores sin facturación). Una moneda
    a la vez (inicia en la de mayor volumen en MXN). Cuatro indicadores limpios, UNA gráfica y dos tablas: A) intermediarios actuales y B) benchmark de mercado."""
    st.header("8. Eficiencia Cambiaria y Operaciones en Divisas",
              help=("Compras de divisas (conceptos de CFDI recibidos con clave 841216) comparadas contra el tipo de cambio de referencia del DÍA de la operación (Fecha de "
                    "operación; último día hábil previo si es inhábil): mide la ejecución spot del banco frente al mercado de ese mismo día. Spread = TC facturado − referencia; "
                    "sobreprecio = divisa comprada × spread. Estas compras no cuentan como egresos operativos; las comisiones bancarias (84121500) sí."))
    if pdf_elements is not None:
        pdf_elements.append({
            "type": "heading",
            "text": "8. Eficiencia Cambiaria y Operaciones en Divisas"
        })

    def _pdf_sin_datos(mensaje):
        if pdf_elements is not None:
            pdf_elements.append({"type": "callout", "text": escape(mensaje)})

    if f_productos is None:
        mensaje = "Para analizar las operaciones en divisas, incluye en la carga la base «CFDI Recibidos Productos» (conceptos de CFDI recibidos)."
        st.info(mensaje)
        _pdf_sin_datos(mensaje)
        return
    try:
        ops = _operaciones_divisas_cache(f_productos.name, f_productos.getvalue(), CODIGO_VERSION)
    except (KeyError, ValueError) as e:
        mensaje = f"Información insuficiente: «{f_productos.name}» no trae las columnas esperadas de conceptos de CFDI recibidos. {e.args[0]}"
        st.info(mensaje)
        _pdf_sin_datos(mensaje)
        return
    if ops.empty:
        mensaje = f"La base «{f_productos.name}» no trae conceptos con la clave {PREFIJO_DIVISAS}… (cambio de divisas)."
        st.info(mensaje)
        _pdf_sin_datos(mensaje)
        return
    fuera_periodo = 0
    if anios:                                                            # ejercicios cerrados de los CFDI cargados: se descarta todo lo de fuera de la ventana
        en_ventana = ops["Fecha_Operacion"].dt.year.isin([int(a) for a in anios])
        fuera_periodo = int((~en_ventana).sum())
        ops = ops[en_ventana].reset_index(drop=True)
        if ops.empty:
            mensaje = f"La base «{f_productos.name}» no trae operaciones de divisas dentro de {min(anios)}–{max(anios)}, el periodo de los CFDI cargados."
            st.info(mensaje)
            _pdf_sin_datos(mensaje)
            return
    volumenes = ops.groupby("Divisa")["Importe_MXN"].sum().reindex(["USD", "EUR"], fill_value=0)
    monedas = ["USD", "EUR"]
    moneda_inicial = int(volumenes["EUR"] > volumenes["USD"])
    fix, fuente, aviso = _obtener_fix(ops, f_fix)
    moneda = st.radio("Moneda", monedas, index=moneda_inicial, horizontal=True, key="div_moneda")
    ops_moneda = ops[ops["Divisa"].eq(moneda)]
    if ops_moneda.empty:
        mensaje = f"No se identificaron operaciones {moneda} en los conceptos 841216. Revisa si la descripción, unidad o moneda del producto indica {moneda}."
        st.info(mensaje)
        _pdf_sin_datos(mensaje)
        return
    d = cruzar_fix(ops_moneda, fix)
    k = kpis_divisas(d)
    hay_fix = k["n_fix"] > 0
    nd = "No disponible"
    st.markdown(_html_kpis_divisas([
        ("Volumen total operado", f"{k['vol_divisa']:,.2f} {moneda}", f"MXN {k['vol_mxn']:,.2f} · {k['n']} operaciones"),
        ("TC promedio facturado", f"{k['tc_facturado']:.4f}", f"MXN por {moneda}: lo que pagó según sus facturas  {PREFIJO_DIVISAS}"),
        ("TC referencia promedio", f"{k['tc_fix']:.4f}" if hay_fix else nd, "Mercado del día de cada operación (Fecha de operación)" if hay_fix else "Sin conexión a la fuente de mercado"),
        ("Spread promedio y sobreprecio total", f"{k['spread_mxn'] * 100:+.2f} ¢ ({k['spread_pct']:+.2f}%)" if hay_fix else nd,
         f"Sobreprecio total: MXN {k['costo_total']:,.2f}" if hay_fix else "Cantidad × (TC facturado − referencia)")]), unsafe_allow_html=True)
    st.divider()
    if anios:
        st.caption(f"Periodo analizado: {min(anios)}–{max(anios)} (ejercicios de los CFDI cargados)"
                   + (f"; {fuera_periodo} operaciones de divisas de otros años quedaron fuera." if fuera_periodo else "."))

    
    if aviso:
        st.warning(f"Referencia de mercado incompleta: {aviso}.")
    if k["n_fix"] < k["n"]:
        st.warning(f"Hay referencia para {k['n_fix']} de {k['n']} operaciones; los cálculos de spread y benchmark solo consideran las que tienen referencia.")

    fig_divisas = fig_tc_fix_vs_facturado(d, fix.get(moneda), moneda, anios)
    st.plotly_chart(fig_divisas, width='stretch', key="div_fig_tc")

    st.markdown("**A) Intermediarios actuales de la empresa**")
    st.markdown(_html_tabla_intermediarios(tabla_intermediarios(d), moneda), unsafe_allow_html=True)
    st.divider()
    st.markdown(f"**B) Comparación de mercados:** ¿con quién conviene operar? Lo que la empresa habría pagado por el mismo volumen de {moneda} y las mismas fechas, sobre la referencia")
    if hay_fix:
        st.markdown(_html_tabla_benchmark(benchmark_mercado(d)), unsafe_allow_html=True)
        st.caption("Spreads de mercado supuestos (pesos por unidad de divisa sobre la referencia): especialistas FX +0.05 a +0.08, banca empresarial preferente +0.12 a +0.15 y ventanilla "
                   "tradicional +0.25 a +0.35. Ahorro neto = lo facturado − lo que habría pagado; negativo si el banco actual fue más barato que ese nivel.")
    else:
        st.info("El benchmark necesita el tipo de cambio de referencia; no se pudo consultar (sin conexión).")
    nota_divisas = st.text_area(
                        f"Insight para la gráfica de Operaciones en Divisas {moneda}",
                        max_chars=600,
                        placeholder="Escribe tus conclusiones (máx. 600 caracteres)...",
                        key="note_divisas"
                    )

    if pdf_elements is not None:
        pdf_elements.append({
            "type": "metrics",
            "title": f"{moneda}",
            "data": [
                ("Volumen total operado", f"{k['vol_divisa']:,.2f} {moneda}", f"MXN {k['vol_mxn']:,.2f} · {k['n']} operaciones"),
                ("TC promedio facturado", f"{k['tc_facturado']:.4f}", f"MXN por {moneda}"),
                ("TC referencia promedio", f"{k['tc_fix']:.4f}" if hay_fix else "No disponible",
                 "Mercado del día de cada operación" if hay_fix else "Sin conexión a la fuente de mercado"),
                ("Spread y sobreprecio total",
                 f"{k['spread_mxn'] * 100:+.2f} ¢ ({k['spread_pct']:+.2f}%)" if hay_fix else "No disponible",
                 f"Sobreprecio total: MXN {k['costo_total']:,.2f}" if hay_fix else "Sin referencia de mercado"),
            ],
        })
        if aviso:
            pdf_elements.append({
                "type": "callout",
                "text": f"<b>Referencia de mercado incompleta:</b> {escape(aviso)}",
            })
        if k["n_fix"] < k["n"]:
            pdf_elements.append({
                "type": "callout",
                "text": f"Hay referencia para {k['n_fix']} de {k['n']} operaciones; los cálculos de spread y benchmark solo consideran las que tienen referencia.",
            })
        pdf_elements.append({
            "type": "image",
            "title": f"Tipo de cambio facturado vs. referencia — {moneda}",
            "fig": fig_divisas
        })
        intermediarios = tabla_intermediarios(d)
        formato_dinero = lambda valor: (
            "n/d" if pd.isna(valor)
            else f"{'-' if valor < 0 else ''}&#36;{abs(valor):,.0f}"
        )
        intermediarios_pdf = pd.DataFrame({
            "Institución (RFC)": intermediarios.apply(
                lambda fila: escape(
                    f"{fila['Institución']} ({fila['RFC']})"
                    if fila["RFC"] else str(fila["Institución"])
                ),
                axis=1,
            ),
            "Operaciones": intermediarios["Operaciones"],
            f"Volumen ({moneda})": intermediarios["Volumen divisa"].map(
                lambda valor: f"{valor:,.0f}"
            ),
            "Volumen (MXN)": intermediarios["Volumen MXN"].map(formato_dinero),
            "Concentración": intermediarios["Concentración %"].map(
                lambda valor: f"{valor:.0f}%"
            ),
            "TC facturado": intermediarios["TC facturado"].map(
                lambda valor: f"{valor:.4f}"
            ),
            "TC referencia": intermediarios["TC referencia"].map(
                lambda valor: "n/d" if pd.isna(valor) else f"{valor:.4f}"
            ),
            "Spread cobrado": intermediarios.apply(
                lambda fila: (
                    "n/d" if pd.isna(fila["Spread MXN"])
                    else f"{fila['Spread MXN'] * 100:+.2f}¢ ({fila['Spread %']:+.2f}%)"
                ),
                axis=1,
            ),
            "Costo sobre referencia": intermediarios["Costo sobre referencia"].map(
                formato_dinero
            ),
        })
        pdf_elements.append({
            "type": "table",
            "title": f"A) Intermediarios actuales de la empresa — {moneda}",
            "df": intermediarios_pdf,
            "column_widths_pct": [23, 15, 11, 13, 16, 12, 12, 10, 13],
        })

        if hay_fix:
            benchmark_pdf = benchmark_mercado(d).copy()
            formato_mxn = lambda valor: f"${abs(valor):,.2f}" if valor >= 0 else f"-${abs(valor):,.2f}"
            benchmark_pdf = pd.DataFrame([
                {
                    "Nivel de mercado": "<b>Lo que le facturaron sus bancos actuales</b>",
                    "Spread sobre referencia": "—",
                    "Monto que habría pagado (MXN)": f"<b>{formato_mxn(benchmark_pdf.attrs['facturado_real'])}</b>",
                    "Ahorro neto (MXN)": "—",
                },
                *[
                    {
                        "Nivel de mercado": escape(str(fila["Nivel"])),
                        "Spread sobre referencia": (
                            f"+${fila['Spread bajo']:.2f} a +${fila['Spread alto']:.2f}"
                        ),
                        "Monto que habría pagado (MXN)": (
                            f"{formato_mxn(fila['Pagaría bajo'])} a {formato_mxn(fila['Pagaría alto'])}"
                        ),
                        "Ahorro neto (MXN)": (
                            f"{formato_mxn(fila['Ahorro máximo'])} a {formato_mxn(fila['Ahorro mínimo'])}"
                        ),
                    }
                    for _, fila in benchmark_pdf.iterrows()
                ],
            ])
            pdf_elements.append({
                "type": "table",
                "title": f"B) Comparación de mercados — {moneda}",
                "df": benchmark_pdf,
                "note":( nota_divisas if nota_divisas and nota_divisas.strip() else ""),
            })
        else:
            pdf_elements.append({
                "type": "callout",
                "text": "El benchmark de mercado no está disponible porque no se obtuvo tipo de cambio de referencia.",
            })