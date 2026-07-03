@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Already running? Just open the browser instead of failing on the busy port.
netstat -ano | findstr ":8095" | findstr "LISTENING" >nul && (
    echo すでに起動しています。ブラウザを開きます。
    start "" http://127.0.0.1:8095
    exit /b 0
)

rem CABT engine runs natively on Windows (no Docker needed).
set CABT_ENGINE_MODE=native
set PYTHON=python
set CABT_SAMPLE_SUBMISSION_DIR=%~dp0..\sample_submission

rem First run only: build the app if the bundled files are missing.
if not exist "dist\index.html" (
    echo 初回準備中です（数分かかることがあります）…
    call npm run build
)

echo ================================================
echo  CABT 対戦シミュレーターを起動しています…
echo  ブラウザが自動で開きます: http://127.0.0.1:8095
echo  終了するときは、このウィンドウを閉じてください。
echo ================================================

rem Open the browser once the server has had a moment to start.
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://127.0.0.1:8095"

npx tsx src/engine/server.ts
pause
