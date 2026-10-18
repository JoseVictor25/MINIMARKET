@echo off
REM ══════════════════════════════════════════════════════════════════════════════
REM  build.bat – Genera el ejecutable de Mini Market POS con PyInstaller
REM  Compatible con: Windows 7, 8, 8.1, 10 y 11 (sin necesidad de pasos extras)
REM
REM  USO:
REM    1. Abre una ventana de Símbolo del Sistema (cmd)
REM    2. Navega a la carpeta del proyecto:  cd /d C:\ruta\al\proyecto
REM    3. Ejecuta este script:               build.bat
REM
REM  RESULTADO:
REM    El ejecutable se genera en:  dist\MiniMarket\MiniMarket.exe
REM ══════════════════════════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║      Mini Market POS - BUILD SCRIPT      ║
echo  ║  Compatible con Windows 7 al 11 (64-bit) ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Activar entorno virtual si existe ──────────────────────────────────────────
IF EXIST "venv\Scripts\activate.bat" (
    echo [INFO] Usando entorno virtual venv...
    call venv\Scripts\activate.bat
)

REM ── Verificar que Python está disponible ─────────────────────────────────────
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.8 o superior.
    pause
    exit /b 1
)

REM ── Verificar/Instalar dependencias ──────────────────────────────────────────
echo [1/4] Instalando dependencias...
pip install -r requirements.txt -q
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

REM ── Eliminar extensiones Cython de SQLAlchemy para máxima compatibilidad ──────
REM  SQLAlchemy compila extensiones en C que son bloqueadas por políticas de
REM  seguridad en Windows 7, 8 y 8.1 cuando el archivo viene de otra PC.
REM  Al eliminarlas, SQLAlchemy usa su modo Python puro (sin pérdida de funciones).
echo.
echo [2/4] Eliminando extensiones Cython de SQLAlchemy para compatibilidad...
python -c "import glob, os, sys; site = os.path.join(sys.prefix, 'Lib', 'site-packages', 'sqlalchemy'); [os.remove(p) for p in glob.glob(site + '/**/*.pyd', recursive=True) if os.path.exists(p)]; print('  Listo: extensiones C verificadas.')"

REM ── Limpiar build anterior ────────────────────────────────────────────────────
echo.
echo [3/4] Limpiando archivos de build anteriores...
IF EXIST "build" rmdir /s /q "build"
IF EXIST "dist"  rmdir /s /q "dist"

REM ── Generar ejecutable ────────────────────────────────────────────────────────
echo.
echo [4/4] Generando ejecutable (esto puede tardar varios minutos)...
pyinstaller -y minimarket.spec --clean

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] La generacion del ejecutable fallo.
    pause
    exit /b 1
)

REM ── Copiar base de datos y archivos auxiliares de distribución ─────────────────
IF EXIST "minimarket.db" (
    echo Copiando base de datos inicial...
    copy "minimarket.db" "dist\MiniMarket\minimarket.db" >nul
)
IF EXIST "assets" (
    echo Copiando carpeta de assets e imagenes...
    xcopy "assets" "dist\MiniMarket\assets\" /E /I /Y >nul
)
IF NOT EXIST "dist\MiniMarket\qrs" mkdir "dist\MiniMarket\qrs"
IF NOT EXIST "dist\MiniMarket\tickets" mkdir "dist\MiniMarket\tickets"
IF NOT EXIST "dist\MiniMarket\comprobantes" mkdir "dist\MiniMarket\comprobantes"

echo.
echo ════════════════════════════════════════════════════════
echo  BUILD EXITOSO
echo  Ejecutable: dist\MiniMarket\MiniMarket.exe
echo.
echo  Para distribuir el software, comparte la carpeta:
echo    dist\MiniMarket\
echo  (incluyendo TODOS los archivos y subcarpetas)
echo.
echo  IMPORTANTE: Compatible con Windows 7, 8, 8.1, 10 y 11.
echo  El usuario final NO necesita instalar nada adicional.
echo ════════════════════════════════════════════════════════
echo.
pause
