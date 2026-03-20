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

REM EBWebView 配下のプロファイルフォルダ内の IndexedDB を探索
REM （プロファイル名は Default / WV2Profile_tfw 等、環境により異なる）
set TEAMS_DB=
set "EBWEBVIEW=%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView"

if not exist "%EBWEBVIEW%" (
    echo [ERROR] Teams の EBWebView フォルダが見つかりません:
    echo   %EBWEBVIEW%
    pause
    exit /b 1
)

for /d %%P in ("%EBWEBVIEW%\*") do (
    if exist "%%P\IndexedDB" (
        set "TEAMS_DB=%%P\IndexedDB"
        goto :found_db
    )
)

echo [ERROR] EBWebView 配下に IndexedDB フォルダが見つかりません
pause
exit /b 1

:found_db
echo   検出: %TEAMS_DB%

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

REM .leveldb と同階層の .blob フォルダを検出（TeamsService.cs と同じロジック）
set "BLOB_PATH=%LEVELDB_PATH:.leveldb=.blob%"
set BLOB_ARG=
if exist "%BLOB_PATH%" (
    set "BLOB_ARG=-b "%BLOB_PATH%""
    echo   blob: %BLOB_PATH%
)

echo   DB: %LEVELDB_PATH%
echo   出力: %OUTPUT_JSON%
echo.

"%PARSER_EXE%" -f "%LEVELDB_PATH%" -o "%OUTPUT_JSON%" %BLOB_ARG%
if errorlevel 1 (
    echo [ERROR] ms_teams_parser.exe の実行に失敗しました
    pause
    exit /b 1
)

echo.
echo === Step 2: 基本検証 ===
echo.

python "%~dp0teams_data_validator.py" "%OUTPUT_JSON%"

echo.
echo === Step 3: 詳細分析 ===
echo.

python "%~dp0teams_deep_analysis.py" "%OUTPUT_JSON%"

echo.
echo === 完了 ===
echo 結果を確認してください。
echo 出力が長い場合は以下でファイルに保存できます:
echo   python "%~dp0teams_deep_analysis.py" "%OUTPUT_JSON%" ^> C:\tmp\analysis_result.txt
pause
