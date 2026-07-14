import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.supabase import get_supabase_service_role_client

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_BATCHES = 50


@dataclass
class GameExpiryReconciliationResult:
    scanned_count: int = 0
    reconciled_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    batch_count: int = 0
    reached_max_batches: bool = False
    reconciled_game_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    cutoff: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_count": self.scanned_count,
            "reconciled_count": self.reconciled_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "batch_count": self.batch_count,
            "reached_max_batches": self.reached_max_batches,
            "reconciled_game_ids": self.reconciled_game_ids,
            "errors": self.errors,
            "cutoff": self.cutoff,
        }


def _normalize_rpc_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict):
        return data
    return {}


def reconcile_expired_games(
    *,
    supabase: Any | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_batches <= 0:
        raise ValueError("max_batches must be positive")

    service_supabase = supabase or get_supabase_service_role_client()
    cutoff_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = cutoff_dt.isoformat()
    result = GameExpiryReconciliationResult(cutoff=cutoff)
    start = time.perf_counter()

    logger.info(
        "game expiry reconciliation started",
        extra={
            "event": "jobs.game_expiry_reconciliation.start",
            "job_name": "game_expiry_reconciliation",
            "batch_size": batch_size,
            "max_batches": max_batches,
            "cutoff": cutoff,
        },
    )

    while result.batch_count < max_batches:
        response = (
            service_supabase.rpc(
                "reconcile_expired_games",
                {"p_cutoff": cutoff, "p_batch_size": batch_size},
            )
            .execute()
        )
        batch = _normalize_rpc_payload(response.data)
        scanned = int(batch.get("scanned_count") or 0)
        reconciled = int(batch.get("reconciled_count") or 0)
        skipped = int(batch.get("skipped_count") or max(0, scanned - reconciled))
        game_ids = [
            str(game_id)
            for game_id in (batch.get("reconciled_game_ids") or [])
            if game_id
        ]

        result.batch_count += 1
        result.scanned_count += scanned
        result.reconciled_count += reconciled
        result.skipped_count += skipped
        result.reconciled_game_ids.extend(game_ids)

        logger.info(
            "game expiry reconciliation batch finished",
            extra={
                "event": "jobs.game_expiry_reconciliation.batch_finish",
                "job_name": "game_expiry_reconciliation",
                "batch_index": result.batch_count,
                "scanned_count": scanned,
                "reconciled_count": reconciled,
                "skipped_count": skipped,
                "cutoff": cutoff,
            },
        )

        if scanned < batch_size or reconciled == 0:
            break

    if result.batch_count >= max_batches and result.scanned_count >= batch_size * max_batches:
        result.reached_max_batches = True

    logger.info(
        "game expiry reconciliation finished",
        extra={
            "event": "jobs.game_expiry_reconciliation.finish",
            "job_name": "game_expiry_reconciliation",
            "result": "success",
            "scanned_count": result.scanned_count,
            "reconciled_count": result.reconciled_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "batch_count": result.batch_count,
            "reached_max_batches": result.reached_max_batches,
            "execution_time_ms": round((time.perf_counter() - start) * 1000, 2),
            "cutoff": cutoff,
        },
    )
    return result.to_dict()
