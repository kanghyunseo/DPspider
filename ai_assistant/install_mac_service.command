#!/usr/bin/env bash
# AllF&B Assistant Bot — macOS 24/7 service installer
# Registers the bot as a launchd LaunchAgent so it auto-starts on login
# and auto-restarts on crash.

set -u
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
SERVICE_LABEL="com.allfnb.assistant"
PLIST_TEMPLATE="$PROJECT_DIR/com.allfnb.assistant.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/${SERVICE_LABEL}.plist"
LOG_PATH="$HOME/Library/Logs/allfnb-assistant.log"

echo "==============================================="
echo "  AllF&B 업무 비서 — 상시 실행 서비스 등록"
echo "==============================================="
echo

pause_exit() {
    echo
    read -rp "(엔터로 창 닫기) " _
    exit "${1:-0}"
}

# --- 1. Check prerequisites ---
missing=0
for required in ".venv/bin/python" "main.py" ".env" "credentials.json" "token.json"; do
    if [ ! -e "$required" ]; then
        if [ "$missing" -eq 0 ]; then
            echo "[오류] 최초 셋업이 완료되지 않았습니다. 누락된 파일:"
            missing=1
        fi
        echo "  ❌ $required"
    fi
done
if [ "$missing" -ne 0 ]; then
    echo
    echo "👉 먼저 start_mac.command 를 더블클릭해서 한번 실행하여"
    echo "   최초 셋업(가상환경, .env, Google 인증)을 완료하세요."
    pause_exit 1
fi

if [ ! -f "$PLIST_TEMPLATE" ]; then
    echo "[오류] plist 템플릿을 찾을 수 없습니다: $PLIST_TEMPLATE"
    pause_exit 1
fi

# --- 2. Render plist ---
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/Library/Logs"

# BSD sed-safe (macOS): use | as delimiter, no -E needed
sed \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__HOME__|$HOME|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

echo "[1/3] plist 생성: $PLIST_DEST"

# --- 3. (Re)load into launchd ---
# Unload first if already installed (idempotent install/upgrade)
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load -w "$PLIST_DEST"
echo "[2/3] launchd 에 등록 완료"

# --- 4. Verify ---
sleep 2
if launchctl list | grep -q "$SERVICE_LABEL"; then
    PID=$(launchctl list | awk -v svc="$SERVICE_LABEL" '$3 == svc {print $1}')
    echo "[3/3] 실행 확인: PID=$PID"
    echo
    echo "==============================================="
    echo "  ✅ 설치 완료"
    echo "==============================================="
    echo
    echo "🤖 봇이 백그라운드에서 실행 중입니다."
    echo "   맥 재시작·로그인할 때마다 자동으로 다시 켜집니다."
    echo
    echo "📄 로그 파일:   $LOG_PATH"
    echo "👀 로그 실시간: service_logs.command 더블클릭"
    echo "🗑️  제거:       uninstall_mac_service.command 더블클릭"
    echo
    echo "⚠️  주의: 맥북 뚜껑을 닫으면 잠들어서 봇이 멈춥니다."
    echo "   뚜껑 열어두거나 클램쉘(외장모니터+전원+키보드) 모드로 쓰세요."
    echo "   자세한 내용은 docs/MACOS_SERVICE.md 참고."
else
    echo "[3/3] ⚠️  launchd list 에서 서비스를 찾을 수 없습니다."
    echo "   로그를 확인해주세요: $LOG_PATH"
    echo "   최근 로그 (tail 20):"
    echo "------"
    tail -n 20 "$LOG_PATH" 2>/dev/null || echo "(아직 로그 없음)"
    echo "------"
fi

pause_exit 0
