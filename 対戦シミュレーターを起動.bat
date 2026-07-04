@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 既に起動している場合は必ず終了して立ち上げ直す。
rem （使い回すと、コード更新後も古いサーバーが動き続けて修正が反映されないため）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8095" ^| findstr "LISTENING"') do (
    echo 前回のサーバー（PID %%p）を終了して、最新の状態で起動し直します…
    taskkill /f /pid %%p >nul 2>&1
)
timeout /t 1 /nobreak >nul

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
