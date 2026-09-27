"""텔레그램 알림."""
from __future__ import annotations

import os

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def send(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("텔레그램 설정 없음 (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)")
        return False
    r = requests.post(API.format(token=token), timeout=20,
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": True})
    ok = r.ok and r.json().get("ok", False)
    print("텔레그램 발송", "성공" if ok else f"실패: {r.text[:200]}")
    return ok


def format_signal(s: dict) -> str:
    comp = " ".join(f"{k} {v:+.1f}" for k, v in s.get("구성", {}).items())
    tags = ("· 하락가드 " if s.get("가드") else "") + ("· 급락매수 " if s.get("급락매수") else "")
    msg = (f"[코스피 지수] {s['기준일']} 마감\n"
           f"지수 {s['지수']:+.2f} / 종가 {s['종가']:,.2f} {tags}\n"
           f"■ 유지할 포지션 (총자산 대비)\n"
           f"  1배 상품 {s['현재포지션_1배']:.0%} · 현금 {1 - s['현재포지션_1배']:.0%}\n"
           f"  2배 상품 {s['현재포지션_2배']:.0%} · 현금 {1 - s['현재포지션_2배']:.0%}")
    if s.get("월요일"):
        chg1 = s["다음조정_1배"] - s["현재포지션_1배"]
        chg2 = s["다음조정_2배"] - s["현재포지션_2배"]
        line = []
        if abs(chg1) >= 0.10:
            line.append(f"1배 → {s['다음조정_1배']:.0%}")
        if abs(chg2) >= 0.10:
            line.append(f"2배 → {s['다음조정_2배']:.0%}")
        msg += "\n■ 내일(화) 종가 조정: " + (", ".join(line) if line else "변경 없음")
    return f"{msg}\n{comp}"


if __name__ == "__main__":
    send("테스트: 코스피 주간지수 봇이 정상 연결되었습니다.")
