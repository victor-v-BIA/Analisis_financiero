# ======================================
#  BLOQUE DE VARIABLES / CONSTANTES
# ======================================

import hashlib
from pathlib import Path
import re
import pandas as pd

# ================================================
#  VARIABLES GLOBALES
# ================================================

# Vistas, gráficas y lógica financiera
MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# st.cache_data no detecta cambios dentro de leer_*; la huella del código evita resultados viejos tras editar app.py.
CODIGO_VERSION = hashlib.md5(Path(__file__).read_bytes()).hexdigest()

# Comprobantes, complementos y el loader
NOMBRE_FECHA = "Fecha de Pago"

# ================================================
# VARIABLES PARA LOADER.PY
# ================================================

# ARCHIVOS DEFAULT PARA EVITAR QUE USUARIO CARGUE LOS ARCHIVOS DE VISTA ECONOMICA

RUTA_ITAEE_DEFAULT = "data/itaee_20.xlsx"
RUTA_INPP_DEFAULT = "data/INP_INP.XLS"



COLS_FACTURAS = {
    "UUID": [],
    "Fecha y Hora": ["Fecha"],
    "RFC Emisor": [],
    "Nombre Emisor": ["Razon Social Emisor", "Nombre del Emisor", "Razon Social"],
    "Estatus": [],
    "Tipo Documento": ["Tipo de documento", "Tipo de Comprobante"],
    "Metodo de Pago": ["Método de Pago"],
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


# Horizonte temporal ESTÁNDAR: toda base cargada es un bloque de 5 años consecutivos (hoy 2021–2025
ANIOS_VENTANA = 5

MES_ABREV = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

# ============================================
# VARIABLES PARA EXPENSE_VIEW.PY
# ============================================

# Validación explícita de columnas de Facturas Recibidas -Egresos- (hard stop temprano, antes de intentar
# ningún cálculo): por concepto, no por nombre exacto -tolerante a acentos/mayúsculas/variantes vía _norm(),
# igual que resolver_columnas()-. Los Complementos de Pago de Egresos NO pasan por aquí: modulo_egresos lee y
# valida su propio archivo (Base PAGO) en línea, dentro de modulo_egresos().
COLUMNAS_FACTURAS_EGR_REQUERIDAS = {
    "Total": ["Total MXN TC"],
    "Metodo de Pago": ["Método de Pago"],
    "Fecha": ["Fecha y Hora", "Fecha de Emision", "Fecha de Emisión", "Fecha Emision"],
    "Estatus": [],
    "Tipo Documento": ["Tipo de documento", "Tipo de Comprobante"],
}

# Tambien se usa en income_view.py
AYUDA_TOTAL = ("Estos montos consideran el Total de la factura (incluyendo IVA e impuestos correspondientes), "
               "no los subtotales.")


# ============================================
# VARIABLES PARA EXECUTIVE_VIEW.PY
# ============================================


# ***** COLORES PARA GRAFICOS -  DASHBOARD Ciclos y Estacionalidad Operativa*****

COLOR = {"PUE": "#2E86AB",
         "PPD": "#F18F01",
         "Facturado": "#6C757D",
         "Cobrado": "#2E9E6B",
         "Por cobrar": "#C0392B"}

COLOR_DIF_POSITIVA, COLOR_DIF_NEGATIVA, COLOR_DIF_CERO = "#28a745", "#dc3545", "#9AA0A6"  

COLOR_VELA_SUBE, COLOR_VELA_BAJA = "#16A34A", "#DC2626"       
VISTAS_CICLOS = ["Tendencia (Líneas)", "Volatilidad (Velas Japonesas)"]

COLOR_LINEA_PROMEDIO = "rgba(160,160,160,0.95)" 
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


# Lista fija de tonos azules de oscuro a medio (sin llegar a blanco)
PALETA_AZULES_BIA = [
    "#0F2E85",  # Azul marino muy oscuro
    "#4160B4",  # Azul marino muy oscuro
    "#8FA5E0",  # Azul rey profundo
    "#2563EB",  # Azul vivo principal
    "#3B82F6",  # Azul claro brillante pero sólido
    "#60A5FA" ,  # Azul cielo
    "#5D92CE"
]

# VARIABLES PARA EL MODULO 7 DEL DASHBOARD EJECUTIVO


# Evaluación INDEPENDIENTE de cada escenario: proporción del flujo del mes frente al mejor mes de la ventana -> viabilidad y porcentaje del flujo libre.
PROPORCION_MINIMA = 0.05        # flujo del mes < 5 % del mejor mes: flujo marginal, no viable
CREDITO_MINIMO = 50_000.0       # línea comercial mínima (MXN): si al 30 % el crédito queda por debajo, el escenario no es viable
PCT_CAPACIDAD = 0.30            # porcentaje ESTANDARIZADO del flujo libre que se compromete en todo escenario viable (mes bajo, intermedio o mejor mes)
PLAZO_DEFECTO_MESES, PLAZO_MIN_MESES, PLAZO_MAX_MESES = 36, 12, 60
MARGEN_COMERCIAL_DEFECTO = 5.0  # puntos porcentuales que el banco suma a la TIIE (editable)
VENTANA_DICTAMEN_MESES = 24     # el dictamen evalúa estrictamente los últimos 24 meses históricos disponibles
TIIE_DEFECTO = 6.79             # último dato conocido de la TIIE a 28 días de Banxico (corte al 25/09/2026); el analista la actualiza a mano según el mercado del momento

# SECCION 8

# Análisis de Divisas (clave 841216): identificación de las compras de divisas y parámetros del cruce con el Tipo de Cambio FIX de Banxico
PREFIJO_DIVISAS = "841216"                       # Clave UNSPSC: cambio de divisas y transferencia de fondos (84121600, 84121603, 84121604, 84121605...)
SERIES_COMPRA_DIVISAS = frozenset({"BSM390DIV"})  # Serie del encabezado con la que Santander timbra sus ventas de divisas (las comisiones, 84121500, van sin esta serie)
RFCS_CASAS_CAMBIO = frozenset({"BMI9704113PA"})   # RFC de Monex: sus facturas recibidas son operaciones cambiarias
SERIES_FIX = {"SF43718": "USD", "SF46410": "EUR"}  # series del SIE de Banxico: Tipo de Cambio FIX USD/MXN y EUR/MXN
DIAS_DESFASE_ALERTA = 5                          # alerta de auditoría: CFDI timbrado más de 5 días después de la operación
DIAS_MAX_FFILL_FIX = 7                           # un día inhábil toma el último FIX hábil previo, hasta 7 días hacia atrás
BENCHMARK_MERCADO = (("Mesa de Dinero Corporativa", 0.05, 0.08),    # (nivel, spread mínimo, spread máximo) en pesos por unidad de divisa sobre la referencia
                     ("Banca Empresarial Preferente", 0.12, 0.15),                     
                     ("Ventanilla Bancaria Tradicional", 0.25, 0.35))                    

CSS_KPI_DIVISAS = """
<style>
.div-kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.75rem; margin:.4rem 0 .6rem 0; }
.div-kpi { border:1px solid rgba(128,128,128,.35); background:rgba(128,128,128,.07); border-radius:10px; padding:.7rem .9rem; }
.div-kpi .t { font-size:.8rem; opacity:.75; }
.div-kpi .v { font-size:1.3rem; font-weight:700; line-height:1.3; }
.div-kpi .s { font-size:.78rem; opacity:.7; }
@media (max-width: 900px) { .div-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
"""

COLUMNAS_OPERACIONES_DIVISAS = [
    "Clave", "Descripcion", "Divisa", "Fecha_Operacion", "Fecha_CFDI", "Cantidad",
    "Monto_Divisa", "TC_Facturado", "Importe_MXN", "RFC_Emisor", "Institucion",
    "Num_Orden", "Orden_Duplicada", "Desfase_Alerta",
]


# SECCION 10
CLAVE_GENERICA_SAT = "01010101"
CLASE_GENERICA_SAT = "010101"
ETIQUETA_CLAVE_GENERICA = "Clave genérica (Sin clasificación específica)"        # descripción de 010101 en la TABLA (en lugar de «No existe en el catálogo»)
ETIQUETA_DONA_CLAVE_GENERICA = "Sin clasificación específica"                     # descripción de 010101 en la leyenda y el tooltip de la DONA derecha, con su prefijo «010101 · » (sin «Clave genérica»)
TOP_FILAS_CLASE_SAT = 12            # filas de la matriz antes de «Resto de Clases»
NOTA_METODOLOGICA_CLASE_SAT = ('''1.- Las claves se agrupan a nivel Clase SAT (primeros 6 dígitos), el mínimo exigido por la Guía de llenado del Anexo 20.Se presenta la descripción oficial de cada Clase, y no el concepto libre de las facturas, para evitar ambigüedades de redacción.''')


COLORES_CLASES_SAT = ("#1E3A8A", "#2563EB", "#3B82F6", "#60A5FA", "#93C5FD")                      # azules: las Top 5 clases específicas de lo facturado
COLOR_OTRAS_CLASES, COLOR_SIN_CLASIFICAR = "#475569", "#94A3B8"                                   # pizarra: «Otras clases»; gris: 010101
TOP_DONA_CLASES_SAT = 5                                                                           # clases que la dona derecha muestra antes de agrupar «Otras clases (N)»


COLS_EMITIDOS_PRODUCTOS = {
    "Clave": [], "Fecha": [], "Importe": [], "UUID CFDI Emitido": [],
}
COLS_EMITIDOS_PRODUCTOS_OPC = {
    "Descripcion": [],
    "Razon Social Receptor": [],
    "RFC Receptor": [],
    "Cantidad": [],
    "Descuento": [],
    "Moneda": [],
    "Tipo de Cambio": [],
    "Tipo de Cambio DOF": [],
    "Impuestos Trasladados": [],
    "Impuestos Retenidos": [],
    "Importe Local Trasladado": [],
    "Importe Local Retenido": [],
}


# ============================================
# VARIABLES PARA FINANCE_LOGIC.PY
# ============================================

MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                "octubre", "noviembre", "diciembre"]

