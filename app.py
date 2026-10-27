# Punto de entrada principal (UI, Sidebar, Enrutador)
'''
El archivo raíz que inicializa Streamlit,
configura la barra lateral para sincronizar archivos desde Google Drive,
aplica los estilos globales, enruta los módulos y maneja las funciones de control.
'''

import streamlit as st
from python_calamine import CalamineError
from pyarrow import ArrowException
from googleapiclient.errors import HttpError
from config import CSS_TARJETAS_KPI
from components.styles import CSS_IMPRESION_GLOBAL
from core.loader import (anios_5_archivos, cargar_base)
from views.executive_view import (modulo_riesgo)
from views.income_view import (modulo_ingresos)
from views.expense_view import (modulo_egresos)
from utils import _ArchivoGrupo
from drive_service import descargar_archivo_drive

# 1. Inyectar estilos globales y reglas @media print al arranque
st.markdown(CSS_IMPRESION_GLOBAL, unsafe_allow_html=True)
# Inyección de CSS para cambiar la fuente predeterminada
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

# Clase auxiliar para imitar el comportamiento de st.file_uploader con Google Drive
class ArchivoDrive:
    def __init__(self, name, id_drive):
        self.name = name
        self.id_drive = id_drive
        self._bytes = None

    def getvalue(self):
        if self._bytes is None:
            self._bytes = descargar_archivo_drive(self.id_drive)
        return self._bytes

