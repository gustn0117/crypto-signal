"""
선물 데이터 분석 모듈
펀딩레이트, 미결제약정(OI), Long/Short Ratio 분석
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FuturesResult:
    """선물 데이터 분석 결과"""
    name: str
    signal: str  # "long", "short", "neutral"
    strength: float  # 0.0 ~ 1.0
    value: float
    description: str


def analyze_funding_rate(funding_rate: float | None) -> FuturesResult | None:
    """
    펀딩레이트 분석
    - 양(+)이 과도 → 롱 포지션 과밀 → 숏 시그널 (롱 청산 압력)
    - 음(-)이 과도 → 숏 포지션 과밀 → 롱 시그널 (숏 청산 압력)
    """
    if funding_rate is None:
        return None

    rate_pct = funding_rate * 100  # 퍼센트로 변환

    if rate_pct > 0.1:
        strength = min((rate_pct - 0.1) / 0.2, 0.9)
        return FuturesResult(
            name="펀딩레이트",
            signal="short",
            strength=strength,
            value=rate_pct,
            description=f"펀딩레이트 +{rate_pct:.4f}% — 롱 과밀 (숏 압력)"
        )
    elif rate_pct > 0.03:
        return FuturesResult(
            name="펀딩레이트",
            signal="short",
            strength=0.3,
            value=rate_pct,
            description=f"펀딩레이트 +{rate_pct:.4f}% — 약한 롱 우세"
        )
    elif rate_pct < -0.1:
        strength = min((abs(rate_pct) - 0.1) / 0.2, 0.9)
        return FuturesResult(
            name="펀딩레이트",
            signal="long",
            strength=strength,
            value=rate_pct,
            description=f"펀딩레이트 {rate_pct:.4f}% — 숏 과밀 (롱 압력)"
        )
    elif rate_pct < -0.03:
        return FuturesResult(
            name="펀딩레이트",
            signal="long",
            strength=0.3,
            value=rate_pct,
            description=f"펀딩레이트 {rate_pct:.4f}% — 약한 숏 우세"
        )

    return FuturesResult(
        name="펀딩레이트",
        signal="neutral",
        strength=0.0,
        value=rate_pct,
        description=f"펀딩레이트 {rate_pct:+.4f}% — 중립"
    )


def analyze_open_interest(
    oi_current: float | None,
    oi_previous: float | None,
    price_change_pct: float | None,
) -> FuturesResult | None:
    """
    미결제약정(OI) 변화율 분석
    - OI 급증 + 가격 상승 → 추세 강화 (롱 확신)
    - OI 급증 + 가격 하락 → 추세 강화 (숏 확신)
    - OI 감소 + 가격 변동 → 추세 약화 (포지션 청산)
    """
    if oi_current is None or oi_previous is None or oi_previous == 0:
        return None

    oi_change_pct = ((oi_current - oi_previous) / oi_previous) * 100

    if abs(oi_change_pct) < 2.0:
        return FuturesResult(
            name="미결제약정",
            signal="neutral",
            strength=0.0,
            value=oi_change_pct,
            description=f"OI 변화 {oi_change_pct:+.1f}% — 변화 미미"
        )

    if price_change_pct is None:
        price_change_pct = 0.0

    if oi_change_pct > 5.0:  # OI 급증
        strength = min(oi_change_pct / 15.0, 0.8)
        if price_change_pct > 0.5:
            return FuturesResult(
                name="미결제약정",
                signal="long",
                strength=strength,
                value=oi_change_pct,
                description=f"OI +{oi_change_pct:.1f}% + 가격 상승 — 롱 포지션 유입"
            )
        elif price_change_pct < -0.5:
            return FuturesResult(
                name="미결제약정",
                signal="short",
                strength=strength,
                value=oi_change_pct,
                description=f"OI +{oi_change_pct:.1f}% + 가격 하락 — 숏 포지션 유입"
            )
    elif oi_change_pct < -5.0:  # OI 급감
        strength = min(abs(oi_change_pct) / 15.0, 0.7)
        if price_change_pct > 0.5:
            return FuturesResult(
                name="미결제약정",
                signal="short",
                strength=strength * 0.5,
                value=oi_change_pct,
                description=f"OI {oi_change_pct:.1f}% + 가격 상승 — 숏 커버링 (추세 약화)"
            )
        elif price_change_pct < -0.5:
            return FuturesResult(
                name="미결제약정",
                signal="long",
                strength=strength * 0.5,
                value=oi_change_pct,
                description=f"OI {oi_change_pct:.1f}% + 가격 하락 — 롱 청산 (반등 가능)"
            )

    return FuturesResult(
        name="미결제약정",
        signal="neutral",
        strength=0.1,
        value=oi_change_pct,
        description=f"OI {oi_change_pct:+.1f}% — 방향 불확실"
    )


def analyze_long_short_ratio(ratio: float | None) -> FuturesResult | None:
    """
    Long/Short Ratio 분석
    - 극단적 편향 → 반대 포지션 (군중 심리 역행)
    """
    if ratio is None:
        return None

    if ratio > 3.0:
        strength = min((ratio - 3.0) / 3.0, 0.8)
        return FuturesResult(
            name="롱숏비율",
            signal="short",
            strength=strength,
            value=ratio,
            description=f"L/S Ratio {ratio:.2f} — 롱 과밀 (역추세 숏 기회)"
        )
    elif ratio > 2.0:
        return FuturesResult(
            name="롱숏비율",
            signal="short",
            strength=0.3,
            value=ratio,
            description=f"L/S Ratio {ratio:.2f} — 롱 우세"
        )
    elif ratio < 0.33:
        strength = min((0.33 - ratio) / 0.33, 0.8)
        return FuturesResult(
            name="롱숏비율",
            signal="long",
            strength=strength,
            value=ratio,
            description=f"L/S Ratio {ratio:.2f} — 숏 과밀 (역추세 롱 기회)"
        )
    elif ratio < 0.5:
        return FuturesResult(
            name="롱숏비율",
            signal="long",
            strength=0.3,
            value=ratio,
            description=f"L/S Ratio {ratio:.2f} — 숏 우세"
        )

    return FuturesResult(
        name="롱숏비율",
        signal="neutral",
        strength=0.0,
        value=ratio,
        description=f"L/S Ratio {ratio:.2f} — 중립"
    )


async def get_futures_signals(client, symbol: str) -> list[FuturesResult]:
    """
    심볼에 대한 선물 데이터 수집 및 분석 통합.
    exchange.py의 AsyncBinanceClient를 사용.
    """
    results = []

    try:
        # 펀딩레이트
        funding_rate = await client.fetch_funding_rate(symbol)
        fr = analyze_funding_rate(funding_rate)
        if fr:
            results.append(fr)
    except Exception as e:
        logger.debug("펀딩레이트 조회 실패 [%s]: %s", symbol, e)

    try:
        # 미결제약정
        oi_data = await client.fetch_open_interest_change(symbol)
        if oi_data:
            oi = analyze_open_interest(
                oi_data.get("current"),
                oi_data.get("previous"),
                oi_data.get("price_change_pct"),
            )
            if oi:
                results.append(oi)
    except Exception as e:
        logger.debug("OI 조회 실패 [%s]: %s", symbol, e)

    try:
        # Long/Short Ratio
        ls_ratio = await client.fetch_long_short_ratio(symbol)
        ls = analyze_long_short_ratio(ls_ratio)
        if ls:
            results.append(ls)
    except Exception as e:
        logger.debug("L/S Ratio 조회 실패 [%s]: %s", symbol, e)

    return results