RFC_GENERICOS = {"XAXX010101000", "XEXX010101000"}  # público en general nacional / extranjero genérico

TASA_REFERENCIA_ANUAL = 16.0   # tasa fija del dictamen: TIIE + margen comercial estimado (% anual); no es un input del usuario
MARGEN_SEGURIDAD_PCT = 30.0    # % del Flujo Neto MÍNIMO del periodo que se destina a la mensualidad (margen conservador)
PERIODOS_EVALUACION = {"Últimos 12 meses": 12,
                       "Últimos 24 meses": 24,
                       "Historial completo": None}

# ÍNDICE DE DESEMPEÑO FINANCIERO (BASADO EN CFDI): reglas paramétricas estrictas, sin juicios de crédito bancario.

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

# ============================================
# VARIABLES PARA UTILS.PY
# ============================================
_CONECTORES_MINUSCULA = {"de", "del", "la", "las", "los", "y", "en", "a", "al"}


# ==================================================
# VARIABLES PARA INCOME_VIEW.PY (FINANCIERA Y ECONOMICA)
# ==================================================

# VISTA ECONÓMICA (Ingresos / Egresos): ingresos y gastos de la empresa frente a ITAEE / INPP (INEGI).
VISTAS_MODULO = ["Vista Financiera", "Vista Económica"]
MENSAJE_CARGA_ECONOMICA = "Carga la base económica correspondiente (ITAEE / INPP / TIIE) para generar el comparativo sectorial."
ETIQUETA_SELECTOR_SERIE = "Selecciona el sector / serie a comparar:"


