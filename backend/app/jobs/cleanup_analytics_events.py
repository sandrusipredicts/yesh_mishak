import argparse
import json
import logging
import sys

from app.services.analytics_events import (
    DEFAULT_RETENTION_DAYS,
    cleanup_analytics_events,
)
from app.services.job_runs import JobRun, JobRunRecorder

logger = logging.getLogger(__name__)
JOB_NAME = "analytics_events_cleanup"


def _retention_days(value: str) -> int:
    days = int(value)
    if days < 1 or days > 365:
        raise argparse.ArgumentTypeError("retention-days must be between 1 and 365")
    return days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete analytics events older than the retention window.",
    )
    parser.add_argument(
        "--retention-days",
        type=_retention_days,
        default=DEFAULT_RETENTION_DAYS,
    )
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
                "retention_days": args.retention_days,
                "entry_point": "app.jobs.cleanup_analytics_events",
            },
        )
    except Exception as exc:
        logger.warning(
            "failed to create analytics events cleanup job run record",
            extra={
                "event": "jobs.analytics_events_cleanup.monitoring_failure",
                "job_name": JOB_NAME,
                "monitoring_stage": "start",
                "result": "partial_failure",
                "error_code": "JOB_RUN_RECORD_FAILED",
                "exception_type": exc.__class__.__name__,
            },
            exc_info=True,
        )

    try:
        deleted_count = cleanup_analytics_events(retention_days=args.retention_days)
        result = {
            "deleted_count": deleted_count,
            "retention_days": args.retention_days,
        }
    except Exception as exc:
        if job_run is not None:
            try:
                recorder.mark_failed(job_run, exc)
            except Exception as monitoring_exc:
                logger.warning(
                    "failed to finalize analytics events cleanup job run as failed",
                    extra={
                        "event": "jobs.analytics_events_cleanup.monitoring_failure",
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
            "analytics events cleanup failed",
            extra={
                "event": "jobs.analytics_events_cleanup.failure",
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
                "failed to finalize analytics events cleanup job run as succeeded",
                extra={
                    "event": "jobs.analytics_events_cleanup.monitoring_failure",
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
