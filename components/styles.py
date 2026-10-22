# components/styles.py

CSS_IMPRESION_GLOBAL = """
<style>
/* 1. Estilo global para el recuadro de notas (Pantalla e Impresión) */
[data-testid="stTextArea"] textarea {
    border: 1px solid #d1d5db !important;
    border-left: 4px solid #1e3a8a !important;
    border-radius: 6px !important;
    background-color: #ffffff !important;
    color: #111111 !important;
}

.reporte-spacer {
    height: 16px;
    clear: both;
    border: 2px solid red;
}

[class*="st-key-ing_facturacion_tiempo_pdf"],
[class*="st-key-ingresos_facturados_pdf"] {
    width: 70% !important;
    max-width: 70% !important;
    min-width: 0 !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

[class*="st-key-ing_facturacion_tiempo_pdf"] [data-testid="stPlotlyChart"],
[class*="st-key-ingresos_facturados_pdf"] [data-testid="stPlotlyChart"],
[class*="st-key-ing_facturacion_tiempo_pdf"] .js-plotly-plot,
[class*="st-key-ingresos_facturados_pdf"] .js-plotly-plot {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
}

[class~="st-key-ing_bump_anual"] {
    width: 100% !important;
    max-width: 1467px !important;
    min-width: 0 !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

[class~="st-key-ing_bump_anual"] [data-testid="stPlotlyChart"],
[class~="st-key-ing_bump_anual"] .js-plotly-plot {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
}

@media print {
    [class*="st-key-exec_ciclos_titulo_pdf"] {
        page-break-before: always !important;
        break-before: page !important;
        page-break-after: avoid !important;
        break-after: avoid-page !important;
    }

    /* Mantener solo el contenido del reporte al imprimir. */
    [data-testid="stSidebar"],
    header,
    footer,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    [data-testid="stButton"],
    [data-testid="stDownloadButton"],
    [data-testid="stRadio"],
    [data-testid="stSelectbox"],
    [data-testid="stMultiSelect"],
    [data-testid="stSegmentedControl"],
    [data-testid="stPills"],
    [data-testid="stFileUploader"],
    [data-testid="stDateInput"],
    [data-testid="stNumberInput"],
    [data-testid="stTextInput"],
    [data-testid="stCheckbox"],
    [data-testid="stToggle"],
    [data-testid="stSlider"],
    [data-testid="stDivider"],
    [data-testid="stTooltipIcon"],
    [data-testid="stElementToolbar"],
    [role="tooltip"],
    [data-baseweb="tooltip"],
    button,
    hr {
        display: none !important;
    }

    @page {
    size: letter portrait;
    margin: 12mm;
}

    *,
    *::before,
    *::after {
        box-sizing: border-box !important;
        animation: none !important;
        transition: none !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }

    html,
    body,
    body *,
    body *::before,
    body *::after {
        opacity: 1 !important;
        filter: none !important;
    }

    html,
    body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background-color: #ffffff !important;
    }

    body {
        margin: 0 !important;
        padding: 8mm !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }

    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .block-container,
    main {
        width: 100% !important;
        max-width: none !important;
        margin: 0 !important;
        padding: 10px !important;
        overflow: visible !important;
    }

    h1 {
        margin: 0 0 10px !important;
        font-size: 18pt !important;
    }

    h2 {
        margin: 12px 0 6px !important;
        font-size: 13pt !important;
        page-break-after: avoid !important;
        break-after: avoid-page !important;
    }

    h3, h4, h5, h6 {
        margin: 8px 0 4px !important;
        page-break-after: avoid !important;
        break-after: avoid-page !important;
    }

    [data-testid="stHorizontalBlock"],
    .stHorizontalBlock {
        display: grid !important;
        grid-template-columns: minmax(0, 1fr) !important;
        grid-auto-flow: row !important;
        align-items: start !important;
        justify-items: stretch !important;
        gap: 0 !important;
        width: 100% !important;
        max-width: 100% !important;
        height: auto !important;
        min-height: 0 !important;
        overflow: visible !important;
        position: static !important;
    }

    [data-testid="stHorizontalBlock"] > [data-testid="column"],
    .stHorizontalBlock > [data-testid="column"],
    [data-testid="stColumn"],
    [data-testid="column"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: auto !important;
        min-height: 0 !important;
        flex: none !important;
        float: none !important;
        position: static !important;
        transform: none !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"],
    [class*="st-key-ing_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"],
    [class*="st-key-ing_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"],
    [class*="st-key-egr_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"],
    [class*="st-key-egr_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"],
    [class*="st-key-egr_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-auto-flow: row !important;
        align-items: stretch !important;
        justify-items: stretch !important;
        gap: 3mm !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
    }

    [class*="st-key-ing_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }

    [class*="st-key-egr_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }

    [class*="st-key-ing_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    }

    [class*="st-key-egr_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    }

    [class*="st-key-ing_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }

    [class*="st-key-egr_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }

    [class*="st-key-ing_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-ing_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-ing_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-egr_kpis_facturacion_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-egr_kpis_cobranza_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-egr_kpis_cierre_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        box-sizing: border-box !important;
        padding: 0 !important;
    }

    [class*="st-key-ing_kpis_facturacion_pdf"] [data-testid="stMetric"],
    [class*="st-key-ing_kpis_cobranza_pdf"] [data-testid="stMetric"],
    [class*="st-key-ing_kpis_cierre_pdf"] [data-testid="stMetric"],
    [class*="st-key-egr_kpis_facturacion_pdf"] [data-testid="stMetric"],
    [class*="st-key-egr_kpis_cobranza_pdf"] [data-testid="stMetric"],
    [class*="st-key-egr_kpis_cierre_pdf"] [data-testid="stMetric"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        box-sizing: border-box !important;
        break-inside: avoid-page !important;
        page-break-inside: avoid !important;
    }

    [data-testid="stElementContainer"],
    .element-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        height: auto !important;
        min-height: 0 !important;
        position: static !important;
        transform: none !important;
        contain: none !important;
        overflow: visible !important;
    }

    [data-testid="stPlotlyChart"] {
        width: 70% !important;
        max-width: 70% !important;
        min-width: 0 !important;
        height: auto !important;
        margin: 0 auto 12px !important;
        display: block !important;
        position: relative !important;
        transform: none !important;
        overflow: visible !important;
        opacity: 1 !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [data-testid="stPlotlyChart"] iframe,
    [data-testid="stPlotlyChart"] > div,
    [data-testid="stPlotlyChart"] .js-plotly-plot,
    [data-testid="stPlotlyChart"] .plot-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        position: relative !important;
        transform: none !important;
        overflow: visible !important;
    }

    [data-testid="stPlotlyChart"] iframe {
        border: 0 !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"],
    [class*="st-key-eco_egresos_base_100_pdf"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 0 8mm !important;
        position: relative !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 380px !important;
        min-height: 380px !important;
        margin: 0 auto 8px !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-eco_egresos_base_100_pdf"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 410px !important;
        min-height: 410px !important;
        margin: 0 auto 8px !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] .js-plotly-plot,
    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] .plot-container,
    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] .svg-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 100% !important;
        min-height: 380px !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-eco_egresos_base_100_pdf"] .js-plotly-plot,
    [class*="st-key-eco_egresos_base_100_pdf"] .plot-container,
    [class*="st-key-eco_egresos_base_100_pdf"] .svg-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 100% !important;
        min-height: 410px !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] [data-testid="stTextArea"],
    [class*="st-key-eco_egresos_base_100_pdf"] [data-testid="stTextArea"] {
        width: 100% !important;
        max-width: 100% !important;
        margin: 8px 0 12px !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] [data-testid="stTextArea"] textarea,
    [class*="st-key-eco_egresos_base_100_pdf"] [data-testid="stTextArea"] textarea {
        min-height: 58px !important;
        height: 58px !important;
    }

    [class*="st-key-eco_egresos_ingresos_gastos_pdf"] .eco-insight,
    [class*="st-key-eco_egresos_base_100_pdf"] .eco-insight {
        display: block !important;
        width: 100% !important;
        margin: 8px 0 12px !important;
        line-height: 1.45 !important;
        overflow-wrap: anywhere !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-plot_exec_flujo_neto"],
    [class*="st-key-plot_exec_ciclos_lineas"],
    [class*="st-key-plot_exec_velas_cobros"],
    [class*="st-key-plot_exec_velas_pagos"],
    [class*="st-key-plot_exec_plazos_comparativa"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        
        min-width: 0 !important;
        margin: 0 auto 12px !important;
        position: relative !important;
        transform: none !important;
        zoom: 1 !important;
        overflow: visible !important;
    }

    [class*="st-key-plot_exec_flujo_neto"] [data-testid="stPlotlyChart"],
    [class*="st-key-plot_exec_ciclos_lineas"] [data-testid="stPlotlyChart"],
    [class*="st-key-plot_exec_velas_cobros"] [data-testid="stPlotlyChart"],
    [class*="st-key-plot_exec_velas_pagos"] [data-testid="stPlotlyChart"],
    [class*="st-key-plot_exec_plazos_comparativa"] [data-testid="stPlotlyChart"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: auto !important;
        margin: 0 44px !important;
        display: block !important;
        position: relative !important;
        transform: none !important;
        zoom: 0.7 !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-ritmo_vista"] [data-testid="stWidgetLabel"],
    [class*="st-key-ritmo_ejercicios"] [data-testid="stWidgetLabel"],
    [class*="st-key-ritmo_metricas"] [data-testid="stWidgetLabel"] {
        display: none !important;
    }

    [data-testid="stPlotlyChart"] .trace,
    [data-testid="stPlotlyChart"] .scatterlayer,
    [data-testid="stPlotlyChart"] .barlayer,
    [data-testid="stPlotlyChart"] .pielayer {
        opacity: 1 !important;
    }

    [data-testid="stTextArea"] textarea {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [data-testid="stTextArea"] {
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-ing_desglose_anual_pdf"],
    [class*="st-key-egr_desglose_anual_pdf"] {
        width: fit-content !important;
        
        max-width: 100% !important;
        margin: 0 auto !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-ing_desglose_anual_pdf"] [data-testid="stDataFrame"],
    [class*="st-key-egr_desglose_anual_pdf"] [data-testid="stDataFrame"] {
        width: fit-content !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow: visible !important;
    }

    [class*="st-key-egr_facturado_por_mes_pdf"],
    [class*="st-key-egr_nomina_vs_gastos_pdf"],
    [class*="st-key-egr_metodo_pago_pdf"],
    [class*="st-key-egr_bump_anual_pdf"],
    [class*="st-key-ing_bump_anual_pdf"] {
        display: block !important;
        width: 100% !important;
        max-width: 22.5in !important;
        min-width: 0 !important;
        zoom:0.7;
        margin: 0 auto !important;
        box-sizing: border-box !important;
        overflow: visible !important;
    }

    [class*="st-key-egr_nomina_vs_gastos_layout"] [data-testid="stHorizontalBlock"],
    [class*="st-key-egr_metodo_pago_layout"] [data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        grid-auto-flow: row !important;
        align-items: start !important;
        justify-items: stretch !important;
        gap: 3mm !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
    }

    [class*="st-key-egr_nomina_vs_gastos_layout"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-egr_metodo_pago_layout"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
    }

    [class*="st-key-egr_tiempo_pdf"] {
        display: block !important;
        
        width: 150% !important;
        max-width: 22.5in !important;
        min-width: 0 !important;
        zoom: 0.7 !important;
        margin: 0 auto !important;
        box-sizing: border-box !important;
        overflow: visible !important;
    }

    [class*="st-key-egr_tiempo_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-egr_facturado_por_mes_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-egr_nomina_vs_gastos_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-egr_metodo_pago_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-egr_bump_anual_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-ing_bump_anual_pdf"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-egr_tiempo_pdf"] [data-testid="stPlotlyChart"] {
        height: 400px !important;
    }

    [class*="st-key-egr_facturado_por_mes_pdf"] [data-testid="stPlotlyChart"] {
        height: 480px !important;
    }

    [class*="st-key-egr_nomina_vs_gastos_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-egr_metodo_pago_pdf"] [data-testid="stPlotlyChart"] {
        height: 320px !important;
    }

    [class*="st-key-egr_bump_anual_pdf"] [data-testid="stPlotlyChart"] {
        height: 460px !important;
    }

    [class*="st-key-ing_bump_anual_pdf"] [data-testid="stPlotlyChart"] {
        height: 460px !important;
    }

    [class*="st-key-egr_tiempo_pdf"] .js-plotly-plot,
    [class*="st-key-egr_tiempo_pdf"] .plot-container,
    [class*="st-key-egr_tiempo_pdf"] .svg-container,
    [class*="st-key-egr_facturado_por_mes_pdf"] .js-plotly-plot,
    [class*="st-key-egr_facturado_por_mes_pdf"] .plot-container,
    [class*="st-key-egr_facturado_por_mes_pdf"] .svg-container,
    [class*="st-key-egr_nomina_vs_gastos_pdf"] .js-plotly-plot,
    [class*="st-key-egr_nomina_vs_gastos_pdf"] .plot-container,
    [class*="st-key-egr_nomina_vs_gastos_pdf"] .svg-container,
    [class*="st-key-egr_metodo_pago_pdf"] .js-plotly-plot,
    [class*="st-key-egr_metodo_pago_pdf"] .plot-container,
    [class*="st-key-egr_metodo_pago_pdf"] .svg-container,
    [class*="st-key-egr_bump_anual_pdf"] .js-plotly-plot,
    [class*="st-key-egr_bump_anual_pdf"] .plot-container,
    [class*="st-key-egr_bump_anual_pdf"] .svg-container,
    [class*="st-key-ing_bump_anual_pdf"] .js-plotly-plot,
    [class*="st-key-ing_bump_anual_pdf"] .plot-container,
    [class*="st-key-ing_bump_anual_pdf"] .svg-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_facturacion_tiempo_pdf"],
    [class*="st-key-ingresos_facturados_pdf"] {
        display: block !important;
        width: 100% !important;
        max-width: 12.5in !important;
        box-sizing: border-box !important;
        min-width: 0 !important;
        margin: 0 !important;
        
        justify-self: center !important;
        align-self: center !important;
        zoom: 1 !important;
        transform: none !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }
    [class~="st-key-ing_bump_anual"] {
        
        width: 100% !important;
        max-width: 100% !important;
        height: auto;
        margin: 0 auto !important;
        box-sizing: border-box !important;
        overflow: visible !important;
    }

    [class~="st-key-ing_bump_anual"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 460px !important;
        margin: 0 !important;
        overflow: visible !important;
    }

    [class~="st-key-ing_bump_anual"] .js-plotly-plot,
    [class~="st-key-ing_bump_anual"] .plot-container,
    [class~="st-key-ing_bump_anual"] .svg-container {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_facturacion_tiempo_pdf"] [data-testid="stPlotlyChart"],
    [class*="st-key-ingresos_facturados_pdf"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 480px !important;
        min-height: 480px !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_facturacion_tiempo_pdf"] .js-plotly-plot,
    [class*="st-key-ingresos_facturados_pdf"] .js-plotly-plot {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] {
        display: block !important;
        width: 100% !important;
        max-width: 7.5in !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        overflow: visible !important;
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        grid-auto-flow: row !important;
        align-items: start !important;
        justify-items: stretch !important;
        gap: 6mm !important;
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stColumn"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important;
        box-sizing: border-box !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stColumn"]:nth-child(2) [data-testid="stMarkdownContainer"],
    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stColumn"]:nth-child(2) [data-testid="stMarkdownContainer"] > div {
        width: 100% !important;
        max-width: 100% !important;
        overflow-wrap: anywhere !important;
        word-break: normal !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stPlotlyChart"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: 360px !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] .js-plotly-plot {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 auto !important;
        overflow: visible !important;
    }

    [class*="st-key-ing_metodo_cobro_pdf"] [data-testid="stTextArea"] {
        width: 100% !important;
        max-width: 100% !important;
        margin: 8px 0 0 !important;
    }

    [class*="st-key-exec_concentracion_tabla"] {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 20px 0 28px !important;
        position: relative !important;
        clear: both !important;
        break-inside: avoid-page !important;
        page-break-inside: avoid !important;
    }

    [class*="st-key-exec_concentracion_tabla"] [data-testid="stDataFrame"] {
        width: 100% !important;
        height: 400px !important;
        min-height: 400px !important;
        margin: 0 !important;
        overflow: visible !important;
    }

    .sf-wrap {
        width: 100% !important;
        height: auto !important;
        max-height: none !important;
        margin: 16px 0 24px !important;
        overflow: visible !important;
        break-inside: auto !important;
        page-break-inside: auto !important;
    }

    .sf-tabla {
        width: 100% !important;
        margin: 0 !important;
        font-size: 8pt !important;
        page-break-inside: auto !important;
        break-inside: auto !important;
    }

    .sf-tabla thead {
        display: table-header-group !important;
    }

    .sf-tabla th {
        position: static !important;
    }

    .sf-tabla th,
    .sf-tabla td {
        height: auto !important;
        min-height: 24px !important;
        padding: 5px 6px !important;
        line-height: 1.3 !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        vertical-align: top !important;
    }

    .sf-tabla tr {
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }

    table {
        border-collapse: collapse !important;
        width: 100% !important;
        page-break-inside: auto !important;
        break-inside: auto !important;
    }
    thead {
        display: table-header-group !important;
    }
    tr {
        page-break-inside: avoid !important;
        break-inside: avoid-page !important;
    }
    th, td {
        border-bottom: 1px solid #999999 !important;
        color: #000000 !important;
        padding: 5px !important;
        font-size: 9pt !important;
    }
    th {
        font-weight: bold !important;
    }
}
</style>
"""