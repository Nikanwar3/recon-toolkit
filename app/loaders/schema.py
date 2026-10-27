from ..errors import ValidationError

REQUIRED_FIELDS = ("order_id", "customer", "amount", "status", "date")


def normalize_record(raw):
    """Coerce a raw record (str-typed, from any source) into a common schema.

    Raises `ValidationError` (not a bare KeyError/ValueError) on a missing
    required field or an unparseable amount, so a malformed record produces
    a typed, catchable error instead of an opaque stack trace.
    """
    missing = [f for f in REQUIRED_FIELDS if raw.get(f) in (None, "")]
    if missing:
        raise ValidationError(f"record missing required field(s): {missing}", field=missing[0])
    try:
        amount = round(float(raw["amount"]), 2)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"invalid amount {raw['amount']!r}: {exc}", field="amount") from exc

    return {
        "order_id": str(raw["order_id"]),
        "customer": str(raw["customer"]),
        "amount": amount,
        "status": str(raw["status"]).strip().upper(),
        "date": str(raw["date"]),
        "source": raw.get("source"),
    }
