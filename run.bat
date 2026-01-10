@echo off
:: 关闭指令回显，使界面整洁
setlocal enabledelayedexpansion
:: 设置字符集为 UTF-8 以支持中文显示
chcp 65001 >nul
cd /d "%~dp0"

:MENU
cls
echo ==================================================
echo         Beancount AI 账单智能导入工具
echo ==================================================
echo.
echo [待处理列表] (支持 CSV / XLSX):
echo.

set i=0
:: 扫描 bills 文件夹下的所有 CSV 和 XLSX 文件
:: 使用 dir /b 组合两个通配符
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" 2^>nul') do (
    set /a i+=1
    set "file!i!=%%f"
    set "fullPath!i!=%~dp0bills\%%f"
    echo  [!i!] %%f
)

if %i%==0 (
    echo  (当前 bills 文件夹为空)
    echo.
    echo  [R] 刷新  [Q] 退出
) else (
    echo.
    echo  [Q] 退出程序
)

echo.
set /p choice="请输入文件编号: "

if /i "%choice%"=="Q" exit /b
if /i "%choice%"=="R" goto MENU

:: 检查输入的编号是否存在
if not defined file%choice% (
    echo [错误] 无效编号，请重新输入！
    timeout /t 2 >nul
    goto MENU
)

set "selectedFile=!file%choice%!"
set "selectedPath=!fullPath%choice%!"

echo.
echo --------------------------------------------------
echo [1/2] 正在解析: !selectedFile!
:: 调用 Python 脚本处理账单
python scripts/importer_main.py --file "!selectedPath!"

echo.
echo [2/2] 正在归档文件...
:: 只有 Python 返回 0 (成功) 时才执行归档 
if %errorlevel% equ 0 (
    echo [归档] 正在移动文件...
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!selectedPath!"
    echo [完成] 处理成功。
) else (
    echo [跳过] 解析出错，文件保留在 bills 文件夹中。 
)

echo.
echo --------------------------------------------------
echo 处理完成！
pause
goto MENU