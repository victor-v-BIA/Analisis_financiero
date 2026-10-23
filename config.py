# ----------------------------------------------------------------------------
# 1. CARGA Y LIMPIEZA
# ----------------------------------------------------------------------------

# ======================================
#  BLOQUE DE VARIABLES / CONSTANTES
# ======================================
import hashlib
from pathlib import Path
import re
import pandas as pd
import os
COLS_FACTURAS = {
    "UUID": [],
    "Fecha y Hora": ["Fecha"],
    "RFC Emisor": [],
    "Nombre Emisor": ["Razon Social Emisor", "Nombre del Emisor", "Razon Social"],
    "Estatus": [],
    "Tipo Documento": ["Tipo de documento", "Tipo de Comprobante"],
    "Metodo de Pago": ["Método de Pago"],
    "Total": [],
}
COLS_COMPLEMENTOS = {
    "UUID": [],
    "Saldo Inicial": [],
    "Saldo Final": [],
}
# La fecha que rige el cruce (se mapea a Fecha_Cobro) es la fecha de pago real de cada complemento (Flujo de Efectivo).
# "Fecha Pago" (sin "de") es la nomenclatura real de los Complementos de Egresos -distinta a "Fecha de Pago"
# de Ingresos, confirmada contra archivos de origen reales-.
COL_FECHA_REP = {"Fecha de Pago": ["Fecha Pago"]}
COLS_COMPLEMENTOS_OPCIONALES = {"RFC Emisor": [], "Estatus": [], "UUID DR": ["Documento Relacionado", "UUID Relacionado"]}
                                                                          
# Validación explícita de columnas de Facturas Recibidas -Egresos- (hard stop temprano, antes de intentar
# ningún cálculo): por concepto, no por nombre exacto -tolerante a acentos/mayúsculas/variantes vía _norm(),
# igual que resolver_columnas()-. Los Complementos de Pago de Egresos NO pasan por aquí: modulo_egresos lee y
# valida su propio archivo (Base PAGO) en línea, dentro de modulo_egresos().
COLUMNAS_FACTURAS_EGR_REQUERIDAS = {
    "Total": [],
    "Metodo de Pago": ["Método de Pago"],
    "Fecha": ["Fecha y Hora", "Fecha de Emision", "Fecha de Emisión", "Fecha Emision"],
    "Estatus": [],
    "Tipo Documento": ["Tipo de documento", "Tipo de Comprobante"],
}

# Horizonte temporal ESTÁNDAR: toda base cargada es un bloque de 5 años consecutivos (hoy 2021–2025; mañana 2022–2026,
# 2023–2027, ...). `obtener_anios_analisis` lo deduce del año máximo de emisión y toda la app trabaja SOLO con esos 5 años
# (`anios_5`): fuera de la ventana no se agrupa ni se grafica nada, y un año sin movimientos aparece en 0.0.
ANIOS_VENTANA = 5

AYUDA_TOTAL = ("Estos montos consideran el Total de la factura (incluyendo IVA e impuestos correspondientes), "
               "no los subtotales.")

# Dashboard Ejecutivo, Indicador "Tiempos documentados de cobro y pago": banda de referencia para la brecha
# Cobro-Pago en Flujo de Efectivo. Es un criterio interno configurable, no un estándar regulatorio ni
# bancario -ajustar libremente según el apetito de análisis del usuario-.
BANDA_BRECHA_DIAS = 5

# Dashboard Ejecutivo, Indicador "Índice de Concentración de Ingresos": bandas descriptivas de concentración
# del Top 1 cliente. También son criterios internos configurables, no un umbral bancario ni una calificación
# automática de salud financiera.
BANDA_CONCENTRACION_BAJA = 15.0
BANDA_CONCENTRACION_ALTA = 30.0


# ----------------------------------------------------------------------------
# 2. LÓGICA FINANCIERA
# ----------------------------------------------------------------------------

NOMBRE_FECHA = "Fecha de Pago"
MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
_MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                "octubre", "noviembre", "diciembre"]
_CONECTORES_MINUSCULA = {"de", "del", "la", "las", "los", "y", "en", "a", "al"}
_RFC_GENERICOS = {"XAXX010101000", "XEXX010101000"}  # público en general nacional / extranjero genérico


# ----------------------------------------------------------------------------
# 3. INTERFAZ / DASHBOARD Ciclos y Estacionalidad Operativa
# ----------------------------------------------------------------------------

# ***** COLORES PARA GRAFICOS *****
# st.cache_data no detecta cambios dentro de leer_*; la huella del código evita resultados viejos tras editar app.py.
CODIGO_VERSION = hashlib.md5(Path(__file__).read_bytes()).hexdigest()


COLOR = {"PUE": "#2E86AB", "PPD": "#F18F01", "Facturado": "#6C757D", "Cobrado": "#2E9E6B",
         "Por cobrar": "#C0392B"}
