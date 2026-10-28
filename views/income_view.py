# Módulo 2: Auditoría Operativa de Ingresos
'''
Contiene la vista completa de Facturación Emitida e
Ingresos Corporativos (incluyendo su Vista Económica y concentraciones).
'''
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from views.controls import barra_control

from utils import (dinero, _nb, _rango_base100, buscar_columna)
from components.charts import (_grafica_ingresos_gastos, _insight_html,
                               _layout_eco, _fig_facturacion_tiempo,
                               _fig_ingresos_facturados, _fig_pie_metodo_cobro,
                               _html_resumen_metodo_cobro, _fig_bump_anual, render_grafica,
                               render_notas_reporte,_fig_poder_adquisitivo,_fig_eficiencia_operativa)

from core.loader import (anios_5_archivos, _facturas_cache, excluir_años_incompletos,
                         _complementos_cache, _facturas_egresos_cache, cargar_base,
                         preparar_complementos_egresos, _facturacion_anual_cache, _cargar_bases_economicas)

from config import (CODIGO_VERSION, REP_VACIO, VISTAS_MODULO, NOMBRE_FECHA,
                    AYUDA_TOTAL, CSS_VISTA_ECONOMICA, ETIQUETA_SELECTOR_SERIE,
                    MENSAJE_CARGA_ECONOMICA, AYUDA_TOP10_ANUAL)

from core.finance_logic import (resumen_mensual, ncr_por_año, complementos_vigentes,
                                _total_facturado_ppd_vigente, diferencia_ppd,
                                matriz_anual, _preparar_concentracion, _pagos_por_factura,
                                _insight_ingresos_gastos, _anio_base, _rebase, _insight_itaee,
                                _insight_inpp, _insight_tiie, _desglose_cobros, _serie_mensual_por_anio,
                                _resumen_metodo_cobro_global, _resumen_metodo_cobro, facturas_a_mxn,
                                _nomina_ingresos_mensual_mxn)

from components.pdf_generator import generate_modular_pdf


def _figura_ingresos_egresos(periodos: pd.PeriodIndex, ingresos: pd.Series,
                             egresos: pd.Series, ingresos_nomina: pd.Series | None = None,
                             mostrar_diferencia: bool = True,
                             forzar_egresos_negativos: bool = False) -> go.Figure:
    """Crea una serie mensual con ingresos y egresos alrededor de cero y su diferencia."""
    x = [str(periodo) for periodo in periodos]
    egresos_negativos = -egresos.abs() if forzar_egresos_negativos else -egresos
    ingresos_totales = ingresos + ingresos_nomina if ingresos_nomina is not None else ingresos
    diferencia = ingresos_totales - egresos
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=ingresos, name="Ingresos", marker_color="#2563EB",
        hovertemplate="<b>%{x}</b><br>Ingresos: $%{y:,.2f}<extra></extra>",
    ))
    if ingresos_nomina is not None:
        fig.add_trace(go.Bar(
            x=x, y=ingresos_nomina, name="Ingresos por Nómina", marker_color="#F59E0B",
            hovertemplate="<b>%{x}</b><br>Ingresos por Nómina: $%{y:,.2f}<extra></extra>",
        ))
    fig.add_trace(go.Bar(
        x=x, y=egresos_negativos, name="Egresos", marker_color="#60A5FA",
        customdata=egresos,
        hovertemplate="<b>%{x}</b><br>Egresos: $%{customdata:,.2f}<extra></extra>",
    ))
    if mostrar_diferencia:
        fig.add_trace(go.Scatter(
            x=x, y=diferencia, name="Diferencia", mode="lines+markers",
            line=dict(color="#F97316", width=3), marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>Diferencia: $%{y:,.2f}<extra></extra>",
        ))
    fig.add_hline(y=0, line_width=1, line_color="#9CA3AF")
    fig.update_layout(
        barmode="relative", height=380,
        margin=dict(l=90, r=20, t=55, b=55),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title=None, yaxis_title="MXN",
    )
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, tickangle=-45)
    fig.update_yaxes(tickformat=",.0f", zeroline=False, gridcolor="rgba(128,128,128,0.18)")
    return fig