# PALETA DE COLORES PARA GRAFICAS DE TOP 10
PALETA_BUMP = ["#60A5FA",
               "#34D399", 
               "#FBBF24",
               "#F87171", 
               "#A78BFA", 
               "#22D3EE", 
               "#FB923C", 
               "#A3E635", 
               "#F472B6", 
               "#94A3B8"]

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
PALETA_ING = {"pue": "#3B82F6", 
              "ppd": "#7DD3FC", 
              "pendiente": "#2563EB"} # azul medio · azul claro · azul profundo

TEXTO_SOBRE_ING = {"#3B82F6": "#FFFFFF", "#7DD3FC": "#0B1220", 
                   "#2563EB": "#FFFFFF", "#1D4ED8": "#FFFFFF", "#F59E0B": "#0B1220"}

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


# ==================================================
# VARIABLES PARA EXPENSE_VIEW.PY
# ==================================================

# Categorías de Egresos, con el mismo nombre y color en barras, sectores, leyendas, tooltips e indicadores
NOMBRE_EGR_PUE, NOMBRE_EGR_PPD, NOMBRE_NOMINA = "PUE", "PPD", "Nómina"
COLOR_EGR_PUE, COLOR_EGR_PPD, COLOR_NOMINA = "#3B82F6", "#7DD3FC", "#F59E0B" # azul medio · azul claro · naranja (la nómina se distingue de los proveedores)
COLOR_GASTOS = "#7DD3FC" # «Gastos (Proveedores)» en Nómina vs. Gastos: azul claro


