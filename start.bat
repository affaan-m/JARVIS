@echo off
REM ============================================================
REM  JARVIS - lokaal starten (Windows)
REM  Start de FastAPI backend (poort 8000) en de Next.js
REM  frontend (poort 3000) elk in een eigen venster.
REM
REM  Gebruik:  start.bat            normaal starten
REM            start.bat --install  dependencies opnieuw installeren
REM ============================================================
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
set "REINSTALL=0"
if /i "%~1"=="--install" set "REINSTALL=1"

echo.
echo  === JARVIS lokale opstart ===
echo.

REM --- Schrijfrechten controleren ----------------------------
echo test> "%ROOT%.jarvis-write-test" 2>nul
if not exist "%ROOT%.jarvis-write-test" (
    echo [FOUT] Geen schrijfrechten in: %ROOT%
    echo        Staat de repo in een beveiligde map zoals C:\Windows\System32 of C:\Program Files?
    echo        Clone de repo opnieuw in je eigen gebruikersmap, bijvoorbeeld:
    echo            cd %%USERPROFILE%%
    echo            git clone https://github.com/Jabba11111/JARVIS.git
    echo        en start daarna JARVIS\start.bat vanuit die map.
    goto :fail
)
del "%ROOT%.jarvis-write-test" >nul 2>&1

REM --- Vereisten controleren ---------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [FOUT] Python niet gevonden. Installeer Python 3.11 - 3.13 en voeg het toe aan PATH.
    goto :fail
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [FOUT] Node.js/npm niet gevonden. Installeer Node.js 20+.
    goto :fail
)

REM --- .env bestanden ----------------------------------------
if not exist ".env" (
    echo [INFO] .env niet gevonden - kopieer .env.example naar .env
    copy /y ".env.example" ".env" >nul
    echo [LET OP] Vul je API keys in .env in. De app draait ook zonder keys, met beperkte functies.
)
if not exist "frontend\.env.local" if exist "frontend\.env.example" (
    echo [INFO] frontend\.env.local aanmaken vanuit frontend\.env.example
    copy /y "frontend\.env.example" "frontend\.env.local" >nul
)

REM --- Backend: virtualenv + dependencies --------------------
if not exist "backend\.venv\Scripts\python.exe" (
    echo [INFO] Python virtualenv aanmaken in backend\.venv ...
    python -m venv "backend\.venv"
    if errorlevel 1 (
        echo [FOUT] Kon virtualenv niet aanmaken.
        goto :fail
    )
    set "REINSTALL=1"
)
if not exist "backend\.venv\.jarvis-installed" set "REINSTALL=1"

if "%REINSTALL%"=="1" (
    echo [INFO] Backend dependencies installeren - dit kan even duren ...
    pushd backend
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 (
        popd
        echo [FOUT] Installatie van backend dependencies mislukt.
        goto :fail
    )
    echo ok> ".venv\.jarvis-installed"
    popd
)

REM --- Frontend: npm dependencies ----------------------------
if "%REINSTALL%"=="1" goto :npm_install
if not exist "frontend\node_modules" goto :npm_install
goto :npm_done
:npm_install
echo [INFO] Frontend dependencies installeren ...
pushd frontend
if exist ".next" rmdir /s /q ".next"
call npm install
if errorlevel 1 (
    popd
    echo [FOUT] npm install mislukt.
    goto :fail
)
popd
:npm_done

REM --- Starten -----------------------------------------------
echo [INFO] Backend starten op http://localhost:8000 ...
start "JARVIS Backend" cmd /k "cd /d "%ROOT%backend" && .venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"

echo [INFO] Frontend starten op http://localhost:3000 ...
start "JARVIS Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo [INFO] Wachten tot de servers opgestart zijn ...
timeout /t 8 /nobreak >nul
start "" "http://localhost:3000"

echo.
echo  Backend : http://localhost:8000  (health: /api/health, services: /api/services)
echo  Frontend: http://localhost:3000
echo.
echo  Sluit de vensters "JARVIS Backend" en "JARVIS Frontend" om te stoppen.
echo  Optioneel: realtime DB via "cd frontend && npx convex dev".
echo.
endlocal
exit /b 0

:fail
echo.
pause
endlocal
exit /b 1
