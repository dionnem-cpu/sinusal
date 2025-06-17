import os
# Configurar la codificación de la consola a UTF-8 al inicio
os.environ['PYTHONIOENCODING'] = 'utf-8'

from flask import Flask, request, render_template, send_file, jsonify
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.google_genai.base import GoogleGenAI
# CAMBIO CLAVE AQUÍ: Importar GoogleGenAIEmbedding (sin "Generative")
# Esta es la línea que debe coincidir con la definición de la clase en tu base.py
from llama_index.embeddings.google_genai.base import GoogleGenAIEmbedding
import PyPDF2
from io import BytesIO
from reportlab.pdfgen import canvas
import unicodedata
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase import ttfonts
from reportlab.lib.pagesizes import letter
import json
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ADVERTENCIA: La clave de API de Gemini no está configurada como variable de entorno.")
    print("Asegúrate de establecer la variable de entorno 'GEMINI_API_KEY' en un archivo .env o en el entorno del sistema.")

UPLOAD_FOLDER = "uploads"
INDEXED_TEXTS_FOLDER = "indexed_texts"
FONTS_FOLDER = "fonts"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INDEXED_TEXTS_FOLDER, exist_ok=True)
os.makedirs(FONTS_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["INDEXED_TEXTS_FOLDER"] = INDEXED_TEXTS_FOLDER
app.config["FONTS_FOLDER"] = FONTS_FOLDER

FONT_NAME = "DejaVuSans"
FONT_PATH = os.path.join(app.config["FONTS_FOLDER"], f"{FONT_NAME}.ttf")

try:
    pdfmetrics.registerFont(ttfonts.TTFont(FONT_NAME, FONT_PATH))
    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME)
    print(f"Fuente '{FONT_NAME}' registrada exitosamente desde '{FONT_PATH}'.")
except Exception as e:
    print(f"ERROR: No se pudo registrar la fuente '{FONT_NAME}' desde '{FONT_PATH}'.")
    print(f"Asegúrate de que el archivo '{FONT_NAME}.ttf' esté en la carpeta '{FONTS_FOLDER}'.")
    print(f"Detalles del error: {e}")

FINAL_FONT_NAME = FONT_NAME

global_query_engine = None

def extraer_texto_pdf(ruta):
    """Extrae texto de un archivo PDF dado su ruta."""
    texto = ""
    try:
        with open(ruta, "rb") as f:
            lector = PyPDF2.PdfReader(f)
            for pagina in lector.pages:
                page_text = pagina.extract_text()
                if page_text:
                    texto += page_text
    except Exception as e:
        print(f"Error al extraer texto del PDF {ruta}: {e}")
        return ""
    return texto

