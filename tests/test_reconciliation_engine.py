from app.reconciliation import FieldComparison, ReconciliationConfig, reconcile_datasets, rules


def _config(**comparators):
    return ReconciliationConfig(
        key_fields=["id"],
        compare_fields=[FieldComparison(name, cmp) for name, cmp in comparators.items()],
    )


def test_matching_records_are_matched():
    source = [{"id": "1", "amount": 100.0}]
    target = [{"id": "1", "amount": 100.0}]
    result = reconcile_datasets(source, target, _config(amount=rules.exact))
    assert result.matched_count == 1
    assert result.mismatched_count == 0


def test_source_only_record_is_detected():
    source = [{"id": "1", "amount": 100.0}]
    target = []
    result = reconcile_datasets(source, target, _config(amount=rules.exact))
    assert result.source_only_count == 1
    assert result.target_only_count == 0
    assert result.source_only[0]["id"] == "1"


def test_target_only_record_is_detected():
    source = []
    target = [{"id": "1", "amount": 100.0}]
    result = reconcile_datasets(source, target, _config(amount=rules.exact))
    assert result.target_only_count == 1
    assert result.target_only[0]["id"] == "1"


def test_field_level_mismatch_is_captured_with_both_values():
    source = [{"id": "1", "amount": 100.0, "status": "OPEN"}]
    target = [{"id": "1", "amount": 150.0, "status": "OPEN"}]
    config = _config(amount=rules.exact, status=rules.exact)
    result = reconcile_datasets(source, target, config)
    assert result.mismatched_count == 1
    mismatch = result.mismatched[0]
    assert len(mismatch.mismatches) == 1
    assert mismatch.mismatches[0].field == "amount"
    assert mismatch.mismatches[0].source_value == 100.0
    assert mismatch.mismatches[0].target_value == 150.0


def test_numeric_tolerance_absorbs_rounding_noise():
    source = [{"id": "1", "amount": 100.00}]
    target = [{"id": "1", "amount": 100.004}]
    result = reconcile_datasets(source, target, _config(amount=rules.numeric_tolerance(0.01)))
    assert result.matched_count == 1


def test_numeric_tolerance_still_flags_real_mismatch():
    source = [{"id": "1", "amount": 100.00}]
    target = [{"id": "1", "amount": 250.00}]
    result = reconcile_datasets(source, target, _config(amount=rules.numeric_tolerance(0.01)))
    assert result.mismatched_count == 1


def test_null_on_both_sides_is_equal_null_vs_value_is_not():
    source = [{"id": "1", "note": None}, {"id": "2", "note": None}]
    target = [{"id": "1", "note": None}, {"id": "2", "note": "present"}]
    result = reconcile_datasets(source, target, _config(note=rules.exact))
    assert result.matched_count == 1
    assert result.mismatched_count == 1


def test_date_rule_treats_equivalent_formats_as_equal():
    source = [{"id": "1", "date": "2026-01-05"}]
    target = [{"id": "1", "date": "01/05/2026"}]
    result = reconcile_datasets(source, target, _config(date=rules.date_equal))
    assert result.matched_count == 1


def test_case_insensitive_rule_ignores_casing_and_whitespace():
    source = [{"id": "1", "status": " Shipped "}]
    target = [{"id": "1", "status": "SHIPPED"}]
    result = reconcile_datasets(source, target, _config(status=rules.case_insensitive))
    assert result.matched_count == 1


def test_composite_business_key_is_supported():
    config = ReconciliationConfig(
        key_fields=["region", "order_id"],
        compare_fields=[FieldComparison("amount", rules.exact)],
    )
    source = [{"region": "US", "order_id": "1", "amount": 10.0}]
    target = [{"region": "EU", "order_id": "1", "amount": 10.0}]
    result = reconcile_datasets(source, target, config)
    # Different regions => different composite key => not the same record.
    assert result.source_only_count == 1
    assert result.target_only_count == 1


def test_result_is_deterministic_across_runs():
    source = [{"id": str(i), "amount": float(i)} for i in range(50)]
    target = [{"id": str(i), "amount": float(i) + 1} for i in range(50)]
    config = _config(amount=rules.exact)
    first = reconcile_datasets(source, target, config)
    second = reconcile_datasets(list(reversed(source)), list(reversed(target)), config)
    assert [m.key for m in first.mismatched] == [m.key for m in second.mismatched]
