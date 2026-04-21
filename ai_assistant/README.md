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
봇   → ✅ "베트남 가맹 신규 계약 검토" 4/25(금) 10:00로 이동 완료
```

## 구조

```
ai_assistant/
├── main.py                  Telegram 봇 진입점
├── agent.py                 Claude API + tool use 루프
├── gcal.py                  Google Calendar 래퍼
├── storage.py               SQLite 대화 기록
├── config.py                환경변수 로더
├── authenticate_gcal.py     Google OAuth 최초 1회 설정
├── requirements.txt
├── .env.example
└── README.md
```

## 셋업

### 1) 파이썬 의존성 설치

```bash
cd ai_assistant
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Telegram 봇 생성

1. 텔레그램에서 `@BotFather` 검색 → `/newbot`
2. 봇 이름 지정 → 토큰 받음 (`123456:ABC-...`)
3. 본인 user id 확인: `@userinfobot` 에 `/start`

### 3) Google Calendar API 설정

1. [Google Cloud Console](https://console.cloud.google.com/) → 새 프로젝트
2. **APIs & Services → Library** → "Google Calendar API" 검색 → Enable
3. **APIs & Services → Credentials** → Create Credentials → **OAuth client ID**
   - Application type: **Desktop app**
   - 이름: 아무거나
4. 생성된 클라이언트 우측 다운로드 아이콘 → `credentials.json` 저장 → 프로젝트 루트에 배치
5. OAuth consent screen 설정에서 본인 Google 계정을 **Test user** 로 추가 (외부 공개 앱이 아닌 경우)

### 4) Anthropic API 키

[Anthropic Console](https://console.anthropic.com/) → Settings → API Keys → Create Key

### 5) 환경변수 설정

```bash
cp .env.example .env
# .env 열어서 TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_TELEGRAM_USER_IDS 채우기
```

### 6) Google OAuth 최초 인증 (1회만)

```bash
python -m ai_assistant.authenticate_gcal
```

브라우저 창이 열리면 본인 구글 계정으로 로그인·허용 → `token.json` 생성됨.

### 7) 봇 실행

```bash
python -m ai_assistant.main
```

로그에 `Bot starting ...` 이 뜨면 성공. 텔레그램에서 봇에게 메시지를 보내세요.

## 명령어

- `/start` — 시작 안내
- `/clear` — 대화 기록 초기화
- `/help` — 도움말

그 외 모든 메시지는 자연어 업무 지시로 처리됩니다.

## 보안 주의

- `.env`, `credentials.json`, `token.json` 은 `.gitignore` 로 제외됨 — **절대 커밋 금지**
- `ALLOWED_TELEGRAM_USER_IDS` 는 반드시 설정 (비우면 누구나 봇 사용 가능)
- 봇 토큰 유출시 즉시 @BotFather 에서 재발급

## 비용 감각 (참고)

Claude Opus 4.7 기준, 평균 지시 1건당:

- 입력 ~2K 토큰 + 출력 ~500 토큰 → 약 $0.023/메시지
- 하루 50건 사용시 월 ~$35

비용을 줄이려면 `.env` 에서 `CLAUDE_MODEL=claude-sonnet-4-6` (1/2 가격) 또는 `claude-haiku-4-5` (1/5 가격) 로 변경.

## 다음 단계 (로드맵)

1. 음성 메시지 → Whisper → 텍스트 (텔레그램 voice 핸들러 추가)
2. Google Drive 연동 (주간 리포트 저장)
3. 리뷰 수집 & 감성 분석 모듈 (Google Maps Place API)
4. 국가별 F&B 트렌드 주간 브리프 (Claude Web Search tool)
5. 마케팅/회계 직영 전용 모듈 (Meta Ads API, QuickBooks 등)

## 트러블슈팅

**"Token not found"** → `python -m ai_assistant.authenticate_gcal` 실행

**"insufficient authentication scopes"** → `token.json` 삭제 후 재인증

**봇이 메시지에 답 안 함** → 로그 확인. `ALLOWED_TELEGRAM_USER_IDS` 에 본인 id 있는지 체크

**Telegram 403 Forbidden** → 봇 토큰 오타 또는 봇이 삭제됨
