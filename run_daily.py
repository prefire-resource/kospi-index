"""평일 수집 + 지수 계산 + 알림.

하루 두 번(21:17 / 23:00 KST) 실행해도 알림은 한 번만 간다.
data/last_sent.json 에 마지막으로 발송한 기준일을 기록하고,
같은 기준일이면 수집·계산만 하고 발송은 건너뛴다.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from checks import check
from collectors import fx, kofia, krx
from collectors.common import DATA
from notify.telegram import send

FAIL = []
SENT = DATA / "last_sent.json"


def step(name, fn):
    try:
        fn()
        print(f"[OK] {name}")
    except Exception as e:
        FAIL.append(f"{name}: {type(e).__name__} {str(e)[:150]}")
        traceback.print_exc()


def already_sent(date_str: str) -> bool:
    if not SENT.exists():
        return False
    try:
        return json.loads(SENT.read_text(encoding="utf-8")).get("기준일") == date_str
    except Exception:
        return False


def mark_sent(date_str: str) -> None:
    SENT.write_text(json.dumps({"기준일": date_str}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    step("KRX", lambda: krx.run())
    step("금투협", lambda: kofia.run())
    step("환율", lambda: fx.run())

    sig = None
    try:
        from index.compute import run as compute_run
        from notify.telegram import format_signal
        sig = compute_run()
        if already_sent(sig["기준일"]):
            print(f"{sig['기준일']} 기준 리포트는 이미 발송됨 — 알림 생략")
        else:
            send(format_signal(sig))
            try:
                from notify.chart import make
                from notify.telegram import send_photo
                p = make(30)
                if p:
                    send_photo(p, f"시그널 지표 추이 ({sig['기준일']} 기준)")
            except Exception as e:
                print("차트 생성 건너뜀:", e)
            mark_sent(sig["기준일"])
    except Exception as e:
        FAIL.append(f"지수계산: {type(e).__name__} {str(e)[:150]}")
        traceback.print_exc()

    problems = check()
    if FAIL or problems:
        # 1차 실행이 실패해도 2차 실행이 받쳐주므로, 같은 경고를 두 번 보내지 않는다
        if not (sig and already_sent(sig["기준일"])):
            send("[수집 경고]\n" + "\n".join(FAIL + problems))
        sys.exit(1 if FAIL else 0)
    print("수집·검증 완료")
