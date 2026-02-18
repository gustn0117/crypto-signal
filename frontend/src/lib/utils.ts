// ─── 가격 포맷 ────────────────────────────────────────────
export function formatPrice(price: number): string {
  if (!price || isNaN(price)) return "0.00";
  if (price >= 1000)
    return price.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

// ─── 거래량 포맷 ──────────────────────────────────────────
export function formatVolume(vol: number): string {
  if (vol >= 1_000_000_000) return `$${(vol / 1_000_000_000).toFixed(2)}B`;
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(2)}M`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(2)}K`;
  return `$${vol.toFixed(0)}`;
}

// ─── 경과 시간 ────────────────────────────────────────────
export function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

// ─── 시그널 컬러 (CSS 변수 반환) ──────────────────────────
export function signalColor(signal: string): string {
  if (signal.includes("LONG")) return "var(--long)";
  if (signal.includes("SHORT")) return "var(--short)";
  return "var(--text-muted)";
}

// ─── 신뢰도 컬러 ─────────────────────────────────────────
export function confidenceColor(confidence: number): string {
  if (confidence >= 0.7) return "var(--success-text)";
  if (confidence >= 0.4) return "var(--warning)";
  return "var(--text-muted)";
}

// ─── 시간 포맷 ────────────────────────────────────────────
export function formatTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
