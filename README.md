# kospi-index

코스피 주간 트레이딩 지수(-10 ~ +10) 자동 수집·계산·알림.

## 구조
- `collectors/` : KRX(pykrx), 네이버 금융, 금융투자협회 수집기
- `data/` : 수집된 CSV가 자동으로 쌓이는 곳
- `index/` : 주간 지수 계산(model.py)과 데이터 결합(compute.py)
- `notify/` : 텔레그램 알림
- `.github/workflows/` : test(수동), backfill(수동), daily(평일 18:30 KST), weekly(금 20:00 KST)

## Secrets (Settings → Secrets and variables → Actions)
`KRX_ID`, `KRX_PW`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`

## 실행 순서
1. Actions → test → Run workflow : 세 소스 접속과 텔레그램 발송 확인
2. Actions → backfill → Run workflow : 2008년부터 과거 데이터 수집 (1회, 수십 분)
3. 이후 daily/weekly 가 자동 실행

## 데이터 단위
- `kospi_index.csv`, `krx_investor.csv` : 원
- `kospi_investor_naver.csv` : 억원
- `kofia_funds.csv` : 백만원

## 주의
지수 로직(`index/model.py`)은 2011~2026년 백테스트 기준이며, 수급 요소는 2024년 이후만 검증됐다.
PBR은 현재 수집·기록만 하고 점수에는 반영하지 않는다(v3에서 반영 예정).
