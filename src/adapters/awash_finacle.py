from typing import Any, Dict, List, Optional

from src.clients.bank_cbs_client import BankCBSClient
from src.services.bank_adapter import BankAdapter, BankAdapterExecutionError, BankSchemaValidationError


class AwashFinacleAdapter(BankAdapter):
    """Adapter for Awash Bank Core Banking System running Infosys Finacle."""

    bank_id: str = "bank_awash"
    bank_name: str = "Awash Bank"
    supported_tiers: List[str] = ["standard", "diaspora", "youth", "enterprise"]

    TIER_CODE_MAPPING: Dict[str, str] = {
        "standard": "AW-SB-STD",
        "diaspora": "AW-SB-DIA",
        "youth": "AW-SB-YTH",
        "enterprise": "AW-CA-ENT",
    }

    def __init__(self, client: Optional[BankCBSClient] = None) -> None:
        self.client = client or BankCBSClient()

    def get_dynamic_schema(self) -> Dict[str, Any]:
        """Returns the JSONSchema for Awash Bank's dynamic intake attributes."""
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "AwashBankDynamicFields",
            "type": "object",
            "required": ["monthly_income_etb", "occupation", "source_of_funds"],
            "properties": {
                "monthly_income_etb": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Applicant monthly income in Ethiopian Birr (ETB).",
                },
                "occupation": {
                    "type": "string",
                    "minLength": 2,
                    "description": "Applicant primary employment occupation.",
                },
                "source_of_funds": {
                    "type": "string",
                    "enum": ["Salary", "Business", "Remittance", "Savings"],
                    "description": "Primary verified source of account funds.",
                },
                "branch_code": {
                    "type": "string",
                    "description": "Preferred Awash Bank home branch routing code.",
                },
                "initial_deposit_etb": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Optional initial opening deposit amount in ETB.",
                },
                "requires_review": {
                    "type": "boolean",
                    "description": "Flag indicating manual AML compliance officer review.",
                },
            },
            "additionalProperties": False,
        }

    def transform_payload(self, application_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transforms platform onboarding application data to Awash Finacle CBS schema."""
        app_id = application_data.get("application_id")
        if not app_id:
            raise BankSchemaValidationError("application_id is mandatory for Finacle payload transformation.")

        tier = str(application_data.get("tier", "standard")).lower()
        if tier not in self.supported_tiers:
            raise BankSchemaValidationError(
                f"Unsupported account tier '{tier}' for Awash Bank. Supported: {self.supported_tiers}"
            )

        dynamic_fields = application_data.get("dynamic_fields", {})
        self.validate_dynamic_fields(dynamic_fields)

        demographics = application_data.get("demographics") or application_data.get("customer_details") or {}
        full_name = demographics.get("full_name", "Anonymous Applicant")
        gender = demographics.get("gender", "UNKNOWN")
        date_of_birth = demographics.get("date_of_birth", "1990-01-01")

        finacle_code = self.TIER_CODE_MAPPING.get(tier, "AW-SB-STD")

        return {
            "application_id": str(app_id),
            "bank_id": self.bank_id,
            "tier": tier,
            "finacle_scheme_code": finacle_code,
            "customer_details": {
                "full_name": full_name,
                "gender": gender,
                "date_of_birth": date_of_birth,
            },
            "dynamic_fields": dynamic_fields,
            "finacle_channel": "EKYC_MOBILE_ONBOARDING",
        }

    async def submit_application(
        self,
        application_data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submits transformed application to Awash Finacle CBS via client."""
        finacle_payload = self.transform_payload(application_data)
        idem_key = idempotency_key or f"idem_{self.bank_id}_{finacle_payload['application_id']}"

        try:
            cbs_result = await self.client.open_account(finacle_payload, idempotency_key=idem_key)
        except Exception as exc:
            raise BankAdapterExecutionError(
                f"Awash Finacle submission failed: {exc}",
                detail=str(exc),
            ) from exc

        return {
            "status": cbs_result.get("status", "SUCCESS"),
            "bank_id": self.bank_id,
            "bank_reference": cbs_result.get("bank_reference", ""),
            "account_number": cbs_result.get("account_number"),
            "account_tier": finacle_payload["tier"],
            "created_at": cbs_result.get("created_at"),
            "message": cbs_result.get("message", "Application submitted to Awash Finacle CBS."),
        }
