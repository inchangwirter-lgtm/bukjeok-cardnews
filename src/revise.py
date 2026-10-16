"""검수 의견을 반영해 Claude가 원고를 고친다. (PR 댓글 '/수정 ...' 에서 호출)

사용: python -m src.revise content/2026-10-17-xxx "3번 카드를 더 구체적으로"
"""
from __future__ import annotations

import sys
from pathlib import Path

import anthropic

from .common import ROOT, Post, load_config, read_post
from .generate import system_prompt


def main() -> None:
    post_dir = ROOT / sys.argv[1]
    instruction = sys.argv[2]
    config = load_config()
    current = read_post(post_dir)

    resp = anthropic.Anthropic().messages.parse(
        model=config["model"]["name"],
        max_tokens=16000,
        system=system_prompt(config),
        thinking={"type": "adaptive"},
        output_config={"effort": config["model"]["effort"]},
        messages=[
            {
                "role": "user",
                "content": f"아래는 현재 원고(JSON)입니다.\n\n{current.model_dump_json(indent=2)}\n\n"
                f"검수자 의견: {instruction}\n\n"
                "의견을 반영해 원고 전체를 다시 출력해 주세요. 의견과 관계없는 부분은 그대로 둡니다.",
            }
        ],
        output_format=Post,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"수정 실패 (stop_reason={resp.stop_reason})")
    revised = resp.parsed_output
    revised.slug = current.slug  # 폴더명과 맞춰 둔다
    Path(post_dir / "post.json").write_text(revised.model_dump_json(indent=2), encoding="utf-8")
    print("✅ 수정 완료")


if __name__ == "__main__":
    main()