# ==================================================
# VARIABLES PARA APP.PY
# ==================================================

#  BLOQUE DE ESTILOS CSS

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

# ==================================================
# VARIABLES PARA UTILS.PY
# ==================================================

_SUFIJOS_CORPORATIVOS = re.compile(
    r",?\s*\b(S\.?A\.?P\.?I\.?\s*DE\s*C\.?V\.?|S\.?\s*DE\s*R\.?L\.?\s*DE\s*C\.?V\.?|S\.?A\.?\s*DE\s*C\.?V\.?"
    r"|S\.?A\.?B\.?|S\.?A\.?|S\.?C\.?)\.?\s*$", re.IGNORECASE)
_GRUPO_FINANCIERO_FINAL = re.compile(r"\bGRUPO\s+FINANCIERO\s+\S+\s*$", re.IGNORECASE)
_PARENTESIS = re.compile(r"\([^)]*\)")


# =================================================
# VARIABLES PARA API_INEGI.PY
# =================================================

ESTADOS_INEGI = {
    "01": "Aguascalientes",
    "02": "Baja California",
    "03": "Baja California Sur",
    "04": "Campeche",
    "05": "Coahuila de Zaragoza",
    "06": "Colima",
    "07": "Chiapas",
    "08": "Chihuahua",
    "09": "Ciudad de México",
    "10": "Durango",
    "11": "Guanajuato",
    "12": "Guerrero",
    "13": "Hidalgo",
    "14": "Jalisco",
    "15": "México",
    "16": "Michoacán de Ocampo",
    "17": "Morelos",
    "18": "Nayarit",
    "19": "Nuevo León",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Querétaro",
    "23": "Quintana Roo",
    "24": "San Luis Potosí",
    "25": "Sinaloa",
    "26": "Sonora",
    "27": "Tabasco",
    "28": "Tamaulipas",
    "29": "Tlaxcala",
    "30": "Veracruz de Ignacio de la Llave",
    "31": "Yucatán",
    "32": "Zacatecas",
}

