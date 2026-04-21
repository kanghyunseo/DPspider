#!/usr/bin/env bash
# AllF&B Assistant Bot — macOS service uninstaller

set -u
SERVICE_LABEL="com.allfnb.assistant"
PLIST_DEST="$HOME/Library/LaunchAgents/${SERVICE_LABEL}.plist"

echo "==============================================="
echo "  AllF&B 업무 비서 — 상시 실행 서비스 제거"
echo "==============================================="
echo

pause_exit() {
    echo
    read -rp "(엔터로 창 닫기) " _
    exit "${1:-0}"
}

if [ ! -f "$PLIST_DEST" ]; then
    echo "ℹ️  서비스가 등록되어 있지 않습니다."
    pause_exit 0
fi

# Stop & unregister
launchctl unload "$PLIST_DEST" 2>/dev/null || true
rm -f "$PLIST_DEST"

sleep 1
if launchctl list | grep -q "$SERVICE_LABEL"; then
    echo "⚠️  서비스가 여전히 실행 중으로 보입니다. 수동 종료:"
    echo "   launchctl remove $SERVICE_LABEL"
    pause_exit 1
fi

echo "✅ 제거 완료. 봇이 더 이상 백그라운드에서 실행되지 않습니다."
echo
echo "💡 다시 돌리려면:"
echo "   - 일회성: start_mac.command 더블클릭"
echo "   - 상시:   install_mac_service.command 더블클릭"
echo
echo "📦 로컬 파일(.env, token.json, assistant.db 등)은 그대로 남아 있습니다."

pause_exit 0
