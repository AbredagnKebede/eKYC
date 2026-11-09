"""Persist and register partner banks for API, portal, and worker."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.awash_finacle import AwashFinacleAdapter
from src.adapters.ethiopian_banks import ETHIOPIAN_BANK_CATALOG, EthiopianBankAdapter
from src.clients.bank_cbs_client import BankCBSClient
from src.models.bank_portal import PartnerBank
from src.services.bank_adapter import BankAdapterService, BankNotFoundError


def build_adapter_from_row(
    row: PartnerBank,
    client: Optional[BankCBSClient] = None,
) -> EthiopianBankAdapter | AwashFinacleAdapter:
    shared = client or BankCBSClient()
    if row.use_legacy_awash or row.bank_id == "bank_awash":
        return AwashFinacleAdapter(client=shared)
    return EthiopianBankAdapter(
        bank_id=row.bank_id,
        bank_name=row.bank_name,
        short_code=row.short_code,
        supported_tiers=list(row.supported_tiers or ["standard"]),
        hq_city=row.hq_city or "Addis Ababa",
        client=shared,
    )


def build_adapter_from_meta(
    meta: Dict[str, Any],
    client: Optional[BankCBSClient] = None,
) -> EthiopianBankAdapter | AwashFinacleAdapter:
    shared = client or BankCBSClient()
    if meta.get("use_legacy_awash") or meta.get("bank_id") == "bank_awash":
        return AwashFinacleAdapter(client=shared)
    return EthiopianBankAdapter(
        bank_id=meta["bank_id"],
        bank_name=meta["bank_name"],
        short_code=meta["short_code"],
        supported_tiers=list(meta.get("supported_tiers") or ["standard"]),
        hq_city=meta.get("hq_city", "Addis Ababa"),
        client=shared,
    )


async def seed_partner_banks_from_catalog(session: AsyncSession) -> int:
    """Insert seed catalogue rows when the table is empty. Returns rows inserted."""
    existing = (await session.execute(select(PartnerBank.bank_id).limit(1))).scalar_one_or_none()
    if existing is not None:
        return 0
    created = 0
    for meta in ETHIOPIAN_BANK_CATALOG:
        session.add(
            PartnerBank(
                bank_id=meta["bank_id"],
                bank_name=meta["bank_name"],
                short_code=meta["short_code"],
                hq_city=meta.get("hq_city"),
                supported_tiers=list(meta.get("supported_tiers") or ["standard"]),
                use_legacy_awash=bool(meta.get("use_legacy_awash")),
                active=True,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def list_partner_bank_rows(
    session: AsyncSession,
    *,
    active_only: bool = True,
) -> List[PartnerBank]:
    stmt = select(PartnerBank).order_by(PartnerBank.bank_name.asc())
    if active_only:
        stmt = stmt.where(PartnerBank.active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def sync_adapters_from_db(
    session: AsyncSession,
    service: BankAdapterService,
    *,
    active_only: bool = True,
    client: Optional[BankCBSClient] = None,
) -> int:
    """Replace in-memory adapters with DB-backed active (or all) banks."""
    rows = await list_partner_bank_rows(session, active_only=active_only)
    service._adapters.clear()
    shared = client or BankCBSClient()
    for row in rows:
        if active_only and not row.active:
            continue
        service.register_adapter(build_adapter_from_row(row, client=shared))
    return len(service._adapters)


async def ensure_adapter_registered(
    session: AsyncSession,
    service: BankAdapterService,
    bank_id: str,
    client: Optional[BankCBSClient] = None,
) -> None:
    """Lazy-load a single bank into the registry (worker-friendly)."""
    try:
        service.get_adapter(bank_id)
        return
    except BankNotFoundError:
        pass
    row = await session.get(PartnerBank, bank_id)
    if row is None or not row.active:
        raise BankNotFoundError(bank_id)
    service.register_adapter(build_adapter_from_row(row, client=client))


def register_catalog_fallback(service: BankAdapterService, client: Optional[BankCBSClient] = None) -> int:
    """In-memory fallback when DB is unavailable (tests / early boot)."""
    shared = client or BankCBSClient()
    for meta in ETHIOPIAN_BANK_CATALOG:
        service.register_adapter(build_adapter_from_meta(meta, client=shared))
    return len(service._adapters)
