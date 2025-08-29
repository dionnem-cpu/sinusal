import os
import json
from flask import Flask, request, render_template, send_file, jsonify
from flask_cors import CORS
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.google_genai.base import GoogleGenAI
from llama_index.embeddings.google_genai.base import GoogleGenAIEmbedding
import PyPDF2
from io import BytesIO
from reportlab.pdfgen import canvas
import unicodedata
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase import ttfonts
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
import re
from dotenv import load_dotenv
from datetime import datetime
import hashlib

# Configurar la codificación de la consola a UTF-8 al inicio
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 IMPORTANTE: Cargar la clave de API de Gemini desde una variable de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ADVERTENCIA: La clave de API de Gemini no está configurada como variable de entorno.")
    print("Asegúrate de establecer la variable de entorno 'GEMINI_API_KEY' en un archivo .env o en el entorno del sistema.")

# Asegurarse de que los directorios necesarios existan
UPLOAD_FOLDER = "uploads"
INDEXED_TEXTS_FOLDER = "indexed_texts"
FONTS_FOLDER = "fonts" # Carpeta para almacenar archivos de fuentes TTF
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INDEXED_TEXTS_FOLDER, exist_ok=True)
os.makedirs(FONTS_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["INDEXED_TEXTS_FOLDER"] = INDEXED_TEXTS_FOLDER
app.config["FONTS_FOLDER"] = FONTS_FOLDER

# --- Configuración de fuente Unicode para ReportLab ---
FONT_NAME = "DejaVuSans"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FONT_PATH = os.path.join(BASE_DIR, app.config["FONTS_FOLDER"], f"{FONT_NAME}.ttf")
FINAL_FONT_NAME = "Helvetica"

try:
    if os.path.exists(FONT_PATH):
        pdfmetrics.registerFont(ttfonts.TTFont(FONT_NAME, FONT_PATH))
        pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME)
        print(f"Fuente '{FONT_NAME}' registrada exitosamente desde '{FONT_PATH}'.")
        FINAL_FONT_NAME = FONT_NAME
    else:
        print(f"ADVERTENCIA: El archivo de fuente no se encontró en '{FONT_PATH}'.")
        print(f"Se utilizará la fuente de fallback '{FINAL_FONT_NAME}'.")
except Exception as e:
    print(f"ERROR: No se pudo registrar la fuente '{FONT_NAME}' desde '{FONT_PATH}'.")
    print(f"Se utilizará la fuente de fallback '{FINAL_FONT_NAME}'.")
    print(f"Detalles del error: {e}")

# --- Encabezado/Pie de página (configurable) ---
CLINIC_NAME = os.getenv("CLINIC_NAME", "CliniKa AI")
CLINIC_SUBTITLE = os.getenv("CLINIC_SUBTITLE", "Informe Médico")
DR_NAME = os.getenv("DR_NAME", "Dr. Rodolfo Gutiérrez Caro")
DR_SPECIALTY = os.getenv("DR_SPECIALTY", "Cardiología")
DR_COLEGIADO = os.getenv("DR_COLEGIADO", "")
CONTACT_INFO = os.getenv("CONTACT_INFO", "info@clinika-ai.com • +34 000 000 000")

def draw_header_footer(canvas_obj, page_num=1):
    """Dibuja membrete y pie en cada página."""
    try:
        # Dimensiones y márgenes
        width, height = canvas_obj._pagesize
        MARGIN_LEFT = 72
        MARGIN_RIGHT = width - 72
        TOP_Y = height - 40
        BOTTOM_Y = 50

        # MEMBRETE/ENCABEZADO
        canvas_obj.saveState()

        # Título principal de la clínica
        canvas_obj.setFont(FINAL_FONT_NAME, 14)  # Más grande para el título
        canvas_obj.setFillColorRGB(0, 0, 0.5)    # Color azul oscuro
        canvas_obj.drawString(MARGIN_LEFT, TOP_Y, CLINIC_NAME)

        # Subtítulo
        if CLINIC_SUBTITLE:
            canvas_obj.setFont(FINAL_FONT_NAME, 10)
            canvas_obj.setFillColorRGB(0, 0, 0)  # Negro
            canvas_obj.drawString(MARGIN_LEFT, TOP_Y - 16, CLINIC_SUBTITLE)

        # Información del médico a la derecha
        x_right = MARGIN_RIGHT
        y_right = TOP_Y
        canvas_obj.setFont(FINAL_FONT_NAME, 9)
        canvas_obj.setFillColorRGB(0, 0, 0)  # Negro

        if DR_NAME:
            canvas_obj.drawRightString(x_right, y_right, DR_NAME)
            y_right -= 12
        if DR_SPECIALTY:
            canvas_obj.drawRightString(x_right, y_right, DR_SPECIALTY)
            y_right -= 12
        if DR_COLEGIADO:
            canvas_obj.drawRightString(x_right, y_right, DR_COLEGIADO)

        # Línea separadora superior
        canvas_obj.setStrokeColorRGB(0.3, 0.3, 0.3)  # Gris
        canvas_obj.setLineWidth(1)
        canvas_obj.line(MARGIN_LEFT, TOP_Y - 30, MARGIN_RIGHT, TOP_Y - 30)

        canvas_obj.restoreState()

        # PIE DE PÁGINA
        canvas_obj.saveState()

        # Línea separadora inferior
        canvas_obj.setStrokeColorRGB(0.3, 0.3, 0.3)
        canvas_obj.setLineWidth(1)
        canvas_obj.line(MARGIN_LEFT, BOTTOM_Y + 15, MARGIN_RIGHT, BOTTOM_Y + 15)

        # Información de contacto centrada
        canvas_obj.setFont(FINAL_FONT_NAME, 8)
        canvas_obj.setFillColorRGB(0.4, 0.4, 0.4)  # Gris oscuro
        canvas_obj.drawCentredString(width / 2, BOTTOM_Y, CONTACT_INFO)

        # Número de página
        canvas_obj.setFont(FINAL_FONT_NAME, 8)
        canvas_obj.drawCentredString(width / 2, BOTTOM_Y - 12, f"Página {page_num}")

        canvas_obj.restoreState()

    except Exception as e:
        # Si algo falla, dibujar algo básico
        print(f"ADVERTENCIA: fallo al dibujar membrete/pie: {e}")
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.drawString(72, height - 40, "Informe Médico")
        canvas_obj.drawCentredString(width / 2, 50, f"Página {page_num}")

