"""post.json → 1080x1350 카드 이미지(JPEG). 인스타그램 API가 JPEG만 받기 때문에 JPEG로 저장한다.

사용: python -m src.render content/2026-10-17-xxx
"""
from __future__ import annotations

import re
import sys

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape
from playwright.sync_api import sync_playwright

from .common import ROOT, load_config, read_post
from .images import image_file


def fmt(text: str) -> Markup:
    html = str(escape(text))
    html = re.sub(r"==(.+?)==", r"<mark>\1</mark>", html)
    html = re.sub(r"\[\[(.+?)\]\]", r"<mark>\1</mark>", html)
    return Markup(html.replace("\\n", "<br>").replace("\n", "<br>"))


def title_size(text: str, base: int) -> int:
    """가장 긴 줄이 한 줄에 들어가도록 글자 크기를 줄인다 (920px 폭 기준)."""
    lines = re.sub(r"==|\[\[|\]\]", "", text).replace("\\n", "\n").split("\n")
    longest = max(sum(0.55 if c in " .,'!?" else (0.6 if c.isascii() else 1) for c in ln) for ln in lines)
    return min(base, int(900 / max(longest, 1)))


def event_fmt(text: str) -> Markup:
    """이벤트 문구의 [지역, 가게명] 같은 대괄호 부분을 네온으로."""
    html = str(fmt(text))
    return Markup(re.sub(r"\[(.+?)\]", r"<b>[\1]</b>", html))


def slide_images(post, post_dir) -> dict:
    """슬라이드 번호 → 실제로 생성된 사진 경로 (없는 사진은 빼고 렌더링)."""
    imgs = {}
    for n, s in enumerate(post.slides, start=1):
        bg = image_file(s.image_prompt, "bg") if s.image_prompt else None
        cuts = []
        for c in s.cutouts[:3]:
            rel = image_file(c.prompt, "cut")
            if (post_dir / rel).exists():
                cuts.append({"src": rel, "label": c.label})
        imgs[n] = {"bg": bg if bg and (post_dir / bg).exists() else None, "cuts": cuts}
    return imgs


def source_labels(sources: list[str]) -> list[str]:
    """출처를 카드에 짧게: URL 은 도메인만, 최대 3개."""
    out = []
    for src in sources:
        m = re.match(r"https?://(?:www\.)?([^/]+)", src.strip())
        label = m.group(1) if m else src.strip()[:30]
        if label and label not in out:
            out.append(label)
    return out[:3]


def render_html(post, config, post_dir) -> str:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["fmt"] = fmt
    env.filters["event_fmt"] = event_fmt
    env.filters["title_size"] = title_size
    return env.get_template("cards.html").render(
        slides=post.slides, brand=config["brand"], c=config["brand"]["colors"],
        imgs=slide_images(post, post_dir), sources=source_labels(post.sources),
    )


def main() -> None:
    post_dir = ROOT / sys.argv[1]
    config = load_config()
    post = read_post(post_dir)
    cards_dir = post_dir / "cards"
    cards_dir.mkdir(exist_ok=True)
    for old in cards_dir.glob("*.jpg"):
        old.unlink()

    html_path = post_dir / "cards.html"
    html_path.write_text(render_html(post, config, post_dir), encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto(html_path.as_uri(), wait_until="networkidle")
        # 모든 글꼴이 완전히 받아질 때까지 기다린다 (덜 받아진 채 찍히면 글자가 겹침)
        page.evaluate("Promise.all([...document.fonts].map(f => f.load().catch(() => null)))")
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=60000)
        page.wait_for_timeout(800)
        for i in range(1, len(post.slides) + 1):
            page.locator(f"#slide-{i}").scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            page.locator(f"#slide-{i}").screenshot(
                path=str(cards_dir / f"{i:02d}.jpg"), type="jpeg", quality=92
            )
        browser.close()
    html_path.unlink()
    print(f"✅ 카드 {len(post.slides)}장 렌더링 → {cards_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
