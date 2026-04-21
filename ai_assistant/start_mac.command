#!/usr/bin/env bash
# AllF&B Assistant Bot launcher (macOS)
# Double-click to run. First run performs setup; later runs just start the bot.

set -u
cd "$(dirname "$0")"

echo "==============================================="
echo "  AllF&B 업무 비서 실행기 (macOS)"
echo "==============================================="
echo

pause_and_exit() {
    echo
    read -rp "(엔터를 눌러 이 창을 닫으세요) " _
    exit "${1:-0}"
}

# --- Find Python ---
if command -v python3 >/dev/null 2>&1; then
    PYEXE="python3"
else
    echo "[오류] Python 3.10 이상이 설치되어 있지 않습니다."
    echo
    echo "설치 방법:"
    echo "  A) https://www.python.org/downloads/ 에서 설치"
    echo "  B) 터미널에서: brew install python@3.12"
    pause_and_exit 1
fi

# --- Create venv ---
if [ ! -d ".venv" ]; then
    echo "[셋업] 가상환경 생성 중..."
    "$PYEXE" -m venv .venv || { echo "[오류] 가상환경 생성 실패"; pause_and_exit 1; }
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# --- Install dependencies ---
if [ ! -f ".venv/.deps_installed" ]; then
    echo "[셋업] 의존성 설치 중... (첫 실행시 1-2분 소요)"
    pip install --upgrade pip >/dev/null
    pip install -r requirements.txt || { echo "[오류] 의존성 설치 실패"; pause_and_exit 1; }
    touch .venv/.deps_installed
fi

# --- Check .env ---
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo
    echo "==============================================="
    echo "  최초 셋업: .env 파일을 편집기에서 열어드립니다."
    echo "  아래 3가지를 채운 후 저장·닫기:"
    echo "    1. TELEGRAM_BOT_TOKEN"
    echo "    2. ANTHROPIC_API_KEY"
    echo "    3. ALLOWED_TELEGRAM_USER_IDS"
    echo "==============================================="
    echo
    if command -v open >/dev/null 2>&1; then
        open -t .env
    fi
    read -rp ".env 저장 완료했으면 엔터: " _
fi

# --- Check credentials.json ---
if [ ! -f "credentials.json" ]; then
    echo
    echo "==============================================="
    echo "  credentials.json 파일이 없습니다."
    echo
    echo "  Google Cloud Console 에서:"
    echo "    1. Calendar API Enable"
    echo "    2. OAuth Client ID (Desktop app) 생성"
    echo "    3. JSON 다운로드"
    echo "    4. 이 폴더에 \"credentials.json\" 이름으로 저장"
    echo
    echo "  자세한 안내는 README.md 참고."
    echo "==============================================="
    if command -v open >/dev/null 2>&1; then
        open .
    fi
    pause_and_exit 1
fi

# --- Google OAuth (first time only) ---
if [ ! -f "token.json" ]; then
    echo
    echo "[셋업] Google Calendar 최초 인증을 시작합니다."
    echo "       브라우저가 열리면 Google 계정으로 로그인·허용하세요."
    echo
    python authenticate_gcal.py || { echo "[오류] Google 인증 실패"; pause_and_exit 1; }
fi

# --- Launch bot ---
echo
echo "==============================================="
echo "  봇 실행 중... 종료하려면 이 창을 닫으세요."
echo "==============================================="
echo
python main.py
echo
echo "[봇 종료됨]"
pause_and_exit 0
