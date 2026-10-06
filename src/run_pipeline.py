"""
Scheduled entry point: ingest every board, then recompute eligibility.

Runs as one unit so a scheduler has a single command to call, and so
filter verdicts never lag behind freshly ingested rows.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pipeline")


def main() -> int:
    started = datetime.now(timezone.utc)
    log.info("=== pipeline start ===")

    try:
        from src.ingest import run as ingest
        from src.apply_filters import run as apply_filters

        ingest_status = ingest()
        apply_filters()

    except Exception:
        # Full traceback to the log file; a scheduler only sees the exit code.
        log.exception("pipeline failed")
        return 1

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log.info(f"=== pipeline done in {elapsed:.0f}s ===")
    return ingest_status


if __name__ == "__main__":
    sys.exit(main())
