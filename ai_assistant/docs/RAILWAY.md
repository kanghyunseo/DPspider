# Railway 배포 가이드 (상시 운영)

이 문서는 봇을 Railway 에 올려 **24시간 상시 운영** 하는 방법입니다. 총 소요시간 **약 20분**, 월 비용 대략 **$5 내외**.

---

## 사전 준비 (로컬 PC에서 1회)

Railway에 올리기 전에, 로컬에서 한 번 봇을 돌려서 `token.json` 을 만들어야 합니다. (Google OAuth 는 로컬에서 한번만 받고, 결과 토큰을 클라우드에 올리는 방식)

### 1. 더블클릭 런처로 로컬에서 최초 인증 완료

[README.md](../README.md) "🚀 빠른 시작" 섹션대로 로컬에서 한 번 구동 → `ai_assistant/` 폴더 안에 `token.json` 파일이 생성됨.

### 2. `token.json` 내용 확보

두 가지 방법 중 편한 거 선택:

**A) 재인증하면서 출력되는 값 복사**

```bash
cd ai_assistant
python authenticate_gcal.py
```

끝나고 터미널에 출력되는 `-----` 사이 JSON 한 줄을 전체 복사.

**B) 파일 직접 열기**

메모장으로 `ai_assistant/token.json` 열어서 내용 전체 복사. (한 줄짜리 JSON)

> 📋 복사한 JSON 을 메모장에 임시로 붙여놓으세요. 다음 단계에서 씁니다.

### 3. GitHub 에 코드 푸시 확인

Railway 는 GitHub 연동으로 배포합니다. 현재 브랜치(`claude/restaurant-ai-task-manager-wzs7Q`)가 이미 푸시되어 있는지 확인:

```bash
git push origin claude/restaurant-ai-task-manager-wzs7Q
```

---

## Railway 셋업

### 1. 계정 생성 & 결제 등록

1. https://railway.com → **Sign in with GitHub**
2. 좌측 메뉴 **Account Settings → Plans** → **Hobby Plan** 선택 ($5/월 크레딧 포함)
3. 결제카드 등록 (크레딧 넘지 않으면 과금 0)

> **무료 Trial Plan 도 있지만** 봇 같은 상시 프로세스는 슬립 걸려서 부적합. Hobby Plan 권장.

### 2. 새 프로젝트 만들기

1. 우측 상단 **New Project** → **Deploy from GitHub repo**
2. `kanghyunseo/DPspider` 선택 (처음이면 GitHub 권한 요청 허용)
3. 브랜치 `claude/restaurant-ai-task-manager-wzs7Q` 선택

### 3. 루트 디렉토리 설정

봇 코드는 `ai_assistant/` 서브폴더 안에 있으므로 Railway 에 알려줘야 합니다.

1. 생성된 서비스 클릭 → **Settings** 탭
2. **Source** → **Root Directory** 필드에 `ai_assistant` 입력 → **Update**
3. (선택) **Service Name** 을 `allfnb-bot` 등으로 변경

### 4. 환경변수(Variables) 등록

**Variables** 탭 → **+ New Variable** 로 아래 키들을 하나씩 등록:

| 키 | 값 | 설명 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather에서 받은 토큰 | `123456:ABC-DEF...` 형태 |
| `ANTHROPIC_API_KEY` | Anthropic Console에서 발급 | `sk-ant-api...` |
| `ALLOWED_TELEGRAM_USER_IDS` | 본인 Telegram user id | 숫자. 쉼표로 여러명 가능 |
| `GOOGLE_TOKEN_JSON` | 위 "사전 준비 2번"에서 복사한 JSON 전체 | `{"token": "...", ...}` 한 줄 |
| `CLAUDE_MODEL` | `claude-haiku-4-5` | 기본값. 변경 가능 |
| `DEFAULT_TIMEZONE` | `Asia/Seoul` | 기본값 |

> ⚠️ `GOOGLE_TOKEN_JSON` 은 **값 전체를 따옴표 없이** 붙여넣으세요. Railway 가 자동으로 처리합니다.

### 5. 영구 볼륨 마운트 (대화 기록 + 토큰 갱신 유지)

볼륨이 없으면 재배포시 SQLite DB 와 자동 갱신된 Google 토큰이 날아갑니다.

