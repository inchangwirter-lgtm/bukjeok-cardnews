"""슬라이드별 배경 사진·콜라주 사진을 AI로 생성한다.

- 프롬프트 내용으로 파일명을 정하므로(해시), /수정 후에는 바뀐 사진만 새로 만든다.
- 'AI 티'를 줄이기 위해 모든 프롬프트 뒤에 실사 스냅 느낌의 스타일 문구를 붙인다.

사용: python -m src.images content/2026-10-17-xxx
필요 환경변수: REPLICATE_API_TOKEN (provider=replicate) 또는 OPENAI_API_KEY (provider=openai)
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from pathlib import Path

import requests

from .common import ROOT, load_config, read_post

KINDS = {"bg": "4:5", "cut": "1:1"}


def image_file(prompt: str, kind: str) -> str:
    """post 폴더 기준 상대 경로."""
    h = hashlib.sha1(f"{kind}:{prompt}".encode()).hexdigest()[:12]
    return f"images/{kind}-{h}.jpg"


def full_prompt(prompt: str, kind: str, config: dict) -> str:
    style = config["images"]["style"]
    if kind == "cut":
        style = config["images"]["cutout_style"] + ", " + style
    return f"{prompt}. {style}"


# ── 공급자별 호출 ─────────────────────────────────────────


def gen_replicate(prompt: str, aspect: str, model: str) -> bytes:
    headers = {"Authorization": f"Bearer {os.environ['REPLICATE_API_TOKEN']}", "Prefer": "wait"}
    r = requests.post(
        f"https://api.replicate.com/v1/models/{model}/predictions",
        headers=headers,
        json={"input": {"prompt": prompt, "aspect_ratio": aspect, "raw": True,
                        "output_format": "jpg", "safety_tolerance": 2}},
        timeout=120,
    )
    r.raise_for_status()
    pred = r.json()
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        time.sleep(3)
        pred = requests.get(pred["urls"]["get"], headers=headers, timeout=60).json()
    if pred["status"] != "succeeded":
        raise RuntimeError(f"Replicate 생성 실패: {pred.get('error')}")
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    return requests.get(url, timeout=120).content


def gen_openai(prompt: str, aspect: str, model: str) -> bytes:
    size = "1024x1536" if aspect == "4:5" else "1024x1024"
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "prompt": prompt, "size": size, "quality": "high", "n": 1},
        timeout=300,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


PROVIDERS = {"replicate": gen_replicate, "openai": gen_openai}


def main() -> None:
    post_dir = ROOT / sys.argv[1]
    config = load_config()
    cfg = config["images"]
    if cfg["provider"] == "none":
        print("이미지 생성 꺼짐 (provider=none) — 단색 배경으로 렌더링합니다.")
        return
    gen = PROVIDERS[cfg["provider"]]
    post = read_post(post_dir)
    (post_dir / "images").mkdir(exist_ok=True)

    jobs = []
    for s in post.slides:
        if s.image_prompt:
            jobs.append((s.image_prompt, "bg"))
        jobs += [(c.prompt, "cut") for c in s.cutouts]

    keep = set()
    for prompt, kind in jobs:
        rel = image_file(prompt, kind)
        keep.add(rel)
        path = post_dir / rel
        if path.exists():
            continue
        for attempt in range(3):
            try:
                path.write_bytes(gen(full_prompt(prompt, kind, config), KINDS[kind], cfg["model"]))
                print(f"  🖼 {rel}  ← {prompt[:60]}")
                break
            except Exception as e:
                print(f"  ⚠️ 재시도 {attempt + 1}/3: {e}")
                time.sleep(5)
        else:
            print(f"  ❌ 생성 실패, 이 사진 없이 진행: {prompt[:60]}")

    # 수정으로 더 이상 안 쓰는 사진 정리
    for old in (post_dir / "images").glob("*.jpg"):
        if f"images/{old.name}" not in keep:
            old.unlink()
    print(f"✅ 사진 {len(keep)}장 준비 완료")


if __name__ == "__main__":
    main()
