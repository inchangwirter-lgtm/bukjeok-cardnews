"""승인된(main 브랜치에 병합된) 게시물 중 발행 시각이 지난 것을 인스타그램·스레드에 올린다.

- 플랫폼별 결과를 content/<게시물>/published.json 에 기록해, 한쪽만 실패해도 다음 실행에서 나머지만 재시도한다.
- 이미지 URL: 기본은 공개 저장소의 raw.githubusercontent.com 주소. 다른 곳에 올린다면 IMAGE_BASE_URL 로 지정.

사용: python -m src.publish [--dry-run] [--only content/2026-10-17-xxx]
필요 환경변수: IG_ACCESS_TOKEN, THREADS_ACCESS_TOKEN, GITHUB_REPOSITORY
(IG_USER_ID / THREADS_USER_ID 는 없으면 토큰으로 자동 조회)
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from . import meta_api
from .common import CONTENT_DIR, ROOT, load_config, now, read_json, read_post, threads_texts, write_json


def image_urls(post_dir: Path) -> list[str]:
    base = os.environ.get("IMAGE_BASE_URL")
    if not base:
        repo = os.environ["GITHUB_REPOSITORY"]
        branch = os.environ.get("PUBLISH_BRANCH", "main")
        base = f"https://raw.githubusercontent.com/{repo}/{branch}"
    rel = post_dir.relative_to(ROOT).as_posix()
    return [f"{base.rstrip('/')}/{rel}/cards/{p.name}" for p in sorted((post_dir / "cards").glob("*.jpg"))]


def due_posts(config: dict) -> list[Path]:
    current = now(config)
    due = []
    for d in sorted(CONTENT_DIR.glob("*/")):
        meta = read_json(d / "meta.json")
        if not meta or not (d / "post.json").exists():
            continue
        done = read_json(d / "published.json", {})
        wanted = [p for p in ("instagram", "threads") if config["publish"].get(p)]
        if all(p in done for p in wanted):
            continue
        if datetime.fromisoformat(meta["publish_at"]) <= current:
            due.append(d)
    return due


def publish_one(post_dir: Path, config: dict, dry_run: bool) -> bool:
    post = read_post(post_dir)
    urls = image_urls(post_dir)
    record_path = post_dir / "published.json"
    record = read_json(record_path, {})
    before = dict(record)
    ok = True
    print(f"\n▶ {post_dir.name}: {post.topic} (카드 {len(urls)}장)")

    if config["publish"].get("instagram") and "instagram" not in record:
        tags = " ".join(f"#{t.lstrip('#')}" for t in post.hashtags)
        event = config["brand"].get("event", {}).get("caption", "")
        caption = f"{post.instagram_caption}\n\n{event}\n.\n{tags}".replace("\n\n\n", "\n\n")
        try:
            if dry_run:
                print("  [dry-run] Instagram 캐러셀:", urls[0], "...")
            else:
                res = meta_api.instagram_carousel(
                    os.environ.get("IG_USER_ID") or meta_api.instagram_me(os.environ["IG_ACCESS_TOKEN"])["id"],
                    os.environ["IG_ACCESS_TOKEN"], urls, caption
                )
                record["instagram"] = {**res, "at": now(config).isoformat()}
                write_json(record_path, record)
                print("  ✅ Instagram:", res.get("permalink"))
        except Exception as e:  # 한 플랫폼이 실패해도 다른 플랫폼은 진행
            ok = False
            print("  ❌ Instagram 실패:", e)

    if config["publish"].get("threads") and "threads" not in record:
        try:
            if dry_run:
                for i, t in enumerate(threads_texts(post, config)):
                    print(f"  [dry-run] Threads {i}: {t[:40]}...")
            else:
                tok = os.environ["THREADS_ACCESS_TOKEN"]
                uid = os.environ.get("THREADS_USER_ID") or meta_api.threads_me(tok)["id"]
                attach = urls if config["publish"].get("threads_attach_cards") else None
                # 중간에 실패하면 올라간 글 id를 남겨두고, 다음 실행에서 이어서 단다 (중복 방지)
                texts = threads_texts(post, config)
                ids = record.get("threads_progress", [])
                for i in range(len(ids), len(texts)):
                    if i == 0:
                        ids.append(meta_api.threads_post(uid, tok, texts[0], image_urls=attach))
                    else:
                        ids.append(meta_api.threads_post(uid, tok, texts[i], reply_to_id=ids[-1]))
                    record["threads_progress"] = ids
                    write_json(record_path, record)
                record.pop("threads_progress", None)
                record["threads"] = {
                    "ids": ids,
                    "permalink": meta_api.threads_permalink(ids[0], tok),
                    "at": now(config).isoformat(),
                }
                write_json(record_path, record)
                print("  ✅ Threads:", record["threads"]["permalink"])
        except Exception as e:
            ok = False
            print("  ❌ Threads 실패:", e)
    if not dry_run and any(k in record for k in ("instagram", "threads")) and read_json(record_path, {}) != before:
        from .notify import published_mail
        if os.environ.get("NAVER_EMAIL") and os.environ.get("NAVER_PASSWORD"):
            try:
                published_mail(post_dir)
            except Exception as e:
                print("  ⚠️ 완료 메일 실패:", e)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="이 게시물만 즉시 발행 (발행 시각 무시)")
    args = ap.parse_args()

    config = load_config()
    if args.only and not args.dry_run:
        # 승인 즉시 발행: 발행 시각을 지금으로 바꿔 두면, 혹시 실패해도 15분 주기 작업이 이어서 재시도한다
        meta_path = ROOT / args.only / "meta.json"
        meta = read_json(meta_path, {})
        meta["publish_at"] = now(config).isoformat()
        write_json(meta_path, meta)
    targets = [ROOT / args.only] if args.only else due_posts(config)
    if not targets:
        print("발행할 게시물이 없습니다.")
        return
    results = [publish_one(d, config, args.dry_run) for d in targets]
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
