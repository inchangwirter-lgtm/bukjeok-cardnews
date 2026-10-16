"""Claude로 카드뉴스 + 스레드 원고를 기획·작성해 content/<날짜-slug>/ 에 저장한다.

사용: python -m src.generate [--topic "직접 지정할 주제"]
"""
from __future__ import annotations

import argparse
import re
from datetime import timedelta

import anthropic
import yaml

from .common import (
    CONTENT_DIR,
    ROOT,
    Post,
    load_config,
    load_topics,
    now,
    read_json,
    set_output,
    write_json,
)


def system_prompt(config: dict) -> str:
    c = config["content"]
    b = config["brand"]
    return f"""당신은 광고대행사 '{b['name']}'의 시니어 마케터이자 콘텐츠 에디터입니다.
요즘 인스타그램에서 잘 퍼지는 카드뉴스와, 같은 내용을 스레드(Threads)용으로 풀어 쓴 연재 글을 만듭니다.

독자: {c['audience']}
말투: {c['voice']}

[가장 중요한 원칙 — 게시물 1개 = 고민 1개 해결]
- 정해진 카테고리 안에서 사장님이 실제로 겪는 '구체적인 고민 하나'만 다룬다. (problem 필드에 한 문장으로)
  나쁜 예: '네이버 플레이스 잘하는 법'  좋은 예: '플레이스 등록했는데 동네 이름으로 검색하면 안 나와요'
- 다 읽은 사장님이 "아 그래서 이거 이렇게 하면 되는구나" 하고 오늘 바로 따라 할 수 있어야 한다.
- 원인 설명은 1장이면 충분하다. 나머지는 해결 방법이다.

[해결되는 느낌을 주는 법]
- 본문은 STEP 1, STEP 2 … 실행 순서로 쓴다 (sticker 에 'STEP 1' 등). 3~4단계.
- 각 STEP 에는 반드시 ①어디서(앱/사이트의 메뉴 경로) ②무엇을 ③어떻게(기준·숫자·예시 문구)가 들어간다.
  예: '스마트플레이스 → 업체정보 → 대표키워드'에서 '성수 파스타'처럼 [동네+메뉴] 조합으로 5개.
- Before/After 실제 예시를 최소 1장 넣는다 (compare 타입: bad=흔히 하는 것, good=고친 것. 구체적인 실제 문구로).
- 따라 쓸 수 있는 문구·프롬프트·템플릿이 있으면 copy 타입 장에 그대로 넣는다 (body 에 복사해서 쓸 텍스트).
  AI 활용 주제라면 실제로 붙여넣어 쓸 수 있는 프롬프트를 반드시 넣는다.
- 뒤쪽에 '오늘 할 일 체크리스트'(list) 장을 넣어 저장할 이유를 만든다.
- 금지어: '꾸준히', '퀄리티 있게', '타겟에 맞게', '진정성 있게', '전략적으로' 같은 두루뭉술한 말.
  쓰고 싶어지면 그 말을 구체적인 행동·숫자로 바꾼다.
- 메뉴 경로·기능명·기준은 리서치에서 확인된 것만 쓴다. 확실하지 않으면 경로를 지어내지 말고 일반적으로 표현한다.
  네이버·메타 알고리즘처럼 공식 공개되지 않은 내용은 '공식 기준은 아니지만 현업에서 효과 본 방법'처럼 솔직하게 쓴다.

[표지(cover) 후킹]
- 카테고리가 바로 보이게 sticker 에 카테고리명 (예: '네이버 플레이스', 'AI 활용').
- 제목 2줄: 첫 줄은 사장님의 고민/상황(흰 글씨), 둘째 줄은 해결 약속을 ==둘째 줄 전체== 로 (네온). 한 줄 12자 안팎.
  예: '플레이스 검색해도 안 나오면\n==대표키워드부터 바꾸세요=='  '리뷰 답글 매일 30분?\n==AI로 3분이면 끝=='
- 숫자·시간을 넣어 '금방 해결된다'는 느낌을 준다 (5분, 3단계, 딱 4개).

[넘기게 만드는 장치]
- cta 를 뺀 모든 장의 teaser 에 다음 장이 궁금해지는 한 줄 (답은 미리 말하지 않는다).
- 2번째 장은 그 고민을 겪는 사장님과의 대화(chat) 또는 상황 묘사로 공감을 잡는다.
- 같은 타입을 3장 연속 쓰지 않는다.

[마지막 장(cta)]
- 제목만 쓴다: 저장·실행을 부르는 2줄 (예: '저장해두고\n==오늘 바로 바꿔보기=='). body 는 빈 문자열.
- 이벤트 문구는 시스템이 고정으로 넣으므로 쓰지 않는다.

[사진 — 매 장 전면 배경 + 콜라주]
- image_prompt: 그 장의 메시지를 보여주는 '진짜 찍은 사진' 같은 장면을 영어로. 한국 동네 가게·사무실·카페 등 일상 공간,
  한국인 인물, 구체적인 행동·표정. 휴대폰·노트북 화면은 'blurred screen' 처럼 글자 없이.
- cutouts: 비스듬히 붙는 작은 사진(사물·화면 클로즈업) + 짧은 한국어 label. 표지 2~3개, 본문 0~1개.
- 실존 인물·연예인·브랜드 로고·읽을 수 있는 글자는 넣지 않는다. 주요 피사체는 화면 위쪽~가운데.

[분량]
- 슬라이드 {c['slides_min']}~{c['slides_max']}장. 첫 장 cover, 마지막 장 cta.
- 제목 2줄 각 12자 안팎, 본문 80자 이내, list 항목 3~5개 각 24자 이내, chat 한 줄 30자 이내, copy 본문 150자 이내.

[인스타그램 캡션]
- 첫 줄: 고민을 짚는 후킹 한 문장. 이어서 STEP 요약(✔)과 '오늘 할 일'.
- 저장 유도 한 줄로 끝낸다. 이벤트 문구는 시스템이 캡션 끝에 자동으로 붙이므로 쓰지 않는다.
- 해시태그는 hashtags 필드에만 (카테고리 관련 + 지역 사장님 관련).

[스레드 — 사진 없이 글만, 반말]
- 말투: 반말. 현업 마케터 선배가 후배·지인 사장님한테 툭 알려주는 느낌. 차분하고 확신 있게.
  'ㅋㅋ', 과한 이모지, 유행어, 밈은 쓰지 않는다 (장난스럽지 않게). 이모지는 글 하나에 많아야 1개.
- threads[0] = 첫 글(후킹): 딱 1줄, 길어도 2줄(줄바꿈 \\n 한 번). 80자 이내.
  ①공감("이거 해봤는데 손님 안 늘었지?") ②손해 짚기 ③상식 뒤집기 중 하나로 시작하고,
  끝은 저장·리포스트를 부르는 말로 맺는다. 예: '저장해두고 따라 해봐', '주변 사장님한테 리포스트해줘'.
  답을 첫 글에 다 말하지 말고, 댓글에서 순서대로 풀린다는 느낌만 준다 (예: '방법은 댓글에 순서대로 적어둘게').
  좋은 예: '대표키워드 5칸에 '맛집'만 넣었으면 그냥 버린 거야.\\n고치는 순서 댓글에 적어둘게, 저장해둬.'
- threads[1..] = 댓글(답글): 카드의 STEP 순서 그대로 하나씩. 3~5개, 각 250자 이내.
  각 댓글은 '1.', '2.' 처럼 번호로 시작하고, 어디서·무엇을·어떻게를 반말로 짧게. 실제 예시 문구 1개씩.
- 마지막 댓글: 한 줄 요약 + 저장·리포스트 부탁 한 줄 +
  '인스타 {b['handle']} 게시물에 지역이랑 가게명 댓글로 남기면 3명 뽑아서 마케팅 진단 PDF 보내줄게.'
- 해시태그 쓰지 않는다. 인스타 캡션·카드 문구는 기존처럼 존댓말을 유지한다.

slug 는 주제를 나타내는 영문 소문자 kebab-case 로 짓는다."""


