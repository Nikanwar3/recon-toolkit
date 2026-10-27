import pytest

from app.errors import SchemaConfigError
from app.validation import FieldSpec, validate_records

SPECS = [
    FieldSpec("order_id", required=True),
    FieldSpec("amount", required=True, coerce=float),
    FieldSpec("note", required=False),
]


def test_valid_records_pass_through_with_coercion():
    records = [{"order_id": "1", "amount": "10.5", "note": "ok"}]
    result = validate_records(records, SPECS, key_fields=["order_id"])
    assert result.valid == [{"order_id": "1", "amount": 10.5, "note": "ok"}]
    assert result.invalid == []


def test_missing_required_field_is_invalid_not_a_crash():
    records = [{"order_id": "1"}]  # amount missing
    result = validate_records(records, SPECS, key_fields=["order_id"])
    assert result.valid == []
    assert len(result.invalid) == 1
    assert result.invalid[0].reason.startswith("missing_required_field:amount")


def test_missing_optional_field_is_fine():
    records = [{"order_id": "1", "amount": "5"}]  # note omitted, not required
    result = validate_records(records, SPECS, key_fields=["order_id"])
    assert result.valid == [{"order_id": "1", "amount": 5.0, "note": None}]


def test_invalid_type_is_captured_as_invalid_record():
    records = [{"order_id": "1", "amount": "not-a-number"}]
    result = validate_records(records, SPECS, key_fields=["order_id"])
    assert result.valid == []
    assert "invalid_type:amount" in result.invalid[0].reason


def test_duplicate_business_key_keeps_first_flags_rest():
    records = [
        {"order_id": "1", "amount": "10"},
        {"order_id": "1", "amount": "20"},
    ]
    result = validate_records(records, SPECS, key_fields=["order_id"])
    assert len(result.valid) == 1
    assert result.valid[0]["amount"] == 10.0
    assert result.invalid[0].reason == "duplicate_key"


def test_empty_input_produces_empty_result_not_an_error():
    result = validate_records([], SPECS, key_fields=["order_id"])
    assert result.is_empty_input
    assert result.valid == []
    assert result.invalid == []


def test_non_dict_record_is_invalid():
    result = validate_records(["not-a-dict"], SPECS, key_fields=["order_id"])
    assert result.invalid[0].reason == "not_a_record"


def test_key_field_not_declared_in_specs_raises_schema_config_error():
    with pytest.raises(SchemaConfigError):
        validate_records([], SPECS, key_fields=["does_not_exist"])
