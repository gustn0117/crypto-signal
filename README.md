# Crypto Signal System

바이낸스 기반 암호화폐 롱/숏 시그널 분석 시스템

## 구조

```
crypto-signal-system/
├── backend/                # Python FastAPI 백엔드
│   ├── analysis/           # 분석 엔진
│   │   ├── indicators.py   # RSI, MACD, BB, EMA, Stochastic
│   │   ├── candle_patterns.py  # 도지, 해머, 잉걸핑 등
│   │   ├── volume.py       # 거래량 급증, OBV, 다이버전스
│   │   └── signal_engine.py    # 종합 시그널 생성
│   ├── exchange.py         # 바이낸스 API 연동
│   ├── scanner.py          # 마켓 스캐너
│   ├── main.py             # FastAPI 서버
│   ├── config.py           # 설정
│   └── requirements.txt
├── frontend/               # Next.js 프론트엔드
│   ├── src/
│   │   ├── app/            # 페이지
│   │   ├── components/     # UI 컴포넌트
│   │   ├── hooks/          # WebSocket 훅
│   │   └── lib/            # API 클라이언트
│   └── package.json
└── README.md
```

## 시작하기

### 1. 백엔드 실행

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env    # 필요 시 API 키 설정
python main.py
```

서버가 http://localhost:8000 에서 실행됩니다.

### 2. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

http://localhost:3000 에서 대시보드를 확인할 수 있습니다.

## 분석 전략

### 기술적 지표 (가중치 45%)
- **RSI** - 과매수/과매도 판단 (30 이하 롱, 70 이상 숏)
- **MACD** - 골든/데드 크로스 + 히스토그램
- **볼린저밴드** - 상단/하단 터치
- **EMA 크로스** - 9/21 이동평균 교차
- **스토캐스틱** - K/D 과매수/과매도

### 캔들 패턴 (가중치 30%)
- 도지, 해머, 행잉맨
- 불리시/베어리시 잉걸핑
- 모닝스타/이브닝스타
- 적삼병/흑삼병

### 거래량 분석 (가중치 25%)
- 거래량 급증 감지 (평균 대비 2배 이상)
- OBV 트렌드
- 가격-거래량 다이버전스

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/markets` | USDT 마켓 목록 |
| GET | `/api/analyze/{symbol}` | 개별 코인 분석 |
| GET | `/api/ohlcv/{symbol}` | 캔들 데이터 |
| GET | `/api/scan` | 마켓 스캔 실행 |
| GET | `/api/signals` | 최근 스캔 결과 |
| WS | `/ws` | 실시간 시그널 |

## 주의사항

이 시스템은 분석 보조 도구입니다. 투자 결정은 본인의 판단으로 하시기 바랍니다.
