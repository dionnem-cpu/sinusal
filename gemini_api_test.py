import os
import asyncio
import google.generativeai as genai

async def test_gemini_api_direct():
    """
    Función asíncrona para probar la conexión a la API de Gemini directamente
    usando la librería google.generativeai.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key:
        print("ERROR: La variable de entorno 'GEMINI_API_KEY' no está configurada.")
        print("Por favor, configúrala antes de ejecutar este script.")
        print("Ejemplo (Linux/macOS): export GEMINI_API_KEY='TU_CLAVE_AQUI'")
        print("Ejemplo (Windows CMD): set GEMINI_API_KEY=TU_CLAVE_AQUI")
        print("Ejemplo (Windows PowerShell): $env:GEMINI_API_KEY='TU_CLAVE_AQUI'")
        return

    print(f"Intentando conectar con Gemini directamente usando la clave: {gemini_api_key[:5]}... (solo los primeros 5 caracteres)")

    try:
        # Configurar la clave de API
        genai.configure(api_key=gemini_api_key)

        # Listar modelos disponibles (esta parte es solo informativa, ya sabemos que 'gemini-pro' no está)
        # Puedes comentar o eliminar esta sección si lo deseas, pero la dejaremos por ahora.
        print("Listando modelos disponibles (solo para referencia)...")
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(f"- {m.name}")

        # Intentar cargar el modelo y hacer una consulta de prueba
        # CAMBIO CLAVE AQUÍ: Usamos "gemini-1.5-flash"
        model_name_to_test = "gemini-1.5-flash"

        print(f"\nIntentando cargar el modelo: {model_name_to_test}")
        model = genai.GenerativeModel(model_name_to_test)

        print("Realizando una consulta de prueba...")
        response = await model.generate_content_async("Hola, ¿cómo estás?")
        print("\n¡Conexión exitosa a Gemini directamente!")
        print(f"Respuesta de prueba: {response.text}")

    except Exception as e:
        print(f"\nERROR: No se pudo conectar o consultar la API de Gemini directamente.")
        print(f"Detalles del error: {e}")
        print("Posibles causas:")
        print("1. La clave de API es incorrecta o no tiene permisos para acceder a los modelos.")
        print("2. No tienes conexión a Internet.")
        print("3. El modelo especificado no existe o no está disponible en tu región.")
        print("4. Problema de cuota o límite de uso.")

if __name__ == "__main__":
    # Asegúrate de instalar la librería: pip install google-generativeai
    asyncio.run(test_gemini_api_direct())
