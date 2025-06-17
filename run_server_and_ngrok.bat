@echo off
setlocal

:: Navega a la carpeta principal del proyecto
CD /D "%~dp0"

ECHO.
ECHO =======================================================
ECHO   INICIANDO SERVIDOR FLASK Y TUNEL NGROK
ECHO =======================================================
ECHO.

:: Activa el entorno virtual
CALL "%~dp0venv\Scripts\activate.bat"
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO ERROR: No se pudo activar el entorno virtual.
    ECHO Asegurate de que el entorno virtual se creo correctamente con install_and_run.bat.
    PAUSE
    EXIT /B 1
)

ECHO Entorno virtual activado.
ECHO.

:: Inicia el servidor Flask en segundo plano (para que ngrok pueda iniciarse en primer plano)
:: Se redirige la salida a NUL para que no sature esta ventana.
:: La salida del servidor Flask se puede ver en la ventana del navegador (desarrollo).
START /B python app.py

ECHO.
ECHO Servidor Flask iniciado en segundo plano (http://127.0.0.1:5000).
ECHO Esperando unos segundos para que el servidor Flask este listo...
TIMEOUT /T 5 /NOBREAK > NUL

ECHO.
ECHO Iniciando tunel ngrok...
:: Lanza ngrok y tuneliza el puerto 5000.
:: La salida de ngrok es crucial, por lo que se mantiene en esta ventana.
:: Asume que ngrok.exe esta en la misma carpeta que este .bat o en el PATH.
ngrok http 5000
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO =======================================================
    ECHO  ERROR: Fallo al iniciar ngrok.
    ECHO =======================================================
    ECHO  - Asegurate de que "ngrok.exe" esta en la carpeta del proyecto.
    ECHO  - Asegurate de que tu Auth Token de ngrok este configurado (ver guia).
    ECHO  - Revisa tu conexion a internet.
    ECHO.
    PAUSE
    EXIT /B 1
)

ECHO.
ECHO =======================================================
ECHO   EL SERVIDOR FLASK O NGROK SE HAN DETENIDO.
ECHO   Revisa los mensajes anteriores en esta ventana si hubo errores.
ECHO =======================================================
ECHO.
PAUSE
EXIT /B 0