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


TIPS_PRINCIPLE = """[가장 중요한 원칙 — 게시물 1개 = 고민 1개 해결]
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

"""

CASES_PRINCIPLE = """[이번 게시물 = 자영업자 마케팅 '사례' 1개 깊게 보기]
- 리서치 메모에 있는 '실제로 있었던 사례' 하나만 다룬다. 사례를 지어내거나 여러 사례를 섞지 않는다.
- problem 필드: 이 사례가 사장님들의 어떤 고민에 답이 되는지 한 문장. topic 에는 '누가 무엇을 해서 어떻게 됐나'.
- 흐름: cover(사례의 결과·반전으로 후킹) → chat 또는 point(그 가게가 처음 겪던 상황) → point 2~3장('무엇을 했나' 단계별)
  → stat 또는 point(결과. 출처에 나온 숫자만) → compare(보통 가게 vs 이 가게) → list('우리 가게라면 이렇게' 적용 3~4개) → cta.
- sticker: 표지에는 '국내 사례' 또는 '해외 사례'. 본문은 '배경', '무엇을 했나 1', '결과', '우리 가게 적용' 같은 라벨.
- 사실 규칙(가장 중요):
  · 가게·브랜드 이름, 지역, 시기, 수치는 리서치 메모의 출처에 있는 것만 쓴다. 없으면 '알려진 바로는' 없이 그냥 빼고 쓴다.
  · 추측은 '~로 보입니다'처럼 추측임을 드러낸다. 결과 수치를 부풀리거나 반올림해 과장하지 않는다.
  · sources 에는 실제 참고한 기사·공식 게시물을 '매체명 | URL' 형식으로 넣는다 (예: '한국경제 | https://...').
    직접 취재 기사 1건만 있는 경우 그 1건만 넣는다.
  · 카드·캡션·스레드에 '교차 확인 전', '미확인' 같은 작업 메모를 쓰지 않는다. 확인 안 된 내용은 아예 빼고 쓴다.
  · 기사 문장을 그대로 베끼지 않고 우리 말로 요약한다. 기사 사진·로고는 쓰지 않는다 (사진은 아래 규칙대로 새로 만든 연출 사진).
- 해외 사례는 우리나라 동네 가게가 바로 따라 할 수 있는 형태로 바꿔 '우리 가게 적용' 장에 쓴다.
- 사진: 표지(cover) 한 장만 쓴다. 나머지 장의 image_prompt 는 빈 문자열, cutouts 는 모든 장에서 빈 배열.
  표지 사진은 실제 사장님으로 오해받지 않도록 얼굴이 주인공인 장면은 피하고,
  손·뒷모습·제품·매장 공간·거리 위주로 묘사한다 (사람이 나오면 from behind, hands only, out of focus).
- 디자인이 글자 중심이므로 문장은 더 짧고 단정하게. 본문은 2~3줄(60자 안팎), 군더더기 수식어 없이.

[표지(cover) 후킹 — 사례]
- 제목 2줄: 첫 줄은 누가/어디서(흰 글씨), 둘째 줄은 결과·반전을 ==둘째 줄 전체== 로. 한 줄 12자 안팎.
  예: '동네 빵집 하나가\\n==줄 서는 집 된 이유==' / '광고비 0원 카페가\\n==예약 마감된 방법=='
- 숫자는 출처에 있을 때만 제목에 쓴다.

[캡션·스레드 — 사례 추가 규칙]
- 인스타 캡션: 첫 줄 후킹 → 사례 3줄 요약 → '우리 가게라면' 2~3줄 → 마지막 줄 '출처: ○○일보 보도 기준'(매체가 여럿이면 쉼표로).
- 스레드 첫 글: 사례의 반전·결과로 찌르고, '어떻게 했는지 댓글에 순서대로 정리했습니다' 류로 맺는다.
- 스레드 댓글: 1. 배경 → 2~3. 무엇을 했나 → 결과 → 우리 가게 적용 → 마지막 댓글(요약·저장/리포스트·이벤트) 끝에 '출처: 매체명'.
  스레드에는 URL·링크를 절대 넣지 않는다. 출처는 매체명만 (예: '출처: 헤럴드경제').

"""


def principle(series: str) -> str:
    return CASES_PRINCIPLE if series == "cases" else TIPS_PRINCIPLE


