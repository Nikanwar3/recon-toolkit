from app.reconcile import reconcile


def rec(order_id, source, **overrides):
    base = {"order_id": order_id, "customer": "Acme", "amount": 100.0,
            "status": "SHIPPED", "date": "2026-01-01", "source": source}
    base.update(overrides)
    return base


def test_identical_records_across_sources_produce_no_discrepancy():
    a = [rec("ORD-1", "sys_a")]
    b = [rec("ORD-1", "sys_b")]
    assert reconcile({"sys_a": a, "sys_b": b}) == []


def test_missing_from_one_source_is_flagged():
    a = [rec("ORD-1", "sys_a")]
    b = []
    discrepancies = reconcile({"sys_a": a, "sys_b": b})
    assert len(discrepancies) == 1
    assert discrepancies[0]["missing_from"] == ["sys_b"]


def test_missing_entire_source_export_is_still_detected():
    """The bug this guards against: a source with zero records anywhere
    must still be known, so a fully-failed export isn't silently invisible."""
    a = [rec("ORD-1", "sys_a"), rec("ORD-2", "sys_a")]
    discrepancies = reconcile({"sys_a": a, "sys_b": []})
    assert len(discrepancies) == 2
    assert all(d["missing_from"] == ["sys_b"] for d in discrepancies)


def test_amount_mismatch_is_flagged_but_rounding_noise_is_not():
    a = [rec("ORD-1", "sys_a", amount=100.00)]
    b = [rec("ORD-1", "sys_b", amount=100.005)]  # sub-cent rounding noise
    c = [rec("ORD-2", "sys_a", amount=100.00)]
    d = [rec("ORD-2", "sys_b", amount=150.00)]  # real mismatch

    discrepancies = reconcile({"sys_a": a + c, "sys_b": b + d})
    ids = {disc["order_id"] for disc in discrepancies}
    assert "ORD-1" not in ids
    assert "ORD-2" in ids


def test_status_mismatch_is_flagged():
    a = [rec("ORD-1", "sys_a", status="SHIPPED")]
    b = [rec("ORD-1", "sys_b", status="CANCELLED")]
    discrepancies = reconcile({"sys_a": a, "sys_b": b})
    assert "status" in discrepancies[0]["field_mismatches"]


def test_duplicate_order_id_within_one_source_keeps_first_record():
    """Regression test for the bug documented in docs/root-cause-analysis.md
    (scenario 1): a source emitting two records under the same order_id used
    to silently let the later one overwrite the earlier one. It must now
    deterministically keep the first-seen record instead."""
    a = [
        rec("ORD-1", "sys_a", amount=100.00),
        rec("ORD-1", "sys_a", amount=999.00),  # duplicate order_id, same source
    ]
    b = [rec("ORD-1", "sys_b", amount=100.00)]

    discrepancies = reconcile({"sys_a": a, "sys_b": b})

    assert discrepancies == []  # first sys_a record (100.00) matches sys_b
