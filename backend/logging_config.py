"""
구조화된 로깅 설정
콘솔 + 파일 로테이션 + 에러 전용 파일
"""
import logging
import logging.handlers
import os


def setup_logging(log_dir: str = "logs", level: str = "INFO"):
    """로깅 초기화 (서버 시작 시 1회 호출)"""
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # 파일 핸들러 (10MB, 5개 보관)
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "crypto_signals.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # 에러 전용 파일 (5MB, 3개 보관)
    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "errors.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console)
    root.addHandler(file_handler)
    root.addHandler(error_handler)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