def system_prompt(config: dict, series: str = "tips") -> str:
    c = config["content"]
    b = config["brand"]
    return f"""당신은 광고대행사 '{b['name']}'의 시니어 마케터이자 콘텐츠 에디터입니다.
요즘 인스타그램에서 잘 퍼지는 카드뉴스와, 같은 내용을 스레드(Threads)용으로 풀어 쓴 연재 글을 만듭니다.

독자: {c['audience']}
말투: {c['voice']}

{principle(series)}
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

[스레드 — 사진 없이 글만, 존댓말, 문단 나누기]
- 말투: 존댓말. 자영업자 마케팅 대표가 같은 사장님께 진지하게 알려주는 톤. 단정하고 확신 있게.
  'ㅋㅋ', 유행어, 밈, 과한 이모지는 쓰지 않는다. 이모지는 글 하나에 많아야 1개.
- 가독성: 스레드는 글이 빠르게 지나가니 한 줄은 짧게(25자 안팎), 2~3줄마다 빈 줄로 문단을 나눈다.
  줄바꿈은 \\n, 문단 사이 빈 줄은 \\n\\n. 긴 문장 한 덩어리 금지.
- threads[0] = 첫 글(후킹). 맨 위의 '{b.get('threads_intro', '')}' 소개 문구는 시스템이 자동으로 붙이니 쓰지 않는다.
  4~6줄, 120자 안팎. 아래 흐름을 문단으로 나눠 쓴다.
  ① 찌르는 첫 문장: 사장님이 지금 하고 있을 법한 행동을 콕 집고, 그게 손해라고 단정한다. 구체적인 숫자·장면을 넣는다.
  ② 이유·공감 한두 줄: 왜 손해인지, 혹은 사장님 입장에서의 공감 (지어낸 경험담·수치는 쓰지 않는다). 듣는 순간 '어 나도인데' 싶게.
  ③ 약속: 이것만 바꾸면 무엇이 달라지는지 + 걸리는 시간.
  ④ 마무리 한 줄: '방법은 댓글에 순서대로 정리했습니다. 저장해두세요.' 류로 댓글·저장 유도.
  금지: '오늘은 ~를 알려드릴게요', '꿀팁', 뜬구름 같은 말, 느낌표 여러 개.
  좋은 예:
  '네이버 플레이스 대표키워드에\\n'맛집' 넣어두셨다면 5칸 중 4칸을 버리고 계신 겁니다.\\n\\n손님은 '맛집'으로 찾지 않고\\n'동네 + 메뉴'로 검색하기 때문이에요.\\n\\n10분만 투자해서 다시 채우면\\n손님이 실제로 치는 단어에 걸리기 시작합니다.\\n\\n순서대로 댓글에 정리했습니다. 저장해두세요.'
- threads[1..] = 댓글(답글): 카드의 STEP 순서 그대로 하나씩. 3~5개, 각 250자 이내, 존댓말.
  첫 줄은 '1. 손님이 실제로 치는 말부터 모으세요'처럼 번호 + 할 일 한 줄. 그다음 빈 줄,
  이어서 어디서·어떻게를 2~3줄, 마지막에 '예)' 로 시작하는 실제 예시 한 줄. 문단을 꼭 나눈다.
- 마지막 댓글: 한 줄 요약\\n\\n저장·리포스트 부탁 한 줄\\n\\n
  '인스타 {b['handle']} 게시물에 지역과 가게명을 댓글로 남겨주시면 3분을 선정해 마케팅 진단 PDF를 보내드립니다.'
- 해시태그 쓰지 않는다.

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


CASES_RESEARCH = """
위 조건에 맞는 '실제 자영업자·소상공인·작은 브랜드의 마케팅 사례' 하나를 웹검색으로 찾아 주세요.
- 최근 30일 안의 기사·공식 게시물을 우선하고, 없으면 최근 6개월까지 넓힙니다.
- 대기업 캠페인보다 동네 가게·작은 브랜드처럼 사장님이 따라 할 수 있는 규모를 고릅니다.
- 믿을 만한 출처(언론 기사, 공식 계정·보도자료, 업계 매체) 2곳 이상에서 사실을 교차 확인합니다.
  같은 원본(예: 유튜브 영상 하나)을 옮겨 적은 기사 여러 개는 1곳으로 칩니다.
  인정되는 조합: ①서로 다른 언론사 기사 2곳, ②언론 기사 1곳 + 그 가게·브랜드의 공식 계정/홈페이지 게시물,
  ③언론사가 사장님을 '직접 취재·인터뷰'한 기사 1곳 (다른 기사·유튜브·SNS 글을 옮겨 적은 기사는 해당 안 됨).
  ③일 때는 메모에 '직접 취재 기사'라고 근거(기자 이름, 인터뷰 인용 등)와 함께 적습니다.
