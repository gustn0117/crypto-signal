"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export default function ErrorState({
  message = "데이터를 불러오는 데 실패했습니다",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <AlertTriangle size={40} className="text-warning mb-4" />
      <p className="text-sm text-muted mb-4">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-2 text-sm text-primary hover:text-white border border-border hover:border-primary rounded-lg transition-colors"
        >
          <RefreshCw size={14} />
          다시 시도
        </button>
      )}
    </div>
  );
}
