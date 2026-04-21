#!/usr/bin/env bash
# AllF&B Assistant Bot — tail service logs
# Follows the launchd-captured stdout/stderr of the bot.

LOG_PATH="$HOME/Library/Logs/allfnb-assistant.log"
SERVICE_LABEL="com.allfnb.assistant"

echo "==============================================="
echo "  AllF&B 업무 비서 — 실시간 로그"
echo "==============================================="
echo

# --- Status ---
if launchctl list | grep -q "$SERVICE_LABEL"; then
    PID=$(launchctl list | awk -v svc="$SERVICE_LABEL" '$3 == svc {print $1}')
    STATUS=$(launchctl list | awk -v svc="$SERVICE_LABEL" '$3 == svc {print $2}')
    if [ "$PID" = "-" ]; then
        echo "상태: 등록됨 (비실행 중 — 다음 이벤트 대기 또는 크래시)"
        echo "최근 종료 코드: $STATUS"
    else
        echo "상태: ✅ 실행 중 (PID $PID)"
    fi
else
    echo "상태: ❌ 서비스가 launchd 에 등록되어 있지 않습니다."
    echo "     install_mac_service.command 더블클릭해서 설치하세요."
    echo
fi

echo "로그: $LOG_PATH"
echo "-----------------------------------------------"
echo "(Ctrl+C 로 종료 — 봇은 계속 실행됩니다)"
echo

if [ ! -f "$LOG_PATH" ]; then
    echo "(아직 로그 파일이 없습니다. 서비스가 시작되면 생성됩니다.)"
    # Wait for file to appear, then tail
    while [ ! -f "$LOG_PATH" ]; do sleep 2; done
fi

exec tail -F -n 100 "$LOG_PATH"
