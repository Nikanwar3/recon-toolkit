def normalize_record(raw):
    """Coerce a raw record (str-typed, from any source) into a common schema."""
    return {
        "order_id": str(raw["order_id"]),
        "customer": str(raw["customer"]),
        "amount": round(float(raw["amount"]), 2),
        "status": str(raw["status"]).strip().upper(),
        "date": str(raw["date"]),
        "source": raw.get("source"),
    }
