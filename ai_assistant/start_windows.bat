@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title AllFnB Assistant Bot

echo ===============================================
echo   AllF^&B 업무 비서 실행기 (Windows)
echo ===============================================
echo.

REM --- Find Python ---
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if "!PYEXE!"=="" (
    where py >nul 2>nul && set "PYEXE=py -3"
)
if "!PYEXE!"=="" (
    echo [오류] Python 3.10 이상이 설치되어 있지 않습니다.
    echo.
    echo https://www.python.org/downloads/ 에서 설치하세요.
    echo  * 설치시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    echo.
    pause
    exit /b 1
)

REM --- Create venv ---
if not exist ".venv" (
    echo [셋업] 가상환경 생성 중...
    !PYEXE! -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

REM --- Install dependencies ---
if not exist ".venv\.deps_installed" (
    echo [셋업] 의존성 설치 중... ^(첫 실행시 1-2분 소요^)
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 의존성 설치 실패.
        pause
        exit /b 1
    )
    echo ok > ".venv\.deps_installed"
)

REM --- Check .env ---
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo ===============================================
    echo   최초 셋업: .env 파일을 메모장에서 열어드립니다.
    echo   아래 3가지를 채운 후 저장^·닫기:
    echo     1. TELEGRAM_BOT_TOKEN
    echo     2. ANTHROPIC_API_KEY
    echo     3. ALLOWED_TELEGRAM_USER_IDS
    echo ===============================================
    echo.
    notepad ".env"
    echo.
    echo .env 저장 완료했으면 아무 키나 누르세요...
    pause >nul
)

REM --- Check credentials.json ---
if not exist "credentials.json" (
    echo.
    echo ===============================================
    echo   credentials.json 파일이 없습니다.
    echo.
    echo   Google Cloud Console 에서:
    echo     1. Calendar API Enable
    echo     2. OAuth Client ID ^(Desktop app^) 생성
    echo     3. JSON 다운로드
    echo     4. 이 폴더에 "credentials.json" 이름으로 저장
    echo.
    echo   자세한 안내는 README.md 참고.
    echo ===============================================
    echo.
    start "" "%~dp0"
    pause
    exit /b 1
)

REM --- Google OAuth (first time only) ---
if not exist "token.json" (
    echo.
    echo [셋업] Google Calendar 최초 인증을 시작합니다.
    echo        브라우저가 열리면 Google 계정으로 로그인^·허용하세요.
    echo.
    python authenticate_gcal.py
    if errorlevel 1 (
        echo [오류] Google 인증 실패.
        pause
        exit /b 1
    )
)

REM --- Launch bot ---
echo.
echo ===============================================
echo   봇 실행 중... 종료하려면 이 창을 닫으세요.
echo ===============================================
echo.
python main.py
echo.
echo [봇 종료됨]
pause
