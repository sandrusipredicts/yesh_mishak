import argparse
import json
import logging
import sys

from app.services.game_expiry_reconciliation import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_BATCHES,
    reconcile_expired_games,
)
from app.services.job_runs import JobRun, JobRunRecorder

logger = logging.getLogger(__name__)
JOB_NAME = "game_expiry_reconciliation"


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
    recorder = JobRunRecorder()
    job_run: JobRun | None = None

    try:
        job_run = recorder.start(
            job_name=JOB_NAME,
            metadata={
                "batch_size": args.batch_size,
                "max_batches": args.max_batches,
                "entry_point": "app.jobs.reconcile_game_expiry",
            },
        )
    except Exception as exc:
        logger.warning(
            "failed to create game expiry reconciliation job run record",
            extra={
                "event": "jobs.game_expiry_reconciliation.monitoring_failure",
                "job_name": JOB_NAME,
                "monitoring_stage": "start",
                "result": "partial_failure",
                "error_code": "JOB_RUN_RECORD_FAILED",
                "exception_type": exc.__class__.__name__,
            },
            exc_info=True,
        )

    try:
        result = reconcile_expired_games(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    except Exception as exc:
        if job_run is not None:
            try:
                recorder.mark_failed(job_run, exc)
            except Exception as monitoring_exc:
                logger.warning(
                    "failed to finalize game expiry reconciliation job run as failed",
                    extra={
                        "event": "jobs.game_expiry_reconciliation.monitoring_failure",
                        "job_name": JOB_NAME,
                        "job_run_id": job_run.id,
                        "monitoring_stage": "failure",
                        "result": "partial_failure",
                        "error_code": "JOB_RUN_RECORD_FAILED",
                        "exception_type": monitoring_exc.__class__.__name__,
                    },
                    exc_info=True,
                )
        logger.exception(
            "game expiry reconciliation failed",
            extra={
                "event": "jobs.game_expiry_reconciliation.failure",
                "job_name": JOB_NAME,
                "job_run_id": job_run.id if job_run else None,
                "result": "failure",
                "error_code": "SCHEDULED_JOB_FAILED",
                "exception_type": exc.__class__.__name__,
            },
        )
        return 1

    if job_run is not None:
        try:
            recorder.mark_succeeded(job_run, result)
        except Exception as exc:
            logger.warning(
                "failed to finalize game expiry reconciliation job run as succeeded",
                extra={
                    "event": "jobs.game_expiry_reconciliation.monitoring_failure",
                    "job_name": JOB_NAME,
                    "job_run_id": job_run.id,
                    "monitoring_stage": "success",
                    "result": "partial_failure",
                    "error_code": "JOB_RUN_RECORD_FAILED",
                    "exception_type": exc.__class__.__name__,
                },
                exc_info=True,
            )

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
