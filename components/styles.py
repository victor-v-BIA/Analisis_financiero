# Styles for the main section and sidebar app

# components/styles.py


CSS_FUENTE_GLOBAL = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300..800;1,300..800&display=swap');
        html, body, [class*="css"] {
            font-family: 'Open Sans', sans-serif !important;
        }
    </style>
"""

CSS_PANTALLA_SELECCION = """
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        .container-bienvenida { text-align: center; margin: 0 auto; max-width: 900px; padding-top: 0.5rem; }
        .sub-bienvenida { color: #64748B; font-size: 1.1rem; margin-bottom: 2.5rem; }
        .card-role {
            background: white; border: 1px solid #1D4ED8; border-radius: 8px;
            padding: 32px 24px; text-align: center; height: 100%;
        }
        .bullet { text-align: left; font-size: 0.95rem; color: #475569; margin: 12px 0; }
    </style>
"""