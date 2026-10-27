"""Generic two-dataset reconciliation engine.

Compares a source and a target dataset on a configurable business key with
per-field comparison rules, producing matched / mismatched / source-only /
target-only buckets. This generalizes `app.reconcile` (which is specialized
to the fixed 5-source order-reconciliation demo and a hardcoded key/field
list) to an arbitrary pair of validated datasets.

Both datasets are indexed into dicts by business key before comparison --
O(n + m) -- rather than compared pairwise, so this does not degrade to a
nested-loop scan as dataset size grows.
"""
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Callable, Dict, List, Sequence, Tuple

from .rules import exact

Key = Tuple[Any, ...]


@dataclass(frozen=True)
class FieldComparison:
    name: str
    comparator: Callable[[Any, Any], bool] = exact


@dataclass(frozen=True)
class ReconciliationConfig:
    key_fields: Sequence[str]
    compare_fields: Sequence[FieldComparison]


@dataclass(frozen=True)
class FieldMismatch:
    field: str
    source_value: Any
    target_value: Any


@dataclass(frozen=True)
class MatchedRecord:
    key: Key
    source: Dict[str, Any]
    target: Dict[str, Any]


@dataclass(frozen=True)
class MismatchedRecord:
    key: Key
    source: Dict[str, Any]
    target: Dict[str, Any]
    mismatches: Tuple[FieldMismatch, ...]


@dataclass
class ReconciliationResult:
    matched: List[MatchedRecord] = dc_field(default_factory=list)
    mismatched: List[MismatchedRecord] = dc_field(default_factory=list)
    source_only: List[Dict[str, Any]] = dc_field(default_factory=list)
    target_only: List[Dict[str, Any]] = dc_field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return len(self.matched)

    @property
    def mismatched_count(self) -> int:
        return len(self.mismatched)

    @property
    def source_only_count(self) -> int:
        return len(self.source_only)

    @property
    def target_only_count(self) -> int:
        return len(self.target_only)


def _index_by_key(records: Sequence[Dict[str, Any]], key_fields: Sequence[str]) -> Dict[Key, Dict[str, Any]]:
    return {tuple(rec.get(k) for k in key_fields): rec for rec in records}


def _sort_key(key: Key) -> Tuple[str, ...]:
    # Keys may mix None with strings/numbers across partially-missing
    # records; comparing raw tuples would raise TypeError in Python 3, so
    # sort on a string projection instead to keep results deterministic.
    return tuple("" if part is None else str(part) for part in key)


def reconcile_datasets(
    source_records: Sequence[Dict[str, Any]],
    target_records: Sequence[Dict[str, Any]],
    config: ReconciliationConfig,
) -> ReconciliationResult:
    """Reconcile two validated, already-coerced datasets.

    Callers are expected to run both datasets through
    `app.validation.validate_records` first -- this function assumes every
    record already has well-typed values for `config.key_fields` and the
    fields named in `config.compare_fields`.
    """
    source_index = _index_by_key(source_records, config.key_fields)
    target_index = _index_by_key(target_records, config.key_fields)

    result = ReconciliationResult()
    all_keys = sorted(set(source_index) | set(target_index), key=_sort_key)

    for key in all_keys:
        if key not in target_index:
            result.source_only.append(source_index[key])
            continue
        if key not in source_index:
            result.target_only.append(target_index[key])
            continue

        src = source_index[key]
        tgt = target_index[key]

        mismatches = tuple(
            FieldMismatch(comparison.name, src.get(comparison.name), tgt.get(comparison.name))
            for comparison in config.compare_fields
            if not comparison.comparator(src.get(comparison.name), tgt.get(comparison.name))
        )

        if mismatches:
            result.mismatched.append(MismatchedRecord(key, src, tgt, mismatches))
        else:
            result.matched.append(MatchedRecord(key, src, tgt))

    return result
