"""Sandbox registry of major Ethiopian commercial banks with CBS adapters."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.adapters.awash_finacle import AwashFinacleAdapter
from src.clients.bank_cbs_client import (
    BankCBSAuthError,
    BankCBSClient,
    BankCBSPayloadError,
)
from src.services.bank_adapter import (
    BankAdapter,
    BankAdapterExecutionError,
    BankAdapterService,
    BankSchemaValidationError,
)

# Major NBE-licensed commercial banks (pilot sandbox catalogue).
ETHIOPIAN_BANK_CATALOG: List[Dict[str, Any]] = [
    {
        "bank_id": "bank_cbe",
        "bank_name": "Commercial Bank of Ethiopia",
        "short_code": "CBE",
        "supported_tiers": ["standard", "diaspora", "youth", "premium"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_awash",
        "bank_name": "Awash Bank",
        "short_code": "AW",
        "supported_tiers": ["standard", "diaspora", "youth", "enterprise"],
        "hq_city": "Addis Ababa",
        "use_legacy_awash": True,
    },
    {
        "bank_id": "bank_abyssinia",
        "bank_name": "Bank of Abyssinia",
        "short_code": "BOA",
        "supported_tiers": ["standard", "diaspora", "youth"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_dashen",
        "bank_name": "Dashen Bank",
        "short_code": "DASH",
        "supported_tiers": ["standard", "diaspora", "premium"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_wegagen",
        "bank_name": "Wegagen Bank",
        "short_code": "WEG",
        "supported_tiers": ["standard", "diaspora", "youth"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_hibret",
        "bank_name": "Hibret Bank",
        "short_code": "HIB",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_coop",
        "bank_name": "Cooperative Bank of Oromia",
        "short_code": "COOP",
        "supported_tiers": ["standard", "youth", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_nib",
        "bank_name": "Nib International Bank",
        "short_code": "NIB",
        "supported_tiers": ["standard", "diaspora", "enterprise"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_bunna",
        "bank_name": "Bunna International Bank",
        "short_code": "BUN",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_zemen",
        "bank_name": "Zemen Bank",
        "short_code": "ZEM",
        "supported_tiers": ["standard", "premium", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_abay",
        "bank_name": "Abay Bank",
        "short_code": "ABY",
        "supported_tiers": ["standard", "youth", "diaspora"],
        "hq_city": "Bahir Dar",
    },
    {
        "bank_id": "bank_berhan",
        "bank_name": "Berhan Bank",
        "short_code": "BER",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_addis",
        "bank_name": "Addis International Bank",
        "short_code": "AIB",
        "supported_tiers": ["standard", "diaspora", "enterprise"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_enat",
        "bank_name": "Enat Bank",
        "short_code": "ENAT",
        "supported_tiers": ["standard", "women", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_lion",
        "bank_name": "Lion International Bank",
        "short_code": "LION",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_oromia",
        "bank_name": "Oromia Bank",
        "short_code": "OROM",
        "supported_tiers": ["standard", "youth", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_goh",
        "bank_name": "Goh Betoch Bank",
        "short_code": "GOH",
        "supported_tiers": ["standard", "mortgage", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_amhara",
        "bank_name": "Amhara Bank",
        "short_code": "AMB",
        "supported_tiers": ["standard", "youth", "diaspora"],
        "hq_city": "Bahir Dar",
    },
    {
        "bank_id": "bank_siinqee",
        "bank_name": "Siinqee Bank",
        "short_code": "SIQ",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_tsedey",
        "bank_name": "Tsedey Bank",
        "short_code": "TSD",
        "supported_tiers": ["standard", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_hijra",
        "bank_name": "Hijra Bank",
        "short_code": "HIJ",
        "supported_tiers": ["standard", "islamic", "diaspora"],
        "hq_city": "Addis Ababa",
    },
    {
        "bank_id": "bank_global",
        "bank_name": "Global Bank Ethiopia",
        "short_code": "GBL",
        "supported_tiers": ["standard", "diaspora", "enterprise"],
        "hq_city": "Addis Ababa",
    },
]


class EthiopianBankAdapter(BankAdapter):
    """CBS adapter for a partner Ethiopian bank in the sandbox environment."""

    def __init__(
        self,
        bank_id: str,
        bank_name: str,
        short_code: str,
        supported_tiers: List[str],
        hq_city: str = "Addis Ababa",
        client: Optional[BankCBSClient] = None,
        custom_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.bank_id = bank_id
        self.bank_name = bank_name
        self.short_code = short_code
        self.supported_tiers = list(supported_tiers)
        self.hq_city = hq_city
        self.client = client or BankCBSClient()
        self._custom_schema = custom_schema

    def set_dynamic_schema(self, schema: Dict[str, Any]) -> None:
        self._custom_schema = schema

    def reset_dynamic_schema(self) -> None:
        self._custom_schema = None

    def get_dynamic_schema(self, tier: Optional[str] = None) -> Dict[str, Any]:
        if self._custom_schema is not None:
            return self._custom_schema
        t = (tier or "standard").lower()
        required = ["monthly_income_etb", "occupation", "source_of_funds"]
        properties: Dict[str, Any] = {
            "monthly_income_etb": {
                "type": "number",
                "minimum": 0,
                "description": "Monthly income in Ethiopian Birr (ETB).",
            },
            "occupation": {
                "type": "string",
                "minLength": 2,
                "description": "Primary occupation.",
            },
            "source_of_funds": {
                "type": "string",
                "enum": ["Salary", "Business", "Remittance", "Savings", "Agriculture"],
                "description": "Primary source of funds.",
            },
            "branch_code": {
                "type": "string",
                "description": f"Preferred {self.bank_name} branch code ({self.hq_city}).",
            },
            "initial_deposit_etb": {
                "type": "number",
                "minimum": 0,
                "description": "Optional opening deposit in ETB.",
            },
            "requires_review": {
                "type": "boolean",
                "description": "Request manual AML officer review.",
            },
        }
        if t == "diaspora":
            required.extend(["country_of_residence", "foreign_tax_id"])
            properties["country_of_residence"] = {
                "type": "string",
                "minLength": 2,
                "description": "Country where the diaspora customer currently resides.",
            }
            properties["foreign_tax_id"] = {
                "type": "string",
                "minLength": 4,
                "description": "Foreign tax identification / TIN for remittance compliance.",
            }
            properties["source_of_funds"]["enum"] = ["Remittance", "Salary", "Business", "Savings"]
        elif t == "youth":
            required.append("guardian_full_name")
            properties["guardian_full_name"] = {
                "type": "string",
                "minLength": 3,
                "description": "Parent or guardian full legal name.",
            }
            properties["student_id"] = {
                "type": "string",
                "description": "Optional school or university student ID.",
            }
        elif t in ("women", "premium"):
            if t == "women":
                required.append("preferred_branch_city")
                properties["preferred_branch_city"] = {
                    "type": "string",
                    "minLength": 2,
                    "description": "Preferred city for Enat / women banking services.",
                }
            else:
                required.append("expected_monthly_turnover_etb")
                properties["expected_monthly_turnover_etb"] = {
                    "type": "number",
                    "minimum": 0,
                    "description": "Expected monthly account turnover in ETB.",
                }
        elif t == "enterprise":
            required.extend(["business_name", "tin_number"])
            properties["business_name"] = {
                "type": "string",
                "minLength": 2,
                "description": "Registered business / trade name.",
            }
            properties["tin_number"] = {
                "type": "string",
                "minLength": 5,
                "description": "Ethiopian TIN for the enterprise.",
            }
            properties["requires_review"] = {
                "type": "boolean",
                "description": "Enterprise openings require AML review.",
                "default": True,
            }

        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{self.short_code}_{t}_DynamicFields",
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False,
            "x-tier": t,
            "x-tier-copy": {
                "standard": "Everyday retail account",
                "diaspora": "For Ethiopians living abroad",
                "youth": "Student / youth account with guardian details",
                "women": "Women-focused banking product",
                "premium": "Higher-turnover personal banking",
                "enterprise": "Business account (manual AML review)",
            }.get(t, t),
        }

    def schemas_by_tier(self) -> Dict[str, Dict[str, Any]]:
        return {tier: self.get_dynamic_schema(tier) for tier in self.supported_tiers}

    def validate_dynamic_fields(self, dynamic_fields: Dict[str, Any], tier: Optional[str] = None) -> None:
        from src.services.bank_adapter import validate_json_schema

        schema = self.get_dynamic_schema(tier)
        validate_json_schema(schema, dynamic_fields)

    def transform_payload(self, application_data: Dict[str, Any]) -> Dict[str, Any]:
        app_id = application_data.get("application_id")
        if not app_id:
            raise BankSchemaValidationError("application_id is mandatory.")

        tier = str(application_data.get("tier", "standard")).lower()
        if tier not in self.supported_tiers:
            raise BankSchemaValidationError(
                f"Unsupported tier '{tier}' for {self.bank_name}. Supported: {self.supported_tiers}"
            )

        dynamic_fields = application_data.get("dynamic_fields", {})
        self.validate_dynamic_fields(dynamic_fields, tier=tier)

        demographics = application_data.get("demographics") or application_data.get("customer_details") or {}
        scheme = f"{self.short_code}-SB-{tier[:3].upper()}"

        return {
            "application_id": str(app_id),
            "bank_id": self.bank_id,
            "tier": tier,
            "finacle_scheme_code": scheme,
            "customer_details": {
                "full_name": demographics.get("full_name", "Anonymous Applicant"),
                "gender": demographics.get("gender", "UNKNOWN"),
                "date_of_birth": demographics.get("date_of_birth", "1990-01-01"),
            },
            "dynamic_fields": dynamic_fields,
            "finacle_channel": "EKYC_MOBILE_ONBOARDING",
        }

    async def submit_application(
        self,
        application_data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self.transform_payload(application_data)
        idem_key = idempotency_key or f"idem_{self.bank_id}_{payload['application_id']}"
        try:
            cbs_result = await self.client.open_account(payload, idempotency_key=idem_key)
        except (BankCBSAuthError, BankCBSPayloadError):
            raise
        except Exception as exc:
            raise BankAdapterExecutionError(
                f"{self.bank_name} CBS submission failed: {exc}",
                detail=str(exc),
            ) from exc

        return {
            "status": cbs_result.get("status", "SUCCESS"),
            "bank_id": self.bank_id,
            "bank_reference": cbs_result.get("bank_reference", ""),
            "account_number": cbs_result.get("account_number"),
            "account_tier": payload["tier"],
            "created_at": cbs_result.get("created_at"),
            "message": cbs_result.get("message", f"Application submitted to {self.bank_name}."),
        }


def register_all_ethiopian_banks(
    service: BankAdapterService,
    client: Optional[BankCBSClient] = None,
) -> BankAdapterService:
    """Register the full Ethiopian commercial bank sandbox catalogue."""
    shared = client or BankCBSClient()
    for meta in ETHIOPIAN_BANK_CATALOG:
        if meta.get("use_legacy_awash"):
            service.register_adapter(AwashFinacleAdapter(client=shared))
            continue
        service.register_adapter(
            EthiopianBankAdapter(
                bank_id=meta["bank_id"],
                bank_name=meta["bank_name"],
                short_code=meta["short_code"],
                supported_tiers=list(meta["supported_tiers"]),
                hq_city=meta.get("hq_city", "Addis Ababa"),
                client=shared,
            )
        )
    return service