def recent_topics(limit: int = 60) -> list[str]:
    topics = []
    for d in sorted(CONTENT_DIR.glob("*/"), reverse=True)[:limit]:
        post = read_json(d / "post.json")
        if post:
            topics.append(post["topic"])
    return topics


def pop_queued_topic() -> str | None:
    path = ROOT / "topics.yaml"
    data = load_topics()
    queue = data.get("queue") or []
    if not queue:
        return None
    topic = queue.pop(0)
    data["queue"] = queue
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return topic


def research(client: anthropic.Anthropic, config: dict, brief: str) -> str:
    """웹검색으로 주제 선정과 최신 사실 확인을 먼저 한다. 결과는 메모 텍스트."""
    messages = [
        {
            "role": "user",
            "content": brief
            + "\n\n위 조건으로 이번 카드뉴스 주제를 하나 정하고, 웹검색으로 최신 정보와 근거를 확인해"
            " 작성에 쓸 리서치 메모를 만들어 주세요. 메모에는 확정한 주제, 핵심 포인트, 쓸 수 있는 수치와 출처 URL을 포함합니다.",
        }
    ]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}]
    for _ in range(5):  # pause_turn 이면 이어서 진행
        resp = client.messages.create(
            model=config["model"]["name"],
            max_tokens=16000,
            system=system_prompt(config),
            thinking={"type": "adaptive"},
            output_config={"effort": config["model"]["effort"]},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude가 리서치 요청을 거절했습니다.")
    return "\n".join(b.text for b in resp.content if b.type == "text")


def write_post(client: anthropic.Anthropic, config: dict, brief: str, notes: str | None) -> Post:
    content = brief
    if notes:
        content += f"\n\n[리서치 메모]\n{notes}"
    content += "\n\n위 내용으로 카드뉴스와 스레드 원고를 완성해 주세요."
    resp = client.messages.parse(
        model=config["model"]["name"],
        max_tokens=16000,
        system=system_prompt(config),
        thinking={"type": "adaptive"},
        output_config={"effort": config["model"]["effort"]},
        messages=[{"role": "user", "content": content}],
        output_format=Post,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"원고 생성 실패 (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def next_category() -> dict:
    """최근 게시물에 가장 오래 안 나온 카테고리를 고른다."""
    cats = load_topics().get("categories", [])
    recent = [read_json(d / "post.json", {}).get("pillar") for d in sorted(CONTENT_DIR.glob("*/"), reverse=True)]
    def last_used(cat):
        return recent.index(cat["name"]) if cat["name"] in recent else 10**6
    return max(cats, key=last_used)


def build_brief(config: dict, forced_topic: str | None) -> str:
    recent = "\n".join(f"- {t}" for t in recent_topics()) or "(없음)"
    today = now(config).strftime("%Y-%m-%d")
    names = ", ".join(c["name"] for c in load_topics().get("categories", []))
    if forced_topic:
        topic_line = (f"이번 주제는 지정되어 있습니다: 「{forced_topic}」\n"
                      f"pillar 에는 가장 가까운 카테고리({names}) 이름을 그대로 쓰세요.")
    else:
        cat = next_category()
        examples = "\n".join(f"- {e}" for e in cat.get("examples", []))
        topic_line = (f"이번 카테고리: 「{cat['name']}」 (pillar 필드에 이 이름을 그대로 쓰세요)\n"
                      "이 카테고리에서 사장님이 실제로 겪는 구체적인 고민 하나를 골라 그것만 해결하세요.\n"
                      f"[고민 예시 — 참고용, 비슷한 결의 새 고민도 좋음]\n{examples}")
    return f"""오늘 날짜: {today}

{topic_line}

[최근에 이미 다룬 주제 — 겹치지 않게]
{recent}"""


def schedule_publish_at(config: dict) -> str:
    s = config["schedule"]
    hh, mm = map(int, s["publish_time"].split(":"))
    at = (now(config) + timedelta(days=s["publish_delay_days"])).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )
    return at.isoformat()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="", help="주제를 직접 지정")
    args = ap.parse_args()

    config = load_config()
    client = anthropic.Anthropic()

    forced = args.topic.strip() or pop_queued_topic()
    brief = build_brief(config, forced)
    notes = research(client, config, brief) if config["content"].get("use_web_search") else None
    post = write_post(client, config, brief, notes)

    slug = re.sub(r"[^a-z0-9-]+", "-", post.slug.lower()).strip("-")[:40] or "post"
    post_dir = CONTENT_DIR / f"{now(config):%Y-%m-%d}-{slug}"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "post.json").write_text(post.model_dump_json(indent=2), encoding="utf-8")
    write_json(post_dir / "meta.json", {"publish_at": schedule_publish_at(config)})
    if notes:
        (post_dir / "research.md").write_text(notes, encoding="utf-8")

    print(f"✅ 생성 완료: {post.topic}")
    set_output("post_dir", str(post_dir.relative_to(ROOT)))
    set_output("topic", post.topic.replace("\n", " "))


if __name__ == "__main__":
    main()
