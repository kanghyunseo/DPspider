# 올에프인비 업무 비서 (MVP: 스케줄링)

글로벌사업팀장용 Telegram 비서. 자연어로 지시하면 Claude API가 분석해서 Google Calendar에 일정을 등록/조회/수정/삭제합니다.

## 사용 예시

```
팀장 → 내일 오후 3시에 싱가포르 매장 리뷰 미팅 1시간 잡아줘
봇   → ✅ 등록 완료: 4/22(화) 15:00–16:00 "싱가포르 매장 리뷰 미팅"

팀장 → 이번주 일정 다 보여줘
봇   → 이번주(4/21~4/27) 일정 5건:
       - 4/22(화) 15:00 싱가포르 매장 리뷰 미팅
       - 4/23(수) 10:00 베트남 가맹 신규 계약 검토
       ...

팀장 → 수요일 10시 회의를 금요일 같은 시간으로 옮겨줘
봇   → ✅ "베트남 가맹 신규 계약 검토" 4/25(금) 10:00 로 이동 완료
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

## 🚂 상시 운영 (Railway 배포)

PC 꺼놓아도 봇이 24/7 돌아가게 하려면 Railway 에 올리세요. **월 $10~15** 수준.
👉 상세 가이드: [docs/RAILWAY.md](docs/RAILWAY.md)

---

## 구조

```
ai_assistant/
├── start_windows.bat        ← Windows 더블클릭 실행
├── start_mac.command        ← macOS 더블클릭 실행
├── Dockerfile               ← Railway/Docker 배포용
├── railway.json             ← Railway 설정
├── main.py                  Telegram 봇 진입점
├── agent.py                 Claude API + tool use 루프
├── gcal.py                  Google Calendar 래퍼
├── storage.py               SQLite 대화 기록
├── config.py                환경변수 로더
├── authenticate_gcal.py     Google OAuth 최초 1회 설정
├── requirements.txt
├── .env.example
├── README.md
└── docs/
    └── RAILWAY.md           ← Railway 배포 가이드 (한글)
```

---

## 텔레그램 명령어

- `/start` — 시작 안내
- `/clear` — 대화 기록 초기화
- `/help` — 도움말

그 외 모든 메시지는 자연어 업무 지시로 처리됩니다.

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

1. 음성 메시지(Whisper) → 텍스트 (텔레그램 voice 핸들러)
2. Google Drive 연동 (주간 리포트 저장)
3. 리뷰 수집 & 감성 분석 모듈 (Google Maps Place API)
4. 국가별 F&B 트렌드 주간 브리프 (Web Search tool)
5. 마케팅/회계 직영 전용 모듈 (Meta Ads API, QuickBooks 등)

## 트러블슈팅

**더블클릭했는데 아무 반응 없음 (Windows)** → 파일 탐색기에서 `start_windows.bat` 우클릭 → 관리자 권한으로 실행 / 또는 PowerShell 에서 `.\start_windows.bat` 실행해서 에러 확인

**"열 수 없음" 경고 (Mac)** → 파일 우클릭 → "열기" → 대화상자에서 "열기"

**"Missing required env var: TELEGRAM_BOT_TOKEN"** → `.env` 파일이 비어있거나 토큰 미입력. 더블클릭 재실행하면 메모장 다시 열림

**"Token not found"** → Google OAuth 인증이 안 됨. `ai_assistant` 폴더의 `token.json` 삭제 후 런처 재실행

**"insufficient authentication scopes"** → `token.json` 삭제 후 런처 재실행하여 재인증

**의존성 재설치가 필요할 때** → `ai_assistant/.venv` 폴더 통째로 삭제 후 런처 재실행

**봇이 메시지에 답 안 함** → 실행창의 로그 확인. `.env` 의 `ALLOWED_TELEGRAM_USER_IDS` 에 본인 텔레그램 user id가 있는지 체크

**Telegram 401/403 에러** → 봇 토큰 오타 또는 봇 삭제됨. `@BotFather` 에서 재확인
