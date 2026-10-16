"""인스타그램·스레드 토큰이 제대로 연결됐는지 확인한다 (아무것도 올리지 않음).

사용: python -m src.check_meta
"""
from __future__ import annotations

import os

from . import meta_api
from .common import load_config


def main() -> None:
    want = load_config()["brand"]["handle"].lstrip("@").lower()
    ok = True
    for name, env, fn in (("인스타그램", "IG_ACCESS_TOKEN", meta_api.instagram_me),
                          ("스레드", "THREADS_ACCESS_TOKEN", meta_api.threads_me)):
        token = os.environ.get(env)
        if not token:
            print(f"⬜ {name}: {env} 가 아직 등록되지 않았어요")
            ok = False
            continue
        try:
            me = fn(token)
            match = "" if (me["username"] or "").lower() == want else f"  ⚠️ config 의 아이디(@{want})와 다름"
            print(f"✅ {name}: @{me['username']} 연결됨 (계정 ID {me['id']}){match}")
        except Exception as e:
            ok = False
            print(f"❌ {name}: 연결 실패 — {e}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