def _bloque_neta_y_flujo_ingresos(fac_ing: pd.DataFrame, rep_ing: pd.DataFrame,
                                   f_fac_egr, f_pago_egr, f_pago_ing, f_nomina,
                                   anios_5, ejercicios, pdf_elements: list) -> None:
    """Muestra facturación devengada y flujo fiscal mensual de ingresos frente a egresos."""
    st.divider()
    st.subheader(
        "Facturación Neta y Flujo Fiscal",
        help=("Facturación Neta: facturas emitidas menos NCR y facturas recibidas menos NCR, por fecha de emisión. "
              "Flujo Fiscal: facturas PUE por fecha de emisión más complementos y nómina por fecha de pago; "
              "excluye NCR y operaciones de divisas de los egresos. En ambas, la línea es ingresos menos egresos."),
    )
    if f_fac_egr is None:
        st.info("Para mostrar la Facturación Neta Mensual falta la Facturación Recibida.")
        return

    try:
        fac_egr, _ = _facturas_egresos_cache(
            f_fac_egr.name, f_fac_egr.getvalue(), CODIGO_VERSION)
        fac_egr, _ = excluir_años_incompletos(fac_egr, "Fecha", "Facturación recibida", anios_5)
    except KeyError as e:
        st.info(f"Información insuficiente en la Facturación Recibida: {e.args[0]}")
        return

    fac_egr = fac_egr[fac_egr["Fecha"].dt.year.isin(ejercicios)]
    rfc_divisas = fac_egr["RFC_Emisor"].fillna("").astype(str).str.strip().str.upper().eq("BMI9704113PA")
    n_divisas = int(rfc_divisas.sum())
    if n_divisas:
        st.info(f"{n_divisas} factura(s) recibida(s) del RFC BMI9704113PA se excluyeron de ambas gráficas.")
        fac_egr = fac_egr[~rfc_divisas]
    fac_egr, n_sin_tc = facturas_a_mxn(fac_egr)
    if n_sin_tc:
        st.warning(f"{n_sin_tc} factura(s) recibida(s) sin Tipo de Cambio válido se excluyeron de las gráficas.")

    anios = sorted(int(anio) for anio in ejercicios)
    periodos = pd.PeriodIndex(
        [pd.Period(f"{anio}-{mes:02d}", freq="M") for anio in anios for mes in range(1, 13)],
        freq="M",
    )

    def sumar_por_mes(df: pd.DataFrame, fecha: str, monto: str) -> pd.Series:
        fechas = df[fecha]
        periodos_df = fechas if isinstance(fechas.dtype, pd.PeriodDtype) else fechas.dt.to_period("M")
        serie = df.assign(_Periodo=periodos_df).groupby("_Periodo")[monto].sum()
        return serie.reindex(periodos, fill_value=0.0).astype(float)

    facturas_ing = fac_ing[~fac_ing["Es_NCR"]]
    facturas_egr = fac_egr[~fac_egr["Es_NCR"]]
    ncr_ing = sumar_por_mes(fac_ing[fac_ing["Es_NCR"]].assign(Total=lambda d: d["Total"].abs()), "Fecha", "Total")
    ncr_egr = sumar_por_mes(fac_egr[fac_egr["Es_NCR"]].assign(Total=lambda d: d["Total"].abs()), "Fecha", "Total")
    ingresos_devengados = sumar_por_mes(facturas_ing, "Fecha", "Total") - ncr_ing
    egresos_devengados = sumar_por_mes(facturas_egr, "Fecha", "Total") - ncr_egr
    fig_neta = _figura_ingresos_egresos(
        periodos, ingresos_devengados, egresos_devengados, forzar_egresos_negativos=True)
    st.markdown("**Facturación Neta Mensual**")
    render_grafica(fig_neta, key="ing_fig_neta", incluir_notas=False, width="stretch")
    pdf_elements.append({
        "type": "image",
        "section_title": "5. Facturación Neta y Flujo Fiscal",
        "title": "Facturación Neta Mensual",
        "fig": fig_neta,
        "custom_height": 270,
    })

    ingresos_pue = sumar_por_mes(
        facturas_ing[facturas_ing["Metodo_Pago"].eq("PUE")], "Fecha", "Total")
    egresos_pue = sumar_por_mes(
        facturas_egr[facturas_egr["Metodo_Pago"].eq("PUE")], "Fecha", "Total")
    ingresos_complementos = (sumar_por_mes(rep_ing, "Fecha_Cobro", "Cobro_Efectivo")
                             if f_pago_ing is not None else None)

    pagos_egr = None
    if f_pago_egr is not None:
        base_pago_egr = cargar_base(f_pago_egr)
        col_monto = buscar_columna(base_pago_egr.columns, "Monto MXN")
        col_fecha = buscar_columna(base_pago_egr.columns, "Fecha Pago")
        if col_monto is None or col_fecha is None:
            st.info("Los pagos de Egresos requieren las columnas 'Monto MXN' y 'Fecha Pago'; se excluyen del flujo parcial.")
        else:
            col_estatus = buscar_columna(base_pago_egr.columns, "Estatus")
            if col_estatus is not None:
                base_pago_egr = base_pago_egr[
                    base_pago_egr[col_estatus].astype(str).str.strip().str.upper().isin(["ACTIVO", "VIGENTE"])
                ]
            pagos_egr = preparar_complementos_egresos(base_pago_egr, col_monto, col_fecha)
            pagos_egr = pagos_egr[pagos_egr["Año"].isin(ejercicios)]
    ingresos_complementos_egr = (sumar_por_mes(pagos_egr, "Mes", "Monto_Num")
                                 if pagos_egr is not None else None)

    ingresos_nomina = None
    if f_nomina is not None:
        ingresos_nomina, _ = _nomina_ingresos_mensual_mxn(cargar_base(f_nomina))
    if ingresos_nomina is not None:
        ingresos_nomina = ingresos_nomina.reindex(periodos, fill_value=0.0).astype(float)

    flujo_completo = (
        ingresos_complementos is not None
        and ingresos_complementos_egr is not None
        and ingresos_nomina is not None
    )
    ingresos_flujo = ingresos_pue + (ingresos_complementos if ingresos_complementos is not None else 0.0)
    egresos_flujo = egresos_pue + (
        ingresos_complementos_egr if ingresos_complementos_egr is not None else 0.0)
    faltan_flujo = []
    if ingresos_complementos is None:
        faltan_flujo.append("Complementos de Pago de Ingresos")
    if ingresos_complementos_egr is None:
        faltan_flujo.append("Complementos de Pago de Egresos")
    if ingresos_nomina is None:
        faltan_flujo.append("nómina de ingresos con Fecha de Certificación")
    if not flujo_completo:
        st.warning(
            "Flujo parcial: la gráfica muestra PUE y los componentes disponibles. "
            "No incluye " + " y ".join(faltan_flujo) +
            "; la diferencia representa solo los componentes disponibles."
        )
    st.markdown("**Flujo Fiscal Mensual**" if flujo_completo else "**Flujo Fiscal**")
    fig_flujo = _figura_ingresos_egresos(
        periodos, ingresos_flujo, egresos_flujo,
        mostrar_diferencia=True)
    render_grafica(fig_flujo, key="ing_fig_flujo", incluir_notas=False, width="stretch")
    pdf_elements.append({
        "type": "image",
        "title": ("Flujo Fiscal Mensual" if flujo_completo
                  else "Flujo Identificado Mensual; componentes faltantes no disponibles"),
        "fig": fig_flujo,
        "custom_height": 270,
    })


def _limpiar_y_formatear(val, prefijo="", sufijo=""):
    """Función auxiliar para formatear valores numéricos a moneda/porcentaje de forma segura."""
    if pd.isnull(val):
        return val
    try:
        num = float(val)
        return f"{prefijo}{num:,.2f}{sufijo}"
    except (ValueError, TypeError):
        return val