- 후보를 찾으면 web_fetch 로 기사 본문을 직접 읽고 확인합니다. 검색 결과 요약만 믿지 않습니다.
- 위 ①②③ 중 하나도 만족하지 못하면 그 사례는 버리고 다른 사례를 찾습니다.
메모에 꼭 넣을 것: 가게/브랜드명, 지역·나라, 시기, 무엇을 했는지(단계별), 결과(출처에 있는 수치만),
각 사실의 출처 URL과 매체명·게재일, 확인되지 않은 부분은 '미확인'으로 표시.
메모의 맨 마지막 줄에는 반드시 아래 둘 중 하나만 그대로 씁니다.
VERDICT: OK      (위 ①②③ 중 하나를 만족하는 사례를 찾음)
VERDICT: NONE    (찾지 못함)
"""

CASES_RETRY = """
첫 조사에서는 조건을 만족하는 사례를 찾지 못했습니다. 이번에는 다른 각도로 찾아 주세요:
업종을 바꿔서(카페·베이커리·미용실·꽃집·공방·학원·헬스장·숙박 등), 또는 지역 언론·업계 매체·지자체 소상공인 지원 사례·
공식 보도자료처럼 다른 종류의 출처에서. 앞에서 탈락한 사례는 다시 고르지 않습니다.
"""

TIPS_RESEARCH = """
위 조건으로 이번 카드뉴스 주제를 하나 정하고, 웹검색으로 최신 정보와 근거를 확인해 작성에 쓸 리서치 메모를 만들어 주세요.
메모에는 확정한 주제, 핵심 포인트, 쓸 수 있는 수치와 출처 URL을 포함합니다.
"""


def research(client: anthropic.Anthropic, config: dict, brief: str, series: str = "tips", extra: str = "") -> str:
    """웹검색으로 주제 선정과 최신 사실 확인을 먼저 한다. 결과는 메모 텍스트."""
    messages = [{"role": "user", "content": brief + "\n" + (CASES_RESEARCH if series == "cases" else TIPS_RESEARCH) + extra}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 20 if series == "cases" else 6}]
    if series == "cases":
        tools.append({"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 12})
    for _ in range(5):  # pause_turn 이면 이어서 진행
        resp = client.messages.create(
            model=config["model"]["name"],
            max_tokens=16000,
            system=system_prompt(config, series),
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
    stu = getattr(resp.usage, "server_tool_use", None)
    if stu:
        print(f"  리서치 도구 사용: 검색 {getattr(stu, 'web_search_requests', 0)}회, 본문 읽기 {getattr(stu, 'web_fetch_requests', 0)}회")
    return "\n".join(b.text for b in resp.content if b.type == "text")


def case_found(notes: str) -> bool:
    tail = notes.strip().splitlines()[-3:] if notes.strip() else []
    return any("VERDICT: OK" in line for line in tail)


def write_post(client: anthropic.Anthropic, config: dict, brief: str, notes: str | None,
               series: str = "tips") -> Post:
    content = brief
    if notes:
        content += f"\n\n[리서치 메모]\n{notes}"
    content += "\n\n위 내용으로 카드뉴스와 스레드 원고를 완성해 주세요."
    resp = client.messages.parse(
        model=config["model"]["name"],
        max_tokens=16000,
        system=system_prompt(config, series),
        thinking={"type": "adaptive"},
        output_config={"effort": config["model"]["effort"]},
        messages=[{"role": "user", "content": content}],
        output_format=Post,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"원고 생성 실패 (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def next_category(skip: str = "") -> dict:
    """최근 게시물에 가장 오래 안 나온 카테고리를 고른다."""
    cats = [c for c in load_topics().get("categories", []) if c["name"] != skip] or load_topics().get("categories", [])
    recent = [read_json(d / "post.json", {}).get("pillar") for d in sorted(CONTENT_DIR.glob("*/"), reverse=True)]
    def last_used(cat):
        return recent.index(cat["name"]) if cat["name"] in recent else 10**6
    return max(cats, key=last_used)


def next_case_region() -> str:
    """사례 시리즈는 국내/해외를 번갈아 다룬다."""
    for d in sorted(CONTENT_DIR.glob("*/"), reverse=True):
        p = read_json(d / "post.json", {}).get("pillar")
        if p in ("국내 사례", "해외 사례"):
            return "해외 사례" if p == "국내 사례" else "국내 사례"
    return "국내 사례"


def build_brief(config: dict, forced_topic: str | None, series: str = "tips", avoid: str = "",
                skip_category: str = "") -> str:
    recent = "\n".join(f"- {t}" for t in ([avoid] if avoid else []) + recent_topics()) or "(없음)"
    today = now(config).strftime("%Y-%m-%d")
    names = ", ".join(c["name"] for c in load_topics().get("categories", []))
    if series == "cases":
        region = next_case_region()
        where = "대한민국" if region == "국내 사례" else "한국 외 해외(미국·일본·유럽 등)"
        topic_line = (f"이번 시리즈: 자영업자 마케팅 사례 — 「{region}」 (pillar 필드에 이 이름을 그대로 쓰세요)\n"
                      f"{where}의 실제 사례 하나를 골라 깊게 분석하세요."
                      + (f"\n지정 키워드: 「{forced_topic}」" if forced_topic else ""))
    elif forced_topic:
        topic_line = (f"이번 주제는 지정되어 있습니다: 「{forced_topic}」\n"
                      f"pillar 에는 가장 가까운 카테고리({names}) 이름을 그대로 쓰세요.")
    else:
        cat = next_category(skip_category)
        examples = "\n".join(f"- {e}" for e in cat.get("examples", []))
        topic_line = (f"이번 카테고리: 「{cat['name']}」 (pillar 필드에 이 이름을 그대로 쓰세요)\n"
                      "이 카테고리에서 사장님이 실제로 겪는 구체적인 고민 하나를 골라 그것만 해결하세요.\n"
                      f"[고민 예시 — 참고용, 비슷한 결의 새 고민도 좋음]\n{examples}")
    return f"""오늘 날짜: {today}

