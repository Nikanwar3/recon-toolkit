"""Input validation for reconciliation datasets.

Runs ahead of the reconciliation engine so bad data produces a structured,
reportable `invalid` bucket instead of an uncaught exception mid-run. This
replaces the old implicit assumption (in `app.loaders.schema.normalize_record`)
that every record is well-formed.
"""
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .errors import SchemaConfigError

Coercer = Callable[[Any], Any]


@dataclass
class FieldSpec:
    """One field's validation rule."""

    name: str
    required: bool = True
    coerce: Optional[Coercer] = None  # e.g. float, str.strip; raises on bad input


@dataclass
class InvalidRecord:
    index: int
    reason: str
    raw: Dict[str, Any]


@dataclass
class ValidationResult:
    valid: List[Dict[str, Any]] = dc_field(default_factory=list)
    invalid: List[InvalidRecord] = dc_field(default_factory=list)
    duplicate_key_values: Dict[tuple, int] = dc_field(default_factory=dict)
    """Business-key tuple -> count of records sharing it (count > 1 means a
    duplicate; the first-seen record is kept in `valid`, later ones are
    moved to `invalid` with reason 'duplicate_key')."""

    @property
    def is_empty_input(self) -> bool:
        return not self.valid and not self.invalid


def validate_records(
    records: Sequence[Dict[str, Any]],
    field_specs: Sequence[FieldSpec],
    key_fields: Sequence[str],
) -> ValidationResult:
    """Validate and coerce a dataset against `field_specs`, flagging
    duplicates of `key_fields`.

    Never raises on bad *data* -- every per-record problem is captured in
    `ValidationResult.invalid`. Raises `SchemaConfigError` only if the config
    itself is wrong (e.g. a key field absent from field_specs).
    """
    spec_names = {s.name for s in field_specs}
    missing_key_fields = [k for k in key_fields if k not in spec_names]
    if missing_key_fields:
        raise SchemaConfigError(
            f"key field(s) {missing_key_fields} are not declared in field_specs"
        )

    result = ValidationResult()
    seen_keys: Dict[tuple, int] = {}  # key_tuple -> index into result.valid

    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            result.invalid.append(
                InvalidRecord(index=index, reason="not_a_record", raw={"_value": repr(raw)})
            )
            continue

        coerced: Dict[str, Any] = {}
        reason = None
        for spec in field_specs:
            value = raw.get(spec.name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                if spec.required:
                    reason = f"missing_required_field:{spec.name}"
                    break
                coerced[spec.name] = None
                continue
            if spec.coerce is not None:
                try:
                    coerced[spec.name] = spec.coerce(value)
                except (ValueError, TypeError) as exc:
                    reason = f"invalid_type:{spec.name}:{exc}"
                    break
            else:
                coerced[spec.name] = value

        if reason:
            result.invalid.append(InvalidRecord(index=index, reason=reason, raw=raw))
            continue

        key = tuple(coerced[k] for k in key_fields)
        if key in seen_keys:
            result.duplicate_key_values[key] = result.duplicate_key_values.get(key, 1) + 1
            result.invalid.append(
                InvalidRecord(index=index, reason="duplicate_key", raw=raw)
            )
            continue

        seen_keys[key] = len(result.valid)
        result.valid.append(coerced)

    return result
