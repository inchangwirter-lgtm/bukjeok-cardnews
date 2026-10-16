"""인스타그램·스레드 장기 토큰(60일)을 갱신해 GitHub Secrets 에 다시 저장한다.

GitHub Actions 에서 주 1회 실행. GH_PAT(Secrets 쓰기 권한) 이 필요하다.
"""
from __future__ import annotations

import os
import subprocess

from . import meta_api


def save_secret(name: str, value: str) -> None:
    print(f"::add-mask::{value}")
    subprocess.run(
        ["gh", "secret", "set", name, "--repo", os.environ["GITHUB_REPOSITORY"], "--body", value],
        check=True,
        env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]},
    )


def main() -> None:
    failed = False
    for name, fn in (
        ("IG_ACCESS_TOKEN", meta_api.refresh_instagram_token),
        ("THREADS_ACCESS_TOKEN", meta_api.refresh_threads_token),
    ):
        token = os.environ.get(name)
        if not token:
            print(f"- {name} 없음, 건너뜀")
            continue
        try:
            res = fn(token)
            save_secret(name, res["access_token"])
            print(f"✅ {name} 갱신 (유효기간 {int(res.get('expires_in', 0)) // 86400}일)")
        except Exception as e:
            failed = True
            print(f"❌ {name} 갱신 실패: {e}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