def modulo_ingresos(file_ingresos_facturas, file_ingresos_pago, anios_5=None,
                    file_egresos_facturas=None, file_egresos_pago=None, file_nomina=None) -> None:
    st.title("Facturación Emitida e Ingresos Corporativos")

    if file_ingresos_facturas is None:
        st.info("Falta el archivo de Facturación Emitida")
        st.stop()
    if anios_5 is None:
        anios_5 = anios_5_archivos(file_ingresos_facturas, None)

    errores: list[str] = []
    facturas = None
    avisos_f: list[str] = []
    avisos_c: list[str] = []
    try:
        facturas, avisos_f = _facturas_cache(file_ingresos_facturas.name, file_ingresos_facturas.getvalue(),
                                             CODIGO_VERSION)
        facturas, av_años = excluir_años_incompletos(facturas, "Fecha", "Facturas", anios_5)
        avisos_f = avisos_f + av_años
    except KeyError as e:
        errores.append(f"'{file_ingresos_facturas.name}' no tiene el formato esperado de facturación emitida. "
                       f"{e.args[0]}")

    rep_total = REP_VACIO.copy()
    if file_ingresos_pago is not None:
        try:
            rep_total, av = _complementos_cache(file_ingresos_pago.name, file_ingresos_pago.getvalue(), CODIGO_VERSION)
            rep_total, av_años = excluir_años_incompletos(rep_total, "Fecha_Cobro", "Complementos de pago", anios_5)
            avisos_c += av + av_años
        except KeyError as e:
            errores.append(f"'{file_ingresos_pago.name}' no tiene el formato esperado de complementos de pago. {e.args[0]}")

    if errores:
        for msg in errores:
            st.error(msg)
        return
    if facturas.empty:
        st.warning("No quedaron facturas tras aplicar los filtros (Estatus 'Activo', Tipo 'Factura' y la "
                   f"ventana de análisis {anios_5[0] if anios_5 else ''}–{anios_5[-1] if anios_5 else ''}).")
        return

    rfc_empresa = facturas["RFC_Emisor"].iloc[0]
    nombre_empresa = facturas["Nombre_Emisor"].iloc[0]
    st.markdown(f"### Empresa en Análisis: **{nombre_empresa}** ({rfc_empresa})")

    vista_modulo = st.radio("Vista", VISTAS_MODULO, horizontal=True, key="ing_vista_modulo", label_visibility="collapsed")
    econ = vista_modulo == "Vista Económica"
    ejercicios = barra_control([int(a) for a in anios_5])

    if not ejercicios:
        st.warning("Selecciona al menos un ejercicio fiscal en la barra de filtros.")
        return
    complementos_disponibles = file_ingresos_pago is not None
    if not complementos_disponibles:
        st.warning(
            "Análisis parcial: falta la base de Complementos de Clientes (PAGO - Flujo Efectivo). "
            "La facturación se mostrará, pero no se pueden determinar los cobros PPD, el saldo por cobrar "
            "ni el flujo de efectivo; esos datos aparecerán como no disponibles, no como cero."
        )

    fac = facturas[facturas["Fecha"].dt.year.isin(ejercicios)]
    rep = rep_total[rep_total["Fecha_Cobro"].dt.year.isin(ejercicios)]
    if len(rep_total) - len(rep):
        avisos_c = avisos_c + [
            f"Complementos (Flujo de Efectivo): {len(rep_total) - len(rep)} filas "
            f"(${rep_total['Cobro_Efectivo'].sum() - rep['Cobro_Efectivo'].sum():,.2f}) con {NOMBRE_FECHA} "
            f"fuera de los ejercicios seleccionados excluidas."]
    if fac.empty:
        st.warning("No hay facturas para los ejercicios seleccionados.")
        return

    nomina_ingresos_total = None
    nomina_ingresos_por_anio = None
    nomina_ingresos = None
    if file_nomina is not None:
        nomina_ingresos, motivo_nomina = _nomina_ingresos_mensual_mxn(cargar_base(file_nomina))
        if motivo_nomina or nomina_ingresos is None:
            st.info(f"La nómina no se sumó como ingreso: {motivo_nomina or 'no se generó una serie mensual válida'}.")
        else:
            nomina_ingresos = nomina_ingresos[nomina_ingresos.index.year.isin(ejercicios)]
            nomina_ingresos_total = float(nomina_ingresos.sum())
            nomina_ingresos_por_anio = nomina_ingresos.groupby(nomina_ingresos.index.year).sum()

    res = resumen_mensual(fac, rep, ejercicios)
    if abs(res["Cobrado_PPD"].sum() - rep["Cobro_Efectivo"].sum()) > 0.01:
        st.error("El resumen mensual no cuadra con el total de cobros filtrado; revisa el registro de limpieza.")

    df_facturas = fac[~fac["Es_NCR"]]
    df_ncr = fac[fac["Es_NCR"]]
    ncr_anual = ncr_por_año(fac)
    n_facturas = df_facturas["UUID"].nunique()
    n_reps = rep["UUID"].nunique()
    fact_total = df_facturas["Total"].sum()
    fact_pue = df_facturas.loc[df_facturas["Metodo_Pago"] == "PUE", "Total"].sum()
    fact_ppd = df_facturas.loc[df_facturas["Metodo_Pago"] == "PPD", "Total"].sum()
    cobr_ppd = complementos_vigentes(rep)
    cobr_total = fact_pue + cobr_ppd if complementos_disponibles else None
    ncr_total = ncr_anual["NCR_Total"].sum()
    ingreso_neto = cobr_total - ncr_total if cobr_total is not None else None

    if complementos_disponibles:
        try:
            total_ppd_facturado = _total_facturado_ppd_vigente(cargar_base(file_ingresos_facturas))
            total_cobrado_rep = complementos_vigentes(rep_total)
            saldo_ppd_macro = dinero(diferencia_ppd(total_ppd_facturado, total_cobrado_rep))
        except KeyError:
            saldo_ppd_macro = "n/a"
    else:
        saldo_ppd_macro = "n/d"

    pdf_elements = []

    if not econ:
        # Fila 1 - Ingresos / facturación
        with st.container(key="ing_kpis_facturacion_pdf"):
            k = st.columns(3)
            k[0].metric("**Facturación Emitida Total**", dinero(fact_total), f"{n_facturas} facturas emitidas",
                        delta_color="off", delta_arrow="off", help=AYUDA_TOTAL)
            k[1].metric("Facturación PUE", dinero(fact_pue), f"{fact_pue / fact_total:.1%} del total",
                        delta_color="off", delta_arrow="off", help=AYUDA_TOTAL)
            k[2].metric("Facturación PPD", dinero(fact_ppd), f"{fact_ppd / fact_total:.1%} del total",
                        delta_color="off", delta_arrow="off", help=AYUDA_TOTAL)
        # Fila 2 - Cobranza y saldos
        with st.container(key="ing_kpis_cobranza_pdf"):
            k = st.columns(4)
            k[0].metric("Cobrado Total (PUE + Complementos)", dinero(cobr_total) if cobr_total is not None else "n/d",
                        f"{cobr_total / fact_total:.1%} de lo facturado" if cobr_total is not None and fact_total else "PUE conocido; PPD no disponible",
                        delta_color="off", delta_arrow="off",
                        help="PUE (cobrado al facturar) más el Cobro Efectivo de los Complementos de Pago Emitidos (por su fecha de pago).")
            k[1].metric("Complementos de Pago Emitidos", dinero(cobr_ppd) if complementos_disponibles else "n/d",
                        f"{n_reps} complementos de pago" if complementos_disponibles else "Base PAGO no disponible",
                        delta_color="off", delta_arrow="off",
                        help=f"Cobro Efectivo (Saldo Inicial - Saldo Final) de los Complementos de Pago Emitidos cuya {NOMBRE_FECHA} "
                             f"cae en los ejercicios seleccionados. Se cuentan complementos únicos (UUID): un complemento puede pagar "
                             f"varias facturas.")
            k[2].metric("Saldo PPD por Cobrar", saldo_ppd_macro,
                        help="Macro-cálculo: Total Facturado menos el Total Cobrado vía Complementos de Pago Emitidos.")
            k[3].metric("% Cobranza PPD",
                        f"{cobr_ppd / fact_ppd:.1%}" if complementos_disponibles and fact_ppd
                        else "n/a" if complementos_disponibles else "n/d",
                        help="Complementos de Pago Emitidos entre Facturación PPD.")

        # Fila 3 - Cierre
        with st.container(key="ing_kpis_cierre_pdf"):
            k = st.columns(2)
            k[0].metric("Notas de Crédito", dinero(ncr_total), f"{df_ncr['UUID'].nunique()} Notas de Crédito",
                        delta_color="off", delta_arrow="off",
                        help="Suma del Total de las Notas de Crédito emitidas.")
            k[1].metric("Ingreso Neto", dinero(ingreso_neto) if ingreso_neto is not None else "n/d", delta_color="off", delta_arrow="off",
                        help="Ingreso Neto = Cobrado Total (PUE + Complementos) - Notas de Crédito.")
        # Métricas para el PDF Financiero
        metrics_kpis = [
            ("Facturación Emitida Total", dinero(fact_total), f"{n_facturas} facturas"),
            ("Facturacion PUE", dinero(fact_pue), f"{fact_pue / fact_total:.1%} del total" if fact_total else "0%"),
            ("Facturación PPD", dinero(fact_ppd), f"{fact_ppd / fact_total:.1%} del total" if fact_total else "0%"),
            ("Cobrado Total", dinero(cobr_total) if cobr_total is not None else "n/d",
             f"{cobr_total / fact_total:.1%} lo facturado" if cobr_total is not None and fact_total else "PUE conocido; PPD no disponible"),
            ("Complementos de Pago Emitidos", dinero(cobr_ppd) if complementos_disponibles else "n/d",
             f"{n_reps} complementos" if complementos_disponibles else "Base PAGO no disponible"),
            ("Saldo PPD por Cobrar", saldo_ppd_macro, "Total Facturado menos Total Cobrado" if complementos_disponibles else "No disponible sin la base PAGO"),
            ("% Cobranza PPD",
             f"{cobr_ppd / fact_ppd:.1%}" if complementos_disponibles and fact_ppd
             else "n/a" if complementos_disponibles else "n/d",
             "Complementos de Pago Emitidos entre Facturación PPD"),
            ("Notas de Crédito", dinero(ncr_total), f"{df_ncr['UUID'].nunique()} Notas de Crédito"),
            ("Ingreso Neto", dinero(ingreso_neto) if ingreso_neto is not None else "n/d",
             "Cobrado menos Notas de Crédito" if ingreso_neto is not None else "No disponible sin la base PAGO"),
            ("Ingresos por Nómina",
             dinero(nomina_ingresos_total) if nomina_ingresos_total is not None else "n/d",
             "Total vigente por Fecha de Certificación; separado de la facturación")
        ]
        # 2. Las dividimos automáticamente en bloques de 3 en 3 para que salgan filas perfectas
        for i in range(0, len(metrics_kpis), 3):
            bloque_tres = metrics_kpis[i:i+3]
            titulo_bloque = "Resumen General de Facturación e Ingresos" if i == 0 else ""
            
            pdf_elements.append({
                "type": "metrics", 
                "title": titulo_bloque, 
                "data": bloque_tres
            })

    with st.container(key="ing_kpis_nomina_pdf"):
        st.metric(
            "Ingresos por Nómina",
            dinero(nomina_ingresos_total) if nomina_ingresos_total is not None else "n/d",
            help=("Suma del Total de comprobantes de nómina Vigente/Activo por Fecha de Certificación, "
                  "en los ejercicios seleccionados; se presenta separado de la facturación.")
        )

    matriz = matriz_anual(res, ncr_anual)
    if nomina_ingresos_por_anio is None:
        matriz["Ingresos por Nómina"] = np.nan
    else:
        matriz["Ingresos por Nómina"] = [
            nomina_ingresos_por_anio.get(int(anio), 0.0) for anio in matriz.index
        ]
    if not complementos_disponibles:
        columnas_sin_pagos = [
            "Complementos de Pago Emitidos", "Cobrado Total (PUE + Complementos)",
            "Ingreso Neto", "Ingreso por Cobrar", "% Cobranza PPD",
        ]
        matriz[columnas_sin_pagos] = np.nan
    texto = matriz.apply(lambda col: col.map(
        lambda v: "n/a" if pd.isna(v) else (f"{v / 100:.1%}" if col.name.startswith("%") else f"${v:,.2f}")))
    try:
        columna_texto = st.column_config.TextColumn(alignment="right")
    except TypeError:
        columna_texto = st.column_config.TextColumn()
    tabla = texto.T.rename_axis(index="Concepto").reset_index()

    def _mostrar_desglose():
        with st.container(key="ing_desglose_anual_pdf"):
            st.markdown("**Desglose año con año**")
            st.dataframe(tabla, hide_index=True, key="ing_desglose_anual",
                         column_config={año: columna_texto for año in texto.index})

    # Copia limpia y formateada del desglose para el PDF
    tabla_pdf = tabla.copy()
    for col in tabla_pdf.columns:
        if col != "Concepto":
            tabla_pdf[col] = tabla_pdf[col].apply(_limpiar_y_formatear)

    st.divider()
    if econ:
        _mostrar_desglose()
        pdf_elements.append({"type": "heading", "text": "1. Evolución de Ingresos y Egresos"})
        pdf_elements.append({"type": "table", "title": "Desglose Año con Año Ingresos", "df": tabla_pdf})
        st.divider()
        _vista_economica("ingresos", file_ingresos_facturas, file_egresos_facturas, ejercicios, anios_5, pdf_elements)
        return

    _bloque_concentracion(
        _preparar_concentracion(df_facturas, "Nombre_Receptor" if "Nombre_Receptor" in df_facturas.columns else None,
                                "RFC_Receptor" if "RFC_Receptor" in df_facturas.columns else None),
        etiqueta="Clientes",
        pagos_agrupados=(_pagos_por_factura(cargar_base(file_ingresos_pago))
                         if complementos_disponibles else None),
        complementos_periodo=cobr_ppd if complementos_disponibles else None,
        desglose=_mostrar_desglose, tabla_pdf=tabla_pdf, pdf_elements=pdf_elements,
        nomina_mensual=nomina_ingresos
    )
    _bloque_neta_y_flujo_ingresos(
        fac, rep, file_egresos_facturas, file_egresos_pago, file_ingresos_pago,
        file_nomina, anios_5, ejercicios, pdf_elements)

    st.divider()
    st.subheader("Exportación de Reporte - Vista Financiera")
    col_pdf_desc, _ = st.columns([1, 2])

    with col_pdf_desc:
        st.write("Genera un PDF con las gráficas, conclusiones, tablas y desglose de este módulo.")
        if st.button("Generar PDF Vista Financiera", key="btn_generar_pdf_fin"):
            with st.spinner("Generando reporte financiero en PDF..."):
                final_elements = [
                    {"type": "heading", "text": "Observaciones del Analista"},
                    {"type": "callout"},
                    *pdf_elements,
                ]
                pdf_bytes = generate_modular_pdf(
                    title="Reporte de Auditoría de Ingresos — Vista Financiera",
                    subtitle="Análisis de Facturación Emitida, Cobranza y Concentración",
                    elements=final_elements
                )
                st.download_button(
                    label="Descargar PDF Financiero",
                    data=pdf_bytes,
                    file_name="Reporte_Ingresos_Vista_Financiera.pdf",
                    mime="application/pdf",
                    key="btn_download_pdf_fin"
                )


