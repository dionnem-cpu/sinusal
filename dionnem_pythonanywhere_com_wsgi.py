import sys
import os

# ¡IMPORTANTE! RUTA DE TU PROYECTO ACTUALIZADA
# Reemplaza 'dionnem' con tu nombre de usuario de PythonAnywhere si es diferente.
project_home = '/home/dionnem/miapp/sinusal'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Añadir la ruta a la carpeta 'fonts' para ReportLab
fonts_path = os.path.join(project_home, 'fonts')
if fonts_path not in sys.path:
    sys.path.insert(0, fonts_path)

# Crear las carpetas necesarias si no existen
uploads_path = os.path.join(project_home, 'uploads')
indexed_texts_path = os.path.join(project_home, 'indexed_texts')
fonts_path = os.path.join(project_home, 'fonts')

# Crear directorios base
for path in [uploads_path, indexed_texts_path, fonts_path]:
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Directorio creado: {path}")

# ======================================================================
# ¡IMPORTANTE! CONFIGURAR LA CLAVE API DE GEMINI AQUÍ COMO VARIABLE DE ENTORNO
# ======================================================================
# Tu clave API de Gemini:
os.environ['GEMINI_API_KEY'] = 'AIzaSyDKbuiCDNwxVGuVSCb5kwMiwGRI99XUfjk'
# ======================================================================

# Configurar encoding para evitar problemas con caracteres especiales
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Importa tu aplicación Flask
from app import app as application

# Log de inicio para debug
print("=== WSGI INICIADO ===")
print(f"Proyecto: {project_home}")
print(f"Directorio uploads: {uploads_path}")
print(f"Directorio indexed_texts: {indexed_texts_path}")
print(f"API Key configurada: {'Sí' if os.environ.get('GEMINI_API_KEY') else 'No'}")
print("=====================")