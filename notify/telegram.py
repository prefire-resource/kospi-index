"""텔레그램 알림 — 시그널 리포트 발송."""
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
                      data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True})
    ok = r.ok and r.json().get("ok", False)
    print("텔레그램 발송", "성공" if ok else f"실패: {r.text[:200]}")
    return ok


def _zone(v: float) -> str:
    if v >= 5: return "적극 매수"
    if v >= 2: return "매수 우위"
    if v > -2: return "중립"
    if v > -5: return "방어"
    return "위험"


def _bar(v: float, width: int = 10) -> str:
    """-10~+10 을 막대로."""
    filled = int(round(abs(v) / 10 * width))
    return ("▓" * filled + "░" * (width - filled))


def _change(prev: float, cur: float) -> str:
    """비중 변화를 사람이 읽는 문장으로."""
    if abs(cur - prev) < 0.05:
        return f"{cur:.0%} 유지"
    if prev == 0:
        return f"0% → {cur:.0%} (신규 진입)"
    if cur == 0:
        return f"{prev:.0%} → 0% (전량 매도)"
    tag = "확대" if cur > prev else "축소"
    return f"{prev:.0%} → {cur:.0%} ({tag})"


def format_signal(s: dict) -> str:
    d, w, p = s["daily"], s["weekly"], s["성과"]
    sign = "+" if s["등락률"] >= 0 else ""
    flags = []
    if s.get("가드"): flags.append("하락 가드 발동")
    if s.get("급락매수"): flags.append("급락 매수 구간")
    comp = "\n".join(f"  · {k:<9} {v:+.1f}" for k, v in s.get("구성", {}).items())

    lines = [
        f"<b>KOSPI 시그널 리포트</b>  {s['기준일']}",
        f"코스피 {s['종가']:,.2f} ({sign}{s['등락률']:.2f}%)",
        "",
        f"<b>시그널 지표  {s['지표']:+.2f}</b>  [{_zone(s['지표'])}]",
        f"{_bar(s['지표'])}  전일 대비 {s['지표변화']:+.2f}",
    ]
    if flags:
        lines.append("⚠ " + " · ".join(flags))
    lines += [
        "",
        "<b>［Daily Position 전략］</b>  내일 종가 기준",
        f"  1배  {_change(d['직전_1배'], d['1배'])}",
        f"  2배  {_change(d['직전_2배'], d['2배'])}",
        "",
        "<b>［Weekly Position 전략］</b>",
    ]
    if w["조정일"]:
        lines += [
            "  내일(화) 종가에 조정",
            f"  1배  {_change(w['1배'], w['다음조정_1배'])}",
            f"  2배  {_change(w['2배'], w['다음조정_2배'])}",
        ]
    else:
        lines += [
            "  다음 화요일까지 현 비중 유지",
            f"  1배  {w['1배']:.0%}  (현금 {1 - w['1배']:.0%})",
            f"  2배  {w['2배']:.0%}  (현금 {1 - w['2배']:.0%})",
        ]

    lines += ["", "<b>지표 구성</b>", comp]

    live = s.get("실전")
    if live:
        lines += [
            "",
            f"<b>실전 기록</b>  {live['시작일']} 시작 ({live['경과일']}일)",
            f"  Daily  1배 {live['Daily 1배']:+.1%}  ·  2배 {live['Daily 2배']:+.1%}",
            f"  Weekly 1배 {live['Weekly 1배']:+.1%}  ·  2배 {live['Weekly 2배']:+.1%}",
            f"  단순보유 {live['단순보유']:+.1%}",
        ]
    lines += [
        "",
        f"<b>백테스트</b> {s.get('검증기간', '')}",
        f"  Daily  1배 연{p['Daily 1배']['연수익']:.1%} / MDD {p['Daily 1배']['최대낙폭']:.0%}"
        f"  ·  2배 연{p['Daily 2배']['연수익']:.1%} / MDD {p['Daily 2배']['최대낙폭']:.0%}",
        f"  Weekly 1배 연{p['Weekly 1배']['연수익']:.1%} / MDD {p['Weekly 1배']['최대낙폭']:.0%}"
        f"  ·  2배 연{p['Weekly 2배']['연수익']:.1%} / MDD {p['Weekly 2배']['최대낙폭']:.0%}",
        f"  단순보유 연{p['단순보유']['연수익']:.1%} / MDD {p['단순보유']['최대낙폭']:.0%}",
        "",
        "<i>포지션은 총자산(주식 평가액 + 현금) 대비 비중입니다.</i>",
        "<i>과거 데이터 기반 분석 자료이며 투자 손익은 본인 책임입니다.</i>",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    send("테스트: 코스피 시그널 봇이 정상 연결되었습니다.")
