# Punto de entrada principal (UI, Sidebar, Enrutador)
'''
El archivo raíz que inicializa Streamlit, configura la barra lateral para 
sincronizar archivos desde Google Drive o localmente (Lazy Loading),
aplica los estilos globales, enruta los módulos y maneja las funciones de control.
'''

import streamlit as st
from views.executive_view import (modulo_riesgo)
from views.income_view import (modulo_ingresos)
from views.expense_view import (modulo_egresos)

# 1. Importar estilos globales de tu archivo modular
from components.styles import  CSS_FUENTE_GLOBAL, CSS_PANTALLA_SELECCION
from config import CSS_TARJETAS_KPI

# 2. Inyectar estilos globales (Asegúrate de tener unsafe_allow_html=True en TODOS)
st.markdown(CSS_FUENTE_GLOBAL, unsafe_allow_html=True)

class ArchivoDrive:
    def __init__(self, name, id):
        self.name = name
        self.id = id
        
    def getvalue(self):
        return self
        
    def descargar(self):
        from drive_service import descargar_archivo_drive 
        return descargar_archivo_drive(self.id)

class ArchivoGrupoSeguro:
    def __init__(self, archivos):
        self.archivos = archivos
        self.name = archivos[-1].name if archivos else "grupo_archivos"

    def getvalue(self):
        return self.archivos

def _reiniciar_diagnostico() -> None:
    st.cache_data.clear()
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
    
