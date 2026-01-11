@echo off
:: 关闭指令回显，使界面整洁
setlocal enabledelayedexpansion
:: 使用 GBK 编码（控制台默认编码），避免 chcp 65001 导致的兼容性问题
cd /d "%~dp0"

:MENU
cls
echo ==================================================
echo         Beancount AI 账单智能导入工具
echo ==================================================
echo.

:: 扫描 bills 文件夹下的所有支持的文件
set i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    set "file!i!=%%f"
    set "fullPath!i!=%~dp0bills\%%f"
    echo  [!i!] %%f
)

if %i%==0 (
    echo.
    echo  (当前 bills 文件夹为空)
    echo.
    echo  [R] 刷新  [Q] 退出
    echo.
    set /p choice="请选择: "
    if /i "%choice%"=="R" goto MENU
    if /i "%choice%"=="Q" exit /b
    goto MENU
)

echo.
echo -----------------------------------------------------------
echo  使用说明:
echo    - 输入单个数字: 导入单个文件 (如: 1)
echo    - 输入多个数字: 批量导入 (如: 1 3 5 或 1,3,5)
echo    - 输入 A: 导入所有文件
echo    - 输入 R: 刷新列表  [Q] 退出程序
echo -----------------------------------------------------------
echo.
set /p choice="请输入文件编号: "

:: 检查退出和刷新
if /i "%choice%"=="Q" exit /b
if /i "%choice%"=="R" goto MENU

:: 检查是否输入了 A（导入全部）
if /i "%choice%"=="A" (
    goto IMPORT_ALL
)

:: 解析输入：支持空格和逗号分隔
set filesParam=
set selected_count=0
set invalid_input=
set first_file=
set first_path=

:: 替换逗号为空格
set "input=%choice:,= %"

:: 提取第一个文件（用于单个文件处理）
for /f "tokens=1" %%f in ("%input%") do (
    set "first_num=%%f"
)

for %%s in (%input%) do (
    :: 检查是否是有效的数字
    set "isNumber=true"
    for /f "delims=0123456789" %%a in ("%%s") do set "isNumber=false"

    if "!isNumber!"=="true" (
        :: 数字范围检查
        if %%s gtr 0 if %%s leq %i% (
            :: 构建文件参数 - 使用延迟扩展获取变量
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
        ) else (
            set invalid_input=true
        )
    )
)

:: 检查无效输入
if "!invalid_input!"=="true" (
    echo [错误] 输入的编号超出范围，请重新输入！
    timeout /t 2 >nul
    goto MENU
)

:: 检查是否有有效选择
if !selected_count!==0 (
    echo [错误] 无效输入，请重新输入！
    timeout /t 2 >nul
    goto MENU
)

:: 执行导入
if !selected_count!==1 (
    :: 单个文件处理
    echo.
    echo [处理中] 正在解析: !first_file!
    python scripts/importer_main_v2.py --file "!first_path!"

    echo.
    echo [归档] 正在移动文件...
    if !errorlevel! equ 0 (
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!first_path!"
        echo [完成] 处理成功。
    ) else (
        echo [跳过] 解析出错，文件保留。
    )
) else (
    :: 批量文件处理
    echo.
    echo [处理中] 开始批量处理 !selected_count! 个文件...
    python scripts/importer_main_v2.py --batch --files !filesParam!

    echo.
    echo [归档] 正在移动文件...
    if !errorlevel! equ 0 (
        :: 批量归档
        for %%s in (%input%) do (
            for /f "delims=" %%x in ("!fullPath%%s!") do set "filepath=%%x"
            if defined filepath (
                powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "!filepath!"
            )
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
:: 导入所有文件
cls
echo ==================================================
echo         导入所有文件
echo ==================================================
echo.

:: 构建所有文件的参数
set filesParam=
set /a i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    set "filesParam=!filesParam! "%~dp0bills\%%f""
)

echo 找到 %i% 个文件待处理
echo.
set /p confirm="确认导入所有 %i% 个文件？ [Y/N]: "
set /p=
choice /c /n /m "确认选择: " /d /t 2 >nul
if /i "!confirm!"=="N" goto MENU
if /i "!confirm!"=="Q" goto MENU

echo.
echo [处理中] 开始批量处理 %i% 个文件...
python scripts/importer_main_v2.py --batch --files !filesParam!

echo.
echo [归档] 正在移动文件...
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
