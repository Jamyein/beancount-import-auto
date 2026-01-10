@echo off
REM ===============================
REM Fava 启动入口（bat）
REM 仅负责调用 PowerShell 脚本
REM ===============================

REM 切换到 bat 所在目录（防止路径错乱）
cd /d %~dp0

REM 调用 PowerShell 执行 start-fava.ps1
powershell -NoProfile -ExecutionPolicy Bypass ^
  -File "scripts\start-fava.ps1"

REM 防止窗口一闪而过
echo.
echo Fava 已退出，按任意键关闭窗口
pause >nul