def main() -> None:
    st.set_page_config(page_title="Facturación Emitida e Ingresos Corporativos", page_icon=":material/bar_chart:", layout="wide")
    st.markdown(CSS_TARJETAS_KPI, unsafe_allow_html=True)

    # INICIALIZACIÓN DE ESTADOS
    if 'regimen' not in st.session_state:
        st.session_state['regimen'] = None
    if 'paso_completado' not in st.session_state:
        st.session_state['paso_completado'] = False

    # ==================================================
    # PANTALLA 1: SELECCIÓN DE RÉGIMEN (Pantalla Completa)
    # ==================================================
    if st.session_state['regimen'] is None:
        
        # Inyectamos el CSS modular de la pantalla inicial
        st.markdown(CSS_PANTALLA_SELECCION, unsafe_allow_html=True)
        
        st.markdown("""
            <div class='container-bienvenida'>
                <h1 style='color: #0F172A; font-weight: 800; font-size: 2.5rem;'>Selecciona el tipo de contribuyente </h1>
                <p class='sub-bienvenida'>Para comenzar, necesitamos personalizar tus preferencias.</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.markdown("""
                <div style='text-align: center;'>
                    <div style='margin-bottom: 5px;'>
                        <img src='https://i.postimg.cc/rmKvZkg6/undraw-business-pitch-h9yw.png' alt='Persona Física' style='width: 180px; height: auto;'>
                    </div>
                    <h2 style='color: #1E3A8A; font-weight: 700; margin: 0;'>Persona Física</h2>
                    <p style='color: #64748B; font-size: 0.9rem; margin-bottom: 20px;'>Análisis simplificado</p>
                    <hr style='border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;'>
                    <div class='bullet'>1. Facturas Emitidas<br>2. Facturas Recibidas<br>3. Nómina de ingreso</div>
                </div>
                <br>
                """, unsafe_allow_html=True)
                if st.button("Elegir Persona Física", use_container_width=True, key="btn_pf"):
                    st.session_state['regimen'] = "Persona Física"
                    st.rerun()

        with col2:
            with st.container(border=True):
                st.markdown("""
                <div style='text-align: center;'>
                    <div style='margin-bottom: 5px;'>
                        <img src='https://i.postimg.cc/xT5qSGnN/undraw-charts-31si.png' alt='Persona Moral' style='width: 189px; height: auto;'>
                    </div>
                    <h2 style='color: #1E3A8A; font-weight: 700; margin: 0;'>Persona Moral</h2>
                    <p style='color: #64748B; font-size: 0.9rem; margin-bottom: 20px;'>Análisis integral</p>
                    <hr style='border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;'>
                    <div class='bullet'>1. Emitidos y Recibidos <br>2. Complementos de Pago <br>3. Nómina <br>4. Pagos Clientes (Operaciones con divisas, etc.) <br></div>
                </div>
                <br>
                """, unsafe_allow_html=True)
                if st.button("Elegir Persona Moral", use_container_width=True, key="btn_pm"):
                    st.session_state['regimen'] = "Persona Moral"
                    st.rerun()
            
        st.stop()


    # ==================================================
    # PANTALLA 2: BARRA LATERAL Y CARGA DE ARCHIVOS
    # ==================================================
    with st.sidebar:
        st.header("Carga de Datos")
        
        if st.session_state['regimen'] == "Persona Física":
            st.info("**Modo actual:** Persona Física")
        else:
            st.info("**Modo actual:** Persona Moral")
            
        if st.button("Cambiar Tipo de Contribuyente", key="btn_regresar"):
            _reiniciar_diagnostico()

        st.markdown("---")
        
        metodo_carga = st.toggle("Empresa con múltiples archivos (Usar Google Drive)", value=False)
        st.caption("Opcional: nombra el archivo histórico de Banxico con «FIX» o «Banxico» para usarlo como primera referencia cambiaria.")
        
        tipos_archivo = {
            "ingresos_facturas": [], "ingresos_pago": [], "egresos_facturas": [],
            "egresos_productos": [], "egresos_pago": [], "nomina": [], "fix": []
        }
        timbrado_omitido = False
        no_clasificados = []
        archivos_listos = False

        if metodo_carga:
            st.write("Conecta tu carpeta para tus reportes.")
            folder_id = st.text_input("ID de la carpeta de Drive:", placeholder="Ej. 1A2B3C4D5E...", key="drive_f_id")
            
            if st.button("Sincronizar Carpeta ", type="primary", disabled=not folder_id):
                with st.spinner("Buscando y clasificando en Drive..."):
                    from drive_service import listar_archivos_carpeta
                    archivos_en_drive = listar_archivos_carpeta(folder_id)
                    
                    for f_info in archivos_en_drive:
                        nombre = f_info["name"].lower()
                        if "timbrad" in nombre and "emitid" not in nombre:
                            timbrado_omitido = True
                            continue
                        
                        tipo = None
                        if nombre.startswith("fix") or "_fix" in nombre or "fix_" in nombre or "banxico" in nombre or "tipo de cambio" in nombre: tipo = "fix"
                        elif "emitid" in nombre and "producto" not in nombre: tipo = "ingresos_facturas"
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
                    st.session_state['paso_completado'] = True
                    st.success(f"✅ Se clasificaron {sum(len(v) for v in tipos_archivo.values())} archivos.")

            if 'cache_archivos_drive' in st.session_state:
                tipos_archivo = st.session_state['cache_archivos_drive']
                archivos_listos = True

        else:
            archivos_subidos = st.file_uploader("Sube tus reportes aquí (Excel/CSV/XLSB/Parquet)",
                                                type=['csv', 'xlsx', 'xls', 'xlsb', 'parquet', 'pqt'],
                                                accept_multiple_files=True)
            if archivos_subidos:
                for f in archivos_subidos:
                    nombre = f.name.lower()
                    if "timbrad" in nombre and "emitid" not in nombre:
                        timbrado_omitido = True
                        continue
                    
                    tipo = None
                    if nombre.startswith("fix") or "_fix" in nombre or "fix_" in nombre or "banxico" in nombre or "tipo de cambio" in nombre: tipo = "fix"
                    elif "emitid" in nombre and "producto" not in nombre: tipo = "ingresos_facturas"
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
                st.session_state['paso_completado'] = True

        if st.button("Limpiar Diagnóstico y Reiniciar"):
            _reiniciar_diagnostico()

        if timbrado_omitido:
            st.warning("Archivos de Timbrado omitidos.")
        if no_clasificados:
            st.warning("Archivos ignorados: " + ", ".join(no_clasificados))

        if archivos_listos:
            def archivo_tipo(clave):
                arch_tipo = tipos_archivo.get(clave, [])
                if not arch_tipo: return None
                if len(arch_tipo) > 1: return ArchivoGrupoSeguro(arch_tipo)
                return arch_tipo[-1]

            file_ingresos_facturas = archivo_tipo("ingresos_facturas")
            file_ingresos_pago = archivo_tipo("ingresos_pago")
            file_egresos_facturas = archivo_tipo("egresos_facturas")
            file_egresos_productos = archivo_tipo("egresos_productos")
            file_egresos_pago = archivo_tipo("egresos_pago")
            file_nomina = archivo_tipo("nomina")
            file_fix = archivo_tipo("fix")
            
            hay_archivos_ruteados = any(f is not None for f in (
                file_ingresos_facturas, file_ingresos_pago,
                file_egresos_facturas, file_egresos_productos,
                file_egresos_pago, file_nomina))
        else:
            hay_archivos_ruteados = False
            file_ingresos_facturas = file_ingresos_pago = file_egresos_facturas = file_egresos_productos = file_egresos_pago = file_nomina = file_fix = None

        if hay_archivos_ruteados:
            modulo = st.radio("Módulo a Analizar:",
                              ["Dashboard Ejecutivo (Riesgo y Viabilidad)", "Ingresos (Auditoría Operativa)",
                               "Egresos (Auditoría Operativa)"])
        else:
            modulo = None

    # ==================================================
    # ZONA CENTRAL (Esperando carga o mostrando gráficos)
    # ==================================================
    if not hay_archivos_ruteados:
        st.success(f"Has seleccionado **{st.session_state['regimen']}**. Utiliza la barra lateral para subir o sincronizar tus reportes y comenzar.")
        st.stop()

    # ENRUTAMIENTO FINAL
    if modulo == "Dashboard Ejecutivo (Riesgo y Viabilidad)":
        modulo_riesgo(file_ingresos_facturas, file_ingresos_pago, file_egresos_facturas,
                      file_egresos_pago, file_nomina, file_egresos_productos=file_egresos_productos,
                      file_fix=file_fix)
    elif modulo == "Ingresos (Auditoría Operativa)":
        modulo_ingresos(file_ingresos_facturas, file_ingresos_pago, None,
                        file_egresos_facturas, file_egresos_pago, file_nomina)
    else:
        modulo_egresos(file_egresos_facturas, file_egresos_pago, file_nomina, None,
                       file_ingresos_facturas, file_egresos_productos=file_egresos_productos)

if __name__ == "__main__":
    main()