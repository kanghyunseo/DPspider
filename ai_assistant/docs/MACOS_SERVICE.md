# macOS 24시간 상시 실행 가이드

맥북에 launchd 서비스로 등록해서 **로그인시 자동 시작 + 크래시시 자동 재시작** 되게 하는 방법입니다.

## 선행 조건

먼저 [README.md](../README.md#-빠른-시작-더블클릭-실행) 의 "빠른 시작" 을 한번 해두세요. `start_mac.command` 를 더블클릭해서 봇이 정상 구동되는 걸 확인 → 터미널 창 닫아서 봇 종료. 이 시점에 필요한 파일이 모두 생성됩니다:

- `.venv/` (가상환경)
- `.env`
- `credentials.json`
- `token.json`
- `assistant.db`

## 설치

`ai_assistant` 폴더의 **`install_mac_service.command`** 더블클릭.

```
✅ 설치 완료
🤖 봇이 백그라운드에서 실행 중입니다.
   맥 재시작·로그인할 때마다 자동으로 다시 켜집니다.
```

가 뜨면 끝. 터미널 창 닫아도 봇은 계속 돌아갑니다.

### 설치 후 해야 할 일 (한 번만)

#### 맥이 안 자게 설정 — **가장 중요**

맥북 뚜껑을 닫거나 맥이 잠들면 봇이 멈춥니다. 다음 중 하나 선택:

**옵션 A: 뚜껑 열고 책상 위 상시 전원 (가장 쉬움)**
1. 시스템 설정 → **배터리** → **옵션...**
2. "**전원 어댑터 연결 시 디스플레이가 꺼져 있을 때 자동으로 잠자지 않음**" **켬**
3. 맥북을 책상 위에 전원 연결, 뚜껑 열어둠 (디스플레이는 꺼져도 됨)

**옵션 B: 클램쉘 모드 (뚜껑 닫고 외장모니터 사용)**
1. 외장 모니터 + 전원 + 무선(혹은 유선) 키보드/마우스 연결
2. 뚜껑 닫아도 맥은 깨어있음 (외장모니터가 주 디스플레이 역할)
3. 완전한 "데스크톱처럼" 쓸 수 있음

**옵션 C: Amphetamine 앱** (App Store 에서 무료)
- 메뉴바 아이콘 클릭 → 항상 켜짐 모드 활성화
- 뚜껑 열어놓은 상태 전제

## 상태 확인 / 로그 보기

**`service_logs.command`** 더블클릭.

```
상태: ✅ 실행 중 (PID 12345)
로그: /Users/홍길동/Library/Logs/allfnb-assistant.log
-----
(실시간 로그 스트림)
```

로그 창은 닫아도 봇에는 영향 없습니다 (Ctrl+C 또는 창 닫기).

## 제거

**`uninstall_mac_service.command`** 더블클릭. 봇 중지 + launchd 등록 해제. `.env`, `token.json` 등 파일은 그대로 남음.

## 명령어 요약

| 동작 | 방법 |
|---|---|
| 최초 셋업 | `start_mac.command` (1회) |
| 상시 실행 등록 | `install_mac_service.command` |
| 로그 보기 | `service_logs.command` |
| 상시 실행 해제 | `uninstall_mac_service.command` |
| 포그라운드 테스트 실행 | `start_mac.command` (제거 후에만 — 중복 실행 불가) |

## 내부 동작

- **LaunchAgent** 로 등록 (`~/Library/LaunchAgents/com.allfnb.assistant.plist`)
  - 시스템 전역 데몬(LaunchDaemon)이 아닌 **유저 단위** 서비스 → 관리자 권한 불필요
- 로그인시 자동 시작 (`RunAtLoad=true`)
- 크래시시 60초 후 자동 재시작 (`KeepAlive=true`, `ThrottleInterval=60`)
- 로그는 `~/Library/Logs/allfnb-assistant.log` 에 누적 저장
- 타임존 `Asia/Seoul` 강제 설정 (주간 리포트 cron 정확성용)

### 주간 리포트 miss-fire 처리

맥이 금요일 17시에 잠자고 있었으면 APScheduler 가 그 시각을 놓칩니다.
본 구현은 **12시간 grace period** 로 설정되어 있어서:

- 금 17:00 에 맥이 잠 → 월요일 아침 9시 깨움 → **리포트 실행 안 함** (12시간 넘김)
- 금 17:00 에 맥이 잠 → 금 20:00 깨움 → **리포트 바로 실행** (3시간 차이)

> Railway 는 24/7 깨어있으니 miss-fire 걱정 없음. 맥북 로컬은 이 리스크가 있으니 **중요 리포트는 수동 `/report` 로 한번 더 체크** 추천.

## 트러블슈팅

### 설치했는데 봇이 응답 안함

1. `service_logs.command` 로 로그 확인
2. 로그 첫 줄에 `Bot starting ...` 이 있는지? 없으면 크래시 중
3. 흔한 원인:
   - `.env` 에 키 오타 → 수정 → `install_mac_service.command` 재실행 (자동 재등록)
   - `token.json` 만료/권한부족 → `start_mac.command` 의 OAuth 재실행

### "launchctl load: Invalid property list"

plist 파일이 깨짐. 다음 실행:
```bash
plutil ~/Library/LaunchAgents/com.allfnb.assistant.plist
```
에러 메시지 확인 후 `install_mac_service.command` 재실행.

### 맥 재시작 후 봇이 안 뜸

- 로그인 화면에서 실제로 **로그인** 했는지 확인 (LaunchAgent 는 로그인 세션에서만 동작)
- 자동 로그인 설정: 시스템 설정 → 사용자 및 그룹 → 자동 로그인

### 두 번 실행됨 (봇이 중복 응답)

`start_mac.command` 와 `install_mac_service.command` 를 **동시에** 돌렸을 때 발생.
→ 하나만 실행. 상시 운영이면 install 만.
→ start 창 종료 + `uninstall_mac_service.command` → 다시 install

### 봇 코드 업데이트 후 반영하려면

1. git pull 또는 새 파일 받기
2. `uninstall_mac_service.command` 더블클릭
3. `install_mac_service.command` 더블클릭 — 새 코드 기준으로 재등록

또는 수동:
```bash
launchctl kickstart -k gui/$(id -u)/com.allfnb.assistant
```

## 맥북 로컬 vs Railway 비교

| 항목 | 맥북 로컬 | Railway |
|---|---|---|
| 초기 비용 | 0원 (맥이 있으니까) | 월 $5 ~ |
| API 비용 | 동일 | 동일 |
| 재부팅시 | 로그인 후 자동 시작 | 즉시 자동 시작 |
| 잠들 때 | 봇 정지 ⚠️ | 걱정 없음 |
| 뚜껑 닫을 때 | 봇 정지 ⚠️ (클램쉘 제외) | 걱정 없음 |
| 네트워크 끊김 | 봇 정지 | 걱정 없음 |
| 업데이트 | 파일 복붙 / git pull + 재설치 | git push 만 |
| 로그 보기 | service_logs.command | Railway 웹 대시보드 |

**추천:** 며칠~몇 주 운용해보다가 안정성·이동성이 필요하다 싶으면 Railway 로 이전. 이전은 `docs/RAILWAY.md` 참고 — 같은 `.env`·`token.json` 을 환경변수로 옮기기만 하면 됩니다.