# Variables globales para almacenar el motor de consulta de LlamaIndex y el contexto del paciente
global_active_patient_id = None
global_query_engine = None
global_patient_data = {}

def generate_soap_hash(soap_data):
    """Genera un hash único para un reporte SOAP basado en su contenido principal."""
    content_for_hash = {
        'patient_id': soap_data.get('patient_id', ''),
        'fecha_consulta': soap_data.get('fecha_consulta', ''),
        'subjective': soap_data.get('subjective', '').strip(),
        'objective': soap_data.get('objective', '').strip(),
        'assessment': soap_data.get('assessment', '').strip(),
        'plan': soap_data.get('plan', '').strip()
    }

    content_string = json.dumps(content_for_hash, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content_string.encode('utf-8')).hexdigest()

def check_soap_duplicate(patient_id, soap_hash):
    """Verifica si ya existe un SOAP con el mismo hash."""
    patient_dir = get_patient_directory(patient_id)

    for filename in os.listdir(patient_dir):
        if filename.startswith("SOAP_Report_") and filename.endswith(".json"):
            filepath = os.path.join(patient_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing_soap = json.load(f)
                    if existing_soap.get('soap_hash') == soap_hash:
                        return True, filename
            except Exception as e:
                print(f"Error al leer archivo SOAP {filepath}: {e}")
                continue

    return False, None

def extraer_texto_pdf(ruta):
    """Extrae texto de un archivo PDF dado su ruta."""
    text = ""
    try:
        reader = PyPDF2.PdfReader(ruta)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    except Exception as e:
        print(f"Error al extraer texto del PDF {ruta}: {e}")
        raise
    return text

def extract_patient_data_from_text(text_content):
    """Extrae datos del paciente del contenido del texto incluyendo ID, nombre, edad y antecedentes."""
    cleaned_text = re.sub(r'\s+', ' ', text_content).lower()
    patient_data = {}

    # Patrones para ID
    id_patterns = [
        r"(?:cédula|cedula|id|identificación|dni|nro expediente|número expediente)[:\s]*([0-9]{7,9})",
        r"(?:paciente|cédula)\s*([0-9]{7,9})",
        r"id[:\s]*([a-zA-Z0-9\-\.]+)",
    ]

    for pattern in id_patterns:
        match = re.search(pattern, cleaned_text)
        if match:
            patient_data['id'] = match.group(1).strip().upper()
            break

    # Patrones para nombre
    name_patterns = [
        r"(?:nombre|paciente)[:\s]*([a-záéíóúñ\s]+?)(?:\n|edad|años|cédula|id)",
        r"^([a-záéíóúñ\s]+?)(?:\n|edad|años|cédula|id)",
        r"(?:sr\.|sra\.|señor|señora|sr|sra)[:\s]*([a-záéíóúñ\s]+?)(?:\n|edad|años|cédula|id)",
    ]

    for pattern in name_patterns:
        match = re.search(pattern, cleaned_text, re.MULTILINE)
        if match:
            name = match.group(1).strip().title()
            if len(name) > 3 and not re.search(r'\d', name):
                patient_data['nombre'] = name
                break

    # Patrones para edad
    age_patterns = [
        r"(?:edad|años)[:\s]*(\d{1,3})",
        r"(\d{1,3})\s*años",
        r"de\s*(\d{1,3})\s*años",
    ]

    for pattern in age_patterns:
        match = re.search(pattern, cleaned_text)
        if match:
            age = int(match.group(1))
            if 0 <= age <= 120:
                patient_data['edad'] = age
                break

    # Patrones para antecedentes médicos
    antecedentes_patterns = [
        r"(?:antecedentes|historial médico|historia clínica)[:\s]*([^\.]+(?:\.[^\.]*){0,3})",
        r"(?:diagnósticos previos|enfermedades previas)[:\s]*([^\.]+(?:\.[^\.]*){0,3})",
        r"(?:medicamentos|tratamientos)[:\s]*([^\.]+(?:\.[^\.]*){0,3})",
    ]

    antecedentes_found = []
    for pattern in antecedentes_patterns:
        matches = re.finditer(pattern, cleaned_text, re.IGNORECASE)
        for match in matches:
            antecedente = match.group(1).strip()
            if len(antecedente) > 10:
                antecedentes_found.append(antecedente)

    if antecedentes_found:
        patient_data['antecedentes'] = '; '.join(antecedentes_found[:3])

    return patient_data

def save_patient_data(patient_id, patient_data):
    """Guarda los datos del paciente en un archivo JSON."""
    patient_dir = get_patient_directory(patient_id)
    patient_data_file = os.path.join(patient_dir, "patient_data.json")

    try:
        existing_data = {}
        if os.path.exists(patient_data_file):
            with open(patient_data_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)

        for key, value in patient_data.items():
            if value:
                existing_data[key] = value

        with open(patient_data_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        print(f"Datos del paciente guardados en: {patient_data_file}")
        return existing_data
    except Exception as e:
        print(f"Error al guardar datos del paciente: {e}")
        return patient_data

def load_patient_data(patient_id):
    """Carga los datos del paciente desde el archivo JSON."""
    patient_dir = get_patient_directory(patient_id)
    patient_data_file = os.path.join(patient_dir, "patient_data.json")

    try:
        if os.path.exists(patient_data_file):
            with open(patient_data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error al cargar datos del paciente: {e}")

    return {}

def format_patient_info(patient_data):
    """Formatea la información del paciente para mostrar en respuestas."""
    if not patient_data:
        return ""

    info_parts = []

    if patient_data.get('id'):
        info_parts.append(f"ID: {patient_data['id']}")

    if patient_data.get('nombre'):
        info_parts.append(f"Nombre: {patient_data['nombre']}")

    if patient_data.get('edad'):
        info_parts.append(f"Edad: {patient_data['edad']} años")

    if patient_data.get('antecedentes'):
        info_parts.append(f"Antecedentes: {patient_data['antecedentes']}")

    if info_parts:
        return "DATOS DEL PACIENTE:\n" + "\n".join(info_parts) + "\n" + "-"*50

    return ""

def clean_duplicate_patient_data(text):
    """Elimina duplicaciones de datos del paciente en el texto."""
    import re

    pattern = r'DATOS DEL PACIENTE:\s*\n(?:(?:ID|Nombre|Edad|Antecedentes):[^\n]*\n)*-{10,}'
    matches = list(re.finditer(pattern, text, re.MULTILINE))

    if len(matches) > 1:
        cleaned_text = text
        for match in reversed(matches[1:]):
            cleaned_text = cleaned_text[:match.start()] + cleaned_text[match.end():]
        return cleaned_text.strip()

    return text

def is_patient_data_in_text(text, patient_data):
    """Verifica si los datos del paciente ya están incluidos en el texto de respuesta."""
    if not patient_data or not text:
        return False

    text_lower = text.lower()

    if "datos del paciente" in text_lower:
        return True

    fields_found = 0

    if patient_data.get('id') and patient_data['id'].lower() in text_lower:
        fields_found += 1

    if patient_data.get('nombre') and patient_data['nombre'].lower() in text_lower:
        fields_found += 1

    if patient_data.get('edad') and str(patient_data['edad']) in text:
        fields_found += 1

    return fields_found >= 2

def clean_document_content(content, patient_id):
    """Limpia el contenido del documento eliminando duplicaciones de datos del paciente."""
    import re

    pattern = r'DATOS DEL PACIENTE:\s*\n(?:(?:ID|Nombre|Edad|Antecedentes):[^\n]*\n)*-{10,}'
    matches = list(re.finditer(pattern, content, re.MULTILINE))

    if len(matches) > 1:
        cleaned_content = content
        for match in reversed(matches[1:]):
            cleaned_content = cleaned_content[:match.start()] + cleaned_content[match.end():]
        content = cleaned_content.strip()

    return content

def extract_patient_id_from_text(text_content):
    """Intenta extraer el ID del paciente del contenido del texto."""
    cleaned_text = re.sub(r'\s+', ' ', text_content).lower()

    patterns = [
        r"(?:cédula|cedula|id|identificación|dni|nro expediente|número expediente)[:\s]*([0-9]{7,9})",
        r"(?:paciente|cédula)\s*([0-9]{7,9})",
        r"id[:\s]*([a-zA-Z0-9\-\.]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned_text)
        if match:
            extracted_id = match.group(1).strip().upper()
            print(f"DEBUG: ID extraído del texto: '{extracted_id}' usando patrón: '{pattern}'")
            return extracted_id
    print("DEBUG: No se encontró un ID de paciente en el contenido del texto.")
    return None

def extract_patient_id_from_filename(filename):
    """Extrae un ID de paciente del nombre del archivo."""
    name_without_ext = os.path.splitext(filename)[0]

    match = re.search(r'([0-9]{7,9})', name_without_ext)
    if match:
        extracted_id = match.group(1).strip().upper()
        print(f"DEBUG: ID extraído del nombre del archivo (numérico): '{extracted_id}'")
        return extracted_id

    parts = name_without_ext.split('_')
    if len(parts) > 0:
        potential_id_part = parts[0].split('-')[0]
        if potential_id_part:
            extracted_id = potential_id_part.strip().upper()
            print(f"DEBUG: ID extraído del nombre del archivo (general): '{extracted_id}'")
            return extracted_id

    print("DEBUG: No se encontró un ID de paciente en el nombre del archivo.")
    return "DESCONOCIDO"

def get_patient_directory(patient_id):
    """Crea y retorna el directorio del paciente dentro de indexed_texts."""
    if not patient_id or patient_id == "DESCONOCIDO":
        patient_id = "DESCONOCIDO"

    patient_dir = os.path.join(app.config["INDEXED_TEXTS_FOLDER"], patient_id)
    os.makedirs(patient_dir, exist_ok=True)
    return patient_dir

def load_patient_documents(patient_id):
    """Carga todos los documentos de un paciente específico, eliminando duplicaciones."""
    documents = []
    patient_dir = get_patient_directory(patient_id)

    print(f"\nCargando documentos del paciente '{patient_id}' desde: {patient_dir}")

    if not os.path.exists(patient_dir):
        print(f"ADVERTENCIA: La carpeta del paciente '{patient_dir}' no existe.")
        return []

    txt_files = [f for f in os.listdir(patient_dir) if f.endswith(".txt")]
    txt_files.sort(key=lambda x: os.path.getmtime(os.path.join(patient_dir, x)), reverse=True)

    for filename in txt_files:
        filepath = os.path.join(patient_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    cleaned_content = clean_document_content(content, patient_id)

                    metadata = {
                        "filename": filename,
                        "patient_id": patient_id,
                        "filepath": filepath,
                        "modification_date": os.path.getmtime(filepath)
                    }

                    if "SOAP_Report_" in filename:
                        metadata["document_type"] = "soap_report"
                    else:
                        metadata["document_type"] = "medical_document"

                    doc_to_add = Document(
                        text=cleaned_content,
                        metadata=metadata
                    )
                    documents.append(doc_to_add)
                    print(f"  - Documento cargado: '{filename}' (tipo: {metadata['document_type']}) para paciente '{patient_id}'")
        except Exception as e:
            print(f"Error al cargar documento {filepath}: {e}")

    print(f"Total de documentos cargados para paciente '{patient_id}': {len(documents)}")
    return documents

def initialize_patient_query_engine(patient_id):
    """Inicializa el motor de consulta para un paciente específico."""
    global global_query_engine, global_active_patient_id, global_patient_data

    if not patient_id or patient_id == "DESCONOCIDO":
        print("No se puede inicializar motor de consulta sin un ID de paciente válido.")
        global_query_engine = None
        global_active_patient_id = None
        global_patient_data = {}
        return False

    # CAMBIO PRINCIPAL: Siempre cargar documentos y reconstruir índice
    # Eliminamos la validación que causaba el problema de no actualizar el índice
    print(f"Inicializando/actualizando motor de consulta para paciente '{patient_id}'...")
    
    patient_documents = load_patient_documents(patient_id)

    if not patient_documents:
        print(f"No se encontraron documentos para el paciente '{patient_id}'.")
        global_query_engine = None
        global_active_patient_id = None
        global_patient_data = {}
        return False

    try:
        if not GEMINI_API_KEY:
            raise ValueError("La clave de API de Gemini no está configurada.")

        llm = GoogleGenAI(api_key=GEMINI_API_KEY, model="gemini-1.5-flash")
        Settings.llm = llm

        embed_model = GoogleGenAIEmbedding(api_key=GEMINI_API_KEY, model_name="models/text-embedding-004")
        Settings.embed_model = embed_model

        # CAMBIO: Siempre reconstruir el índice con todos los documentos
        print(f"Reconstruyendo índice vectorial para paciente '{patient_id}' con {len(patient_documents)} documentos...")
        index = VectorStoreIndex.from_documents(patient_documents)
        global_query_engine = index.as_query_engine()
        global_active_patient_id = patient_id

        global_patient_data = load_patient_data(patient_id)

        print(f"✓ Motor de consulta actualizado exitosamente para paciente '{patient_id}' con {len(patient_documents)} documentos.")
        return True

    except Exception as e:
        print(f"ERROR: No se pudo inicializar el motor de consulta para el paciente '{patient_id}': {e}")
        import traceback
        traceback.print_exc()
        global_query_engine = None
        global_active_patient_id = None
        global_patient_data = {}
        return False

def list_available_patients():
    """Lista todos los pacientes disponibles en el sistema con sus datos."""
    patients = []
    indexed_folder = app.config["INDEXED_TEXTS_FOLDER"]

    if os.path.exists(indexed_folder):
        for item in os.listdir(indexed_folder):
            patient_path = os.path.join(indexed_folder, item)
            if os.path.isdir(patient_path):
                txt_files = [f for f in os.listdir(patient_path) if f.endswith('.txt')]
                if txt_files:
                    patient_data = load_patient_data(item)
                    patients.append({
                        'id': item,
                        'document_count': len(txt_files),
                        'documents': txt_files,
                        'nombre': patient_data.get('nombre', 'Sin nombre'),
                        'edad': patient_data.get('edad', 'Sin edad'),
                        'antecedentes': patient_data.get('antecedentes', 'Sin antecedentes registrados')
                    })

    return patients

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

def analizar_y_categorizar_texto(texto):
    """Aplica NLP sobre el texto clínico para extraer estructura semántica."""
    texto_limpio = clean_duplicate_patient_data(texto)

    prompt = (
        "Eres un asistente médico experto. A partir del siguiente texto clínico, "
        "haz lo siguiente:\n\n"
        "- Enumera las principales entidades médicas encontradas (síntomas, diagnósticos, medicamentos, pruebas).\n"
        "- Clasifica el texto por especialidades médicas involucradas.\n"
        "- Resume el tema principal del documento en 1-2 frases.\n"
        "- NO incluyas ni repitas los datos básicos del paciente (ID, nombre, edad) ya que estos se manejan por separado.\n\n"
        f"Texto clínico:\n{texto_limpio[:2000]}"
    )
    try:
        if not GEMINI_API_KEY:
            return "No se pudo realizar el análisis NLP: API key no configurada."

        llm = GoogleGenAI(api_key=GEMINI_API_KEY, model="gemini-1.5-flash")
        response = llm.complete(prompt)
        return response.text
    except Exception as e:
        print(f"Error al llamar a la API de Gemini para análisis NLP: {e}")
        return "No se pudo realizar el análisis NLP debido a un error."

@app.route("/procesar", methods=["POST"])
def procesar():
    global global_patient_data

    if 'documento' not in request.files:
        return jsonify({"mensaje": "No se ha subido ningún archivo"}), 400

    archivo = request.files["documento"]

    if not archivo.filename:
        return jsonify({"mensaje": "Nombre de archivo vacío"}), 400

    ruta_archivo = os.path.join(app.config["UPLOAD_FOLDER"], archivo.filename)
    try:
        archivo.save(ruta_archivo)
    except Exception as e:
        print(f"Error al guardar el archivo subido: {e}")
        return jsonify({"mensaje": f"Error al guardar el archivo: {e}"}), 500

    texto_extraido = ""
    if archivo.filename.lower().endswith(".pdf"):
        texto_extraido = extraer_texto_pdf(ruta_archivo)
    else:
        try:
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                texto_extraido = f.read()
        except Exception as e:
            print(f"Error al leer el archivo de texto: {e}")
            return jsonify({"mensaje": f"Error al leer el archivo de texto: {e}"}), 500

    texto_extraido_normalizado = unicodedata.normalize('NFKD', texto_extraido).encode('ascii', 'ignore').decode('utf-8')

    patient_data = extract_patient_data_from_text(texto_extraido_normalizado)

    if not patient_data.get('id'):
        patient_id = extract_patient_id_from_filename(archivo.filename)
        patient_data['id'] = patient_id

    patient_id = patient_data.get('id', 'DESCONOCIDO')

    print(f"\n--- Depuración de Procesamiento de Documento ---")
    print(f"Archivo subido: '{archivo.filename}'")
    print(f"Datos del paciente extraídos: {patient_data}")
    print(f"Texto extraído del archivo (primeros 200 caracteres):")
    print(texto_extraido_normalizado[:200])
    print("-" * 50)

    patient_dir = get_patient_directory(patient_id)
    indexed_text_filename_base = os.path.splitext(archivo.filename)[0]
    indexed_text_filepath = os.path.join(patient_dir, f"{indexed_text_filename_base}.txt")

    try:
        with open(indexed_text_filepath, "w", encoding="utf-8") as f:
            f.write(texto_extraido_normalizado)
        print(f"Texto guardado en directorio del paciente: '{indexed_text_filepath}'")
    except Exception as e:
        print(f"Error al guardar el texto extraído: {e}")
        return jsonify({"mensaje": f"Error al guardar el documento: {e}"}), 500

    saved_patient_data = save_patient_data(patient_id, patient_data)

    # CAMBIO: Forzar actualización del índice después de procesar documento
    if not initialize_patient_query_engine(patient_id):
        print(f"ADVERTENCIA: No se pudo inicializar/actualizar el motor de consulta para el paciente '{patient_id}'")

    analisis_nlp = analizar_y_categorizar_texto(texto_extraido_normalizado)
    print("Análisis NLP:")
    print(analisis_nlp)

    try:
        os.remove(ruta_archivo)
    except Exception as e:
        print(f"Error al eliminar el archivo temporal {ruta_archivo}: {e}")

    return jsonify({
        "mensaje": f"Documento procesado para paciente ID: {patient_id}",
        "analisis_nlp": analisis_nlp,
        "patient_id": patient_id,
        "patient_data": saved_patient_data,
        "patient_directory": patient_dir
    }), 200

@app.route("/patients", methods=["GET"])
def get_patients():
    """Endpoint para obtener lista de pacientes disponibles."""
    patients = list_available_patients()
    return jsonify({"patients": patients})

@app.route("/switch_patient", methods=["POST"])
def switch_patient():
    """Endpoint para cambiar el contexto a otro paciente."""
    data = request.json
    patient_id = data.get("patient_id", "")

    if not patient_id:
        return jsonify({"error": "ID de paciente requerido"}), 400

    patient_dir = get_patient_directory(patient_id)
    if not os.path.exists(patient_dir):
        return jsonify({"error": f"Paciente '{patient_id}' no encontrado"}), 404

    if initialize_patient_query_engine(patient_id):
        return jsonify({
            "message": f"Contexto cambiado al paciente '{patient_id}'",
            "patient_id": patient_id,
            "patient_data": global_patient_data
        })
    else:
        return jsonify({"error": f"No se pudo inicializar el contexto para el paciente '{patient_id}'"}), 500

@app.route("/chat", methods=["POST"])
def chat():
    global global_query_engine, global_active_patient_id, global_patient_data

    data = request.json
    user_message = data.get("message", "")
    chat_history = data.get("chat_history", [])
    current_patient_id = data.get("current_patient_id", None)

    if not user_message:
        return jsonify({"response": "Mensaje vacío."}), 400

    print(f"DEBUG: Mensaje de usuario recibido: {user_message}")
    print(f"DEBUG: ID de paciente actual: {current_patient_id}")
    print(f"DEBUG: ID de paciente activo globalmente: {global_active_patient_id}")

    if current_patient_id and current_patient_id != global_active_patient_id:
        print(f"Cambiando contexto de paciente de '{global_active_patient_id}' a '{current_patient_id}'")
        if not initialize_patient_query_engine(current_patient_id):
            return jsonify({
                "response": f"Error: No se pudo cargar el contexto del paciente '{current_patient_id}'. Verifica que existan documentos para este paciente."
            }), 500

    if global_query_engine is None:
        available_patients = list_available_patients()
        if available_patients:
            patient_list = ", ".join([p['id'] for p in available_patients])
            return jsonify({
                "response": f"No hay un paciente activo. Pacientes disponibles: {patient_list}. Sube un documento o especifica un ID de paciente."
            }), 503
        else:
            return jsonify({
                "response": "El chatbot no está disponible. Por favor, procesa un documento primero."
            }), 503

    try:
        # Detectar si es solicitud de informe ANTES de construir el prompt
        is_report_request = (
            "informe" in user_message.lower() or
            "resumen estructurado" in user_message.lower() or
            "formato soap" in user_message.lower() or
            "reporte" in user_message.lower() or
            "informe médico" in user_message.lower()
        )

        context_prompt_parts = []
        context_prompt_parts.append("Eres un asistente médico virtual experto y útil. Tu objetivo es responder preguntas sobre documentos clínicos.")
        context_prompt_parts.append("Es ABSOLUTAMENTE CRUCIAL que SIEMPRE respondas en español.")

        if global_active_patient_id and global_patient_data:
            patient_info = format_patient_info(global_patient_data)
            if patient_info:
                context_prompt_parts.append(f"\nCONTEXTO DEL PACIENTE (para tu referencia interna):")
                context_prompt_parts.append(patient_info)
                context_prompt_parts.append("INSTRUCCIONES IMPORTANTES:")
                context_prompt_parts.append("- Utiliza esta información para personalizar y contextualizar tu respuesta")

                if is_report_request:
                    context_prompt_parts.append("- Para informes médicos, INCLUYE los datos del paciente al inicio de tu respuesta")
                    context_prompt_parts.append("- Usa el formato: DATOS DEL PACIENTE: seguido de ID, Nombre, Edad, Antecedentes")
                else:
                    context_prompt_parts.append("- Para respuestas generales, incluye datos del paciente solo si es relevante para la pregunta")
                    context_prompt_parts.append("- NO dupliques innecesariamente los datos del paciente")

        if global_active_patient_id:
            context_prompt_parts.append(f"Estás trabajando específicamente con los documentos del paciente ID: {global_active_patient_id}")
            context_prompt_parts.append(f"TODA la información que proporciones debe ser exclusivamente de este paciente.")
            context_prompt_parts.append(f"Si no encuentras información específica para este paciente, indícalo claramente.")

        context_prompt_parts.append("Considera el historial de conversación para dar respuestas coherentes y contextualizadas.")

        context_prompt_parts.append("\n--- Historial de Conversación ---")
        for chat_entry in chat_history:
            if chat_entry['sender'] == 'user':
                context_prompt_parts.append(f"Usuario: {chat_entry['message']}")
            elif chat_entry['sender'] == 'ai':
                context_prompt_parts.append(f"Asistente: {chat_entry['message']}")

        context_prompt_parts.append(f"\n--- Nueva Pregunta del Usuario ---")
        context_prompt_parts.append(f"Usuario: {user_message}")
        context_prompt_parts.append("Asistente:")

        full_prompt = "\n".join(context_prompt_parts)

        if is_report_request:
            final_query_prompt = (
                f"{full_prompt}\n\nPor favor, genera un informe estructurado en formato SOAP "
                "(Subjetivo, Objetivo, Evaluación, Plan) basado EXCLUSIVAMENTE en la información "
                f"disponible del paciente {global_active_patient_id}. "
                "IMPORTANTE: Comienza el informe con los datos del paciente (ID, nombre, edad, antecedentes). "
                "Utiliza los encabezados 'Subjetivo:', 'Objetivo:', 'Evaluación:' y 'Plan:' UNA SOLA VEZ."
            )
            print(f"DEBUG: Generando informe SOAP para paciente '{global_active_patient_id}'")
        else:
            final_query_prompt = full_prompt
            print(f"DEBUG: Generando respuesta para paciente '{global_active_patient_id}'")

        respuesta = global_query_engine.query(final_query_prompt)
        texto_respuesta = str(respuesta)

        if global_patient_data and global_active_patient_id:
            if is_report_request:
                if not is_patient_data_in_text(texto_respuesta, global_patient_data):
                    patient_info_header = format_patient_info(global_patient_data)
                    if patient_info_header:
                        texto_respuesta = patient_info_header + "\n\n" + texto_respuesta
                        print("DEBUG: Datos del paciente agregados al inicio del informe")
            else:
                if not is_patient_data_in_text(texto_respuesta, global_patient_data):
                    if len(texto_respuesta.strip()) < 100 or "paciente" not in texto_respuesta.lower():
                        patient_info_header = format_patient_info(global_patient_data)
                        if patient_info_header:
                            texto_respuesta = patient_info_header + "\n\n" + texto_respuesta
                            print("DEBUG: Datos del paciente agregados a respuesta corta")

        texto_respuesta = clean_duplicate_patient_data(texto_respuesta)

        if global_active_patient_id:
            texto_respuesta += f"\n\n---\n*Información basada en documentos del paciente: {global_active_patient_id}*"

        print(f"DEBUG: Respuesta final generada para paciente '{global_active_patient_id}': {texto_respuesta[:150]}...")
        return jsonify({
            "response": texto_respuesta,
            "active_patient_id": global_active_patient_id,
            "patient_data": global_patient_data
        })

    except Exception as e:
        print(f"ERROR al procesar el mensaje del chat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response": f"Error al procesar tu mensaje. Detalles: {e}"}), 500

# FUNCIONES NECESARIAS PARA PDF
# Variable global para trackear posición Y en PDF
pdf_last_y_position = 0

def process_markdown_text(text):
    """Procesa texto con markdown simple para convertir **texto** en formato negrita."""
    import re
    
    # Encontrar todas las instancias de texto entre ** y reemplazarlas con marcadores
    # Usamos marcadores únicos para identificar texto en negrita
    bold_pattern = r'\*\*(.*?)\*\*'
    
    # Lista para almacenar los segmentos de texto con su formato
    segments = []
    last_end = 0
    
    for match in re.finditer(bold_pattern, text):
        # Agregar texto normal antes del texto en negrita
        if match.start() > last_end:
            normal_text = text[last_end:match.start()]
            if normal_text:
                segments.append(('normal', normal_text))
        
        # Agregar texto en negrita
        bold_text = match.group(1)
        if bold_text:
            segments.append(('bold', bold_text))
        
        last_end = match.end()
    
    # Agregar texto restante
    if last_end < len(text):
        remaining_text = text[last_end:]
        if remaining_text:
            segments.append(('normal', remaining_text))
    
    return segments

def get_last_y_position():
    """Retorna la última posición Y utilizada en el PDF."""
    return pdf_last_y_position

def draw_formatted_text(canvas_obj, text_segments, x_start, y_start, max_width, font_size, line_height):
    """Dibuja texto con formato (normal/negrita) respetando el ancho máximo."""
    global pdf_last_y_position
    
    current_x = x_start
    current_y = y_start
    pdf_last_y_position = y_start
    
    for segment_type, segment_text in text_segments:
        # Configurar fuente según el tipo
        if segment_type == 'bold':
            try:
                canvas_obj.setFont("Helvetica-Bold", font_size)
            except:
                # Si no hay Helvetica-Bold, usar fuente normal
                canvas_obj.setFont(FINAL_FONT_NAME, font_size)
        else:
            canvas_obj.setFont(FINAL_FONT_NAME, font_size)
        
        # Dividir en líneas por saltos de línea explícitos
        lines = segment_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            if line.strip():  # Solo procesar líneas no vacías
                words = line.split()
                
                for word in words:
                    word_with_space = word + " "
                    word_width = canvas_obj.stringWidth(word_with_space, canvas_obj._fontname, font_size)
                    
                    # Si la palabra no cabe en la línea actual, saltar a la siguiente
                    if current_x + word_width > x_start + max_width and current_x > x_start:
                        current_y -= line_height + 2
                        current_x = x_start
                    
                    # Verificar si necesitamos nueva página
                    if current_y < 120:  # Margen inferior
                        canvas_obj.showPage()
                        draw_header_footer(canvas_obj, 1)
                        current_y = 650  # Resetear posición Y
                        current_x = x_start
                        # Reconfigurar fuente después de nueva página
                        if segment_type == 'bold':
                            try:
                                canvas_obj.setFont("Helvetica-Bold", font_size)
                            except:
                                canvas_obj.setFont(FINAL_FONT_NAME, font_size)
                        else:
                            canvas_obj.setFont(FINAL_FONT_NAME, font_size)
                    
                    # Dibujar la palabra
                    canvas_obj.drawString(current_x, current_y, word_with_space)
                    current_x += word_width
            
            # Si no es la última línea del segmento, hacer salto de línea
            if line_idx < len(lines) - 1:
                current_y -= line_height + 2
                current_x = x_start
    
    pdf_last_y_position = current_y - (line_height + 5)
    return pdf_last_y_position

def get_wrapped_text_lines_justified(text, font_name, font_size, max_width, justify=True):
    """Divide un texto en líneas justificadas que caben dentro de un ancho máximo dado."""
    lines = []

    paragraphs = re.split(r'\n\s*\n|\n', text)

    temp_canvas = canvas.Canvas(BytesIO())
    temp_canvas.setFont(font_name, font_size)

    for para_index, paragraph in enumerate(paragraphs):
        if not paragraph.strip():
            continue

        words = paragraph.strip().split()
        if not words:
            continue

        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            text_width = temp_canvas.stringWidth(test_line, font_name, font_size)

            if text_width < max_width:
                current_line.append(word)
            else:
                if current_line:
                    if justify and len(current_line) > 1:
                        lines.append(('justified', current_line, max_width))
                    else:
                        lines.append(('normal', ' '.join(current_line), max_width))
                current_line = [word]

        if current_line:
            lines.append(('normal', ' '.join(current_line), max_width))

        if para_index < len(paragraphs) - 1:
            lines.append(('space', '', max_width))

    return lines

def draw_justified_text(canvas_obj, x, y, line_data, font_name, font_size):
    """Dibuja texto justificado en el canvas."""
    line_type, content, max_width = line_data

    if line_type == 'space':
        return 0
    elif line_type == 'normal':
        canvas_obj.setFont(font_name, font_size)
        canvas_obj.drawString(x, y, content)
        return font_size + 2
    elif line_type == 'justified':
        if len(content) < 2:
            canvas_obj.setFont(font_name, font_size)
            canvas_obj.drawString(x, y, ' '.join(content))
            return font_size + 2

        text_without_spaces = ''.join(content)
        total_text_width = canvas_obj.stringWidth(text_without_spaces, font_name, font_size)
        available_space = max_width - total_text_width
        num_gaps = len(content) - 1

        if num_gaps > 0 and available_space > 0:
            space_width = available_space / num_gaps
            current_x = x

            canvas_obj.setFont(font_name, font_size)
            for i, word in enumerate(content):
                canvas_obj.drawString(current_x, y, word)
                current_x += canvas_obj.stringWidth(word, font_name, font_size)
                if i < len(content) - 1:
                    current_x += space_width
        else:
            canvas_obj.setFont(font_name, font_size)
            canvas_obj.drawString(x, y, ' '.join(content))

        return font_size + 2

    return 0

def get_wrapped_text_lines(text, font_name, font_size, max_width):
    """Función de compatibilidad con el código existente."""
    justified_lines = get_wrapped_text_lines_justified(text, font_name, font_size, max_width, justify=False)
    simple_lines = []

    for line_type, content, width in justified_lines:
        if line_type == 'space':
            simple_lines.append('')
        elif line_type == 'normal':
            simple_lines.append(content)
        elif line_type == 'justified':
            simple_lines.append(' '.join(content))

    return simple_lines

@app.route("/export_chat_response_pdf", methods=["POST"])
def export_chat_response_pdf():
    """Exporta el contenido EXACTO del chat a PDF."""
    data = request.json
    text_content = data.get("text_content", "")

    if not text_content:
        return jsonify({"mensaje": "No hay contenido para exportar a PDF."}), 400

    try:
        buffer_pdf = BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=letter)
        width, height = letter

        MARGIN_LEFT = 72
        MARGIN_RIGHT = width - 72
        MARGIN_TOP = height - 100
        MARGIN_BOTTOM = 100
        LINE_HEIGHT = 14
        NORMAL_FONT_SIZE = 10

        page_num = 1

        draw_header_footer(c, page_num)

        c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
        y_position = MARGIN_TOP - 20

        normalized_text = unicodedata.normalize('NFC', text_content)
        try:
            texto = normalized_text.encode('utf-8', 'ignore').decode('utf-8')
        except Exception:
            texto = normalized_text

        import re as _re
        texto = _re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
        texto = _re.sub(r"(?m)^\s*\*\s+", "• ", texto)

        justified_lines = get_wrapped_text_lines_justified(
            texto,
            FINAL_FONT_NAME,
            NORMAL_FONT_SIZE,
            MARGIN_RIGHT - MARGIN_LEFT - 20,
            justify=True
        )

        for line_data in justified_lines:
            line_type, content, width = line_data

            if y_position < MARGIN_BOTTOM + 20:
                c.showPage()
                page_num += 1
                draw_header_footer(c, page_num)
                c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
                y_position = MARGIN_TOP - 20

            if line_type == 'space':
                y_position -= LINE_HEIGHT
            else:
                line_height = draw_justified_text(c, MARGIN_LEFT, y_position, line_data, FINAL_FONT_NAME, NORMAL_FONT_SIZE)
                y_position -= line_height

        c.save()
        buffer_pdf.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"informe_medico_{timestamp}.pdf"

        return send_file(
            buffer_pdf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf"
        )

    except Exception as e:
        print(f"ERROR al generar PDF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"mensaje": f"Error al generar PDF: {str(e)}"}), 500

@app.route("/reset_context", methods=["POST"])
def reset_context():
    """Reinicia el contexto del paciente activo."""
    global global_query_engine, global_active_patient_id, global_patient_data
    global_query_engine = None
    global_active_patient_id = None
    global_patient_data = {}
    return jsonify({"response": "Contexto reiniciado"})

# RUTAS PARA EL FORMULARIO SOAP
@app.route("/soap_form")
def soap_form():
    """Renderiza el formulario SOAP."""
    return render_template("soap_form.html")

@app.route("/soap")
def soap_alias():
    return render_template("soap_form.html")

@app.route("/holter-matrix")
def holter_matrix():
    return render_template("holter_matrix.html")

@app.route("/get_patient_for_soap/<patient_id>", methods=["GET"])
def get_patient_for_soap(patient_id):
    """Obtiene los datos de un paciente específico para el formulario SOAP."""
    try:
        patient_data = load_patient_data(patient_id)
        if not patient_data:
            return jsonify({"error": "Paciente no encontrado"}), 404

        patient_dir = get_patient_directory(patient_id)
        documents = []
        if os.path.exists(patient_dir):
            documents = [f for f in os.listdir(patient_dir) if f.endswith('.txt')]

        return jsonify({
            "patient_data": patient_data,
            "documents_count": len(documents),
            "documents": documents
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate_soap_assessment", methods=["POST"])
def generate_soap_assessment():
    """Genera Assessment y Plan basado en Subjetivo y Objetivo usando IA."""
    try:
        data = request.json
        patient_id = data.get("patient_id", "")
        subjective = data.get("subjective", "")
        objective = data.get("objective", "")
        patient_data = data.get("patient_data", {})

        if not subjective.strip() and not objective.strip():
            return jsonify({"error": "Se requiere información subjetiva u objetiva para generar la evaluación"}), 400

        patient_info = ""
        if patient_data:
            if patient_data.get('nombre'):
                patient_info += f"Paciente: {patient_data['nombre']}\n"
            if patient_data.get('edad'):
                patient_info += f"Edad: {patient_data['edad']} años\n"
            if patient_data.get('antecedentes'):
                patient_info += f"Antecedentes: {patient_data['antecedentes']}\n"

        prompt = f"""Eres un médico especialista experimentado. Basándote en la información clínica proporcionada, genera un Assessment (Evaluación) y Plan de tratamiento siguiendo el formato SOAP.

{patient_info}

INFORMACIÓN CLÍNICA:

Subjetivo (S):
{subjective}

Objetivo (O):
{objective}

INSTRUCCIONES:
1. Genera un Assessment (A) que incluya:
   - Diagnóstico diferencial
   - Evaluación clínica basada en hallazgos
   - Interpretación de los datos objetivos y subjetivos

2. Genera un Plan (P) que incluya:
   - Plan diagnóstico (si se requieren más estudios)
   - Plan terapéutico
   - Plan de seguimiento
   - Recomendaciones para el paciente

Responde ÚNICAMENTE con el Assessment y Plan, sin incluir los encabezados "Assessment:" o "Plan:", ya que se agregarán automáticamente.

Formato de respuesta:
ASSESSMENT:
[Tu evaluación aquí]

PLAN:
[Tu plan aquí]"""

        if not GEMINI_API_KEY:
            return jsonify({"error": "API de IA no configurada"}), 500

        llm = GoogleGenAI(api_key=GEMINI_API_KEY, model="gemini-1.5-flash")
        response = llm.complete(prompt)
        ai_response = str(response)

        assessment = ""
        plan = ""

        if "ASSESSMENT:" in ai_response and "PLAN:" in ai_response:
            parts = ai_response.split("PLAN:")
            assessment = parts[0].replace("ASSESSMENT:", "").strip()
            plan = parts[1].strip()
        else:
            assessment = ai_response.strip()
            plan = "Plan de tratamiento requiere evaluación adicional basada en la evolución del paciente."

        return jsonify({
            "assessment": assessment,
            "plan": plan
        })

    except Exception as e:
        print(f"Error al generar Assessment/Plan: {e}")
        return jsonify({"error": f"Error al generar evaluación: {str(e)}"}), 500

@app.route("/save_soap_report", methods=["POST"])
def save_soap_report():
    """Guarda un reporte SOAP completo."""
    try:
        data = request.json
        patient_id = data.get("patient_id", "")
        soap_data = data.get("soap_data", {})

        if not patient_id:
            return jsonify({"error": "ID de paciente requerido"}), 400

        soap_hash = generate_soap_hash(soap_data)
        is_duplicate, existing_file = check_soap_duplicate(patient_id, soap_hash)

        if is_duplicate:
            return jsonify({
                "error": "DUPLICADO_DETECTADO",
                "message": f"Ya existe un reporte SOAP idéntico guardado en: {existing_file}",
                "existing_file": existing_file,
                "duplicate": True
            }), 409

        patient_dir = get_patient_directory(patient_id)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        soap_filename = f"SOAP_Report_{timestamp}.json"
        soap_filepath = os.path.join(patient_dir, soap_filename)

        soap_data['created_at'] = datetime.now().isoformat()
        soap_data['patient_id'] = patient_id
        soap_data['report_type'] = 'SOAP'
        soap_data['soap_hash'] = soap_hash

        with open(soap_filepath, 'w', encoding='utf-8') as f:
            json.dump(soap_data, f, ensure_ascii=False, indent=2)

        soap_text_filename = f"SOAP_Report_{timestamp}.txt"
        soap_text_filepath = os.path.join(patient_dir, soap_text_filename)

        soap_text = f"""REPORTE SOAP - {soap_data.get('fecha_consulta', 'Sin fecha')}
Paciente: {soap_data.get('nombre', 'Sin nombre')} (ID: {patient_id})
Edad: {soap_data.get('edad', 'Sin edad')} años
Antecedentes: {soap_data.get('antecedentes', 'Sin antecedentes')}

SUBJETIVO:
{soap_data.get('subjective', '')}

OBJETIVO:
{soap_data.get('objective', '')}

ASSESSMENT (EVALUACIÓN):
{soap_data.get('assessment', '')}

PLAN:
{soap_data.get('plan', '')}"""

        with open(soap_text_filepath, 'w', encoding='utf-8') as f:
            f.write(soap_text)

        # CAMBIO: Forzar actualización del índice después de guardar SOAP
        print(f"Actualizando índice después de guardar SOAP para paciente '{patient_id}'...")
        initialize_patient_query_engine(patient_id)

        # GENERAR PDF AUTOMÁTICAMENTE
        buffer_pdf = BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=letter)
        width, height = letter

        MARGIN_LEFT = 72
        MARGIN_RIGHT = width - 72
        MARGIN_TOP = height - 100
        MARGIN_BOTTOM = 100
        LINE_HEIGHT = 14
        TITLE_FONT_SIZE = 14
        SECTION_FONT_SIZE = 11  # Reducido para títulos SOAP
        NORMAL_FONT_SIZE = 10

        page_num = 1
        draw_header_footer(c, page_num)

        y_position = MARGIN_TOP - 20

        # Título principal
        c.setFont(FINAL_FONT_NAME, TITLE_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0.5)
        c.drawCentredString(width / 2, y_position, "INFORME MÉDICO")
        y_position -= 35

        # Información del paciente
        c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0)

        patient_info = [
            f"Paciente: {soap_data.get('nombre', 'Sin nombre')}",
            f"ID: {soap_data.get('patient_id', 'Sin ID')}",
            f"Edad: {soap_data.get('edad', 'Sin edad')} años",
            f"Fecha de consulta: {soap_data.get('fecha_consulta', 'Sin fecha')}",
        ]

        for info in patient_info:
            c.drawString(MARGIN_LEFT, y_position, info)
            y_position -= LINE_HEIGHT + 2

        # Antecedentes clínicos
        if soap_data.get('antecedentes'):
            y_position -= 15
            c.setFont(FINAL_FONT_NAME, SECTION_FONT_SIZE)
            c.setFillColorRGB(0, 0, 0)
            c.drawString(MARGIN_LEFT, y_position, "ANTECEDENTES CLÍNICOS:")
            y_position -= LINE_HEIGHT + 5

            # Procesar texto de antecedentes
            antecedentes_segments = process_markdown_text(soap_data['antecedentes'])
            y_position = draw_formatted_text(c, antecedentes_segments, MARGIN_LEFT + 10, y_position, 
                              MARGIN_RIGHT - MARGIN_LEFT - 20, NORMAL_FONT_SIZE, LINE_HEIGHT)

        y_position -= 20

        # Secciones SOAP
        soap_sections = [
            ("SUBJETIVO", soap_data.get('subjective', '')),
            ("OBJETIVO", soap_data.get('objective', '')),
            ("ASSESSMENT (EVALUACIÓN)", soap_data.get('assessment', '')),
            ("PLAN", soap_data.get('plan', ''))
        ]

        for section_title, section_content in soap_sections:
            if section_content.strip():
                # Verificar si necesitamos nueva página
                if y_position < MARGIN_BOTTOM + 60:
                    c.showPage()
                    page_num += 1
                    draw_header_footer(c, page_num)
                    y_position = MARGIN_TOP - 20

                # Título de sección en negrita y tamaño moderado
                c.setFont(FINAL_FONT_NAME, SECTION_FONT_SIZE)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN_LEFT, y_position, f"{section_title}:")
                y_position -= LINE_HEIGHT + 8

                # Contenido de la sección con formato mejorado
                content_segments = process_markdown_text(section_content)
                y_position = draw_formatted_text(c, content_segments, MARGIN_LEFT + 10, y_position,
                                              MARGIN_RIGHT - MARGIN_LEFT - 20, NORMAL_FONT_SIZE, LINE_HEIGHT)
                y_position -= 18

        c.save()
        buffer_pdf.seek(0)

        patient_name = soap_data.get('nombre', 'paciente').replace(' ', '_')
        pdf_filename = f"SOAP_{patient_name}_{timestamp}.pdf"

        import base64
        pdf_content = buffer_pdf.getvalue()
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')

        return jsonify({
            "message": "Reporte SOAP guardado, indexado y PDF generado exitosamente",
            "filename": soap_filename,
            "filepath": soap_filepath,
            "pdf_data": pdf_base64,
            "pdf_filename": pdf_filename,
            "reset_form": True,
            "duplicate": False
        })

    except Exception as e:
        print(f"Error al guardar reporte SOAP: {e}")
        return jsonify({"error": f"Error al guardar reporte: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')