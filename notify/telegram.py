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
    head = (f"[코스피 지수] {s['기준일']} 마감\n"
            f"지수 {s['지수']:+.2f} / 종가 {s['종가']:,.2f} {tags}\n"
            f"목표 {s['목표비중']:.0%} · 현재 {s['현재비중']:.0%}")
    o = s.get("주문")
    if not o:
        return f"{head}\n(주문 안내는 월요일 마감 후)\n{comp}"
    body = f"\n■ 화요일 종가 주문: {o['설명']}"
    if s.get("레버리지목표", 0) > 0:
        body += f"\n■ 레버리지 ETF 목표 {s['레버리지목표']:.0%}"
    return f"{head}{body}\n{comp}"


if __name__ == "__main__":
    send("테스트: 코스피 주간지수 봇이 정상 연결되었습니다.")
