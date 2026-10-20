"""슬라이드별 배경 사진·콜라주 사진을 AI로 생성한다.

- 프롬프트 내용으로 파일명을 정하므로(해시), /수정 후에는 바뀐 사진만 새로 만든다.
- 'AI 티'를 줄이기 위해 모든 프롬프트 뒤에 실사 스냅 느낌의 스타일 문구를 붙인다.

사용: python -m src.images content/2026-10-17-xxx
필요 환경변수: HF_KEY (provider=higgsfield, 콘솔의 Copy API key 값) / REPLICATE_API_TOKEN / OPENAI_API_KEY
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
import uuid
from pathlib import Path

import requests

from .common import ROOT, load_config, read_json, read_post

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


def gen_higgsfield(prompt: str, aspect: str, model: str) -> bytes:
    """Higgsfield API (구독 크레딧과 별개인 API 잔액에서 차감).
    모델이 지원하지 않는 비율이면 가까운 세로 비율로 바꿔 다시 시도한다 (카드에선 잘라서 맞춤)."""
    key = os.environ.get("HF_KEY") or f"{os.environ['HF_API_KEY']}:{os.environ['HF_API_SECRET']}"
    auth = {"Authorization": f"Key {key.strip()}"}
    fallbacks = {"4:5": ["3:4", "4:5", "2:3"], "1:1": ["1:1"]}.get(aspect, [aspect])
    for ratio in fallbacks:
        r = requests.post(f"https://api.higgsfield.ai/{model}",
                          headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
                          json={"prompt": prompt, "aspect_ratio": ratio}, timeout=120)
        if r.status_code == 400 and ratio != fallbacks[-1]:
            print(f"    비율 {ratio} 거절 → 다음 비율로 ({r.text[:200]})")
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Higgsfield {r.status_code}: {r.text[:300]}")
        break
    req = r.json()
    status_url = req.get("status_url") or f"https://api.higgsfield.ai/requests/{req['request_id']}/status"
    deadline = time.time() + 600
    while req.get("status") not in ("completed", "failed", "nsfw", "canceled"):
        if time.time() > deadline:
            raise RuntimeError("Higgsfield 생성 시간 초과")
        time.sleep(4)
        req = requests.get(status_url, headers=auth, timeout=60).json()
    if req["status"] != "completed":
        raise RuntimeError(f"Higgsfield 생성 실패: {req['status']} {req.get('error') or ''}")
    return requests.get(req["images"][0]["url"], timeout=120).content


PROVIDERS = {"higgsfield": gen_higgsfield, "replicate": gen_replicate, "openai": gen_openai}


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
    # 마케팅 사례는 표지 사진 한 장만 쓴다 (나머지 장은 글자 중심 디자인)
    cases = read_json(post_dir / "meta.json", {}).get("series") == "cases"
    slides = post.slides[:1] if cases else post.slides
    for s in slides:
        if s.image_prompt:
            jobs.append((s.image_prompt, "bg"))
        if not cases:
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
