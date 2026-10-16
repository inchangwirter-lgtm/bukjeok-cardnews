# 마케팅 카드뉴스 & 스레드 자동발행

Claude가 마케팅 주제를 기획해 **인스타그램 카드뉴스(캐러셀)** 와 **같은 내용의 스레드 연재 글**을 만들고,
사람이 GitHub에서 검수·승인하면 예정 시각에 두 채널로 자동 발행합니다. 서버 없이 GitHub Actions만으로 돌아갑니다.

```
[매일 20:00]    1. 생성        Claude 웹 리서치 → 원고·사진 프롬프트 작성 → AI 사진 생성 → 카드 렌더링 → 검수용 PR
                  │
[검수]         2. 검수         PR에서 카드 미리보기 확인
                  │            · 고칠 점 → 댓글 "/수정 3번 카드 더 구체적으로" → Claude가 고쳐서 다시 올림
                  │            · 승인 → Merge   · 반려 → Close
                  │
[다음날 13:00] 3. 발행        인스타그램 캐러셀 + 스레드 (첫 글에 카드 첨부, 이어지는 답글 연재)
[매주 월]      4. 토큰 갱신   메타 토큰(60일 만료) 자동 연장
```

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `config.yaml` | 브랜드명·아이디·색상, 말투, 슬라이드 수, 발행 시각 등 **모든 설정** |
| `topics.yaml` | 4개 카테고리(네이버 플레이스·인스타그램·스레드·AI 활용)와 고민 예시, 꼭 다룰 주제 대기열 |
| `templates/cards.html` | 카드 디자인 (1080×1350, 4:5) |
| `src/generate.py` | Claude로 주제 선정·리서치·원고 작성 |
| `src/images.py` | 슬라이드별 배경 사진·콜라주 사진 AI 생성 (실사 스냅 스타일) |
| `src/render.py` | 원고 + 사진 → 카드 이미지(JPEG) |
| `src/revise.py` | `/수정` 댓글 반영 |
| `src/publish.py`, `src/meta_api.py` | 인스타그램·스레드 발행 |
| `content/<날짜-주제>/` | 게시물별 `post.json`(원고), `cards/`(이미지), `meta.json`(발행 시각), `published.json`(발행 기록) |
| `examples/sample/` | 샘플 게시물과 렌더링된 카드 |

---

## 처음 설정하기 (약 30~40분)

### 1) GitHub 저장소 만들기
1. GitHub에서 새 저장소를 만들고 이 폴더의 파일을 모두 올립니다.
2. **저장소는 Public 으로** 만드세요. 인스타그램/스레드 API는 공개 URL의 이미지만 가져갈 수 있어서,
   카드 이미지를 `raw.githubusercontent.com` 주소로 넘깁니다. (어차피 공개로 올라갈 카드라 문제는 없고, API 키는 Secrets에 따로 안전하게 보관됩니다.)
   - 비공개로 쓰고 싶다면 이미지를 따로 호스팅(S3, Cloudflare R2 등)하고, 저장소 **Settings → Secrets and variables → Actions → Variables** 에 `IMAGE_BASE_URL` 을 지정하세요.
3. **Settings → Actions → General → Workflow permissions** 에서
   - `Read and write permissions` 선택
   - `Allow GitHub Actions to create and approve pull requests` 체크

### 2) Claude API 키
1. https://console.anthropic.com 에서 API 키 발급
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - `ANTHROPIC_API_KEY` = 발급받은 키

### 2-1) AI 사진 생성 키 (힉스필드 API)
카드 배경·콜라주 사진을 주제에 맞게 힉스필드로 만듭니다.
> ⚠️ 힉스필드 **웹 구독 크레딧과 API 잔액은 별개**입니다. 자동화 서버는 API 잔액(달러, $5부터 충전)을 씁니다.

1. 힉스필드 API 콘솔 로그인 → 잔액 충전 → **API Keys → 새 키 만들기**
2. 키가 한 번만 보이니 **Copy API key** 버튼으로 바로 복사
3. Secret 추가: `HF_KEY` = 복사한 키 전체
4. 다른 모델(GPT 이미지 등)을 쓰고 싶으면 콘솔의 모델 페이지에 나온 주소를 `config.yaml` 의 `images.model` 에

