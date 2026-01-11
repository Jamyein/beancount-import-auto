@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

cls
echo ==================================================
echo     Beancount AI Bill Import Tool
echo ==================================================
echo.

set i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    echo  [!i!] %%f
)

echo.
if %i%==0 (
    echo  No bills found
    echo  [R] Refresh  [Q] Quit
    echo.
    set /p choice="Select: "
    if /i "%choice%"=="R" goto MENU
    if /i "%choice%"=="Q" exit /b
    goto MENU
)

echo -------------------------------------------------
echo  Input number (1 3 5) or A for all
echo -------------------------------------------------
echo.
set /p choice="Input: "

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
    echo Processing: !first_file!
    python scripts/importer_main_v2.py --file "!first_path!"
    if !errorlevel! equ 0 (
        echo Success
    ) else (
        echo Failed
    )
) else (
    echo Processing !selected_count! files
    python scripts/importer_main_v2.py --batch --files !filesParam!
    if !errorlevel! equ 0 (
        echo Batch success
    ) else (
        echo Batch failed
    )
)

echo.
set /p confirm="Done. Press Enter to return to menu"
goto MENU


:IMPORT_ALL
cls
echo ==================================================
echo         Import All Files
echo ==================================================
echo.

set filesParam=
set /a i=0
for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
    set /a i+=1
    set "filesParam=!filesParam! "%~dp0bills\%%f""
)

echo Found %i% files
echo.
set /p confirm="Import all files? [Y/N]: "

if /i "%confirm%"=="N" goto MENU

python scripts/importer_main_v2.py --batch --files !filesParam!

if !errorlevel! equ 0 (
    for /f "delims=" %%f in ('dir /b /a-d "bills\*.csv" "bills\*.xlsx" "bills\*.xls" "bills\*.pdf" 2^>nul') do (
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/selector.ps1" -targetFile "%~dp0bills\%%f"
    )
    echo All files processed
) else (
    echo Some files failed
)

echo.
set /p confirm="Done. Press Enter to return to menu"
goto MENU
