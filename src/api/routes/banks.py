from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.adapters.ethiopian_banks import register_all_ethiopian_banks
from src.services.bank_adapter import BankAdapterService, BankNotFoundError

router = APIRouter(prefix="/v1/banks", tags=["Banks"])

_bank_service = BankAdapterService()
register_all_ethiopian_banks(_bank_service)


def get_bank_adapter_service() -> BankAdapterService:
    return _bank_service


class BankMetadataResponse(BaseModel):
    bank_id: str = Field(..., description="Unique partner bank identifier")
    bank_name: str = Field(..., description="Human-readable partner bank name")
    short_code: Optional[str] = Field(default=None, description="Bank short code / ticker")
    hq_city: Optional[str] = Field(default=None, description="Headquarters city")
    operational_status: str = Field(
        default="OPERATIONAL", description="Bank CBS integration operational health"
    )
    supported_tiers: List[str] = Field(..., description="Supported onboarding account tiers")
    dynamic_schema: Dict[str, Any] = Field(
        ..., description="JSONSchema draft-2020-12 specification for dynamic intake"
    )
    schemas_by_tier: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None, description="Per-tier JSONSchemas when available"
    )


@router.get("", response_model=List[BankMetadataResponse])
async def list_partner_banks(
    tier: Optional[str] = None,
    service: BankAdapterService = Depends(get_bank_adapter_service),
) -> List[BankMetadataResponse]:
    """Retrieves the active registry of partner banks, supported tiers, and dynamic JSONSchemas."""
    banks = service.list_supported_banks()
    items: List[BankMetadataResponse] = []
    for b in banks:
        schema = b["dynamic_schema"]
        by_tier = b.get("schemas_by_tier")
        if tier and by_tier and tier in by_tier:
            schema = by_tier[tier]
        elif tier and hasattr(service.get_adapter(b["bank_id"]), "get_dynamic_schema"):
            try:
                schema = service.get_adapter(b["bank_id"]).get_dynamic_schema(tier)  # type: ignore[call-arg]
            except TypeError:
                pass
        items.append(
            BankMetadataResponse(
                bank_id=b["bank_id"],
                bank_name=b["bank_name"],
                short_code=b.get("short_code"),
                hq_city=b.get("hq_city"),
                operational_status="OPERATIONAL",
                supported_tiers=b["supported_tiers"],
                dynamic_schema=schema,
                schemas_by_tier=by_tier,
            )
        )
    return items


@router.get("/{bank_id}", response_model=BankMetadataResponse)
async def get_partner_bank(
    bank_id: str,
    tier: Optional[str] = None,
    service: BankAdapterService = Depends(get_bank_adapter_service),
) -> BankMetadataResponse:
    """Retrieves metadata and schema specification for a specific partner bank."""
    try:
        adapter = service.get_adapter(bank_id)
        try:
            schema = adapter.get_dynamic_schema(tier) if tier else adapter.get_dynamic_schema()  # type: ignore[call-arg]
        except TypeError:
            schema = adapter.get_dynamic_schema()
        by_tier = adapter.schemas_by_tier() if hasattr(adapter, "schemas_by_tier") else None
        return BankMetadataResponse(
            bank_id=adapter.bank_id,
            bank_name=adapter.bank_name,
            short_code=getattr(adapter, "short_code", None),
            hq_city=getattr(adapter, "hq_city", None),
            operational_status="OPERATIONAL",
            supported_tiers=adapter.supported_tiers,
            dynamic_schema=schema,
            schemas_by_tier=by_tier,
        )
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{bank_id}' not found.",
        )


class UpdateBankSchemaRequest(BaseModel):
    dynamic_schema: Dict[str, Any] = Field(
        ..., description="Updated JSONSchema definition for dynamic intake"
    )


@router.put("/{bank_id}/schema", response_model=BankMetadataResponse)
async def update_partner_bank_schema(
    bank_id: str,
    req: UpdateBankSchemaRequest,
    service: BankAdapterService = Depends(get_bank_adapter_service),
) -> BankMetadataResponse:
    """Updates the active JSONSchema definition for a partner bank dynamically."""
    try:
        service.update_dynamic_schema(bank_id, req.dynamic_schema)
        adapter = service.get_adapter(bank_id)
        return BankMetadataResponse(
            bank_id=adapter.bank_id,
            bank_name=adapter.bank_name,
            short_code=getattr(adapter, "short_code", None),
            hq_city=getattr(adapter, "hq_city", None),
            operational_status="OPERATIONAL",
            supported_tiers=adapter.supported_tiers,
            dynamic_schema=adapter.get_dynamic_schema(),
        )
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{bank_id}' not found.",
        )