다른 공급자: `provider: replicate`(Secret `REPLICATE_API_TOKEN`) / `openai`(Secret `OPENAI_API_KEY`) / `none`(사진 없이)

AI 티를 줄이는 장치: 모든 프롬프트에 '아이폰 스냅·자연광·필름 그레인·무보정 색감' 스타일을 붙이고(`images.style`),
카드에서도 채도를 살짝 낮추고 그레인을 한 겹 더 얹습니다. Claude에게는 실존 인물·로고·글자를 사진에 넣지 않도록 지시해 두었습니다.

### 3) 인스타그램 연결
준비물: **프로페셔널 계정(비즈니스 또는 크리에이터)** 으로 전환된 인스타그램 계정
1. https://developers.facebook.com → 내 앱 → 앱 만들기 → 사용 사례에서 **"Instagram API로 메시지 및 콘텐츠 관리"(Instagram 로그인 방식)** 선택
2. 권한: `instagram_business_basic`, `instagram_business_content_publish`
3. 앱 대시보드의 **Instagram 로그인으로 API 설정 → 액세스 토큰 생성** 에서 우리 인스타 계정을 추가하고 토큰을 생성 (장기 토큰, 60일)
4. 같은 화면에 표시되는 **Instagram 사용자 ID**(숫자)를 확인
5. Secrets 추가: `IG_USER_ID`, `IG_ACCESS_TOKEN`

> 내 계정에만 올리는 용도라면 앱 검수(App Review) 없이 개발 모드에서 앱 관리자/테스터 계정으로 사용할 수 있습니다.

### 4) 스레드 연결
1. 같은 앱(또는 새 앱)에 **Threads API 액세스** 사용 사례 추가
2. 권한: `threads_basic`, `threads_content_publish`
3. **앱 역할 → 역할** 에서 우리 스레드 계정을 *Threads 테스터* 로 추가하고, 스레드 앱 설정 → 웹사이트 권한에서 초대 수락
4. **사용자 토큰 생성기** 로 토큰을 생성한 뒤 장기 토큰으로 교환
5. 사용자 ID 확인: 브라우저에서 `https://graph.threads.net/v1.0/me?fields=id,username&access_token=토큰`
6. Secrets 추가: `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN`

### 5) 토큰 자동 갱신용 (권장)
메타 토큰은 60일이면 만료됩니다. 매주 자동 연장하려면 Secrets를 다시 쓸 수 있는 GitHub 토큰이 필요합니다.
1. GitHub → Settings → Developer settings → **Fine-grained tokens** → 이 저장소만 선택, 권한 `Secrets: Read and write`
2. Secrets 추가: `GH_PAT`

### 6) 브랜드 설정
`config.yaml` 에서 에이전시 이름, 인스타 아이디, 브랜드 색상, 말투, 발행 시각을 바꾸세요.
`topics.yaml` 에서 다룰 주제 분야를 조정할 수 있습니다.

### 7) 첫 실행
1. **Actions → "1. 카드뉴스 생성 → 검수 PR" → Run workflow** (주제를 직접 넣어도 되고 비워도 됩니다)
2. 2~4분 뒤 **Pull requests** 탭에 `[검수] ...` PR이 생깁니다
3. 바로 올려보고 싶다면 Merge 후 **Actions → "3. 승인된 게시물 자동 발행" → Run workflow** 에서
   `only` 칸에 `content/폴더명` 을 넣고, 먼저 `dry_run` 을 체크해 확인 → 체크 해제 후 실제 발행

---

## 매일 쓰는 법

