"""네이버 메일로 검수 요청 / 발행 결과를 보낸다.

사용:
  python -m src.notify review  content/2026-10-17-xxx <PR번호> [수정본]
  python -m src.notify published content/2026-10-17-xxx

필요 환경변수: NAVER_EMAIL, NAVER_PASSWORD (네이버 비밀번호 또는 애플리케이션 비밀번호)
선택: NOTIFY_TO (받는 주소, 기본은 NAVER_EMAIL), CARDS_SHA, GITHUB_REPOSITORY
"""
from __future__ import annotations

import os
from datetime import datetime
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from .common import ROOT, load_config, read_json, read_post, threads_texts


def card_urls(post_dir) -> list[str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("CARDS_SHA", "main")
    rel = post_dir.relative_to(ROOT).as_posix()
    return [f"https://raw.githubusercontent.com/{repo}/{ref}/{rel}/cards/{p.name}"
            for p in sorted((post_dir / "cards").glob("*.jpg"))]


def button(url: str, label: str, color: str = "#C9FF3B") -> str:
    return (f'<a href="{escape(url)}" style="display:inline-block;background:{color};color:#111;'
            f'font-weight:800;font-size:18px;padding:16px 28px;border-radius:12px;text-decoration:none">{label}</a>')


def send(subject: str, html: str) -> None:
    user = os.environ["NAVER_EMAIL"]
    pw = os.environ["NAVER_PASSWORD"]
    to = os.environ.get("NOTIFY_TO") or user
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.naver.com", 465, timeout=60) as s:
        try:
            s.login(user.split("@")[0], pw)  # 네이버는 보통 아이디로 로그인
        except smtplib.SMTPAuthenticationError:
            s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"📧 메일 보냄 → {to}: {subject}")


def review_mail(post_dir, pr: str, revised: bool) -> None:
    post = read_post(post_dir)
    meta = read_json(post_dir / "meta.json", {})
    at = datetime.fromisoformat(meta["publish_at"]).strftime("%m월 %d일 %H:%M") if meta.get("publish_at") else "-"
    kind = "📰 마케팅 사례" if meta.get("series") == "cases" else "💡 마케팅 꿀팁"
    urls = card_urls(post_dir)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pr_url = f"https://github.com/{repo}/pull/{pr}"
    thumbs = "".join(f'<img src="{u}" width="180" style="margin:4px;border-radius:8px">' for u in urls)
    action = button(pr_url, "✅ 확인하고 올리기")
    html = f"""<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:640px;margin:auto;color:#111">
  <p style="font-size:14px;color:#888">{'✏️ 수정본이 도착했어요' if revised else '📬 오늘의 카드뉴스가 도착했어요'}</p>
  <h2 style="margin:4px 0 6px">{escape(post.topic)}</h2>
  <p style="margin:0 0 4px">{kind} · <b>{escape(post.pillar)}</b> · <b>발행 예약 {at}</b></p>
  <p style="margin:0 0 18px;color:#555"><b>해결하는 고민</b> {escape(post.problem)}</p>
  <div style="margin:0 0 22px">{action}</div>
  <div>{thumbs}</div>
  <h3 style="margin-top:26px">📝 인스타 캡션</h3>
  <pre style="white-space:pre-wrap;background:#f5f5f5;padding:14px;border-radius:10px;font-family:inherit">{escape(post.instagram_caption)}</pre>
  <h3>🧵 스레드 첫 글</h3>
  <pre style="white-space:pre-wrap;background:#f5f5f5;padding:14px;border-radius:10px;font-family:inherit">{escape(threads_texts(post, load_config())[0])}</pre>
  {('<p style="font-size:13px;color:#666"><b>출처</b><br>' + '<br>'.join(escape(x) for x in post.sources) + '</p>') if post.sources else ''}
  <div style="margin:22px 0">{action}</div>
  <div style="background:#f7f7f7;border-radius:10px;padding:14px;font-size:14px;line-height:1.8">
    버튼을 누르면 GitHub 검수 화면이 열려요.<br>
    ✅ <b>승인</b>: 아래로 내려 <b>Merge pull request → Confirm merge</b> → <b>{at}</b>에 인스타·스레드에 자동으로 올라가요<br>
    ✏️ <b>고치기</b>: 댓글에 <code>/수정 고칠 내용</code> 을 쓰고 Comment (고친 버전을 메일로 다시 보내드려요)<br>
    ❌ <b>안 올리기</b>: 맨 아래 <b>Close pull request</b>
  </div>
</div>"""
    prefix = ("[수정본]" if revised else "[검수]") + ("[사례]" if meta.get("series") == "cases" else "[꿀팁]")
    send(f"{prefix} {post.topic}", html)


def published_mail(post_dir) -> None:
    post = read_post(post_dir)
    rec = read_json(post_dir / "published.json", {})
    rows = []
    for name, key in (("인스타그램", "instagram"), ("스레드", "threads")):
        link = (rec.get(key) or {}).get("permalink")
        rows.append(f"<li>{name}: " + (f'<a href="{escape(link)}">게시물 보기</a>' if link else "실패 또는 대기 중") + "</li>")
    html = f"""<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:640px;margin:auto">
  <h2>🎉 올라갔어요: {escape(post.topic)}</h2><ul style="font-size:16px;line-height:1.8">{''.join(rows)}</ul></div>"""
    send(f"[발행 완료] {post.topic}", html)


def main() -> None:
    if not os.environ.get("NAVER_EMAIL") or not os.environ.get("NAVER_PASSWORD"):
        print("메일 설정(NAVER_EMAIL/NAVER_PASSWORD)이 없어 메일은 건너뜁니다.")
        return
    kind, post_dir = sys.argv[1], ROOT / sys.argv[2]
    try:
        if kind == "review":
            review_mail(post_dir, sys.argv[3], revised=len(sys.argv) > 4)
        elif kind == "published":
            published_mail(post_dir)
    except Exception as e:  # 메일 실패가 생성·발행을 막지 않게
        print(f"⚠️ 메일 전송 실패: {e}")


if __name__ == "__main__":
    load_config()
    main()
