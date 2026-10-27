"""Performance-sensitive path: reconcile_datasets must stay near-linear as
dataset size grows, since it indexes both sides by business key (O(n + m))
rather than comparing every source record against every target record
(O(n * m)). The nested-loop version of this test (pairwise comparison)
would take noticeably longer at this size; this asserts a generous wall
clock bound rather than a strict benchmark to avoid CI flakiness, and
exists to catch an accidental regression to the quadratic approach, not to
make a timing claim.
"""
import time

from app.reconciliation import FieldComparison, ReconciliationConfig, reconcile_datasets, rules

N = 20_000


def _build_dataset(n, offset=0):
    return [
        {"id": str(i), "amount": float(i), "status": "OPEN"}
        for i in range(offset, offset + n)
    ]


def test_reconcile_datasets_handles_large_input_within_a_generous_bound():
    source = _build_dataset(N)
    # Target overlaps half the ids, half are target-only, and every 10th
    # overlapping record has a deliberate amount mismatch.
    target = _build_dataset(N // 2, offset=N // 4)
    for rec in target:
        if int(rec["id"]) % 10 == 0:
            rec["amount"] += 1

    config = ReconciliationConfig(
        key_fields=["id"],
        compare_fields=[FieldComparison("amount", rules.exact), FieldComparison("status", rules.exact)],
    )

    start = time.perf_counter()
    result = reconcile_datasets(source, target, config)
    elapsed = time.perf_counter() - start

    assert result.matched_count + result.mismatched_count == N // 2
    assert result.source_only_count == N - N // 2
    assert result.target_only_count == 0
    # Generous bound (nested-loop comparison at this N would take far
    # longer): this is a regression guard, not a performance benchmark.
    assert elapsed < 10.0
