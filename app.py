# Punto de entrada principal (UI, Sidebar, Enrutador)
'''
El archivo raíz que inicializa Streamlit,
configura la barra lateral de carga de archivos (sidebar),
aplica los estilos globales, enruta los módulos y maneja las funciones secundarias de control (
'''

import streamlit as st
from config import CSS_TARJETAS_KPI
from components.styles import CSS_IMPRESION_GLOBAL
from core.loader import (anios_5_archivos)
from views.executive_view import (modulo_riesgo)
from views.income_view import (modulo_ingresos)
from views.expense_view import (modulo_egresos)
import time
# 1. Inyectar estilos globales y reglas @media print al arranque
st.markdown(CSS_IMPRESION_GLOBAL, unsafe_allow_html=True)
# Inyección de CSS para cambiar la fuente predeterminada (Ejemplo con 'Inter')
st.markdown("""
    <style>
        /* Importar fuente desde Google Fonts */
      @import url('https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300..800;1,300..800&display=swap');

        /* Aplicar la fuente a todos los elementos de la interfaz de Streamlit */
        html, body, [class*="css"] {
            font-family: 'Open Sans', sans-serif !important;
        }
    </style>
""", unsafe_allow_html=True)
# 2. Configuración de la barra lateral y botón de impresión instantáneo
with st.sidebar:
  st.header("Acciones del Reporte")

  

    

def main() -> None:
    st.set_page_config(page_title="Facturación Emitida e Ingresos Corporativos", page_icon=":material/bar_chart:", layout="wide")
    # st.set_page_config(layout="centered")

    st.markdown(CSS_TARJETAS_KPI, unsafe_allow_html=True)

    with st.sidebar:
        st.header("Carga de Datos")
        archivos_subidos = st.file_uploader("Sube todos tus reportes aquí (Excel/CSV)",
                                            type=['csv', 'xlsx', 'xls', 'xlsb'], accept_multiple_files=True)
        st.caption("Opcional: incluye el archivo de Productos de CFDI recibidos (nombre con “Productos”) con "
                   "columnas Clave, RFC Emisor, Fecha e Importe para filtrar compras de divisas.")

        # Inicializar 5 variables de ruteo
        file_ingresos_facturas = None
        file_ingresos_pago = None
        file_egresos_facturas = None
        file_egresos_productos = None
        file_egresos_pago = None
        file_nomina = None

        # Motor de clasificación exacto por nombre
        timbrado_omitido = False
        if archivos_subidos:
            for f in archivos_subidos:
                nombre = f.name.lower()

                # Los archivos de Timbrado ya no se usan: el dashboard opera solo con la fecha de pago real
                if "timbrad" in nombre and "emitid" not in nombre:
                    timbrado_omitido = True
                    continue

                # Clasificación Ingresos (Clientes)
                if "emitid" in nombre and "producto" not in nombre:
                    file_ingresos_facturas = f
                elif "cliente" in nombre and "pago" in nombre:
                    file_ingresos_pago = f

                # Clasificación Egresos (Proveedores)
                if "producto" in nombre and "emitid" not in nombre:
                    file_egresos_productos = f
                elif "recibid" in nombre and "pago" not in nombre:
                    file_egresos_facturas = f
                elif "recibid" in nombre and "pago" in nombre:
                    file_egresos_pago = f

                # Clasificación Nómina
                elif "nomina" in nombre or "nómina" in nombre:
                    file_nomina = f

        if timbrado_omitido:
            st.warning("Archivo de Timbrado detectado y omitido. El dashboard opera exclusivamente bajo Flujo de Efectivo.")

        # Revelación progresiva: el selector de Módulo solo aparece una vez que el enrutador clasificó al
        # menos un archivo; antes de eso, un clic prematuro en Ingresos/Egresos expondría un módulo sin datos.
        hay_archivos_ruteados = any(f is not None for f in (
            file_ingresos_facturas, file_ingresos_pago,
            file_egresos_facturas, file_egresos_pago, file_nomina))

        if hay_archivos_ruteados:
            st.markdown("---")
            modulo = st.radio("Selecciona el Módulo:",
                              ["Dashboard Ejecutivo (Riesgo y Viabilidad)", "Ingresos (Auditoría Operativa)",
                               "Egresos (Auditoría Operativa)"])
        else:
            modulo = None

    if not hay_archivos_ruteados:
        st.info("👋 Bienvenido al Analizador Financiero. Por favor, carga tus reportes en la barra lateral "
                "para comenzar.")
        st.stop()

    # Ventana móvil estándar de 5 años, común a todos los módulos (año máximo de emisión entre Emitidos y Recibidos).
    anios_5 = anios_5_archivos(file_ingresos_facturas, file_egresos_facturas)

    if modulo == "Dashboard Ejecutivo (Riesgo y Viabilidad)":
        modulo_riesgo(file_ingresos_facturas, file_ingresos_pago, file_egresos_facturas,
                     file_egresos_pago, file_nomina)
    elif modulo == "Ingresos (Auditoría Operativa)":
        modulo_ingresos(file_ingresos_facturas, file_ingresos_pago, anios_5,
                        file_egresos_facturas, file_egresos_pago, file_nomina)
    else:
        modulo_egresos(file_egresos_facturas, file_egresos_pago, file_nomina, anios_5,
                       file_ingresos_facturas, file_egresos_productos)


if __name__ == "__main__":
    main()
