# 올에프인비 업무 비서

글로벌사업팀장용 Telegram 비서. 자연어 지시 → Claude API 분석 → Google Calendar 일정 관리 + 주간 리포트 자동 생성·Drive 업로드.

## 기능

| 기능 | 설명 |
|---|---|
| 📅 **스케줄링** | 텔레그램 메시지로 Google Calendar 일정 등록·조회·수정·삭제 |
| 📋 **주간 리포트** | 매주 금 17:00 KST 자동. 이번주 일정 정리 + **Airwallex 수익·지출 요약** → Google Docs 업로드 |
| 🌏 **F&B 트렌드 브리프** | 매주 월 09:00 KST 자동. 지정 국가들의 외식 트렌드를 웹에서 조사 → Google Docs |
| 💰 **Airwallex 연동** | 주간 리포트에 통화별 잔액, 입출금 요약, Top 5 거래 포함 (선택) |
| 📂 **Drive 연동** | 모든 리포트는 Google Docs 로 저장 (편집 가능) |

## 사용 예시

```
팀장 → 내일 오후 3시에 싱가포르 매장 리뷰 미팅 1시간 잡아줘
봇   → ✅ 등록 완료: 4/22(화) 15:00–16:00 "싱가포르 매장 리뷰 미팅"

팀장 → 이번주 일정 다 보여줘
봇   → 이번주(4/21~4/27) 일정 5건:
       - 4/22(화) 15:00 싱가포르 매장 리뷰 미팅
       ...

팀장 → /report
봇   → 📋 주간 리포트 업로드 완료
       📅 2026-04-20 ~ 2026-04-26
       📝 일정 8건
       🔗 https://docs.google.com/document/d/...
```

---

## 🚀 빠른 시작 (더블클릭 실행)

### Windows

1. `ai_assistant` 폴더 안의 **`start_windows.bat`** 더블클릭
2. 처음 실행시 자동으로:
   - Python 가상환경 생성
   - 의존성 설치
   - `.env` 파일 메모장으로 열림 → **API 키 3개 입력 후 저장**
3. `credentials.json` 없으면 에러 메시지와 함께 폴더 열림 → **Google OAuth JSON 을 `credentials.json` 으로 저장**
4. 다시 `start_windows.bat` 더블클릭 → 브라우저에서 Google 인증 → 봇 실행

### macOS

1. `ai_assistant` 폴더 안의 **`start_mac.command`** 더블클릭
2. **처음에 "열 수 없음" 경고가 뜨면**: 파일 우클릭 → "열기" → "열기" 재클릭 (Gatekeeper 우회, 1회만)
3. 이후는 Windows 와 동일

> **종료:** 터미널 창을 닫으면 봇도 종료됩니다.
> **재시작:** 더블클릭 하면 됩니다. 이미 셋업된 상태라면 바로 봇이 실행됩니다.

---

## 최초 1회 준비물

더블클릭 실행 전에 아래 3가지만 준비하세요.

### 1) Telegram 봇 토큰 & 본인 User ID

- 텔레그램에서 `@BotFather` 검색 → `/newbot` → 봇 이름 지정 → **토큰** 복사
- `@userinfobot` 검색 → `/start` → 본인 **user id** 확인 (숫자)

### 2) Anthropic API 키

