import os
# Configurar la codificación de la consola a UTF-8 al inicio
os.environ['PYTHONIOENCODING'] = 'utf-8'

from flask import Flask, request, render_template, send_file, jsonify
# AÑADE ESTA LÍNEA para importar CORS
from flask_cors import CORS
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.google_genai.base import GoogleGenAI
from llama_index.embeddings.google_genai.base import GoogleGenAIEmbedding
import PyPDF2
from io import BytesIO
from reportlab.pdfgen import canvas
import unicodedata # Para normalizar caracteres Unicode
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase import ttfonts # Para registrar fuentes TrueType
from reportlab.lib.pagesizes import letter # Para definir el tamaño de página del PDF
from reportlab.lib.units import inch # Para usar pulgadas como unidad de medida en el PDF
import re # Para expresiones regulares en la extracción de ID
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
# Asegúrate de que un archivo '.env' exista en la raíz de tu proyecto con GEMINI_API_KEY.
load_dotenv()

app = Flask(__name__)
# AÑADE ESTA LÍNEA para habilitar CORS para todas las rutas y orígenes
# Esto es crucial para que tu frontend React (ejecutándose en localhost) pueda comunicarse con el túnel.
CORS(app) 

# 🔐 IMPORTANTE: Cargar la clave de API de Gemini desde una variable de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ADVERTENCIA: La clave de API de Gemini no está configurada como variable de entorno.")
    print("Asegúrate de establecer la variable de entorno 'GEMINI_API_KEY' en un archivo .env o en el entorno del sistema.")
    # En un entorno de producción, podrías querer lanzar una excepción o salir
    # exit(1)

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
# Se recomienda usar una fuente TrueType (TTF) con soporte Unicode completo.
# Asegúrate de que 'DejaVuSans.ttf' esté en la carpeta 'fonts/'.
FONT_NAME = "DejaVuSans" # Nombre que se usará para la fuente en ReportLab
FONT_PATH = os.path.join(app.config["FONTS_FOLDER"], f"{FONT_NAME}.ttf")

try:
    # Registrar la fuente TrueType con ReportLab
    pdfmetrics.registerFont(ttfonts.TTFont(FONT_NAME, FONT_PATH))
    # Registrar la familia de fuentes para que ReportLab la reconozca correctamente
    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME)
    print(f"Fuente '{FONT_NAME}' registrada exitosamente desde '{FONT_PATH}'.")
except Exception as e:
    print(f"ERROR: No se pudo registrar la fuente '{FONT_NAME}' desde '{FONT_PATH}'.")
    print(f"Asegúrate de que el archivo '{FONT_NAME}.ttf' esté en la carpeta '{FONTS_FOLDER}'.")
    print(f"Detalles del error: {e}")
    # Si la fuente no se puede registrar, la generación del PDF con caracteres especiales podría fallar.

# Nombre de la fuente final que se usará para dibujar el texto en el PDF
FINAL_FONT_NAME = FONT_NAME

# Variable global para almacenar el motor de consulta de LlamaIndex
# Se inicializa y reconstruye cuando se procesan documentos.
global_query_engine = None

