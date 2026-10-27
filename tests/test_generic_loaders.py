import pytest

from app.errors import ValidationError
from app.loaders import load_csv_records, load_json_records, load_records


def test_load_csv_records_parses_rows(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("order_id,amount\n1,10.5\n2,20.0\n")
    records = load_csv_records(str(path))
    assert records == [{"order_id": "1", "amount": "10.5"}, {"order_id": "2", "amount": "20.0"}]


def test_load_csv_records_empty_file_returns_empty_list(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    assert load_csv_records(str(path)) == []


def test_load_csv_records_header_only_returns_empty_list(tmp_path):
    path = tmp_path / "header_only.csv"
    path.write_text("order_id,amount\n")
    assert load_csv_records(str(path)) == []


def test_load_csv_records_missing_value_becomes_none(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("order_id,amount\n1,\n")
    records = load_csv_records(str(path))
    assert records[0]["amount"] is None


def test_load_json_records_parses_array(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('[{"order_id": "1"}, {"order_id": "2"}]')
    assert load_json_records(str(path)) == [{"order_id": "1"}, {"order_id": "2"}]


def test_load_json_records_empty_file_returns_empty_list(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")
    assert load_json_records(str(path)) == []


def test_load_json_records_malformed_json_raises_validation_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    with pytest.raises(ValidationError):
        load_json_records(str(path))


def test_load_json_records_top_level_object_raises_validation_error(tmp_path):
    path = tmp_path / "object.json"
    path.write_text('{"order_id": "1"}')  # not a top-level array
    with pytest.raises(ValidationError):
        load_json_records(str(path))


def test_load_records_dispatches_by_extension(tmp_path):
    csv_path = tmp_path / "a.csv"
    csv_path.write_text("order_id\n1\n")
    json_path = tmp_path / "a.json"
    json_path.write_text("[]")
    assert load_records(str(csv_path)) == [{"order_id": "1"}]
    assert load_records(str(json_path)) == []


def test_load_records_unsupported_extension_raises_validation_error(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("whatever")
    with pytest.raises(ValidationError):
        load_records(str(path))
