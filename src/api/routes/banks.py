from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.adapters.awash_finacle import AwashFinacleAdapter
from src.services.bank_adapter import BankAdapterService, BankNotFoundError

router = APIRouter(prefix="/v1/banks", tags=["Banks"])

# Shared service singleton
_bank_service = BankAdapterService()
_bank_service.register_adapter(AwashFinacleAdapter())


def get_bank_adapter_service() -> BankAdapterService:
    return _bank_service


class BankMetadataResponse(BaseModel):
    bank_id: str = Field(..., description="Unique partner bank identifier")
    bank_name: str = Field(..., description="Human-readable partner bank name")
    operational_status: str = Field(default="OPERATIONAL", description="Bank CBS integration operational health")
    supported_tiers: List[str] = Field(..., description="Supported onboarding account tiers")
    dynamic_schema: Dict[str, Any] = Field(..., description="JSONSchema draft-2020-12 specification for dynamic intake")


@router.get("", response_model=List[BankMetadataResponse])
async def list_partner_banks(
    service: BankAdapterService = Depends(get_bank_adapter_service),
) -> List[BankMetadataResponse]:
    """Retrieves the active registry of partner banks, supported tiers, and dynamic JSONSchemas."""
    banks = service.list_supported_banks()
    return [
        BankMetadataResponse(
            bank_id=b["bank_id"],
            bank_name=b["bank_name"],
            operational_status="OPERATIONAL",
            supported_tiers=b["supported_tiers"],
            dynamic_schema=b["dynamic_schema"],
        )
        for b in banks
    ]


@router.get("/{bank_id}", response_model=BankMetadataResponse)
async def get_partner_bank(
    bank_id: str,
    service: BankAdapterService = Depends(get_bank_adapter_service),
) -> BankMetadataResponse:
    """Retrieves metadata and schema specification for a specific partner bank."""
    try:
        adapter = service.get_adapter(bank_id)
        return BankMetadataResponse(
            bank_id=adapter.bank_id,
            bank_name=adapter.bank_name,
            operational_status="OPERATIONAL",
            supported_tiers=adapter.supported_tiers,
            dynamic_schema=adapter.get_dynamic_schema(),
        )
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{bank_id}' not found.",
        )


class UpdateBankSchemaRequest(BaseModel):
    dynamic_schema: Dict[str, Any] = Field(..., description="Updated JSONSchema definition for dynamic intake")


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
            operational_status="OPERATIONAL",
            supported_tiers=adapter.supported_tiers,
            dynamic_schema=adapter.get_dynamic_schema(),
        )
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{bank_id}' not found.",
        )
