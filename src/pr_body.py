"""검수용 PR 본문(카드 미리보기 + 캡션 + 스레드 원고)을 만든다.

사용: python -m src.pr_body content/2026-10-17-xxx <브랜치명>  > body.md
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from .common import ROOT, load_config, read_json, read_post, threads_texts


def main() -> None:
    post_dir = ROOT / sys.argv[1]
    branch = sys.argv[2]
    post = read_post(post_dir)
    meta = read_json(post_dir / "meta.json", {})
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    rel = post_dir.relative_to(ROOT).as_posix()
    sha = os.environ.get("CARDS_SHA", branch)
    imgs = sorted((post_dir / "cards").glob("*.jpg"))
    at = datetime.fromisoformat(meta["publish_at"]).strftime("%m월 %d일 %H:%M") if meta else "-"

    out = [
        f"## 📌 {post.topic}",
        f"**발행 예약:** {at}  ·  **카테고리:** {post.pillar}",
        f"**해결하는 고민:** {post.problem}",
        "",
        f"> ✅ **승인** → 아래 **Merge pull request → Confirm merge** 를 눌러두면 **{at}** 에 인스타그램·스레드에 자동으로 올라갑니다. (시각이 지난 뒤 승인하면 바로 올라가요)",
        "> ✏️ **수정 요청** → 댓글로 `/수정 3번 카드를 더 구체적으로` 처럼 남기면 Claude가 고쳐서 다시 올립니다.",
        "> ❌ **반려** → 맨 아래 **Close pull request** 를 누르세요.",
        "",
        "### 🖼 카드뉴스",
        "",
    ]
    row = []
    for i, p in enumerate(imgs, 1):
        url = f"https://raw.githubusercontent.com/{repo}/{sha}/{rel}/cards/{p.name}"
        row.append(f'<img src="{url}" width="260">')
        if i % 3 == 0:
            out.append(" ".join(row))
            row = []
    if row:
        out.append(" ".join(row))

    tags = " ".join(f"#{t.lstrip('#')}" for t in post.hashtags)
    event = load_config()["brand"].get("event", {}).get("caption", "")
    out += ["", "### 📝 인스타그램 캡션", "", "```", post.instagram_caption, "", event, ".", tags, "```", "", "### 🧵 스레드 연재", ""]
    for i, t in enumerate(threads_texts(post, load_config())):
        label = "첫 글 (후킹)" if i == 0 else f"댓글 {i}"
        out += [f"**{label}** · {len(t)}자", "", "> " + t.replace("\n", "\n> "), ""]
    if post.sources:
        out += ["### 🔗 출처", ""] + [f"- {s}" for s in post.sources]
    print("\n".join(out))


if __name__ == "__main__":
    main()