def _vista_economica(lado: str, f_ingresos_fac, f_egresos_fac, ejercicios, anios_5, pdf_elements: list,
                     egresos_facturas: pd.DataFrame | None = None) -> None:
    st.markdown(CSS_VISTA_ECONOMICA, unsafe_allow_html=True)
    if f_ingresos_fac is None or f_egresos_fac is None:
        st.info("La Vista Económica compara Ingresos contra Gastos: carga también la Facturación "
                f"{'Recibida' if f_egresos_fac is None else 'Emitida'} en la zona de carga.")
        return
    anios = sorted(int(a) for a in ejercicios)
    anios_str = [str(a) for a in anios]
    ing_d = _facturacion_anual_cache(_nb(f_ingresos_fac), "ingresos", anios_5, CODIGO_VERSION)
    if lado == "egresos" and egresos_facturas is not None:
        facturas_gastos = egresos_facturas[~egresos_facturas["Es_NCR"]]
        totales_gastos = facturas_gastos.groupby(facturas_gastos["Fecha"].dt.year)["Total"].sum()
        gas_d = {
            int(anio): float(monto)
            for anio, monto in totales_gastos.reindex([int(a) for a in anios_5], fill_value=0.0).items()
        }
    else:
        gas_d = _facturacion_anual_cache(_nb(f_egresos_fac), "egresos", anios_5, CODIGO_VERSION)
    for d in (ing_d, gas_d):
        if "motivo" in d:
            st.info(f"Información insuficiente: {d['motivo']}")
            return
    ing, gas = [ing_d.get(a, 0.0) / 1e6 for a in anios], [gas_d.get(a, 0.0) / 1e6 for a in anios]
    ext = _cargar_bases_economicas(lado)
    ingresos = lado == "ingresos"

    def tarjeta_serie(clave, etiqueta_extra="", sufijo_key=""):
        series = ext.get(clave)
        if not series:
            return None, None
        nombre = st.selectbox(ETIQUETA_SELECTOR_SERIE + etiqueta_extra, list(series), key=f"eco_sel_{lado}_{clave}{sufijo_key}")
        return nombre, series[nombre]

    fila1 = st.columns(2)
    with fila1[0], st.container(border=True):
        st.markdown("**Ingresos vs Gastos Anuales (Millones MXN)**")
        fig_ing_gas = _grafica_ingresos_gastos(anios_str, ing, gas)
        render_grafica(fig_ing_gas, key=f"eco_{lado}_ingresos_gastos")
        # _insight_html(_insight_ingresos_gastos(anios, ing, gas))
        
        nota_ing_gas = st.text_area("Insight - Ingresos vs Gastos Anuales", max_chars=600, key="note_eco_ing_gas")
        pdf_elements.append({
            "type": "image",
            "title": "Ingresos vs Gastos Anuales (Millones MXN)",
            "fig": fig_ing_gas,
            "note": nota_ing_gas
        })

    with fila1[1], st.container(border=True):
        clave, empresa, color_barra, nombre_barra = (("itaee", ing, "#2563EB", "Ingresos (Base 100)") if ingresos
                                                     else ("inpp", gas, "#991B1B", "Gastos Operativos (Base 100)"))
        titulo_ref = "ITAEE" if ingresos else "INPP"
        sector, serie = tarjeta_serie(clave)
        base = _anio_base(anios, empresa, serie) if serie else None
        if serie is None:
            st.markdown(f"**{'Ingresos' if ingresos else 'Gastos'} vs {titulo_ref} (Base 100 = Año Base)**")
            st.info(MENSAJE_CARGA_ECONOMICA)
        elif base is None or len(anios) < 2:
            st.markdown(f"**{'Ingresos' if ingresos else 'Gastos'} vs {titulo_ref} (Base 100 = Año Base)**")
            st.info("Selecciona dos o más ejercicios que existan en la base cargada para calcular el índice Base 100.")
        else:
            st.markdown(f"**{'Ingresos' if ingresos else 'Gastos'} vs {titulo_ref} (Base 100 = {base})**")
            idx_emp = [(v / empresa[anios.index(base)] * 100) if a >= base else float("nan") for a, v in zip(anios, empresa)]
            idx_ext = [v if a >= base else float("nan") for a, v in zip(anios, _rebase(serie, anios, base))]
            fig_base100 = go.Figure()
            fig_base100.add_trace(go.Bar(x=anios_str, y=idx_emp, name=nombre_barra, marker_color=color_barra, texttemplate="%{y:.1f}",
                                         textposition="outside", cliponaxis=False,
                                         hovertemplate=f"<b>%{{x}}</b><br>{nombre_barra}: %{{y:.1f}}<extra></extra>"))
            if ingresos:
                fig_base100.add_trace(go.Scatter(
                        x=anios_str, 
                        y=idx_ext, 
                        name="ITAEE (Índice Referencia)", 
                        
                        # 1. Añadimos "+text" al mode
                        mode="lines+markers+text", 
                        
                        line=dict(color="#10B981", dash="dot", width=3), 
                        marker=dict(size=9, color="#10B981"),
                        connectgaps=True, 
                        
                        # 2. Definimos el texto a mostrar en cada punto (con 1 decimal, omitiendo nulos)
                        text=[f"{y:.1f}" if y is not None else "" for y in idx_ext],
                        
                        # 3. Posición del texto respecto al marcador (ej. "top center" para que aparezca arriba del punto)
                        textposition="bottom center",
                        textfont=dict(size=11),
                        cliponaxis=False, # Evita que los números muy altos se corten en el borde superior de la gráfica
                        
                        hovertemplate="<b>%{x}</b><br>ITAEE (Base 100): %{y:.1f}<extra></extra>"
                    ))
            else:
                fig_base100.add_trace(go.Scatter(
                        x=anios_str,
                        y=idx_ext,
                        name="INPP (Inflación Productor)", 
                                                    
                        mode="lines+markers+text",                             
                        line=dict(color="#FACC15", width=3),
                        marker=dict(size=9, color="#FACC15"),
                        connectgaps=False,
                        # 2. Definimos el texto a mostrar en cada punto (con 1 decimal, omitiendo nulos)
                        text=[f"{y:.1f}" if y is not None else "" for y in idx_ext],
                                                
                        # 3. Posición del texto respecto al marcador (ej. "top center" para que aparezca arriba del punto)
                        textposition="bottom center",
                        textfont=dict(size=11),
                        cliponaxis=False, # Evita que los números muy altos se corten en el borde superior de la gráfica
                                                          
                        hovertemplate="<b>%{x}</b><br>INPP (Base 100): %{y:.1f}<extra></extra>"))
            
            fig_base100 = _layout_eco(fig_base100, anios_str, "Índice (Base 100)")
            fig_base100.update_yaxes(range=_rango_base100(idx_emp, idx_ext))
            render_grafica(fig_base100, key=f"eco_{lado}_base_100")
            # _insight_html((_insight_itaee if ingresos else _insight_inpp)(anios, idx_emp, idx_ext, sector, base))
            if not ingresos:
                nota_base100 = st.text_area(f"Insight - Egresos vs {titulo_ref}", max_chars=600, key="note_eco_base100")
                pdf_elements.append({
                                "type": "image",
                                "section_title": f"3. Egresos vs INPP",
                                "title": f"Egresos vs {titulo_ref} (Base 100 = {base}, Sector: {sector})",
                                "fig": fig_base100,
                                "note": nota_base100
                                
                            })
                
            else:
                nota_base100 = st.text_area(f"Insight - Ingresos vs {titulo_ref}", max_chars=600, key="note_eco_base100")

                pdf_elements.append({
                    "type": "image",
                    "section_title": f"3.Ingresos vs ITAEE",
                    "title": f"Ingresos vs {titulo_ref} (Base 100 = {base}, Sector: {sector})",
                    "fig": fig_base100,
                    "note": nota_base100
                    
                })
     
    if not ingresos and serie is not None and base is not None and len(anios) >= 2:
        fig_ing = _fig_poder_adquisitivo(anios_str, ing, gas)
        st.markdown("Poder Adquisitivo: Ingresos vs Inflación General (INPC)")
        render_grafica(fig_ing, key="exec_poder_adquisitivo")

        nota_poder_adq = st.text_area("Insight - Poder Adquisitivo", max_chars=600, key="note_poder_adq")
        pdf_elements.append({
            "type": "image",
            "section_title": "4. Comportamiento de Ingresos en el Entorno",
            "title": "Poder Adquisitivo: Ingresos vs Inflación General",
            "fig": fig_ing,
            "note": nota_poder_adq if nota_poder_adq and nota_poder_adq.strip() else ""
        })
   
    # ---------------------------------------------------------------
    # SECCIÓN DE DESCARGA PDF - VISTA ECONÓMICA
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("Exportación de Reporte - Vista Económica")
    
    col_pdf_desc, col_pdf_info = st.columns([1, 2])
    with col_pdf_info:
        econ_notes = st.text_area(
            "Notas / Observaciones Generales de la Vista Económica:",
            placeholder="Escribe tus conclusiones económicas ejecutivas aquí...",
            key="eco_notes_general"
        )
    with col_pdf_desc:
        st.write("Genera un PDF con las gráficas de contexto macroeconómico e indicadores.")
        if st.button("Generar PDF Vista Económica", key=f"btn_generar_pdf_eco_{lado}"):
            with st.spinner("Generando reporte económico en PDF..."):
                final_elements = []
                if econ_notes.strip():
                    final_elements.append({"type": "heading", "text": "Observaciones Económicas"})
                    final_elements.append({"type": "callout", "text": econ_notes})
                final_elements.extend(pdf_elements)

                titulo_pdf = ("Reporte de Auditoría de Ingresos — Vista Económica" if ingresos
                              else "Reporte de Egresos — Vista Económica")
                subtitulo_pdf = ("Contexto Macroeconómico e Indicadores de Sector" if ingresos
                                 else "Vista Económica y Evolución Anual")
                nombre_archivo_pdf = ("Reporte_Ingresos_Vista_Economica.pdf" if ingresos
                                      else "Reporte_Egresos_Vista_Economica.pdf")
                etiqueta_descarga = ("Descargar PDF Económico" if ingresos
                                     else "Descargar Reporte PDF (Vista Económica)")
                pdf_bytes = generate_modular_pdf(
                    title=titulo_pdf,
                    subtitle=subtitulo_pdf,
                    elements=final_elements
                )
                st.download_button(
                    label=etiqueta_descarga,
                    data=pdf_bytes,
                    file_name=nombre_archivo_pdf,
                    mime="application/pdf",
                    key=f"btn_download_pdf_eco_{lado}"
                )


