"""Per-bank Fast Forward routing settings and helpers."""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bank_portal import BankSettings
from src.services.audit import AuditService


class BankRoutingService:
    def __init__(self, audit: Optional[AuditService] = None) -> None:
        self.audit = audit or AuditService()

    async def get_or_create_settings(self, session: AsyncSession, bank_id: str) -> BankSettings:
        row = await session.get(BankSettings, bank_id)
        if row is None:
            row = BankSettings(bank_id=bank_id, ff_outbound=True, ff_inbound=True)
            session.add(row)
            await session.flush()
        return row

    async def get_flags(self, session: AsyncSession, bank_id: str) -> Tuple[bool, bool]:
        row = await self.get_or_create_settings(session, bank_id)
        return bool(row.ff_outbound), bool(row.ff_inbound)

    async def update_flags(
        self,
        session: AsyncSession,
        bank_id: str,
        *,
        ff_outbound: Optional[bool] = None,
        ff_inbound: Optional[bool] = None,
        actor_id: str = "SYSTEM",
    ) -> BankSettings:
        row = await self.get_or_create_settings(session, bank_id)
        if ff_outbound is not None:
            row.ff_outbound = ff_outbound
        if ff_inbound is not None:
            row.ff_inbound = ff_inbound
        row.updated_by = actor_id
        await self.audit.record_event(
            session=session,
            actor_type="BANK",
            actor_id=actor_id,
            action="FF_TOGGLED",
            application_id=None,
            payload={
                "bank_id": bank_id,
                "ff_outbound": row.ff_outbound,
                "ff_inbound": row.ff_inbound,
            },
        )
        await session.flush()
        return row

    async def ensure_defaults_for_banks(self, session: AsyncSession, bank_ids: list[str]) -> int:
        created = 0
        for bank_id in bank_ids:
            existing = await session.get(BankSettings, bank_id)
            if existing is None:
                session.add(BankSettings(bank_id=bank_id))
                created += 1
        if created:
            await session.flush()
        return created