[console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys → Create Key

> 기본 모델은 **Claude Haiku 4.5** (저렴·빠름). 성능을 올리려면 `.env` 에서 `CLAUDE_MODEL=claude-sonnet-4-6` 또는 `claude-opus-4-7` 로 변경.

### 3) Google Calendar API 인증 (`credentials.json`)

1. [console.cloud.google.com](https://console.cloud.google.com/) → 새 프로젝트
2. **APIs & Services → Library** → "Google Calendar API" 검색 → **Enable**
3. **APIs & Services → OAuth consent screen** → External → 본인 Google 계정을 **Test users** 에 추가
4. **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
5. 생성된 클라이언트 우측 다운로드 아이콘 → JSON 다운로드 → 이름을 **`credentials.json`** 으로 바꿔 `ai_assistant` 폴더에 저장

---

## 🖥️ 맥북에서 24시간 상시 운영

맥북을 집/사무실에 켜놓고 돌리려면 `install_mac_service.command` 더블클릭.
launchd 에 등록되어 로그인시 자동 시작 + 크래시시 자동 재시작.
👉 가이드: [docs/MACOS_SERVICE.md](docs/MACOS_SERVICE.md)

> ⚠️ 맥북은 **뚜껑 닫으면 잠** 들어서 봇이 멈춥니다. 뚜껑 열어두거나 클램쉘(외장모니터+전원) 모드 필수.

---

## 🚂 클라우드 상시 운영 (Railway)

맥 꺼놓고 어디서든 돌아가게 하려면 Railway. **월 $10~15** 수준.
👉 가이드: [docs/RAILWAY.md](docs/RAILWAY.md)

---

## 구조

```
ai_assistant/
├── start_windows.bat                  ← Windows 더블클릭 (일회성)
├── start_mac.command                  ← macOS 더블클릭 (일회성)
├── install_mac_service.command        ← macOS 상시 실행 등록
├── uninstall_mac_service.command      ← macOS 상시 실행 해제
├── service_logs.command               ← macOS 실시간 로그
├── com.allfnb.assistant.plist.template  launchd 서비스 템플릿
├── Dockerfile                         ← Railway/Docker 배포용
├── railway.json                       ← Railway 설정
├── main.py                  Telegram 봇 진입점
├── agent.py                 Claude API + tool use 루프
├── gcal.py                  Google Calendar 래퍼
├── gdrive.py                Google Drive 래퍼
├── weekly_report.py         주간 리포트 생성기
├── google_auth.py           공용 Google OAuth
├── storage.py               SQLite 대화 기록
├── config.py                환경변수 로더
├── authenticate_gcal.py     Google OAuth 최초 1회 설정
├── requirements.txt
├── .env.example
├── README.md
└── docs/
    ├── MACOS_SERVICE.md     ← 맥북 상시 실행 가이드
    └── RAILWAY.md           ← Railway 배포 가이드
```

---

## 텔레그램 명령어

- `/start` — 시작 안내
- `/clear` — 대화 기록 초기화
- `/report` — 이번주 주간 리포트 (일정 + 자금) 즉시 생성 (자동: 금 17시)
- `/trends` — F&B 트렌드 브리프 즉시 생성 (자동: 월 9시)
  - 국가 지정: `/trends 싱가포르 베트남 일본`
- `/help` — 도움말

그 외 모든 메시지는 자연어 업무 지시로 처리됩니다.

## 선택 기능 활성화

### 💰 Airwallex 자금 요약

`.env` 또는 환경변수에 **`AIRWALLEX_CLIENT_ID`** + **`AIRWALLEX_API_KEY`** 추가. 없으면 주간 리포트의 자금 섹션이 자동으로 생략됩니다.

발급: Airwallex 웹 → Developer → API Keys

포함 내용:
- 통화별 현재 잔액
- 이번주 수익/지출/순액 (통화별)
- 주요 입금·출금 Top 5

### 🌏 F&B 트렌드 조사 대상 국가

기본 `싱가포르,베트남,일본,미국,인도네시아`. 변경하려면:

```
TREND_COUNTRIES=싱가포르,베트남,일본,대만,말레이시아,태국
```

### 📂 Google Drive 특정 폴더 지정

기본은 My Drive 루트에 저장. 특정 폴더에 저장하려면:

1. Drive 웹에서 원하는 폴더 생성 → 열기
2. URL 의 마지막 조각이 폴더 ID: `drive.google.com/drive/folders/1abcDEF...`
3. `.env` 의 **`DRIVE_FOLDER_ID`** 에 이 값 입력

> 주의: `drive.file` 스코프라서 봇이 **직접 만든 파일만** 읽고 쓸 수 있습니다. 기존 파일은 건드리지 않으므로 안전합니다.

### 📋 주간 리포트 시간·요일 변경

기본 금요일 17:00. 바꾸려면 `.env`:

```
WEEKLY_REPORT_DAY=fri        # mon/tue/wed/thu/fri/sat/sun
WEEKLY_REPORT_HOUR=17
WEEKLY_REPORT_MINUTE=0
```

---

## 수동 실행 (개발자용)

```bash
cd ai_assistant
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # .env 편집
python authenticate_gcal.py          # Google OAuth (최초 1회)
python main.py                       # 봇 실행
```

---

## 보안 주의

- `.env`, `credentials.json`, `token.json`, `assistant.db` 는 `.gitignore` 로 제외됨 — **절대 커밋 금지**
- `.env` 의 `ALLOWED_TELEGRAM_USER_IDS` 는 반드시 설정 (비우면 아무나 봇 사용 가능)
- 봇 토큰 유출시 즉시 `@BotFather` 에서 재발급

## 비용 감각 (참고)

| 모델 | 지시 1건 비용 | 하루 50건 → 월 |
|---|---|---|
| **claude-haiku-4-5** (기본) | ~$0.005 | ~$7 |
| claude-sonnet-4-6 | ~$0.014 | ~$21 |
| claude-opus-4-7 | ~$0.023 | ~$35 |

스케줄링만 한다면 Haiku로 충분합니다. 정교한 리뷰 분석/리포트 생성은 Sonnet 이상 추천.

## 다음 단계 (로드맵)

1. 리뷰 수집 & 감성 분석 모듈 (Google Maps Place API)
2. 마케팅 직영 전용 모듈 (Meta Ads / Google Ads API 연동, ROAS 리포트)
3. 매장별 P&L 대시보드 (Airwallex 거래 + 매장 태그)

## 트러블슈팅

**더블클릭했는데 아무 반응 없음 (Windows)** → 파일 탐색기에서 `start_windows.bat` 우클릭 → 관리자 권한으로 실행 / 또는 PowerShell 에서 `.\start_windows.bat` 실행해서 에러 확인

**"열 수 없음" 경고 (Mac)** → 파일 우클릭 → "열기" → 대화상자에서 "열기"

**"Missing required env var: TELEGRAM_BOT_TOKEN"** → `.env` 파일이 비어있거나 토큰 미입력. 더블클릭 재실행하면 메모장 다시 열림

**"Token not found"** → Google OAuth 인증이 안 됨. `ai_assistant` 폴더의 `token.json` 삭제 후 런처 재실행

**"insufficient authentication scopes"** → `token.json` 삭제 후 런처 재실행하여 재인증

**의존성 재설치가 필요할 때** → `ai_assistant/.venv` 폴더 통째로 삭제 후 런처 재실행

**봇이 메시지에 답 안 함** → 실행창의 로그 확인. `.env` 의 `ALLOWED_TELEGRAM_USER_IDS` 에 본인 텔레그램 user id가 있는지 체크

**Telegram 401/403 에러** → 봇 토큰 오타 또는 봇 삭제됨. `@BotFather` 에서 재확인
