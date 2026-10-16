"""공통 유틸: 설정 로드, 경로, 시간, 게시물 스키마."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

# 키를 붙여넣을 때 딸려 들어간 줄바꿈·공백 제거 (헤더 오류 방지)
for _k in ("ANTHROPIC_API_KEY", "HF_KEY", "HF_API_KEY", "HF_API_SECRET", "REPLICATE_API_TOKEN", "OPENAI_API_KEY",
           "IG_USER_ID", "IG_ACCESS_TOKEN", "THREADS_USER_ID", "THREADS_ACCESS_TOKEN", "GH_PAT",
           "NAVER_EMAIL", "NAVER_PASSWORD"):
    if os.environ.get(_k):
        os.environ[_k] = os.environ[_k].strip()

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_topics() -> dict:
    return yaml.safe_load((ROOT / "topics.yaml").read_text(encoding="utf-8")) or {}


def tz(config: dict) -> ZoneInfo:
    return ZoneInfo(config["schedule"]["timezone"])


def now(config: dict) -> datetime:
    return datetime.now(tz(config))


# ── 게시물 스키마 (Claude 구조화 출력) ─────────────────────────


class ChatLine(BaseModel):
    who: Literal["client", "us"] = Field(description="client=고객(대표님), us=우리 마케터")
    text: str


class Cutout(BaseModel):
    prompt: str = Field(description="콜라주로 비스듬히 붙일 작은 사진의 영어 프롬프트 (사물·장면 클로즈업)")
    label: str = Field(description="사진에 붙는 네온 태그 문구 (한국어 8자 이내)")


class Slide(BaseModel):
    type: Literal["cover", "chat", "point", "list", "compare", "copy", "stat", "cta"] = Field(
        description="cover=표지, chat=대화 캡처, point=핵심/STEP 설명, list=체크리스트, "
        "compare=Before/After 비교, copy=복사해서 쓰는 문구·프롬프트, stat=숫자 강조, cta=마지막 장"
    )
    sticker: str = Field(description="제목 위 라벨 박스 (예: 'CHECK 1', '사장님 필독'). 없으면 빈 문자열")
    title: str = Field(
        description="카드 제목. 줄바꿈은 \\n. ==문구== 는 네온 포인트 색 (보통 둘째 줄 전체)"
    )
    image_prompt: str = Field(description="이 장의 전면 배경 사진 영어 프롬프트 (사람·장면·사물, 글자 없음)")
    cutouts: List[Cutout] = Field(description="배경 위에 붙일 콜라주 사진 0~3개 (표지 2~3개, 본문 0~1개)")
    body: str = Field(description="본문 설명. 없으면 빈 문자열")
    teaser: str = Field(description="다음 장을 넘기게 만드는 하단 한 줄 (cta 제외 필수, 20자 이내)")
    items: List[str] = Field(description="list 타입의 항목들. 다른 타입은 빈 배열")
    chat: List[ChatLine] = Field(description="chat 타입의 대화 3~5줄. 다른 타입은 빈 배열")
    bad: str = Field(description="compare 타입의 ❌ 쪽 문장. 다른 타입은 빈 문자열")
    good: str = Field(description="compare 타입의 ⭕ 쪽 문장. 다른 타입은 빈 문자열")
    stat: str = Field(description="stat 타입의 큰 숫자/수치 (예: '3초'). 다른 타입은 빈 문자열")


class Post(BaseModel):
    topic: str = Field(description="한 줄 주제")
    pillar: str = Field(description="카테고리 이름 (topics.yaml 의 categories.name 그대로)")
    problem: str = Field(description="이 게시물이 해결하는 사장님의 구체적인 고민 한 문장")
    slug: str = Field(description="영문 소문자 kebab-case 폴더명, 40자 이내")
    slides: List[Slide]
    instagram_caption: str = Field(description="인스타그램 캡션 본문 (해시태그 제외)")
    hashtags: List[str] = Field(description="# 없이 해시태그 단어만, 5~10개")
    threads: List[str] = Field(
        description="스레드 연재. [0]=첫 글, 나머지는 순서대로 이어지는 답글. 각 450자 이내"
    )
    sources: List[str] = Field(description="수치·사실의 출처 (URL 또는 기관명). 없으면 빈 배열")


def read_post(post_dir: Path) -> Post:
    return Post.model_validate_json((post_dir / "post.json").read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def set_output(name: str, value: str) -> None:
    """GitHub Actions step output 으로 값 전달 (로컬 실행 시엔 출력만)."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    print(f"{name}={value}")
