@echo off
chcp 65001 >nul
setlocal EnableExtensions

REM ============================================================
REM  network-autosave 一键启动脚本
REM  用法:
REM    start.bat              开发模式：后端 + 前端（推荐）
REM    start.bat backend      仅启动后端  http://localhost:5000
REM    start.bat frontend     仅启动前端  http://localhost:3001
REM ============================================================

cd /d "%~dp0"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=dev"

if /i not "%MODE%"=="dev" if /i not "%MODE%"=="backend" if /i not "%MODE%"=="frontend" (
  echo [错误] 未知参数: %MODE%
  echo 用法: start.bat [dev^|backend^|frontend]
  pause
  exit /b 1
)

echo ========================================
echo   network-autosave 启动
echo   模式: %MODE%
echo ========================================
echo.

if /i "%MODE%"=="frontend" goto START_FRONTEND

REM ---------- 解析 Python ----------
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
  echo [OK] 使用虚拟环境: .venv
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未找到 Python，且不存在 .venv
    echo 请先安装 Python 3.10，或执行:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
  )
  for /f "delims=" %%i in ('where python') do set "PYTHON_EXE=%%i" & goto PYTHON_READY
)
:PYTHON_READY
"%PYTHON_EXE%" --version
if errorlevel 1 (
  echo [错误] Python 无法运行: %PYTHON_EXE%
  pause
  exit /b 1
)

if /i "%MODE%"=="backend" (
  echo.
  echo [启动] 后端 Flask  http://localhost:5000
  echo 默认账号: admin / admin123
  echo 按 Ctrl+C 停止
  echo.
  "%PYTHON_EXE%" web_app.py
  goto :eof
)

REM 开发模式：后端新窗口，当前窗口跑前端
echo [启动] 后端 ^(新窗口^) http://localhost:5000
start "network-autosave-backend" cmd /k "cd /d ""%~dp0"" && ""%PYTHON_EXE%"" web_app.py"

echo [等待] 后端就绪中...
set /a "_wait=0"
:WAIT_BACKEND
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',5000); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo [OK] 后端已监听 5000
  goto START_FRONTEND
)
set /a "_wait+=1"
if %_wait% LSS 60 goto WAIT_BACKEND
echo [错误] 后端 60 秒内未就绪，请查看标题为 network-autosave-backend 的窗口报错
echo 前端仍会启动，但登录会失败，直到后端可用。
echo.

:START_FRONTEND
where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未安装 Node.js，请先安装 Node.js 18+
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 npm
  pause
  exit /b 1
)

cd /d "%~dp0frontend"
if not exist "node_modules\" (
  echo [安装] 前端依赖 npm install ...
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
  )
)

echo.
echo [启动] 前端 Vite  http://localhost:3001
echo 后端 API: http://localhost:5000
echo 默认账号: admin / admin123
echo.
echo 按 Ctrl+C 停止前端
if /i "%MODE%"=="dev" echo （开发模式下后端在独立窗口运行，关闭该窗口可停后端）
echo.
call npm run dev
pause
exit /b 0