COLOR_DIF_POSITIVA, COLOR_DIF_NEGATIVA, COLOR_DIF_CERO = "#28a745", "#dc3545", "#9AA0A6"   # verde / rojo / gris neutro

COLOR_VELA_SUBE, COLOR_VELA_BAJA = "#16A34A", "#DC2626"          # Close > Open: verde · Close < Open: rojo
VISTAS_CICLOS = ["Tendencia (Líneas)", "Volatilidad (Velas Japonesas)"]

COLOR_LINEA_PROMEDIO = "rgba(160,160,160,0.95)"   # guía neutra (gris claro) que no opaca las velas
METRICAS_VISUALIZAR = ["Cobros", "Pagos"]


# ----------- Clientes sin facturación en el periodo---------
ANCHOS_SIN_FACTURACION = (30, 17, 13, 23, 17)   # % inicial: Cliente | RFC | Última factura | Facturado [año] (MXN) | Participación (%)
CSS_SIN_FACTURACION = (
    "<style>.sf-wrap{width:100%;overflow-x:hidden;overflow-y:auto}"
    ".sf-tabla{width:100%;border-collapse:collapse;table-layout:auto;font-size:.875rem;font-variant-numeric:tabular-nums;margin:0}"
    ".sf-tabla th,.sf-tabla td{padding:0 .5rem;height:35px;box-sizing:border-box;border-bottom:1px solid rgba(128,128,128,.3);"
    "line-height:1.2;text-align:left;white-space:nowrap}"
    ".sf-tabla th{height:38px;background:rgba(128,128,128,.12);font-weight:600;white-space:normal;vertical-align:middle;position:sticky;top:0}"
    # el nombre es la única columna que cede ancho: se abrevia con puntos suspensivos (el nombre completo va en el tooltip `title`)
    ".sf-tabla .sf-nombre{max-width:0;overflow:hidden;text-overflow:ellipsis}"
    ".sf-tabla .sf-num{text-align:right}"
    ".sf-tabla tr.sf-total td{font-weight:700;border-top:2px solid rgba(128,128,128,.5)}</style>")


COLUMNAS_DETALLE_ANUAL = ["Año", "Facturación PPD (MXN)", "Complementos (MXN)", "Diferencia"]
# Anchos (% del contenedor) y estilo de la tabla de detalle: CSS acotado a la clase `ppd-detalle` (no afecta otras
# secciones). Año al centro, importes a la derecha y SIN saltos de línea, encabezados con salto permitido, relleno
# interno reducido antes que la tipografía. Colores neutros (heredan el tema claro/oscuro).
ANCHOS_DETALLE_ANUAL = (12, 30, 30, 28)
CSS_DETALLE_ANUAL = (
    "<style>.ppd-detalle-wrap{width:100%;overflow-x:auto}"
    ".ppd-detalle{width:100%;border-collapse:collapse;table-layout:fixed;font-size:.85rem;"
    "font-variant-numeric:tabular-nums;margin:0}"
    ".ppd-detalle th,.ppd-detalle td{padding:.2rem .35rem;border-bottom:1px solid rgba(128,128,128,.3);"
    "line-height:1.25;text-align:right}"
    ".ppd-detalle th{background:rgba(128,128,128,.12);font-weight:600;white-space:normal;vertical-align:bottom}"
    ".ppd-detalle td{white-space:nowrap}"
    ".ppd-detalle .ppd-anio{text-align:center}"
    # Apilado en anchos medios/estrechos: la columna (gráfica + tabla) nunca baja de 300 px; como las columnas de
    # Streamlit hacen flex-wrap, si dos no caben lado a lado se apilan -sin tocar otras secciones (solo las
    # columnas que contienen esta tabla)-.
    'div[data-testid="stColumn"]:has(.ppd-detalle-wrap){min-width:300px}</style>')


# ***** DICTAMEN CREDITICIO *****

TASA_REFERENCIA_ANUAL = 16.0   # tasa fija del dictamen: TIIE + margen comercial estimado (% anual); no es un input del usuario
MARGEN_SEGURIDAD_PCT = 30.0    # % del Flujo Neto MÍNIMO del periodo que se destina a la mensualidad (margen conservador)
PLAZO_DEFECTO_MESES = 36
PERIODOS_EVALUACION = {"Últimos 12 meses": 12, "Últimos 24 meses": 24, "Historial completo": None}