| 하고 싶은 것 | 방법 |
|---|---|
| 승인 | PR **Merge** → 예정 시각(기본: 다음 날 오후 1시)에 자동 발행 |
| 수정 요청 | PR 댓글 `/수정 표지 문구를 더 자극적으로` · `/수정 스레드 첫 글을 질문형으로` |
| 직접 수정 | PR의 `post.json` 을 GitHub에서 바로 편집 → 카드가 자동으로 다시 렌더링 |
| 발행 시각 변경 | PR의 `meta.json` 에서 `publish_at` 수정 |
| 반려 | PR **Close** |
| 이벤트 문구 변경 | `config.yaml` 의 `brand.event` (마지막 장 + 캡션 끝에 고정으로 들어감) |
| 카테고리 추가·변경 | `topics.yaml` 의 `categories` (최근에 덜 다룬 순서로 자동 순환) |
| 특정 주제 요청 | `topics.yaml` 의 `queue` 에 추가 (또는 수동 실행 시 주제 입력) |
| 생성 요일·시간 변경 | `.github/workflows/1-generate.yml` 의 `cron` (UTC 기준, 한국시간 −9시간) |

### post.json 직접 고칠 때 알아두면 좋은 문법
| 쓰는 법 | 카드에서 |
|---|---|
| `==문구==` | 네온 포인트 색 (보통 제목 둘째 줄 전체) |
| `\n` | 줄바꿈 |
| `sticker` | 제목 위 라벨 박스. `CHECK 1` 처럼 끝이 숫자면 숫자 칸만 네온으로 |
| `image_prompt` | 그 장의 전면 배경 사진 (영어) — 고치면 그 사진만 새로 생성 |
| `cutouts` | 비스듬히 붙는 콜라주 사진 + 네온 태그 (`prompt`, `label`) |
| `teaser` | 하단 "넘겨보기" 옆, 다음 장이 궁금해지는 한 줄 |

슬라이드 종류: `cover`(표지) · `chat`(대표님↔마케터 대화) · `point`(원인/STEP) · `list`(체크리스트) · `compare`(Before/After) · `copy`(복사해서 쓰는 문구·프롬프트) · `stat`(큰 숫자) · `cta`(마지막 장 + 고정 이벤트)

검수를 놓쳐서 예정 시각이 지나도 괜찮습니다. Merge 하는 순간 다음 15분 주기에 바로 발행됩니다.

## 비용과 한도 (하루 1개 = 월 30개 기준, 예상치)

| 항목 | 1개당 | 월 30개 | 비고 |
|---|---|---|---|
| Claude 원고 (Opus 5.5 + 웹 리서치) | 약 $0.6~0.8 | 약 $20~25 (3만~3.5만 원) | `/수정` 요청이 많으면 조금 늘어남 |
| AI 사진 (힉스필드 API, 1개당 13장 안팎) | 약 $1.2 (장당 약 $0.09 가정) | 약 $37 (5만 원) | 실제 단가는 힉스필드 콘솔에서 확인 |
| GitHub Actions | 0 | 0 | Public 저장소 무료 |
| 인스타그램·스레드 API | 0 | 0 | |
| **합계** | | **약 $60 (월 8만~9만 원)** | 환율 1,400원 가정 |

더 줄이려면: `model.name: claude-sonnet-5-5` + `effort: medium` (원고비 약 1/3), 본문 장 콜라주 사진 끄기(사진 약 30%↓).
메타 API 한도는 인스타 24시간 100건, 스레드 250건이라 하루 1개는 넉넉합니다.

## 로컬에서 돌려보기 (선택)
```bash
pip install -r requirements.txt && python -m playwright install chromium
```
```bash
python -m src.render examples/sample
```
```bash
ANTHROPIC_API_KEY=sk-... python -m src.generate --topic "네이버 플레이스 상위노출 기본기"
```

## 문제 해결
- **PR이 안 만들어짐** → 1)-3번 Workflow permissions 설정 확인
- **인스타 발행 실패 `media type` / `image` 오류** → 저장소가 Public인지, 이미지 URL이 브라우저에서 열리는지 확인
- **토큰 오류 (code 190)** → 토큰 만료. 3)·4)번으로 새로 발급해 Secrets 교체 (`GH_PAT` 를 설정해 두면 예방됩니다)
- **한쪽만 발행됨** → `published.json` 에 성공한 쪽이 기록되고, 다음 주기에 실패한 쪽만 재시도합니다. Actions 로그에서 오류 메시지를 확인하세요.
