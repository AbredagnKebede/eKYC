"""Dynamic JSONSchema Bank Form Renderer for Mobile Client."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple

from src.ui.i18n import Locale, get_translation


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    BOOLEAN = "boolean"


@dataclass
class FormField:
    name: str
    label: str
    field_type: FieldType
    required: bool = False
    options: List[str] = field(default_factory=list)
    placeholder: str = ""
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    value: Any = None
    error: Optional[str] = None


class DynamicFormRenderer:
    """Parses JSONSchema from GET /v1/banks and manages field validation and submission."""

    def __init__(self, schema: Dict[str, Any], locale: Locale = Locale.EN):
        self.schema = schema
        self.locale = locale
        self.fields: Dict[str, FormField] = self._parse_schema(schema)

    def _parse_schema(self, schema: Dict[str, Any]) -> Dict[str, FormField]:
        properties = schema.get("properties", {})
        required_keys = set(schema.get("required", []))
        fields: Dict[str, FormField] = {}

        for key, prop in properties.items():
            raw_type = prop.get("type", "string")
            enum_vals = prop.get("enum")

            if enum_vals:
                f_type = FieldType.SELECT
            elif raw_type in ("integer", "number"):
                f_type = FieldType.NUMBER
            elif raw_type == "boolean":
                f_type = FieldType.BOOLEAN
            else:
                f_type = FieldType.TEXT

            fields[key] = FormField(
                name=key,
                label=prop.get("title", key.replace("_", " ").title()),
                field_type=f_type,
                required=(key in required_keys),
                options=enum_vals or [],
                placeholder=prop.get("description", ""),
                pattern=prop.get("pattern"),
                min_length=prop.get("minLength"),
                max_length=prop.get("maxLength"),
                value=prop.get("default", None),
            )
        return fields

    def set_value(self, field_name: str, value: Any) -> None:
        if field_name in self.fields:
            self.fields[field_name].value = value
            self.fields[field_name].error = None

    def validate_field(self, field_name: str) -> Tuple[bool, Optional[str]]:
        field_obj = self.fields.get(field_name)
        if not field_obj:
            return False, f"Unknown field: {field_name}"

        val = field_obj.value
        # 1. Required check
        if field_obj.required and (val is None or (isinstance(val, str) and not val.strip())):
            err = get_translation("fields.err_required", self.locale)
            field_obj.error = err
            return False, err

        if val is not None and isinstance(val, str) and val.strip():
            # 2. Length check
            if field_obj.min_length and len(val) < field_obj.min_length:
                err = f"Minimum length is {field_obj.min_length} characters"
                field_obj.error = err
                return False, err
            if field_obj.max_length and len(val) > field_obj.max_length:
                err = f"Maximum length is {field_obj.max_length} characters"
                field_obj.error = err
                return False, err

            # 3. Pattern check
            if field_obj.pattern and not re.match(field_obj.pattern, val):
                err = f"Value does not match required format: {field_obj.pattern}"
                field_obj.error = err
                return False, err

            # 4. Enum check
            if field_obj.options and val not in field_obj.options:
                err = f"Must be one of {field_obj.options}"
                field_obj.error = err
                return False, err

        field_obj.error = None
        return True, None

    def validate_all(self) -> Tuple[bool, Dict[str, str]]:
        errors: Dict[str, str] = {}
        for name in self.fields:
            ok, err = self.validate_field(name)
            if not ok and err:
                errors[name] = err
        return len(errors) == 0, errors

    def get_form_values(self) -> Dict[str, Any]:
        return {name: f.value for name, f in self.fields.items() if f.value is not None}