# ÍNDICE DE DESEMPEÑO FINANCIERO (BASADO EN CFDI): reglas paramétricas estrictas, sin juicios de crédito bancario.
# ----------------------------------------------------------------------------
MOSTRAR_INDICE_DESEMPENO = False   # interruptor temporal: el Índice de Desempeño Financiero NO se renderiza (poner True para volver a mostrarlo)
DIAS_GRACIA_PPD = 90          # una factura PPD emitida hace menos de 90 días al corte aún no es exigible: no entra al Pilar 2
VENTANA_MARGEN_MESES = 24     # Pilar 1: últimos 24 meses del resumen mensual de la sección 2
MIN_MESES_MARGEN = 12         # menos de 12 meses con registros: datos insuficientes
MIN_ANIOS_ESTABILIDAD = 3     # Pilar 3: al menos 3 años con facturación
PESOS_INDICE = (("1. Margen de excedente documental", 40), ("2. Efectividad de cobranza PPD", 35), ("3. Estabilidad y crecimiento", 25))
REGLAS_INDICE = (
    "Margen = (Cobros − Pagos a proveedores − Nómina) ÷ Cobros de los últimos 24 meses del resumen mensual de la sección 2 (mínimo 12 meses). "
    "Menos de 0 % → 0 pts; de 0 % a menos de 3 % → 20; de 3 % a menos de 8 % → 50; de 8 % a menos de 15 % → 75; 15 % o más → 100. Sin cobros: datos insuficientes.",
    "Efectividad = importe aplicado mediante REP hasta la fecha de corte (cobros parciales incluidos, con tope en el total de cada factura) ÷ importe de las facturas PPD "
    f"emitidas con más de {DIAS_GRACIA_PPD} días de antigüedad al corte. 95 % o más → 100 pts; de 85 % a menos de 95 % → 75; de 70 % a menos de 85 % → 50; "
    "de 50 % a menos de 70 % → 20; menos de 50 % → 0. Sin facturas PPD: No aplica.",
    "Estabilidad = coeficiente de variación de la facturación ANUAL (así la estacionalidad dentro del año no penaliza): 10 % o menos → 100 pts; hasta 20 % → 75; hasta 35 % → 50; "
    "hasta 50 % → 20; más de 50 % → 0. Crecimiento = tasa anual compuesta: 10 % o más → 100; 5 % o más → 75; 0 % o más → 50; −5 % o más → 20; menos de −5 % → 0. "
    "Puntaje = el MAYOR de ambos (estable sin crecer, o variable pero creciendo, no se penaliza); si la tasa es menor a −5 % el puntaje no supera 20. Mínimo 3 años; menos: datos insuficientes.")
BANDAS_DICTAMEN = ((85.0, "Desempeño Documental Sólido", "#10B981"), (70.0, "Desempeño Documental Adecuado", "#38BDF8"),
                   (50.0, "Desempeño Documental Moderado", "#F59E0B"), (0.0, "Desempeño Documental Débil", "#EF4444"))
SIN_DICTAMEN = ("Datos insuficientes para dictaminar", "#9AA0A6")


#  ********** INGRESOS (FINANCIERA Y ECONOMICA) ***********************
# VISTA ECONÓMICA (Ingresos / Egresos): ingresos y gastos de la empresa frente a ITAEE / INPP (INEGI) y TIIE (Banxico).
# ============================================================================
VISTAS_MODULO = ["Vista Financiera", "Vista Económica"]
MENSAJE_CARGA_ECONOMICA = "Carga la base económica correspondiente (ITAEE / INPP / TIIE) para generar el comparativo sectorial."
ETIQUETA_SELECTOR_SERIE = "Selecciona el sector / serie a comparar:"
_MES_ABREV = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

# RIESGO DEPENDENCIA

# Paleta sobria para fondo oscuro (el fondo de las figuras es transparente y hereda el tema; sin cuadrículas)
PALETA_BUMP = ["#60A5FA", "#34D399", "#FBBF24", "#F87171", "#A78BFA", "#22D3EE", "#FB923C", "#A3E635", "#F472B6", "#94A3B8"]
PALETA_BUMP_INGRESOS = [
    "#1E3A8A",  # Azul marino muy oscuro (Base fuerte)
    "#1D4ED8",  # Azul rey profundo
    "#2563EB",  # Azul vivo principal
    "#3B82F6",  # Azul claro brillante
    "#60A5FA",  # Azul cielo intermedio
    "#93C5FD",  # Azul cielo suave
    "#38BDF8",  # Azul cian / celeste vibrante
    "#0284C7",  # Azul océano profundo
    "#0EA5E9",  # Azul turquesa claro
    "#BFDBFE"   # Azul pastel muy claro (para el último nivel)
]
AYUDA_TOP10_ANUAL = ("Cada año muestra sus diez principales empresas. La leyenda puede incluir más de diez porque los integrantes cambian entre ejercicios.")