def extraer_texto_pdf(ruta):
    """
    Extrae texto de un archivo PDF dado su ruta.
    Maneja posibles errores de lectura.
    """
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
    Se busca específicamente la cédula de 7-9 dígitos y otros patrones.
    """
    cleaned_text = re.sub(r'\s+', ' ', text_content).lower()

    # Patrones para buscar la cédula o ID. El más específico primero.
    # 1. Cédula: 7-9 dígitos
    patterns = [
        r"(?:cédula|cedula|id|identificación|dni|nro expediente|número expediente)[:\s]*([0-9]{7,9})",
        r"(?:paciente|cédula)\s*([0-9]{7,9})",
        r"id[:\s]*([a-zA-Z0-9\-\.]+)", # Patrón más general para IDs alfanuméricos
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned_text)
        if match:
            extracted_id = match.group(1).strip().upper()
            print(f"DEBUG: extract_patient_id_from_text encontró ID: '{extracted_id}' con patrón: '{pattern}'")
            return extracted_id
    print("DEBUG: extract_patient_id_from_text no encontró ID numérico o alfanumérico principal en el texto.")
    return None

def extract_patient_id_from_filename(filename):
    """
    Extrae un ID de paciente del nombre del archivo.
    Asume un formato como 'ID_RESTO_DEL_NOMBRE.pdf' o 'ID-RESTO-DEL-NOMBRE.txt'
    o simplemente 'ID.pdf'.
    """
    name_without_ext = os.path.splitext(filename)[0]
    
    # Intentar buscar un patrón numérico (7-9 dígitos) o el primer segmento como ID
    match = re.search(r'([0-9]{7,9})', name_without_ext) # Buscar 7-9 dígitos
    if match:
        extracted_id = match.group(1).strip().upper()
        print(f"DEBUG: extract_patient_id_from_filename encontró ID numérico: '{extracted_id}'")
        return extracted_id

    # Fallback al método original si no se encuentra un ID numérico en el nombre
    parts = name_without_ext.split('_')
    if len(parts) > 0:
        potential_id_part = parts[0].split('-')[0]
        if potential_id_part:
            extracted_id = potential_id_part.strip().upper()
            print(f"DEBUG: extract_patient_id_from_filename (fallback) usó: '{extracted_id}'")
            return extracted_id
    print("DEBUG: extract_patient_id_from_filename no encontró un ID en el nombre.")
    return "DESCONOCIDO" # Default if no ID found

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
                        print(f"  - Documento cargado: '{filename}', ID Paciente FINAL en metadata: '{patient_id}'")
            except Exception as e:
                print(f"Error al cargar documento indexado {filepath}: {e}")
    print("-" * 50)
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
    # En un entorno de producción con React, Flask no serviría el index.html
    # Solo se usa aquí para pruebas locales o si no hay un servidor frontend separado
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
    print(f"ID Paciente (extraído para metadata): '{patient_id}'") # Imprimir el ID extraído
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
        patient_id_in_query_match = re.search(r"(?:paciente|cédula|cedula|id)[:\s]*([0-9]{7,9}|[a-zA-Z0-9\-\.]+)", user_message, re.IGNORECASE)
        patient_id_in_query = patient_id_in_query_match.group(1).strip().upper() if patient_id_in_query_match else None

        print(f"DEBUG: Mensaje de usuario recibido: '{user_message}'")
        print(f"DEBUG: ID de paciente extraído de la consulta: '{patient_id_in_query}'")

        base_prompt = (
            "Eres un asistente médico virtual. Tu tarea es analizar los documentos proporcionados "
            "y responder a las preguntas con la mayor precisión posible, extrayendo información relevante. "
            "Siempre responde en español."
        )

        if patient_id_in_query:
            base_prompt += (
                f" **ATENCIÓN: CONCÉNTRATE ESTRICTAMENTE en la información del paciente con ID '{patient_id_in_query}'.** "
                "IGNORA Y OMITE cualquier dato que no esté **DIRECTAMENTE** relacionado con este ID de paciente, incluso si aparece en el contexto. "
                "Si la información solicitada para este paciente específico NO se encuentra en los documentos, "
                "responde ÚNICAMENTE: 'Lo siento, no se encontró información relevante para el paciente con ID {patient_id_in_query} en los documentos disponibles.' "
                "NO inventes información ni te refieras a otros IDs."
            )
        else:
            base_prompt += " Si tu pregunta no especifica un ID de paciente, responde basándote en toda la información disponible. "

        user_message_lower = user_message.lower()
        final_prompt = ""
        action_identified = False

        # Lógica para las opciones de burbujas/chips (orden actualizado y 'redactame' eliminado)
        if "informes completo" in user_message_lower or "informes médicos" in user_message_lower:
            final_prompt = f"{base_prompt} Proporciona un resumen detallado o los puntos clave de los informes médicos completos disponibles para el paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. {user_message}"
            print("Acción: Informes completos.")
            action_identified = True
        elif "resumen" in user_message_lower:
            final_prompt = f"{base_prompt} Proporciona un resumen de la historia clínica del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}', incluyendo antecedentes familiares y personales, alergias, medicación actual y pasada, y conclusiones de pruebas diagnósticas relevantes. {user_message}"
            print("Acción: Resumen de historia clínica.")
            action_identified = True
        elif "alergias e intolerancias" in user_message_lower:
            final_prompt = f"{base_prompt} Enumera todas las alergias e intolerancias documentadas para el paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. Si no se encuentran, indica 'No documentado' para ese paciente. {user_message}"
            print("Acción: Alergias e intolerancias.")
            action_identified = True
        elif "medicación" in user_message_lower or "medicacion" in user_message_lower: # Acepta con y sin tilde
            final_prompt = f"{base_prompt} Detalla la medicación actual y pasada del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}', incluyendo la dosis, frecuencia y las causas de suspensión si están disponibles en los documentos. Si no hay medicación documentada para este paciente, indícalo. {user_message}"
            print("Acción: Medicación.")
            action_identified = True
        elif "curvas evolutivas" in user_message_lower:
            final_prompt = f"{base_prompt} Describe cualquier información sobre curvas evolutivas, tendencias o cambios significativos en mediciones (ej. peso, tensión arterial, glucosa) a lo largo del tiempo, según los documentos disponibles para el paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. Si no hay datos, indícalo. {user_message}"
            print("Acción: Curvas evolutivas.")
            action_identified = True
        elif "pruebas" in user_message_lower:
            final_prompt = f"{base_prompt} Resume las pruebas diagnósticas realizadas al paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}', enfocándote específicamente en sus conclusiones y resultados clave. {user_message}"
            print("Acción: Pruebas diagnósticas.")
            action_identified = True
        elif "analíticas" in user_message_lower or "analiticas" in user_message_lower: # Acepta con y sin tilde
            final_prompt = f"{base_prompt} Proporciona un resumen de los resultados de las analíticas de laboratorio del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}', destacando cualquier valor fuera de rango o significativo. {user_message}"
            print("Acción: Analíticas de laboratorio.")
            action_identified = True
        elif "diagnósticos" in user_message_lower or "diagnosticos" in user_message_lower: # Acepta con y sin tilde
            final_prompt = f"{base_prompt} Lista todos los diagnósticos registrados o mencionados para el paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}' en los documentos. {user_message}"
            print("Acción: Diagnósticos.")
            action_identified = True
        elif "electros" in user_message_lower or "electrocardiogramas" in user_message_lower:
            final_prompt = f"{base_prompt} Describe los hallazgos y conclusiones de los electrocardiogramas (ECG) mencionados en los documentos del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. {user_message}"
            print("Acción: Electros/ECG.")
            action_identified = True
        elif "especialidades" in user_message_lower:
            final_prompt = f"{base_prompt} Lista todas las especialidades médicas que han tratado al paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}' o que se mencionan en sus documentos, junto con los motivos de consulta si están disponibles. {user_message}"
            print("Acción: Especialidades.")
            action_identified = True
        elif "imágenes" in user_message_lower or "imagenes" in user_message_lower:
            final_prompt = f"{base_prompt} Resume los hallazgos principales y las conclusiones de los estudios de imágenes diagnósticas (radiografías, ecografías, resonancias, etc.) mencionados en los documentos del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. {user_message}"
            print("Acción: Imágenes diagnósticas.")
            action_identified = True
        elif "archivos adj." in user_message_lower or "archivos adjuntos" in user_message_lower:
            final_prompt = f"{base_prompt} Menciona cualquier información relevante sobre archivos adjuntos o documentos anexos que se describan en los registros del paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. {user_message}"
            print("Acción: Archivos adjuntos.")
            action_identified = True
        elif "formato soap" in user_message_lower: # Mantenemos esta para casos específicos o si no se usa la burbuja
            final_prompt = (
                f"{base_prompt} Por favor, genera un informe estructurado en formato SOAP "
                f"(Subjetivo, Objetivo, Evaluación, Plan) basado en la información para el paciente con ID '{patient_id_in_query if patient_id_in_query else 'general'}'. "
                f"Pregunta original: {user_message}"
            )
            print("Acción: Generando informe estructurado (SOAP).")
            action_identified = True
        
        if not action_identified:
            final_prompt = f"{base_prompt} Pregunta original: {user_message}"
            print("Acción: Generando respuesta general.")

        response_obj = global_query_engine.query(final_prompt)
        texto_respuesta = str(response_obj)

        # --- DIAGNOSTIC: Print retrieved source nodes metadata ---
        print("\nDEBUG: Metadata de los nodos fuente recuperados por LlamaIndex:")
        if hasattr(response_obj, 'source_nodes') and response_obj.source_nodes:
            for i, node in enumerate(response_obj.source_nodes):
                print(f"  Nodo {i+1}:")
                print(f"    ID de Documento (LlamaIndex): {node.node_id}")
                print(f"    ID de Paciente (metadata): {node.metadata.get('patient_id', 'N/A')}")
                print(f"    Nombre de Archivo (metadata): {node.metadata.get('filename', 'N/A')}")
                # Imprimir el texto del nodo, solo los primeros 200 caracteres para no saturar la consola
                print(f"    Texto (primeros 200 chars): {node.text[:200]}...")
        else:
            print("  - No se recuperaron nodos fuente o no se pudo acceder a ellos.")
        print("-" * 50)
        # --- END DIAGNOSTIC ---

        return jsonify({"response": texto_respuesta})
    except Exception as e:
        print(f"ERROR al procesar el mensaje del chat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response": f"Error al procesar tu mensaje. Detalles: {e}"}), 500

@app.route("/export_chat_response_pdf", methods=["POST"])
def export_chat_response_pdf():
    """
    Genera un PDF con el texto de la última respuesta del chatbot,
    aplicando un formato de "hoja membreteada" y estructurando el contenido
    si detecta un formato SOAP.
    """
    data = request.json
    text_content = data.get("text_content", "")

    if not text_content:
        return "No hay contenido para exportar a PDF.", 400

    buffer_pdf = BytesIO()
    c = canvas.Canvas(buffer_pdf, pagesize=letter)
    width, height = letter # Obtener dimensiones de la página (letter = 612x792 puntos)

    # --- Configuración de fuentes y márgenes ---
    MARGIN_LEFT = 72 # 1 pulgada = 72 puntos
    MARGIN_RIGHT = width - 72
    MARGIN_TOP = height - 72
    MARGIN_BOTTOM = 72
    LINE_HEIGHT = 14
    NORMAL_FONT_SIZE = 10
    HEADING_FONT_SIZE = 12
    SUB_HEADING_FONT_SIZE = 10
    
    # --- Datos del Membrete ---
    DR_NAME = "Dr. Rodolfo Gutiérrez Caro"
    DR_SPECIALTY = "Especialista en Cardiología"
    DR_COLEGIADO = "Colegiado 332405519"
    CLINIC_INFO = "CliniKa AI - Asistente Médico Virtual"
    CONTACT_INFO = "Contacto: info@clinika-ai.com | Tel: +58 412-1234567" # Ejemplo

    def draw_header_footer(canvas_obj, page_num=1):
        """Dibuja el encabezado y pie de página."""
        # Encabezado (Header)
        canvas_obj.setFont(FINAL_FONT_NAME, HEADING_FONT_SIZE)
        canvas_obj.drawString(MARGIN_LEFT, height - 40, CLINIC_INFO)
        # Puedes añadir un logo aquí. Por ejemplo:
        # canvas_obj.drawImage("path/to/your/logo.png", MARGIN_LEFT, height - 70, width=50, height=50)

        canvas_obj.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
        canvas_obj.drawRightString(MARGIN_RIGHT, height - 40, DR_NAME)
        canvas_obj.drawRightString(MARGIN_RIGHT, height - 55, DR_SPECIALTY)
        canvas_obj.drawRightString(MARGIN_RIGHT, height - 70, DR_COLEGIADO)
        
        # Línea divisoria del encabezado
        canvas_obj.line(MARGIN_LEFT, height - 80, MARGIN_RIGHT, height - 80)

        # Pie de página (Footer)
        canvas_obj.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE - 2) # Fuente más pequeña para el pie
        canvas_obj.drawCentredString(width / 2, 40, CONTACT_INFO)
        canvas_obj.drawCentredString(width / 2, 25, f"Página {page_num}")
        
        # Línea divisoria del pie de página
        canvas_obj.line(MARGIN_LEFT, 50, MARGIN_RIGHT, 50)

    # Iniciar la primera página
    page_num = 1
    draw_header_footer(c, page_num)
    c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
    y_position = MARGIN_TOP - 60 # Posición inicial del texto después del encabezado

    c.drawString(MARGIN_LEFT, y_position, "Informe Generado por Asistente Médico Virtual:")
    y_position -= LINE_HEIGHT * 2

    # Normalizar el texto de la respuesta (buena práctica Unicode)
    normalized_text_content = unicodedata.normalize('NFC', text_content)
    # Codificación/decodificación explícita para asegurar la compatibilidad con ReportLab
    try:
        texto_para_pdf = normalized_text_content.encode('utf-8', 'ignore').decode('utf-8')
    except Exception as e:
        print(f"Advertencia: Error al codificar/decodificar texto para PDF antes de dibujar: {e}")
        texto_para_pdf = normalized_text_content

    # --- Detección y Formato de Secciones SOAP ---
    # Patrones para detectar las secciones (Subjetivo, Objetivo, Evaluación, Plan)
    # Se usa re.IGNORECASE para que sea insensible a mayúsculas/minúsculas.
    soap_sections = {
        "Subjetivo": re.compile(r"^(subjetivo|s)\s*[:\.]?\s*", re.IGNORECASE),
        "Objetivo": re.compile(r"^(objetivo|o)\s*[:\.]?\s*", re.IGNORECASE),
        "Evaluación": re.compile(r"^(evaluacion|e)\s*[:\.]?\s*", re.IGNORECASE),
        "Plan": re.compile(r"^(plan|p)\s*[:\.]?\s*", re.IGNORECASE),
    }
    
    current_section = None
    processed_lines = []
    lines = texto_para_pdf.split("\n")

    for i, line in enumerate(lines):
        line = line.strip()
        if not line: # Saltar líneas vacías
            continue

        is_new_section = False
        for section_name, pattern in soap_sections.items():
            if pattern.match(line):
                # Extraer solo el contenido después del título de la sección
                content_after_title = pattern.sub('', line, 1).strip()
                processed_lines.append((section_name.upper(), content_after_title)) # Guardar como (HEADING, CONTENT)
                current_section = section_name.upper()
                is_new_section = True
                break
        
        if not is_new_section:
            if current_section: # Si estamos dentro de una sección, añadir la línea al contenido de la sección
                processed_lines.append(("CONTENT", line))
            else: # Si no estamos en una sección formal, tratar como texto normal
                processed_lines.append(("NORMAL", line))

    # --- Dibujar el contenido procesado en el PDF ---
    for item_type, text_to_draw in processed_lines:
        # Manejo de salto de página antes de dibujar cada elemento
        required_height = LINE_HEIGHT
        if item_type in ["SUBJETIVO", "OBJETIVO", "EVALUACIÓN", "PLAN"]:
            required_height += (HEADING_FONT_SIZE - NORMAL_FONT_SIZE) + LINE_HEIGHT # Espacio extra para el título
        
        if y_position - required_height < MARGIN_BOTTOM:
            c.showPage()
            page_num += 1
            draw_header_footer(c, page_num)
            c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
            y_position = MARGIN_TOP - 60 # Reiniciar posición después del encabezado

        if item_type in ["SUBJETIVO", "OBJETIVO", "EVALUACIÓN", "PLAN"]:
            c.setFont(FINAL_FONT_NAME, HEADING_FONT_SIZE) # Fuente más grande para el título
            c.drawString(MARGIN_LEFT, y_position, item_type + ":")
            y_position -= LINE_HEIGHT # Espacio para el título
            c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE) # Volver a la fuente normal para el contenido
            
            # Dibujar el contenido de la sección
            for line_part in c._wrapText(text_to_draw, MARGIN_RIGHT - MARGIN_LEFT, FINAL_FONT_NAME, NORMAL_FONT_SIZE):
                if y_position < MARGIN_BOTTOM:
                    c.showPage()
                    page_num += 1
                    draw_header_footer(c, page_num)
                    c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
                    y_position = MARGIN_TOP - 60
                c.drawString(MARGIN_LEFT + 20, y_position, line_part) # Pequeña sangría para el contenido
                y_position -= LINE_HEIGHT
            y_position -= LINE_HEIGHT / 2 # Pequeño espacio extra entre secciones
        else: # Tipo "CONTENT" o "NORMAL"
            for line_part in c._wrapText(text_to_draw, MARGIN_RIGHT - MARGIN_LEFT, FINAL_FONT_NAME, NORMAL_FONT_SIZE):
                if y_position < MARGIN_BOTTOM:
                    c.showPage()
                    page_num += 1
                    draw_header_footer(c, page_num)
                    c.setFont(FINAL_FONT_NAME, NORMAL_FONT_SIZE)
                    y_position = MARGIN_TOP - 60
                c.drawString(MARGIN_LEFT, y_position, line_part)
                y_position -= LINE_HEIGHT
            y_position -= LINE_HEIGHT / 2 # Pequeño espacio extra entre párrafos/líneas

    c.save() # Guardar el contenido del PDF
    buffer_pdf.seek(0) # Mover el puntero al inicio del buffer para la lectura

    return send_file(buffer_pdf, as_attachment=True, download_name="informe_medico_ia.pdf", mimetype="application/pdf")

# Este bloque se elimina o comenta para despliegue en plataformas como PythonAnywhere
# if __name__ == "__main__":
#     app.run(host='0.0.0.0', port=5000, debug=True)
