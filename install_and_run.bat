@echo off
setlocal EnableDelayedExpansion

ECHO.
ECHO =======================================================
ECHO           Iniciando instalacion y ejecucion
ECHO           del Asistente Medico Virtual (MVP)
ECHO =======================================================
ECHO.

:: =======================================================
:: Verificacion de privilegios de administrador
:: =======================================================
NET SESSION >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO =======================================================
    ECHO  ERROR: Se requieren privilegios de ADMINISTRADOR.
    ECHO =======================================================
    ECHO  Por favor, haz clic derecho en este archivo BAT (install_and_run.bat)
    ECHO  y selecciona "Ejecutar como administrador".
    ECHO.
    PAUSE
    EXIT /B 1
)

ECHO.
ECHO [Paso 1/6] Navegando a la carpeta del proyecto y limpiando cache de pip...
CD /D "%~dp0"
ECHO Carpeta actual: %CD%

:: Limpiar cache de pip y desactivar venv (si existe). Redirigir errores para que no interrumpan.
CALL deactivate 2>NUL
CALL "%~dp0venv\Scripts\pip.exe" cache purge 2>NUL
ECHO Hecho.
PAUSE
ECHO.

ECHO [P2/6] Eliminando entorno virtual existente (para una instalacion limpia)...
RMDIR /S /Q "%~dp0venv" 2>NUL
ECHO Hecho.
PAUSE
ECHO.

ECHO [P3/6] Creando nuevo entorno virtual 'venv'...
python -m venv "%~dp0venv"
IF !ERRORLEVEL! NEQ 0 (
    ECHO.
    ECHO =======================================================
    ECHO  ERROR CRITICO: No se pudo crear el entorno virtual.
    ECHO =======================================================
    ECHO  Asegurate de que Python 3.9+ esta instalado y anadido al PATH del sistema.
    ECHO  Puedes descargarlo desde: https://www.python.org/downloads/
    ECHO.
    PAUSE
    EXIT /B 1
)
ECHO Entorno virtual creado.
PAUSE
ECHO.

ECHO [P4/6] Instalando/actualizando librerias Python necesarias dentro del entorno virtual...
:: Activar el entorno virtual para este comando de pip en la ventana actual.
CALL "%~dp0venv\Scripts\activate.bat"
IF !ERRORLEVEL! NEQ 0 (
    ECHO.
    ECHO ERROR: Fallo la activacion del entorno virtual. No se pueden instalar librerias.
    PAUSE
    EXIT /B 1
)
:: Instalar librerias. Los errores se mostraran directamente en la consola.
pip install --upgrade Flask PyPDF2 reportlab python-dotenv llama-index-core llama-index-llms-google-genai llama-index-embeddings-google-genai
IF !ERRORLEVEL! NEQ 0 (
    ECHO.
    ECHO =======================================================
    ECHO  ERROR CRITICO: Fallo la instalacion de librerias.
    ECHO =======================================================
    ECHO  Revisa tu conexion a internet y los mensajes de error anteriores.
    ECHO.
    PAUSE
    EXIT /B 1
)
ECHO Librerias instaladas/actualizadas.
PAUSE
ECHO.

ECHO =======================================================
ECHO   ATENCION: PASOS MANUALES CRITICOS REQUERIDOS!
ECHO =======================================================
ECHO.
ECHO  Antes de continuar, por favor, realiza los siguientes pasos:
ECHO.
ECHO  1. Crea un archivo llamado ".env" (sin nombre antes del punto)
ECHO     en la carpeta principal del proyecto: "%~dp0"
ECHO     Dentro de ".env", pega la siguiente linea (reemplazando TU_CLAVE_API_AQUI):
ECHO        GEMINI_API_KEY=TU_CLAVE_API_AQUI
ECHO     (Puedes obtener tu clave API en: https://aistudio.google.com/app/apikey)
ECHO.
ECHO  2. Asegurate de que el archivo "DejaVuSans.ttf" esta en la carpeta: "%~dp0fonts\"
ECHO     (Si no existe la carpeta 'fonts', creala. Puedes descargar la fuente desde
ECHO      https://dejavu-fonts.github.io/ y extraer 'DejaVuSans.ttf').
ECHO.
ECHO  3. Asegurate de que "ngrok.exe" esta en la carpeta principal del proyecto: "%~dp0"
ECHO     (Descargalo de https://ngrok.com/download y descomprimelo alli).
ECHO     Una vez alli, abre una terminal, navega a "%~dp0" y ejecuta:
ECHO     ngrok authtoken TU_TOKEN_DE_NGROK_AQUI
ECHO     (Obten tu token en https://ngrok.com/dashboard/authtokens)
ECHO.
ECHO  4. Vacia las carpetas 'uploads' y 'indexed_texts' si contienen archivos antiguos:
ECHO     - "%~dp0uploads\"
ECHO     - "%~dp0indexed_texts\"
ECHO.
ECHO Presiona cualquier tecla para continuar despues de completar estos pasos...
PAUSE >NUL

ECHO.
ECHO [P5/6] Limpiando carpetas de documentos para un inicio fresco...
RMDIR /S /Q "%~dp0uploads" 2>NUL
RMDIR /S /Q "%~dp0indexed_texts" 2>NUL
MD "%~dp0uploads" 2>NUL
MD "%~dp0indexed_texts" 2>NUL
ECHO Hecho.
PAUSE
ECHO.

ECHO [P6/6] Lanzando el servidor Flask y el tunel ngrok en una nueva ventana...
ECHO.
ECHO Se abrira una NUEVA ventana de terminal. En ella se iniciara el servidor Flask
ECHO y luego el tunel ngrok. Observa esa ventana para ver la URL publica de ngrok.
ECHO.

:: Lanza el nuevo script 'run_server_and_ngrok.bat' en una nueva ventana de CMD
START "Servidor Flask y ngrok" cmd /k "%~dp0run_server_and_ngrok.bat"

ECHO.
ECHO =======================================================
ECHO   INSTALACION FINALIZADA.
ECHO =======================================================
ECHO   La ventana de instalacion actual se cerrara.
ECHO   Por favor, revisa la NUEVA ventana de terminal que se abrio
ECHO   para ver el estado del servidor Flask y la URL de ngrok.
ECHO.
PAUSE
EXIT /B 0
