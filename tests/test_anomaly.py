from app.anomaly import score_discrepancies


def _d(missing=0, mismatches=0, spread=0.0):
    return {
        "order_id": "X",
        "missing_from": ["s"] * missing,
        "field_mismatches": {f"f{i}": {} for i in range(mismatches)},
        "max_amount_spread": spread,
    }


def test_severe_discrepancies_ranked_above_mild_ones():
    mild = [_d(missing=0, mismatches=1, spread=0.5) for _ in range(8)]
    severe = [_d(missing=2, mismatches=3, spread=500.0) for _ in range(2)]

    scored = score_discrepancies(mild + severe, contamination=0.2)

    severe_ranks = [i for i, d in enumerate(scored) if d["max_amount_spread"] == 500.0]
    mild_ranks = [i for i, d in enumerate(scored) if d["max_amount_spread"] == 0.5]
    assert max(severe_ranks) < min(mild_ranks)


def test_small_batches_flag_everything_instead_of_fitting_a_model():
    tiny = [_d(missing=1, mismatches=1, spread=10.0) for _ in range(3)]
    scored = score_discrepancies(tiny)
    assert all(d["flagged"] for d in scored)
    assert all(d["anomaly_score"] is None for d in scored)