# Ingresos (variaciones de azul sobre fondo oscuro). PPD total = PPD cobrado
PALETA_ING = {"pue": "#3B82F6", "ppd": "#7DD3FC", "pendiente": "#2563EB"}               # azul medio · azul claro · azul profundo
TEXTO_SOBRE_ING = {"#3B82F6": "#FFFFFF", "#7DD3FC": "#0B1220", "#2563EB": "#FFFFFF", "#1D4ED8": "#FFFFFF", "#F59E0B": "#0B1220"}   # etiqueta legible sobre cada tono (claro -> texto oscuro)
SEPARADOR_PIE = "rgba(14,17,23,0.9)"  


#  **************** EGRESOS *************
#  ============================================
# Categorías de Egresos, con el mismo nombre y color en barras, sectores, leyendas, tooltips e indicadores
NOMBRE_EGR_PUE, NOMBRE_EGR_PPD, NOMBRE_NOMINA = "Egresos PUE", "Egresos PPD", "Pagos a Nómina"
COLOR_EGR_PUE, COLOR_EGR_PPD, COLOR_NOMINA = "#3B82F6", "#7DD3FC", "#F59E0B" # azul medio · azul claro · naranja (la nómina se distingue de los proveedores)
COLOR_GASTOS = "#7DD3FC" # «Gastos (Proveedores)» en Nómina vs. Gastos: azul claro



# ======================================
#  BLOQUE DE ESTILOS CSS
# ======================================

CSS_TARJETAS_KPI = """
<style>
/* Tarjetas de KPI homologadas: misma altura, mismo tamaño de letra, contenido repartido simétricamente
   (título arriba, valor al centro, nota/ayuda abajo) sin importar qué tan corto o largo sea cada dato. */
[data-testid="stMetric"] {
    background-color: #1C2B4F;
    border-radius: 10px;
    padding: 15px 20px;
    box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
    height: 100%;
    min-height: 120px;
    width:auto;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
[data-testid="stMetric"] > div {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100%;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.95rem !important;
    line-height: 1.25rem;
    white-space: normal;
}
[data-testid="stMetricValue"] div {
    font-size: 1.65rem !important;
    line-height: 2rem;
}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
    color: #FFFFFF !important;
}
[data-testid="stMetricDelta"], [data-testid="stMetric"] [data-testid="stTooltipIcon"],
[data-testid="stMetric"] [data-testid="stTooltipHoverTarget"] svg {
    color: #E0E0E0 !important;
}
[data-testid="stMetricDelta"] p {
    font-size: 0.8rem !important;
}
</style>
"""

CSS_BARRA_CONTROL = """
<style>
button[data-testid="stBaseButton-pillsActive"] {
    background-color: #1E293B !important; border: 1px solid #3B82F6 !important; color: #F8FAFC !important;
    border-radius: 6px !important;
}
button[data-testid="stBaseButton-pillsActive"] p { color: #F8FAFC !important; }
button[data-testid="stBaseButton-pills"] { border-radius: 6px !important; }
</style>
"""

CSS_VISTA_ECONOMICA = """
<style>
.eco-insight { background:#111827; border:1px solid rgba(148,163,184,.25); border-left:4px solid #3B82F6; border-radius:8px;
               padding:.65rem .9rem; margin:.35rem 0 1rem 0; font-size:.88rem; line-height:1.35; color:#E5E7EB; }
.eco-insight b { color:#93C5FD; }
.eco-insight.eco-tiie { background:#2E1065; border-left-color:#A855F7; }
.eco-insight.eco-tiie b { color:#D8B4FE; }
</style>
"""
REP_VACIO = pd.DataFrame({
    "UUID": pd.Series(dtype=str), "RFC_Emisor": pd.Series(dtype=str),
    "Fecha_Cobro": pd.Series(dtype="datetime64[ns]"),
    "Saldo_Inicial": pd.Series(dtype=float), "Saldo_Final": pd.Series(dtype=float),
    "Cobro_Efectivo": pd.Series(dtype=float),
})

_SUFIJOS_CORPORATIVOS = re.compile(
    r",?\s*\b(S\.?A\.?P\.?I\.?\s*DE\s*C\.?V\.?|S\.?\s*DE\s*R\.?L\.?\s*DE\s*C\.?V\.?|S\.?A\.?\s*DE\s*C\.?V\.?"
    r"|S\.?A\.?B\.?|S\.?A\.?|S\.?C\.?)\.?\s*$", re.IGNORECASE)
_GRUPO_FINANCIERO_FINAL = re.compile(r"\bGRUPO\s+FINANCIERO\s+\S+\s*$", re.IGNORECASE)
_PARENTESIS = re.compile(r"\([^)]*\)")


# PARA EL ESCENARIO DE CREDITO
# AQUIII

# ARCHIVOS DEFAULT PARA EVITAR QUE USUARIO CARGUE LOS ARCHIVOS DE ECONOMICA

RUTA_ITAEE_DEFAULT = "data/itaee_20.xlsx"
RUTA_INPP_DEFAULT = "data/INP_INP.XLS"
RUTA_INPC_DEFAULT = "data/INPC_base.csv"
