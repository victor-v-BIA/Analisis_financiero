import io
import json
import os
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

def obtener_servicio_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None
    
    # 1. Prioridad Local: Buscar el archivo físico primero
    # (Asegúrate de que 'google_credentials.json' esté en la misma carpeta que app.py)
    if os.path.exists('google_credentials.json'):
        creds = service_account.Credentials.from_service_account_file('google_credentials.json', scopes=SCOPES)
        
    # 2. Prioridad Nube: Solo si NO hay archivo local
    else:
        try:
            # 🛑 TODO el bloque de secrets debe estar indentado dentro del "try"
            if "gcp_credentials" in st.secrets:
                creds_dict = dict(st.secrets["gcp_credentials"])
                creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception:
            # Si estamos en local y no hay secrets, fallará silenciosamente aquí
            pass
            
    # 3. Validación final
    if creds is None:
        raise FileNotFoundError("No se encontró 'google_credentials.json' en tu carpeta local, y tampoco hay secretos en la nube.")
        
    return build('drive', 'v3', credentials=creds)
def descargar_archivo_drive(file_id: str) -> bytes:
    """Descarga un archivo de Google Drive directamente a la memoria RAM"""
    servicio = obtener_servicio_drive()
    request = servicio.files().get_media(fileId=file_id)
    
    file_io = io.BytesIO()
    downloader = MediaIoBaseDownload(file_io, request)
    
    done = False
    while done is False:
        status, done = downloader.next_chunk()
            
    file_io.seek(0)
    return file_io.read()

def listar_archivos_carpeta(folder_id: str) -> list:
    """Obtiene el nombre y el ID de todos los archivos en la raíz de una carpeta de Drive."""
    servicio = obtener_servicio_drive()
    archivos = []
    page_token = None
    
    while True:
        # Filtra para buscar solo en la carpeta indicada y evitar carpetas anidadas
        query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        response = servicio.files().list(q=query,
                                         spaces='drive',
                                         fields='nextPageToken, files(id, name)',
                                         pageToken=page_token).execute()
        
        for file in response.get('files', []):
            archivos.append({"name": file.get("name"), "id": file.get("id")})
            
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
            
    return archivos