def extract_patient_id_from_text(text_content):
    """
    Intenta extraer el ID del paciente (ej. cédula) del contenido del texto.
    Se busca específicamente la cédula de 8 dígitos y otros patrones.
    """
    cleaned_text = re.sub(r'\s+', ' ', text_content).lower()

    # Patrones para buscar la cédula o ID. El más específico primero.
    # 1. Cédula: 8 dígitos (ej. 14473217)
    patterns = [
        r"(?:cédula|cedula|id|identificación|dni|nro expediente|número expediente)[:\s]*([0-9]{7,9})", # Cédulas de 7 a 9 dígitos
        r"(?:paciente|cédula)\s*([0-9]{7,9})", # Paciente o Cédula seguido de 7 a 9 dígitos
        r"id[:\s]*([a-zA-Z0-9\-\.]+)", # Patrón más general para IDs alfanuméricos
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
    """
    Extrae un ID de paciente del nombre del archivo.
    Asume un formato como 'ID_RESTO_DEL_NOMBRE.pdf' o 'ID-RESTO-DEL-NOMBRE.txt'
    o simplemente 'ID.pdf'.
    """
    name_without_ext = os.path.splitext(filename)[0]
    
    # Intentar buscar un patrón numérico o el primer segmento como ID
    match = re.search(r'([0-9]{7,9})', name_without_ext) # Buscar 7-9 dígitos
    if match:
        extracted_id = match.group(1).strip().upper()
        print(f"DEBUG: ID extraído del nombre del archivo (numérico): '{extracted_id}'")
        return extracted_id

    # Fallback al método original si no se encuentra un ID numérico
    parts = name_without_ext.split('_')
    if len(parts) > 0:
        potential_id_part = parts[0].split('-')[0]
        if potential_id_part:
            extracted_id = potential_id_part.strip().upper()
            print(f"DEBUG: ID extraído del nombre del archivo (general): '{extracted_id}'")
            return extracted_id
    
    print("DEBUG: No se encontró un ID de paciente en el nombre del archivo.")
    return "DESCONOCIDO"

def load_all_indexed_documents(indexed_texts_folder):
    """
    Carga todos los documentos de texto previamente guardados con sus metadatos.
    """
    documents = []
    print(f"\nCargando documentos de la carpeta de índice: {indexed_texts_folder}")
    if not os.path.exists(indexed_texts_folder):
        print(f"ADVERTENCIA: La carpeta '{indexed_texts_folder}' no existe.")
        return []

    for filename in os.listdir(indexed_texts_folder):
        if filename.endswith(".txt"):
            filepath = os.path.join(indexed_texts_folder, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content:
                        # Priorizar ID del texto si está presente, sino del nombre de archivo.
                        extracted_id_from_text = extract_patient_id_from_text(content)
                        patient_id = extracted_id_from_text if extracted_id_from_text else extract_patient_id_from_filename(filename)

                        doc_to_add = Document(text=content, metadata={"filename": filename, "patient_id": patient_id})
                        documents.append(doc_to_add)
                        print(f"  - Documento cargado: '{filename}', ID Paciente asociado: '{patient_id}'")
            except Exception as e:
                print(f"Error al cargar documento indexado {filepath}: {e}")
    return documents

def initialize_global_query_engine():
    global global_query_engine
    all_documents = load_all_indexed_documents(app.config["INDEXED_TEXTS_FOLDER"])

    if not all_documents:
        print("No se encontraron documentos para la indexación inicial. El chatbot no estará disponible hasta que se procese un documento.")
        global_query_engine = None
        return

    try:
        if not GEMINI_API_KEY:
            raise ValueError("La clave de API de Gemini no está configurada. Por favor, establece la variable de entorno GEMINI_API_KEY.")

        llm = GoogleGenAI(api_key=GEMINI_API_KEY, model="gemini-1.5-flash")
        Settings.llm = llm

        # AQUÍ ESTÁ LA CORRECCIÓN: Usar GoogleGenAIEmbedding
        embed_model = GoogleGenAIEmbedding(api_key=GEMINI_API_KEY, model_name="models/text-embedding-004")
        Settings.embed_model = embed_model

        index = VectorStoreIndex.from_documents(all_documents)
        global_query_engine = index.as_query_engine()
        print(f"Motor de consulta de LlamaIndex inicializado/reconstruido exitosamente con {len(all_documents)} documentos.")
    except Exception as e:
        print(f"ERROR: No se pudo inicializar el motor de consulta de LlamaIndex globalmente: {e}")
        import traceback
        traceback.print_exc()
        global_query_engine = None

with app.app_context():
    initialize_global_query_engine()

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/procesar", methods=["POST"])
def procesar():
    if 'documento' not in request.files:
        return "No se ha subido ningún archivo", 400

    archivo = request.files["documento"]

    if not archivo.filename:
        return "Nombre de archivo vacío", 400

    ruta_archivo = os.path.join(app.config["UPLOAD_FOLDER"], archivo.filename)
    try:
        archivo.save(ruta_archivo)
    except Exception as e:
        print(f"Error al guardar el archivo subido: {e}")
        return "Error al guardar el archivo", 500

    texto_extraido = ""
    if archivo.filename.lower().endswith(".pdf"):
        texto_extraido = extraer_texto_pdf(ruta_archivo)
    else:
        try:
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                texto_extraido = f.read()
        except Exception as e:
            print(f"Error al leer el archivo de texto: {e}")
            return "Error al leer el archivo de texto", 500

    # Priorizar la extracción del ID del texto, sino del nombre de archivo.
    patient_id = extract_patient_id_from_text(texto_extraido)
    if not patient_id:
        patient_id = extract_patient_id_from_filename(archivo.filename) # Fallback al nombre de archivo

    print(f"\n--- Depuración de Procesamiento de Documento ---")
    print(f"Archivo subido: '{archivo.filename}'")
    print(f"ID Paciente (extraído): '{patient_id}'") # Imprimir el ID extraído
    print(f"Texto extraído del archivo (primeros 200 caracteres):")
    print(texto_extraido[:200])
    print("-" * 50)

    # Guardar el texto extraído en la carpeta de documentos indexados
    indexed_text_filename_base = os.path.splitext(archivo.filename)[0]
    indexed_text_filepath = os.path.join(app.config["INDEXED_TEXTS_FOLDER"], f"{indexed_text_filename_base}.txt")

    try:
        with open(indexed_text_filepath, "w", encoding="utf-8") as f:
            f.write(texto_extraido)
        print(f"Texto guardado/actualizado en '{indexed_text_filepath}'")
    except Exception as e:
        print(f"Error al guardar el texto extraído para indexación: {e}")

    # Reconstruir el motor de consulta global con los metadatos actualizados
    initialize_global_query_engine()

    try:
        os.remove(ruta_archivo)
    except Exception as e:
        print(f"Error al eliminar el archivo temporal {ruta_archivo}: {e}")

    return f"Documento procesado (Paciente ID: {patient_id}) y asistente actualizado. Ahora puedes analizar.", 200


@app.route("/chat", methods=["POST"])
def chat():
    global global_query_engine
    if global_query_engine is None:
        return jsonify({"response": "El chatbot no está disponible. Por favor, procesa un documento primero."}), 503

    user_message = request.json.get("message", "")
    if not user_message:
        return jsonify({"response": "Mensaje vacío."}), 400

    try:
        # Buscar ID de paciente en el mensaje del usuario para instruir a la IA.
        # Usa re.IGNORECASE para hacer la búsqueda insensible a mayúsculas/minúsculas.
        # Buscar específicamente la cédula numérica en la consulta del usuario
        patient_id_in_query_match = re.search(r"(?:paciente|cédula|cedula|id)[:\s]*([0-9]{7,9}|[a-zA-Z0-9\-\.]+)", user_message, re.IGNORECASE)
        patient_id_in_query = patient_id_in_query_match.group(1).upper() if patient_id_in_query_match else None

        base_prompt = (
            "Eres un asistente médico virtual. Tu tarea es analizar los documentos proporcionados "
            "y responder a las preguntas con la mayor precisión posible, extrayendo información relevante. "
            "Siempre responde en español."
        )

        if patient_id_in_query:
            base_prompt += (
                f" Concéntrate exclusivamente en la información del paciente con ID '{patient_id_in_query}'. "
                "Ignora cualquier otro dato de otros pacientes si no se relaciona con este ID. "
                "Prioriza los datos de este paciente al responder."
            )
        else:
            base_prompt += " Si tu pregunta no especifica un ID de paciente, responde basándote en toda la información disponible. "


        if "informe" in user_message.lower() or "resumen estructurado" in user_message.lower() or "formato soap" in user_message.lower():
            final_prompt = (
                f"{base_prompt} Por favor, genera un informe estructurado en formato SOAP "
                "(Subjetivo, Objetivo, Evaluación, Plan) basado en la información. "
                f"Pregunta original: {user_message}"
            )
            print("Generando informe estructurado (SOAP)...")
        else:
            final_prompt = f"{base_prompt} Pregunta original: {user_message}"
            print("Generando respuesta general...")

        respuesta = global_query_engine.query(final_prompt)
        texto_respuesta = str(respuesta)
        return jsonify({"response": texto_respuesta})
    except Exception as e:
        print(f"ERROR al procesar el mensaje del chat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response": f"Error al procesar tu mensaje. Detalles: {e}"}), 500

@app.route("/export_chat_response_pdf", methods=["POST"])
def export_chat_response_pdf():
    data = request.json
    text_content = data.get("text_content", "")

    if not text_content:
        return "No hay contenido para exportar a PDF.", 400

    buffer_pdf = BytesIO()
    c = canvas.Canvas(buffer_pdf, pagesize=letter)
    c.setFont(FINAL_FONT_NAME, 12)
    y_position = 800
    line_height = 15

    c.drawString(100, y_position, "Respuesta del Asistente Médico Virtual:")
    y_position -= line_height * 2

    normalized_text_content = unicodedata.normalize('NFC', text_content)
    try:
        texto_para_pdf = normalized_text_content.encode('utf-8', 'ignore').decode('utf-8')
    except Exception as e:
        print(f"Advertencia: Error al codificar/decodificar texto para PDF antes de dibujar: {e}")
        texto_para_pdf = normalized_text_content

    for line in texto_para_pdf.split("\n"):
        if y_position < 50:
            c.showPage()
            c.setFont(FINAL_FONT_NAME, 12)
            y_position = 800
        words = line.split(' ')
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if c.stringWidth(test_line, FINAL_FONT_NAME, 12) < 400:
                current_line.append(word)
            else:
                c.drawString(100, y_position, ' '.join(current_line))
                y_position -= line_height
                current_line = [word]
        if current_line:
            c.drawString(100, y_position, ' '.join(current_line))
            y_position -= line_height

    c.save()
    buffer_pdf.seek(0)

    return send_file(buffer_pdf, as_attachment=True, download_name="informe_medico_ia.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
