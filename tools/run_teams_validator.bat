@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set PARSER_EXE=%~dp0ms_teams_parser.exe
set OUTPUT_JSON=%TEMP%\teams_output.json

echo === Step 1: Teams データのパース ===

if not exist "%PARSER_EXE%" (
    echo [ERROR] ms_teams_parser.exe が見つかりません: %PARSER_EXE%
    pause
    exit /b 1
)

REM Teams IndexedDB の候補パスを順に探索
set TEAMS_DB=
set "CANDIDATE1=%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView\Default\IndexedDB"
set "CANDIDATE2=%LOCALAPPDATA%\Microsoft\MSTeams\EBWebView\Default\IndexedDB"
set "CANDIDATE3=%APPDATA%\Microsoft\Teams\IndexedDB"

for %%C in ("%CANDIDATE1%" "%CANDIDATE2%" "%CANDIDATE3%") do (
    if exist %%C (
        set "TEAMS_DB=%%~C"
        goto :found_db
    )
)

echo [ERROR] Teams の IndexedDB フォルダが見つかりません。
echo   以下のパスを確認しましたが、いずれも存在しません:
echo     %CANDIDATE1%
echo     %CANDIDATE2%
echo     %CANDIDATE3%
echo.
echo   Teams がインストールされていないか、別のパスにある可能性があります。
echo   IndexedDB フォルダのパスを手動で指定して実行してください:
echo     run_teams_validator.bat "C:\path\to\IndexedDB"
pause
exit /b 1

:found_db
echo   検出: %TEAMS_DB%

REM コマンドライン引数でパスが指定された場合はそちらを優先
if not "%~1"=="" (
    set "TEAMS_DB=%~1"
    echo   手動指定: %TEAMS_DB%
)

REM IndexedDB 内の .leveldb フォルダを探す
set LEVELDB_PATH=
for /d %%d in ("%TEAMS_DB%\*") do (
    if exist "%%d\*.ldb" set "LEVELDB_PATH=%%d"
)

if "%LEVELDB_PATH%"=="" (
    echo [ERROR] .ldb ファイルを含むフォルダが見つかりません: %TEAMS_DB%
    pause
    exit /b 1
)

echo   DB: %LEVELDB_PATH%
echo   出力: %OUTPUT_JSON%
echo.

"%PARSER_EXE%" -f "%LEVELDB_PATH%" -o "%OUTPUT_JSON%"
if errorlevel 1 (
    echo [ERROR] ms_teams_parser.exe の実行に失敗しました
    pause
    exit /b 1
)

echo.
echo === Step 2: データ検証 ===
echo.

python "%~dp0teams_data_validator.py" "%OUTPUT_JSON%"

echo.
echo === 完了 ===
echo 結果を確認してください。
pause
