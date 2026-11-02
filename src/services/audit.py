import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.security.hash_chain import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_hmac_seal,
    compute_payload_hash,
    verify_single_seal,
)


class AuditService:
    """Tamper-evident audit logging service with hash-chained cryptographic ledger."""

    def __init__(self, secret_key: Optional[str] = None) -> None:
        self.secret_key = secret_key

    async def get_latest_log(self, session: AsyncSession) -> Optional[AuditLog]:
        """Fetch the most recent audit entry to continue the cryptographic chain."""
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1).with_for_update()
        )
        return result.scalar_one_or_none()

    async def record_event(
        self,
        session: AsyncSession,
        actor_type: str,
        actor_id: str,
        action: str,
        application_id: Optional[uuid.UUID] = None,
        payload: Optional[Dict[str, Any] | str] = None,
    ) -> AuditLog:
        """
        Appends an immutable audit log entry to PostgreSQL with SHA-256 chain and HMAC seal.
        """
        payload_data = payload if payload is not None else {}
        p_hash = compute_payload_hash(payload_data)

        # Serialize ledger writes across concurrent processes/transactions
        await session.execute(text("SELECT pg_advisory_xact_lock(424242)"))

        latest = await self.get_latest_log(session)
        now = datetime.now(timezone.utc)

        if latest is None:
            prev_hash = GENESIS_HASH
            # For the first row, log_id placeholder is 1
            expected_id = 1
        else:
            prev_hash = compute_chain_hash(
                prev_log_hash=latest.prev_log_hash,
                log_id=latest.id,
                timestamp_iso=latest.timestamp.isoformat(),
                actor_type=latest.actor_type,
                actor_id=latest.actor_id,
                action=latest.action,
                application_id=str(latest.application_id) if latest.application_id else None,
                payload_hash=latest.payload_hash,
            )
            expected_id = latest.id + 1

        # Current row's chain hash to compute HMAC seal
        current_chain_hash = compute_chain_hash(
            prev_log_hash=prev_hash,
            log_id=expected_id,
            timestamp_iso=now.isoformat(),
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            application_id=str(application_id) if application_id else None,
            payload_hash=p_hash,
        )
        signature = compute_hmac_seal(current_chain_hash, self.secret_key)

        entry = AuditLog(
            timestamp=now,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            application_id=application_id,
            payload_hash=p_hash,
            prev_log_hash=prev_hash,
            hmac_signature=signature,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def verify_ledger_integrity(
        self,
        session: AsyncSession,
        limit: int = 1000,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies the cryptographic integrity of sequential audit logs.
        Detects tampering, unauthorized deletions, or altered payloads.
        """
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.id.asc()).limit(limit)
        )
        logs: List[AuditLog] = list(result.scalars().all())

        if not logs:
            return True, None

        expected_prev = GENESIS_HASH

        for i, entry in enumerate(logs):
            # 1. Check prev_log_hash continuity
            if entry.prev_log_hash != expected_prev:
                return (
                    False,
                    f"Chain break at id {entry.id}: expected prev_hash {expected_prev}, found {entry.prev_log_hash}",
                )

            # 2. Recompute chain hash for current entry
            current_chain_hash = compute_chain_hash(
                prev_log_hash=entry.prev_log_hash,
                log_id=entry.id,
                timestamp_iso=entry.timestamp.isoformat(),
                actor_type=entry.actor_type,
                actor_id=entry.actor_id,
                action=entry.action,
                application_id=str(entry.application_id) if entry.application_id else None,
                payload_hash=entry.payload_hash,
            )

            # 3. Verify HMAC seal signature
            if not verify_single_seal(current_chain_hash, entry.hmac_signature, self.secret_key):
                return False, f"HMAC seal mismatch at id {entry.id}: data has been modified"

            # 4. Advance expected_prev for next entry
            expected_prev = current_chain_hash

        return True, None