1. **Settings** 탭 → **Volumes** 섹션
2. **+ New Volume** 클릭
3. **Mount Path**: `/data`
4. **Size**: 1 GB (이걸로 충분. 확장 가능)
5. 저장

Dockerfile 이 이미 `DB_PATH=/data/assistant.db` 로 설정되어 있어서 자동으로 볼륨을 사용합니다.

### 6. 배포 확인

1. **Deployments** 탭에서 최근 빌드 로그 확인
2. 빌드 완료 후 **View Logs** 클릭
3. 다음 로그가 보이면 정상:
   ```
   Bot starting (model=claude-haiku-4-5, calendar=primary, tz=Asia/Seoul)
   ```

### 7. 동작 테스트

텔레그램에서 본인 봇에게:
```
안녕, 오늘 일정 보여줘
```

응답 오면 **끝**. 이제 PC 꺼도 봇은 계속 돌아갑니다. 🎉

---

## 운영 중 할 일

### 코드 업데이트

로컬에서 수정 → `git push` → Railway 가 자동으로 재빌드·재배포.

```bash
# 예: 시스템 프롬프트 수정 후
git add ai_assistant/agent.py
git commit -m "Tune system prompt"
git push
# ~2분 뒤 자동 재배포
```

### 환경변수 변경

Railway 대시보드 → **Variables** → 값 수정 → 자동 재시작.

### 로그 보기

**Deployments** 탭 → 최근 배포 클릭 → **View Logs**. 실시간 스트리밍됨.

### 비용 모니터링

좌측 상단 프로젝트 이름 → **Usage** 탭. 평균적으로:
- 24시간 상시 실행: ~$3-5/월 (512MB RAM × 730h)
- Anthropic API (Haiku, 하루 50건): ~$7/월
- **합계 월 $10~15 수준**

---

## 트러블슈팅

### "Missing required env var: TELEGRAM_BOT_TOKEN"

Variables 탭에서 키 오타 확인. 대소문자 구분.

### 로그에 "Token not found" 나옴

`GOOGLE_TOKEN_JSON` 이 비어있거나 JSON 포맷 깨짐. 로컬 token.json 을 다시 복사해서 붙여넣기.

### 배포는 됐는데 봇이 답 안함

1. `ALLOWED_TELEGRAM_USER_IDS` 에 본인 user id 가 포함되어 있는지
2. Variables 에 `TELEGRAM_BOT_TOKEN` 오타 없는지
3. 로그에 `Bot starting` 이 보이는지

### Google API 에서 "Token has been expired or revoked"

Google 토큰이 어떤 이유로 revoke 됨. 로컬에서 `python authenticate_gcal.py` 재실행 → 출력된 새 JSON 을 Railway Variables 의 `GOOGLE_TOKEN_JSON` 에 다시 붙여넣기.

### 갑자기 빌드 실패

Deployments 탭 로그 확인. 대부분 `requirements.txt` 의 버전 충돌. `pip install` 부분 에러 메시지 확인.

### 월 비용이 예상보다 나옴

1. Anthropic Console 에서 API 사용량 확인 (Usage tab)
2. Railway Usage 탭에서 Memory/CPU 사용 확인
3. 필요시 Anthropic 의 **Monthly Budget** 에 상한 설정 가능

---

## 보안 체크리스트

- [ ] `ALLOWED_TELEGRAM_USER_IDS` 반드시 설정 (비면 누구나 봇 사용 가능)
- [ ] `.env`, `credentials.json`, `token.json` 이 git 에 안 올라갔는지 재확인 (`git log --all -- '**/.env' '**/token.json' '**/credentials.json'` — 결과 없어야 정상)
- [ ] Anthropic API 에 월 사용 한도 설정
- [ ] Anthropic / Railway 계정에 2FA 활성화
- [ ] Telegram 봇 토큰 유출 의심되면 즉시 @BotFather 에서 재발급 → Railway Variables 업데이트

---

## 대체 옵션

Railway 가 마음에 안 들면:

- **Fly.io** — Dockerfile 그대로 재활용. `fly launch` 한 번. 무료 플랜 있음
- **Render** — Railway 와 거의 동일한 UX
- **자체 VPS** (DigitalOcean, Lightsail $5) — Dockerfile 이미 있으므로 `docker compose up -d` 로 즉시 배포 가능