def main() -> None:
    st.set_page_config(page_title="Facturación Emitida e Ingresos Corporativos", page_icon=":material/bar_chart:", layout="wide")
    st.markdown(CSS_TARJETAS_KPI, unsafe_allow_html=True)

    with st.sidebar:
        st.header("Carga de Datos")
        
        # 1. El interruptor principal
        modo_drive = st.checkbox(
            "Empresa con múltiples archivos (Usar Google Drive)",
            help="Marca esta opción si tienes bases divididas en múltiples archivos dentro de una carpeta de Drive."
        )
        
        # Diccionario maestro para unificar cualquier método de carga
        tipos_archivo = {
            "ingresos_facturas": [], "ingresos_pago": [], "egresos_facturas": [],
            "egresos_productos": [], "egresos_pago": [], "nomina": []
        }
        timbrado_omitido = False
        no_clasificados = []
        archivos_listos = False

        # ==========================================
        # MODO 2: GOOGLE DRIVE
        # ==========================================
        if modo_drive:
            st.write("Sincroniza tu carpeta de Drive para combinar múltiples reportes.")
            folder_id = st.text_input("ID de la carpeta de Drive:", placeholder="Ej. 1A2B3C4D5E6F7G8H9I0J")
            
            if st.button("Sincronizar Carpeta", type="primary", disabled=not folder_id):
                with st.spinner("Buscando y descargando archivos desde Google Drive..."):
                    from drive_service import listar_archivos_carpeta
                    archivos_en_drive = listar_archivos_carpeta(folder_id)
                    
                    for f_info in archivos_en_drive:
                        nombre = f_info["name"].lower()
                        if "timbrad" in nombre and "emitid" not in nombre:
                            timbrado_omitido = True
                            continue
                        
                        tipo = None
                        if "emitid" in nombre and "producto" not in nombre: tipo = "ingresos_facturas"
                        elif "cliente" in nombre and "pago" in nombre: tipo = "ingresos_pago"
                        elif "producto" in nombre and "emitid" not in nombre: tipo = "egresos_productos"
                        elif "recibid" in nombre and "pago" not in nombre: tipo = "egresos_facturas"
                        elif "recibid" in nombre and "pago" in nombre: tipo = "egresos_pago"
                        elif "nomina" in nombre or "nómina" in nombre: tipo = "nomina"
                        else:
                            no_clasificados.append(f_info["name"])
                            continue
                            
                        tipos_archivo[tipo].append(ArchivoDrive(f_info["name"], f_info["id"]))
                    
                    st.session_state['cache_archivos_drive'] = tipos_archivo
                    st.success(f"✅ Se clasificaron {sum(len(v) for v in tipos_archivo.values())} archivos desde Drive.")

            # Recuperar de caché si ya se sincronizó
            if 'cache_archivos_drive' in st.session_state:
                tipos_archivo = st.session_state['cache_archivos_drive']
                archivos_listos = True

        # ==========================================
        # MODO 1: CARGA LOCAL TRADICIONAL
        # ==========================================
        else:
            archivos_subidos = st.file_uploader("Sube tus reportes aquí (Excel/CSV/XLSB/Parquet)",
                                                type=['csv', 'xlsx', 'xls', 'xlsb', 'parquet'],
                                                accept_multiple_files=True)
            if archivos_subidos:
                for f in archivos_subidos:
                    nombre = f.name.lower()
                    if "timbrad" in nombre and "emitid" not in nombre:
                        timbrado_omitido = True
                        continue
                    
                    tipo = None
                    if "emitid" in nombre and "producto" not in nombre: tipo = "ingresos_facturas"
                    elif "cliente" in nombre and "pago" in nombre: tipo = "ingresos_pago"
                    elif "producto" in nombre and "emitid" not in nombre: tipo = "egresos_productos"
                    elif "recibid" in nombre and "pago" not in nombre: tipo = "egresos_facturas"
                    elif "recibid" in nombre and "pago" in nombre: tipo = "egresos_pago"
                    elif "nomina" in nombre or "nómina" in nombre: tipo = "nomina"
                    else:
                        no_clasificados.append(f.name)
                        continue
                        
                    tipos_archivo[tipo].append(f)
                archivos_listos = True

        # ==========================================
        # AVISOS Y ENRUTAMIENTO COMÚN
        # ==========================================
        if timbrado_omitido:
            st.warning("Archivos de Timbrado omitidos (operación bajo Flujo de Efectivo).")
        if no_clasificados:
            st.warning("Archivos ignorados (no clasificados): " + ", ".join(no_clasificados))

        if archivos_listos:
            def archivo_tipo(clave):
                arch_tipo = tipos_archivo[clave]
                if not arch_tipo: return None
                # Si hay más de 1, sin importar el modo, los agrupa automáticamente
                if len(arch_tipo) > 1: return _ArchivoGrupo(arch_tipo)
                return arch_tipo[-1]

            file_ingresos_facturas = archivo_tipo("ingresos_facturas")
            file_ingresos_pago = archivo_tipo("ingresos_pago")
            file_egresos_facturas = archivo_tipo("egresos_facturas")
            file_egresos_productos = archivo_tipo("egresos_productos")
            file_egresos_pago = archivo_tipo("egresos_pago")
            file_nomina = archivo_tipo("nomina")

            try:
                for archivos_tipo in tipos_archivo.values():
                    if len(archivos_tipo) > 1 or (
                        archivos_tipo and archivos_tipo[0].name.lower().endswith(".parquet")
                    ):
                        archivo = _ArchivoGrupo(archivos_tipo) if len(archivos_tipo) > 1 else archivos_tipo[0]
                        cargar_base(archivo)
            except (ArrowException, CalamineError, HttpError, OSError, UnicodeDecodeError, ValueError) as error:
                st.error(
                    "No se pudieron leer o combinar las partes de una base. Verifica que todos los archivos "
                    f"de cada tipo tengan las mismas columnas y sean válidos. Detalle: {error}"
                )
                st.stop()
            
            hay_archivos_ruteados = any(f is not None for f in (
                file_ingresos_facturas, file_ingresos_pago,
                file_egresos_facturas, file_egresos_pago, file_nomina))
        else:
            hay_archivos_ruteados = False
            file_ingresos_facturas = file_ingresos_pago = file_egresos_facturas = file_egresos_productos = file_egresos_pago = file_nomina = None

        if hay_archivos_ruteados:
            st.markdown("---")
            modulo = st.radio("Selecciona el Módulo:",
                              ["Dashboard Ejecutivo (Riesgo y Viabilidad)", "Ingresos (Auditoría Operativa)",
                               "Egresos (Auditoría Operativa)"])
        else:
            modulo = None

    if not hay_archivos_ruteados:
        st.success('''Bienvenido al Analizador Financiero.
        Haz clic en 'Sincronizar desde Google Drive' o arrastra los archivos para comenzar.''')
        st.stop()

    # Ventana móvil estándar de 5 años, común a todos los módulos.
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