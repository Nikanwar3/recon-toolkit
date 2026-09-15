from unittest.mock import patch

from app.soap_client import amount_to_words


def test_amount_to_words_returns_none_on_transport_failure():
    with patch("app.soap_client._get_client", side_effect=Exception("network down")):
        assert amount_to_words(123.45) is None


def test_amount_to_words_live_call():
    """Hits the real public demo SOAP service; skipped if unreachable."""
    result = amount_to_words(1204.50)
    if result is None:
        import pytest
        pytest.skip("public SOAP demo endpoint unreachable in this environment")
    assert "thousand" in result.lower()
