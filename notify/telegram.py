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
    pbr = f"\nPBR {s['PBR']:.2f}" + (f" (상위 {100 - s['PBR백분위'] * 100:.0f}%)" if s.get("PBR백분위") is not None else "") if s.get("PBR") else ""
    return (f"[코스피 주간지수] {s['기준일']} 마감\n"
            f"지수 {s['지수']:+.2f} → {s['신호']}\n"
            f"종가 {s['종가']:,.2f} / 가드 {s['가드']}\n"
            f"{comp}{pbr}")


if __name__ == "__main__":
    send("테스트: 코스피 주간지수 봇이 정상 연결되었습니다.")
