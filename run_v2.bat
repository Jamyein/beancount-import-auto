@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

cls
echo ==================================================
echo         Beancount AI 账单智能导入工具
echo ==================================================
echo.

set i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    set "file!i!=%%f"
    set "fullPath!i!=%~dp0bills\%%f"
    echo  [!i!] %%f
)

echo.
if %i%==0 (
    echo  (当前 bills 文件夹为空)
    echo  [R] 刷新  [Q] 退出
    echo.
    set /p choice="请选择: "
    if /i "%choice%"=="R" goto MENU
    if /i "%choice%"=="Q" exit /b
    goto MENU
)

echo -----------------------------------------------------------
echo  使用说明: 输入数字导入文件，输入 A 导入全部
echo -----------------------------------------------------------
echo.
set /p choice="请输入文件编号: "

if /i "%choice%"=="Q" exit /b
if /i "%choice%"=="R" goto MENU
if /i "%choice%"=="A" goto IMPORT_ALL

set filesParam=
set selected_count=0
set "input=%choice:,= %"

for %%s in (%input%) do (
    if %%s gtr 0 if %%s leq %i% (
        for /f "delims=" %%x in ("!file%%s!") do set "filename=%%x"
        for /f "delims=" %%x in ("!fullPath%%s!") do set "filepath=%%x"

        if !selected_count!==0 (
            set "filesParam=!filesParam! "!filepath!""
            set "first_file=!filename!"
            set "first_path=!filepath!"
        ) else (
            set "filesParam=!filesParam! "!filepath!""
        )
        set /a selected_count+=1
    )
)

if !selected_count!==1 (
    echo.
    echo [处理中] 正在解析: !first_file!
    python scripts/importer_main_v2.py --file "!first_path!"
    if !errorlevel! equ 0 (
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!first_path!"
        echo [完成] 处理成功。
    ) else (
        echo [跳过] 解析出错，文件保留。
    )
) else (
    echo.
    echo [处理中] 开始批量处理 !selected_count! 个文件...
    python scripts/importer_main_v2.py --batch --files !filesParam!
    if !errorlevel! equ 0 (
        for %%s in (%input%) do (
            for /f "delims=" %%x in ("!fullPath%%s!") do set "filepath=%%x"
            powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!filepath!"
        )
        echo [完成] 批量处理成功。
    ) else (
        echo [警告] 部分文件处理失败。
    )
)

echo.
echo -----------------------------------------------------------
echo 处理完成！
echo -----------------------------------------------------------
echo.
pause
goto MENU


:IMPORT_ALL
cls
echo ==================================================
echo         导入所有文件
echo ==================================================
echo.

set filesParam=
set /a i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    set "filesParam=!filesParam! "%~dp0bills\%%f""
)

echo 找到 %i% 个文件待处理
echo.
set /p confirm="确认导入所有 %i% 个文件？ [Y/N]: "

if /i "!confirm!"=="N" goto MENU

echo.
echo [处理中] 开始批量处理 %i% 个文件...
python scripts/importer_main_v2.py --batch --files !filesParam!

if !errorlevel! equ 0 (
    for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "%~dp0bills\%%f"
    )
    echo [完成] 全部处理成功。
) else (
    echo [警告] 部分文件处理失败。
)

echo.
echo -----------------------------------------------------------
echo 批量处理完成！
echo -----------------------------------------------------------
echo.
pause
goto MENU

:MENU
goto MENU
