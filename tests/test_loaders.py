from app.loaders import load_csv, load_html, load_json, load_xlsx, load_xml

EXPECTED_KEYS = {"order_id", "customer", "amount", "status", "date", "source"}


def test_load_json(sample_data):
    records = load_json(sample_data / "erp_orders.json")
    assert records
    assert set(records[0].keys()) == EXPECTED_KEYS
    assert records[0]["source"] == "erp"


def test_load_xml(sample_data):
    records = load_xml(sample_data / "warehouse_orders.xml")
    assert records
    assert set(records[0].keys()) == EXPECTED_KEYS
    assert records[0]["source"] == "warehouse"


def test_load_csv(sample_data):
    records = load_csv(sample_data / "finance_orders.csv")
    assert records
    assert set(records[0].keys()) == EXPECTED_KEYS
    assert records[0]["source"] == "finance"


def test_load_xlsx(sample_data):
    records = load_xlsx(sample_data / "billing_orders.xlsx")
    assert records
    assert set(records[0].keys()) == EXPECTED_KEYS
    assert records[0]["source"] == "billing"


def test_load_html(sample_data):
    records = load_html(sample_data / "legacy_report.html")
    assert records
    assert set(records[0].keys()) == EXPECTED_KEYS
    assert records[0]["source"] == "legacy_portal"


def test_amounts_are_floats_across_all_loaders(sample_data):
    for loader, filename in [
        (load_json, "erp_orders.json"),
        (load_xml, "warehouse_orders.xml"),
        (load_csv, "finance_orders.csv"),
        (load_xlsx, "billing_orders.xlsx"),
        (load_html, "legacy_report.html"),
    ]:
        records = loader(sample_data / filename)
        assert all(isinstance(r["amount"], float) for r in records)