def _bloque_concentracion(df: pd.DataFrame, etiqueta: str = "Clientes", pagos_agrupados: pd.DataFrame | None = None,
                          complementos_periodo: float | None = None, desglose=None, tabla_pdf=None,
                          pdf_elements=None, nomina_mensual: pd.Series | None = None) -> None:
    col_monto = "Total"
    if desglose is not None:
        
        desglose()
        if tabla_pdf is not None and pdf_elements is not None:
            pdf_elements.append({
                "type": "table",
                "section_title": "1. Facturación PPD y Complementos: Diferencias Anuales",
                "title": "Desglose Año con Año Ingresos",
                "df": tabla_pdf
            })

    if df.empty or float(df[col_monto].sum()) <= 0:
        st.subheader("Concentración y Riesgo de Dependencia")
        st.info("Sin facturación en los ejercicios seleccionados para graficar la concentración.")
        return

    if pagos_agrupados is not None:
        d, dif = _desglose_cobros(df, pagos_agrupados, col_monto)
        if abs(dif) > 0.005:
            st.error(f"El desglose PUE / PPD cobrado / PPD pendiente no cuadra con el total de {col_monto}; revisa los datos.")
        st.divider()
        st.markdown("**Facturación emitida en el tiempo**")
        fig_tiempo = _fig_facturacion_tiempo(d, col_monto)
        render_grafica(fig_tiempo, key="ing_facturacion_tiempo")
        # nota_tiempo = st.text_area("Conclusión - Facturación Emitida en el Tiempo", max_chars=600, key="note_ing_tiempo")
        
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                # "section_title": "2. Comportamiento de la Facturación e Ingresos",
                "title": "Ingresos en el Tiempo",
                "fig": fig_tiempo,
                "custom_height": 250
                # "note": nota_tiempo
            })
        st.divider()
        st.markdown("**Ingresos facturados**")
        fig_ing_fact = _fig_ingresos_facturados(d, col_monto, nomina_mensual=nomina_mensual)
        render_grafica(fig_ing_fact, key="ingresos_facturados")
        # nota_ing_fact = st.text_area("Conclusión - Ingresos Facturados", max_chars=600, key="note_ing_fact")
        
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "title": "Ingresos Facturados por Mes",
                "fig": fig_ing_fact,
                "custom_height": 270
            })

        st.divider()
        resumen = (_resumen_metodo_cobro_global(d, complementos_periodo) if complementos_periodo is not None else _resumen_metodo_cobro(d, col_monto))
        
        st.markdown("**Método de cobro**")
        c_pie, c_tabla = st.columns([1, 1], gap="medium")
        fig_pie = _fig_pie_metodo_cobro(resumen)
        with c_pie:
            render_grafica(fig_pie, key="ing_metodo_cobro", incluir_notas=False)
        with c_tabla:
            st.markdown(_html_resumen_metodo_cobro(resumen, col_monto, rotular_base=False), unsafe_allow_html=True)
        
        # nota_metodo = st.text_area("Conclusión - Método de Cobro", max_chars=600, key="note_ing_metodo")
        
        if pdf_elements is not None:
            # 1. Agregamos la gráfica de dona al PDF
            pdf_elements.append({
                "type": "image",
                "section_title": "3. Estructura y Método de Cobro",
                "title": "Distribución por Método de Cobro",
                "fig": fig_pie,
                "preserve_textfont_size": True,
              
            })
            
            # 2. Extraemos los valores de forma segura directamente de 'resumen' (diccionario o serie)
            try:
                # Convertimos 'resumen' a diccionario estándar si es de tipo dict o Series de Pandas
                if hasattr(resumen, "to_dict"):
                    dic_resumen = resumen.to_dict()
                elif isinstance(resumen, dict):
                    dic_resumen = resumen
                else:
                    dic_resumen = dict(resumen)

                # Buscamos de manera flexible las llaves o valores contenidos
                # Dependiendo de cómo devuelva la estructura _resumen_metodo_cobro
                valores_lista = list(dic_resumen.values()) if len(dic_resumen) > 0 else [0, 0, 0, 0]
                
                # Intentamos extraer por clave exacta o por posición si el diccionario usa nombres estándar
                total_monto = float(dic_resumen.get("Total", dic_resumen.get("Total Facturado", valores_lista[0] if len(valores_lista) > 0 else 0)))
                pue_monto = float(dic_resumen.get("PUE", dic_resumen.get("Facturado PUE", valores_lista[1] if len(valores_lista) > 1 else 0)))
                ppd_monto = float(dic_resumen.get("PPD", dic_resumen.get("Cobros a plazos (PPD Total)", valores_lista[2] if len(valores_lista) > 2 else 0)))
                
                # Para PPD pendiente y cobrado
                ppd_cobrado = float(dic_resumen.get("PPD cobrado", dic_resumen.get("Cobrado_PPD", valores_lista[3] if len(valores_lista) > 3 else 0)))
                ppd_pendiente = float(dic_resumen.get("PPD pendiente", dic_resumen.get("PPD Pendiente", max(0.0, ppd_monto - ppd_cobrado))))

                # Si el total viene en cero pero tenemos componentes, recalculamos
                if total_monto == 0:
                    total_monto = pue_monto + ppd_monto

                # Porcentajes calculados
                pct_pue = (pue_monto / total_monto * 100) if total_monto > 0 else 0
                pct_ppd = (ppd_monto / total_monto * 100) if total_monto > 0 else 0
                pct_cobrado = (ppd_cobrado / total_monto * 100) if total_monto > 0 else 0
                pct_pendiente = (ppd_pendiente / total_monto * 100) if total_monto > 0 else 0

                # Creamos el DataFrame formateado con la estructura jerárquica idéntica a la vista web
                filas_resumen = [
                    {"Concepto": f"<font size=8 color='#6B7280'>Monto total</font><br/><b><font size=13 color='#1F2937'>MXN {total_monto:,.2f}</font></b>"},
                    {"Concepto": f"<font color='#2563EB'>●</font> <b><font color='#1F2937'>Facturado PUE</font></b><br/><font color='#4B5563'>MXN {pue_monto:,.2f} · {pct_pue:.1f}%</font>"},
                    {"Concepto": f"<font color='#60A5FA'>●</font> <b><font color='#1F2937'>Cobros a plazos (PPD Total)</font></b><br/><font color='#4B5563'>MXN {ppd_monto:,.2f} · {pct_ppd:.1f}%</font>"},
                    {"Concepto": f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#2563EB'>●</font> <b><font color='#1F2937'>PPD pendiente</font></b><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#4B5563'>MXN {ppd_pendiente:,.2f} · {pct_pendiente:.1f}%</font>"},
                    {"Concepto": f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#60A5FA'>●</font> <b><font color='#1F2937'>PPD cobrado</font></b><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#4B5563'>MXN {ppd_cobrado:,.2f} · {pct_cobrado:.1f}%</font>"}
                ]
                
                df_metodo_pdf = pd.DataFrame(filas_resumen)[["Concepto"]]
                
                pdf_elements.append({
                    "type": "table",
                    "title": "Resumen del Método de Cobro",
                    "df": df_metodo_pdf,
                    "white_background": True,
                    # "note": nota_metodo
                })
            except Exception as e:
                pass

        st.divider()
    else:
        d = df.copy()
        es_pue, es_ppd = d["Metodo_Pago"].eq("PUE"), d["Metodo_Pago"].eq("PPD")
        d["Monto_PUE"] = d[col_monto].where(es_pue, 0.0)
        d["Monto_PPD_Cobrado"] = 0.0
        d["Monto_PPD_Pendiente"] = d[col_monto].where(es_ppd, 0.0)

        if complementos_periodo is None:
            st.info(
                "Sin la base PAGO solo se muestran importes facturados por método de pago. "
                "No se determina cuánto PPD se cobró ni cuánto sigue pendiente."
            )
        else:
            st.info(
                "La base PAGO no permite relacionar los complementos con cada factura. Se muestra la facturación "
                "por método y mes; el cobro PPD y su saldo se presentan solo de forma global."
            )
        st.divider()
        st.markdown("**Facturación emitida por método y mes**")
        fig_tiempo = _fig_facturacion_tiempo(d, col_monto, nomina_mensual=nomina_mensual)
        render_grafica(fig_tiempo, key="ing_facturacion_tiempo")
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "title": ("Facturación Emitida por Método y Mes (incluye nómina de ingresos)"
                          if nomina_mensual is not None
                          else "Facturación Emitida por Método y Mes (sin datos de cobro PPD)"),
                "fig": fig_tiempo,
                "custom_height": 250,
            })

        st.divider()
        st.markdown("**Ingresos facturados**")
        fig_ing_fact = _fig_ingresos_facturados(d, col_monto, nomina_mensual=nomina_mensual)
        render_grafica(fig_ing_fact, key="ingresos_facturados")
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "title": "Ingresos Facturados por Mes",
                "fig": fig_ing_fact,
                "custom_height": 270,
            })

        st.divider()
        st.markdown("**Método de pago facturado**")
        monto_pue = float(d.loc[es_pue, col_monto].sum())
        monto_ppd = float(d.loc[es_ppd, col_monto].sum())
        if complementos_periodo is None:
            fig_pie = _fig_pie_metodo_cobro(
                {"pue": monto_pue, "cobrado": monto_ppd, "pendiente": 0.0},
                realizado="facturado",
            )
        else:
            resumen = _resumen_metodo_cobro_global(d, complementos_periodo)
            fig_pie = _fig_pie_metodo_cobro(resumen)
        c_pie, c_tabla = st.columns([1, 1], gap="medium")
        with c_pie:
            render_grafica(fig_pie, key="ing_metodo_cobro", incluir_notas=False)
        with c_tabla:
            if complementos_periodo is None:
                st.dataframe(
                    pd.DataFrame({
                        "Método facturado": ["Facturado PUE", "Facturado PPD"],
                        "Importe": [dinero(monto_pue), dinero(monto_ppd)],
                    }),
                    hide_index=True,
                )
            else:
                st.markdown(_html_resumen_metodo_cobro(resumen, col_monto, rotular_base=False),
                            unsafe_allow_html=True)
                st.caption("El cobro PPD global no está distribuido entre facturas.")
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "section_title": "3. Estructura de la Facturación",
                "title": ("Método de pago facturado (cobros PPD no disponibles)"
                          if complementos_periodo is None
                          else "Método de Cobro (complementos no relacionados por factura)"),
                "fig": fig_pie,
                "preserve_textfont_size": True,
            })
            resumen_pdf = (
                resumen if complementos_periodo is not None
                else {
                    "total": monto_pue + monto_ppd,
                    "pue": monto_pue,
                    "ppd": monto_ppd,
                    "pendiente": 0.0,
                    "cobrado": 0.0,
                }
            )
            pdf_elements.append({
                "type": "table",
                "title": "Resumen — Método de pago facturado",
                "df": pd.DataFrame({
                    "Concepto": [
                        _html_resumen_metodo_cobro(
                            resumen_pdf,
                            col_monto,
                            rotular_base=False,
                            incluir_detalle_ppd=complementos_periodo is not None,
                            formato_pdf=True,
                        )
                    ],
                }),
                "white_background": True,
            })

        st.divider()

    st.subheader("Concentración y Riesgo de Dependencia")
    st.markdown("**Top 10 clientes de cada año**", help=AYUDA_TOP10_ANUAL)
    if df["Año"].nunique() < 2:
        st.info("El Bump Chart compara posiciones entre años: selecciona al menos dos ejercicios.")
    else:
        fig_bump = _fig_bump_anual(df, col_monto)
        render_grafica(fig_bump, key="ing_bump_anual", width="stretch")
        # nota_bump = st.text_area("Conclusión - Concentración y Top 10 Clientes", max_chars=600, key="note_ing_bump")
        
        if pdf_elements is not None:
            pdf_elements.append({
                "type": "image",
                "section_title": "4. Concentración y Riesgo de Dependencia",
                "title": "Top 10 Clientes de Cada Año",
                "fig": fig_bump,
               "custom_height": 290
            })