# Mapa {nombre_visible_en_selector: (id_23_o_32_estados, [id_9_estados_con_petroleo])}
# Series originales · Índice de volumen físico base 2018=100 (FREQ=4, UNIT=1061)
INDICADORES_ITAEE = {
    "Total": ("741177", "741180"),
    "Actividades primarias": ("741259",),
    "111-112 - Agricultura. Cría y explotación de animales": ("778083",),
    "Resto (Actividades primarias)": ("778147",),
    "Actividades secundarias": ("741323", "741326"),
    "21 - Minería": ("741405", "741408"),
    "22 - Generación, transmisión, distribución y comercialización de energía eléctrica, suministro de agua y de gas natural por ductos al consumidor final": ("741487", "741490"),
    "23 - Construcción": ("741569", "741572"),
    "31-33 - Industrias manufactureras": ("741651", "741654"),
    "Actividades terciarias": ("741733",),
    "43-46 - Comercio": ("741797",),
    "48-49-51 - Transportes, correos y almacenamiento. Información en medios masivos": ("778211",),
    "52-53 - Servicios financieros y de seguros. Servicios inmobiliarios y de alquiler de bienes muebles e intangibles": ("778275",),
    "54-55-56-81 - Servicios profesionales, científicos y técnicos. Corporativos. Servicios de apoyo a los negocios y manejo de residuos y desechos, y servicios de remediación. Otros servicios excepto actividades gubernamentales": ("778339",),
    "61-62-93 - Servicios educativos. Servicios de salud y de asistencia social. Actividades legislativas, gubernamentales, de impartición de justicia": ("778403",),
    "71-72 - Servicios de esparcimiento culturales y deportivos, y otros servicios recreativos. Servicios de alojamiento temporal y de preparación de alimentos y bebidas": ("778467",),
}

# =====================================================
# VARIABLES PARA GRAFICA DE INPC (VISTA ECONOMICA)
# =====================================================

RUTA_INPC_DEFAULT = "data/INPC_base.csv"
# Indicador oficial del INPC Nacional mensual (base 2a quincena julio 2018, canasta 2024 · FREQ=15)
INDICADOR_INPC_NACIONAL = "865541"

# Mapa {nombre_visible_en_selector: id_indicador_BIE_BISE}
# INPP Producción total por actividad económica · Índice mensual (FREQ=8, UNIT=190, cobertura nacional)
INDICADORES_INPP = {
    "INPP sin Petróleo y con Servicios": "1700001",
    "INPP con Petróleo y con Servicios": "1700002",
    "Actividades primarias": "1700003",
    "Actividades primarias, 11 Agricultura, cría y explotación de animales, aprovechamiento forestal, pesca y caza": "1700004",
    "Actividades secundarias sin petróleo": "1700160",
    "Actividades secundarias con petróleo": "1700161",
    "Actividades secundarias con petróleo, 21 Minería sin petróleo": "1700162",
    "Actividades secundarias con petróleo, 21 Minería con Petróleo": "1700163",
    "Actividades secundarias con petróleo, 22 Generación, transmisión, distribución y comercialización de energía eléctrica, suministro de agua y de gas natural por ductos al consumidor final": "1700211",
    "Actividades secundarias con petróleo, 23 Construcción": "1700226",
    "Actividades secundarias con petróleo, 31-33 Industrias manufactureras": "1700244",
    "Actividades terciarias": "1701070",
    "Actividades terciarias, 48-49 Transportes, correos y almacenamiento": "1701071",
    "Actividades terciarias, 51 Información en medios masivos": "1701146",
    "Actividades terciarias, 53 Servicios inmobiliarios y de alquiler de bienes muebles e intangibles": "1701192",
    "Actividades terciarias, 54 Servicios profesionales, científicos y técnicos": "1701215",
    "Actividades terciarias, 56 Servicios de apoyo a los negocios y manejo de residuos, y servicios de remediación": "1701264",
    "Actividades terciarias, 61 Servicios educativos": "1701306",
    "Actividades terciarias, 62 Servicios de salud y de asistencia social": "1701329",
    "Actividades terciarias, 71 Servicios de esparcimiento culturales y deportivos, y otros servicios recreativos": "1701362",
    "Actividades terciarias, 72 Servicios de alojamiento temporal y de preparación de alimentos y bebidas": "1701381",
    "Actividades terciarias, 81 Otros servicios excepto actividades gubernamentales": "1701404",
}