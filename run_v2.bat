@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

:MENU
cls
echo ==================================================
echo         Beancount AI 账单智能导入工具
echo ==================================================
echo.
echo.
echo  使用说明: 输入数字导入文件，多个数字间空格或逗号，输入 A 导入全部
echo.
echo.
echo [待处理列表] (支持 CSV / XLSX):
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
)

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
    echo -----------------------------------------------------------
    set success_count=0
    set failed_count=0

    for %%s in (%input%) do (
        if %%s gtr 0 if %%s leq %i% (
            for /f "delims=" %%x in ("!fullPath%%s!") do set "filepath=%%x"
            for /f "delims=" %%x in ("!file%%s!") do set "filename=%%x"

            echo.
            echo [处理中] 正在解析: !filename!
            python scripts/importer_main_v2.py --file "!filepath!"

            if !errorlevel! equ 0 (
                powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!filepath!"
                echo [完成] !filename! 处理成功。
                set /a success_count+=1
            ) else (
                echo [跳过] !filename! 解析出错，文件保留。
                set /a failed_count+=1
            )
        )
    )

    echo.
    echo -----------------------------------------------------------
    echo 批量处理完成！
    echo 成功: !success_count! 个
    echo 失败: !failed_count! 个
    echo -----------------------------------------------------------
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
echo -----------------------------------------------------------
set success_count=0
set failed_count=0
set /a file_index=0

for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a file_index+=1
    set "current_file=%~dp0bills\%%f"
    set "file_name=%%f"

    echo.
    echo [!file_index!/%i%] 正在解析: !file_name!
    python scripts/importer_main_v2.py --file "!current_file!"

    if !errorlevel! equ 0 (
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!current_file!"
        echo [完成] !file_name! 处理成功。
        set /a success_count+=1
    ) else (
        echo [跳过] !file_name! 解析出错，文件保留。
        set /a failed_count+=1
    )
)

echo.
echo -----------------------------------------------------------
echo 批量处理完成！
echo 成功: !success_count! 个
echo 失败: !failed_count! 个
echo -----------------------------------------------------------

echo.
echo -----------------------------------------------------------
echo 批量处理完成！
echo -----------------------------------------------------------
echo.
pause
goto MENU

:MENU
goto MENU
