"""평일 수집: KRX → 네이버 → 금투협 순서로 증분 수집하고 검증한다."""
from __future__ import annotations

import sys
import traceback

from checks import check
from collectors import fx, kofia, krx
from notify.telegram import send

FAIL = []


def step(name, fn):
    try:
        fn()
        print(f"[OK] {name}")
    except Exception as e:
        FAIL.append(f"{name}: {type(e).__name__} {str(e)[:150]}")
        traceback.print_exc()


if __name__ == "__main__":
    step("KRX", lambda: krx.run())
    step("금투협", lambda: kofia.run())
    step("환율", lambda: fx.run())
    try:
        from index.compute import run as compute_run
        from notify.telegram import format_signal
        sig = compute_run()
        send(format_signal(sig))
    except Exception as e:
        FAIL.append(f"지수계산: {type(e).__name__} {str(e)[:150]}")
        traceback.print_exc()

    problems = check()
    if FAIL or problems:
        send("[수집 경고]\n" + "\n".join(FAIL + problems))
        sys.exit(1 if FAIL else 0)
    print("수집·검증 완료")
