import argparse
import json
import logging
import sys

from app.services.push_delivery import process_retry_batch
from app.services.job_runs import JobRun, JobRunRecorder

logger = logging.getLogger(__name__)
JOB_NAME = "push_delivery_retry"

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_BATCHES = 10
DEFAULT_STALENESS_HOURS = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retry failed push delivery attempts with exponential backoff.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES)
    parser.add_argument("--staleness-hours", type=float, default=DEFAULT_STALENESS_HOURS)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    staleness_seconds = int(args.staleness_hours * 3600)

    recorder = JobRunRecorder()
    job_run: JobRun | None = None

    try:
        job_run = recorder.start(
            job_name=JOB_NAME,
            metadata={
                "batch_size": args.batch_size,
                "max_batches": args.max_batches,
                "staleness_hours": args.staleness_hours,
                "entry_point": "app.jobs.retry_push_deliveries",
            },
        )
    except Exception as exc:
        logger.warning(
            "failed to create push delivery retry job run record",
            extra={
                "event": "jobs.push_delivery_retry.monitoring_failure",
                "job_name": JOB_NAME,
                "monitoring_stage": "start",
                "result": "partial_failure",
                "error_code": "JOB_RUN_RECORD_FAILED",
                "exception_type": exc.__class__.__name__,
            },
            exc_info=True,
        )

    try:
        from app.db.supabase import get_supabase_service_role_client
        client = get_supabase_service_role_client()

        totals = {
            "claimed": 0, "delivered": 0,
            "failed_retryable": 0, "failed_permanent": 0, "abandoned": 0,
            "batch_count": 0, "reached_max_batches": False,
        }

        for batch_num in range(args.max_batches):
            counts = process_retry_batch(
                client,
                batch_size=args.batch_size,
                staleness_seconds=staleness_seconds,
            )
            totals["batch_count"] += 1
            for key in ("claimed", "delivered", "failed_retryable", "failed_permanent", "abandoned"):
                totals[key] += counts.get(key, 0)

            if counts["claimed"] == 0:
                break
        else:
            totals["reached_max_batches"] = True

        result = {
            "reconciled_count": totals["delivered"],
            "scanned_count": totals["claimed"],
            "skipped_count": totals["failed_retryable"],
            "failed_count": totals["failed_permanent"] + totals["abandoned"],
            "batch_count": totals["batch_count"],
            "reached_max_batches": totals["reached_max_batches"],
        }

    except Exception as exc:
        if job_run is not None:
            try:
                recorder.mark_failed(job_run, exc)
            except Exception as monitoring_exc:
                logger.warning(
                    "failed to finalize push delivery retry job run as failed",
                    extra={
                        "event": "jobs.push_delivery_retry.monitoring_failure",
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
            "push delivery retry failed",
            extra={
                "event": "jobs.push_delivery_retry.failure",
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
                "failed to finalize push delivery retry job run as succeeded",
                extra={
                    "event": "jobs.push_delivery_retry.monitoring_failure",
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
