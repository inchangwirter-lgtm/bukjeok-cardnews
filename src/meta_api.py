"""Instagram Graph API(인스타그램 로그인 방식) / Threads API 최소 클라이언트."""
from __future__ import annotations

import time

import requests

IG_BASE = "https://graph.instagram.com/v23.0"
TH_BASE = "https://graph.threads.net/v1.0"


class MetaError(RuntimeError):
    pass


def _call(method: str, url: str, token: str, **params) -> dict:
    params["access_token"] = token
    r = requests.request(method, url, params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise MetaError(f"{r.status_code} {err.get('type', '')}: {err.get('message', r.text[:300])}")
    return data


def _wait(base: str, container_id: str, token: str, field: str, timeout: int = 300) -> None:
    """미디어 컨테이너가 처리 완료될 때까지 대기."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _call("GET", f"{base}/{container_id}", token, fields=field).get(field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise MetaError(f"컨테이너 {container_id} 처리 실패: {status}")
        time.sleep(5)
    raise MetaError(f"컨테이너 {container_id} 처리 시간 초과")


# ── Instagram ────────────────────────────────────────────


def instagram_carousel(user_id: str, token: str, image_urls: list[str], caption: str) -> dict:
    children = []
    for url in image_urls:
        c = _call("POST", f"{IG_BASE}/{user_id}/media", token, image_url=url, is_carousel_item="true")
        children.append(c["id"])
    for cid in children:
        _wait(IG_BASE, cid, token, "status_code")
    carousel = _call("POST", f"{IG_BASE}/{user_id}/media", token,
                     media_type="CAROUSEL", children=",".join(children), caption=caption)
    _wait(IG_BASE, carousel["id"], token, "status_code")
    published = _call("POST", f"{IG_BASE}/{user_id}/media_publish", token, creation_id=carousel["id"])
    info = _call("GET", f"{IG_BASE}/{published['id']}", token, fields="permalink")
    return {"id": published["id"], "permalink": info.get("permalink")}


# ── Threads ──────────────────────────────────────────────


def _threads_publish(user_id: str, token: str, container_id: str) -> str:
    _wait(TH_BASE, container_id, token, "status")
    return _call("POST", f"{TH_BASE}/{user_id}/threads_publish", token, creation_id=container_id)["id"]


def threads_post(user_id: str, token: str, text: str, image_urls: list[str] | None = None,
                 reply_to_id: str | None = None) -> str:
    extra = {"reply_to_id": reply_to_id} if reply_to_id else {}
    if image_urls and len(image_urls) > 1:
        children = [
            _call("POST", f"{TH_BASE}/{user_id}/threads", token,
                  media_type="IMAGE", image_url=u, is_carousel_item="true")["id"]
            for u in image_urls[:20]
        ]
        for cid in children:
            _wait(TH_BASE, cid, token, "status")
        c = _call("POST", f"{TH_BASE}/{user_id}/threads", token, media_type="CAROUSEL",
                  children=",".join(children), text=text, **extra)
    elif image_urls:
        c = _call("POST", f"{TH_BASE}/{user_id}/threads", token, media_type="IMAGE",
                  image_url=image_urls[0], text=text, **extra)
    else:
        c = _call("POST", f"{TH_BASE}/{user_id}/threads", token, media_type="TEXT", text=text, **extra)
    return _threads_publish(user_id, token, c["id"])


def instagram_me(token: str) -> dict:
    """토큰 주인의 인스타 계정 정보. user_id 가 게시용 계정 ID."""
    d = _call("GET", f"{IG_BASE}/me", token, fields="user_id,username")
    return {"id": str(d.get("user_id") or d["id"]), "username": d.get("username")}


def threads_me(token: str) -> dict:
    d = _call("GET", f"{TH_BASE}/me", token, fields="id,username")
    return {"id": str(d["id"]), "username": d.get("username")}


def threads_permalink(post_id: str, token: str) -> str | None:
    return _call("GET", f"{TH_BASE}/{post_id}", token, fields="permalink").get("permalink")


# ── 토큰 갱신 (장기 토큰은 60일 유효, 만료 전에 갱신) ──────────


def refresh_instagram_token(token: str) -> dict:
    return _call("GET", "https://graph.instagram.com/refresh_access_token", token,
                 grant_type="ig_refresh_token")


def refresh_threads_token(token: str) -> dict:
    return _call("GET", "https://graph.threads.net/refresh_access_token", token,
                 grant_type="th_refresh_token")
