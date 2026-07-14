import argparse
import json
import logging
import sys

from app.services.game_expiry_reconciliation import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_BATCHES,
    reconcile_expired_games,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile expired games by marking eligible open/full rows as finished.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)

    try:
        result = reconcile_expired_games(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    except Exception as exc:
        logger.exception(
            "game expiry reconciliation failed",
            extra={
                "event": "jobs.game_expiry_reconciliation.failure",
                "job_name": "game_expiry_reconciliation",
                "result": "failure",
                "error_code": "SCHEDULED_JOB_FAILED",
                "exception_type": exc.__class__.__name__,
            },
        )
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
