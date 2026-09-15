"""Rank reconciliation discrepancies by how likely they are a real problem
vs. benign noise, using an IsolationForest over simple numeric features.

This is intentionally basic ML (per a "basic ML exposure" requirement, not a
research pipeline): a handful of interpretable features feeding a standard
scikit-learn anomaly detector, used to prioritize triage rather than to
replace the rule-based reconciliation logic in reconcile.py.
"""
import numpy as np
from sklearn.ensemble import IsolationForest

FEATURE_NAMES = ["missing_count", "field_mismatch_count", "max_amount_spread"]


def _features(discrepancy):
    return [
        len(discrepancy["missing_from"]),
        len(discrepancy["field_mismatches"]),
        discrepancy["max_amount_spread"],
    ]


def score_discrepancies(discrepancies, contamination=0.15, random_state=42):
    """Attach an `anomaly_score` and `flagged` bool to each discrepancy.

    Higher (more negative) anomaly_score = more anomalous. Returns the same
    list, sorted with the most anomalous discrepancies first.
    """
    if len(discrepancies) < 5:
        # Too little data for a meaningful model fit; flag everything so
        # nothing silently falls through triage.
        for d in discrepancies:
            d["anomaly_score"] = None
            d["flagged"] = True
        return discrepancies

    X = np.array([_features(d) for d in discrepancies])
    model = IsolationForest(contamination=contamination, random_state=random_state)
    model.fit(X)
    scores = model.decision_function(X)
    flags = model.predict(X)  # -1 = anomaly, 1 = normal

    for d, score, flag in zip(discrepancies, scores, flags):
        d["anomaly_score"] = round(float(score), 4)
        d["flagged"] = bool(flag == -1)

    discrepancies.sort(key=lambda d: d["anomaly_score"])
    return discrepancies