{topic_line}

[최근에 이미 다룬 주제 — 겹치지 않게]
{recent}"""


def schedule_publish_at(config: dict, series: str = "tips") -> str:
    """다음 발행 시각: 지금부터 최소 검수 시간(min_review_hours) 뒤에 오는 가장 가까운 발행 시각.
    (GitHub 예약 실행이 늦어져 자정을 넘겨도 하루가 밀리지 않게, '날짜+1' 대신 이렇게 계산)"""
    s = config["schedule"]
    t = s["publish_time"]
    hh, mm = map(int, (t.get(series) or t.get("tips") if isinstance(t, dict) else t).split(":"))
    earliest = now(config) + timedelta(hours=s.get("min_review_hours", 4))
    at = earliest.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if at < earliest:
        at += timedelta(days=1)
    return at.isoformat()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="", help="주제를 직접 지정")
    ap.add_argument("--series", default="tips", choices=["tips", "cases"], help="tips=고민 해결 / cases=마케팅 사례")
    ap.add_argument("--avoid", default="", help="이번에 피할 주제 (다시 만들기용)")
    ap.add_argument("--skip-category", default="", help="이번에 피할 카테고리")
    ap.add_argument("--publish-at", default="", help="발행 시각 직접 지정 (예: 2026-10-21T13:00:00+09:00)")
    args = ap.parse_args()
    series = args.series

    config = load_config()
    client = anthropic.Anthropic()

    forced = args.topic.strip() or (None if series == "cases" else pop_queued_topic())
    brief = build_brief(config, forced, series, args.avoid, args.skip_category)
    use_web = series == "cases" or config["content"].get("use_web_search")  # 사례는 항상 리서치
    notes = research(client, config, brief, series) if use_web else None
    if series == "cases" and not case_found(notes):
        print("⚠️ 1차 조사: 출처가 확인된 사례 없음 → 다른 각도로 다시 조사")
        first = notes
        notes = research(client, config, brief, series,
                         extra=CASES_RETRY + "\n[1차 조사 메모]\n" + first[-3000:])
        if not case_found(notes):
            print("⛔ 2차 조사도 실패: 오늘 사례 게시물은 만들지 않습니다 (사실 확인 안 된 글은 올리지 않음).")
            set_output("post_dir", "")
            return
    post = write_post(client, config, brief, notes, series)

    slug = re.sub(r"[^a-z0-9-]+", "-", post.slug.lower()).strip("-")[:40] or "post"
    prefix = "case-" if series == "cases" else ""
    post_dir = CONTENT_DIR / f"{now(config):%Y-%m-%d}-{prefix}{slug}"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "post.json").write_text(post.model_dump_json(indent=2), encoding="utf-8")
    write_json(post_dir / "meta.json", {"publish_at": args.publish_at or schedule_publish_at(config, series), "series": series})
    if notes:
        (post_dir / "research.md").write_text(notes, encoding="utf-8")

    print(f"✅ 생성 완료: {post.topic}")
    set_output("post_dir", str(post_dir.relative_to(ROOT)))
    set_output("topic", post.topic.replace("\n", " "))


if __name__ == "__main__":
    main()
