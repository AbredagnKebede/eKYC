from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set


class BankAdapterError(Exception):
    """Base exception for bank adapter errors."""

    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or message


class BankNotFoundError(BankAdapterError):
    """Raised when an unconfigured or unknown partner bank is requested."""

    def __init__(self, bank_id: str) -> None:
        super().__init__(
            f"Partner bank '{bank_id}' is not registered or supported.",
            status_code=404,
            detail=f"Bank '{bank_id}' not found",
        )


class BankSchemaValidationError(BankAdapterError):
    """Raised when application dynamic fields fail the bank's JSONSchema specification."""

    def __init__(self, message: str, field_errors: Optional[Dict[str, str]] = None) -> None:
        super().__init__(message, status_code=422, detail=message)
        self.field_errors = field_errors or {}


class BankAdapterExecutionError(BankAdapterError):
    """Raised when downstream bank CBS communication or transaction fails."""
    pass


def validate_json_schema(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Validates dynamic fields dictionary against a standard JSON Schema subset.

    Supports: type (object, string, number, integer, boolean), required, properties,
    minimum, maximum, minLength, maxLength, enum, additionalProperties.
    """
    if not isinstance(data, dict):
        raise BankSchemaValidationError(f"Expected object/dictionary for dynamic fields, got {type(data).__name__}")

    # Check required fields
    required_fields: List[str] = schema.get("required", [])
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise BankSchemaValidationError(
            f"Missing required dynamic field(s): {', '.join(missing)}",
            field_errors={f: "Field is required" for f in missing},
        )

    # Check properties
    properties: Dict[str, Any] = schema.get("properties", {})
    allow_additional = schema.get("additionalProperties", True)

    if not allow_additional:
        unknown = [k for k in data.keys() if k not in properties]
        if unknown:
            raise BankSchemaValidationError(
                f"Unknown dynamic field(s) not allowed by schema: {', '.join(unknown)}",
                field_errors={k: "Additional property not permitted" for k in unknown},
            )

    field_errors: Dict[str, str] = {}

    for field_name, val in data.items():
        if field_name not in properties:
            continue

        prop_schema = properties[field_name]
        expected_type = prop_schema.get("type")

        # Type validation
        if expected_type == "string":
            if not isinstance(val, str):
                field_errors[field_name] = f"Expected string, got {type(val).__name__}"
                continue
            min_len = prop_schema.get("minLength")
            if min_len is not None and len(val) < min_len:
                field_errors[field_name] = f"Length must be at least {min_len} characters"
            max_len = prop_schema.get("maxLength")
            if max_len is not None and len(val) > max_len:
                field_errors[field_name] = f"Length must not exceed {max_len} characters"

        elif expected_type in ("number", "integer"):
            if expected_type == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
                field_errors[field_name] = f"Expected integer, got {type(val).__name__}"
                continue
            elif expected_type == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
                field_errors[field_name] = f"Expected number, got {type(val).__name__}"
                continue

            minimum = prop_schema.get("minimum")
            if minimum is not None and val < minimum:
                field_errors[field_name] = f"Value must be greater than or equal to {minimum}"
            maximum = prop_schema.get("maximum")
            if maximum is not None and val > maximum:
                field_errors[field_name] = f"Value must be less than or equal to {maximum}"

        elif expected_type == "boolean":
            if not isinstance(val, bool):
                field_errors[field_name] = f"Expected boolean, got {type(val).__name__}"

        # Enum validation
        if "enum" in prop_schema and val not in prop_schema["enum"]:
            allowed = prop_schema["enum"]
            field_errors[field_name] = f"Value '{val}' must be one of {allowed}"

    if field_errors:
        err_msg = "; ".join(f"{k}: {v}" for k, v in field_errors.items())
        raise BankSchemaValidationError(f"Dynamic fields validation error: {err_msg}", field_errors=field_errors)


class BankAdapter(ABC):
    """Abstract interface defining required behavior for partner Core Banking System adapters."""

    bank_id: str
    bank_name: str
    supported_tiers: List[str]

    @abstractmethod
    def get_dynamic_schema(self) -> Dict[str, Any]:
        """Returns the JSONSchema governing bank-specific intake form fields."""
        raise NotImplementedError

    def validate_dynamic_fields(self, dynamic_fields: Dict[str, Any]) -> None:
        """Validates applicant dynamic fields against the bank's active schema."""
        schema = self.get_dynamic_schema()
        validate_json_schema(schema, dynamic_fields)

    @abstractmethod
    def transform_payload(self, application_data: Dict[str, Any]) -> Dict[str, Any]:
        """Translates canonical platform application format into CBS-specific intake schema."""
        raise NotImplementedError

    @abstractmethod
    async def submit_application(
        self,
        application_data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches verified customer application to CBS and returns unified submission result."""
        raise NotImplementedError


class BankAdapterService:
    """Registry and orchestrator managing bank adapter instances."""

    def __init__(self) -> None:
        self._adapters: Dict[str, BankAdapter] = {}

    def register_adapter(self, adapter: BankAdapter) -> None:
        """Registers a new bank adapter instance into the active registry."""
        self._adapters[adapter.bank_id] = adapter

    def get_adapter(self, bank_id: str) -> BankAdapter:
        """Resolves the registered adapter for a given bank identifier."""
        if bank_id not in self._adapters:
            raise BankNotFoundError(bank_id)
        return self._adapters[bank_id]

    def list_supported_banks(self) -> List[Dict[str, Any]]:
        """Returns metadata and schemas for all active partner banks."""
        return [
            {
                "bank_id": adapter.bank_id,
                "bank_name": adapter.bank_name,
                "supported_tiers": adapter.supported_tiers,
                "dynamic_schema": adapter.get_dynamic_schema(),
            }
            for adapter in self._adapters.values()
        ]

    def validate_fields(self, bank_id: str, dynamic_fields: Dict[str, Any]) -> None:
        """Validates dynamic fields against the specified partner bank's schema."""
        adapter = self.get_adapter(bank_id)
        adapter.validate_dynamic_fields(dynamic_fields)

    async def submit(
        self,
        bank_id: str,
        application_data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches verified application to the appropriate partner bank adapter."""
        adapter = self.get_adapter(bank_id)
        return await adapter.submit_application(application_data, idempotency_key=idempotency_key)
