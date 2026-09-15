"""SOAP client integration, used to render a flagged reconciliation total as
words for a human-readable audit note (e.g. "$1,204.50 -> one thousand two
hundred four dollars and fifty cents").

Uses the public NumberConversion demo SOAP service via zeep. Real production
SOAP integrations (this project's stand-in for enterprise SOAP endpoints)
follow the same shape: parse the WSDL, build a client, call an operation,
and degrade gracefully if the endpoint is unreachable -- the same
fallback-if-unavailable pattern already used for AWS/Redis elsewhere.
"""
import logging

from zeep import Client
from zeep.exceptions import Fault, TransportError

logger = logging.getLogger(__name__)

_WSDL = "https://www.dataaccess.com/webservicesserver/NumberConversion.wso?WSDL"
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(_WSDL)
    return _client


def amount_to_words(amount):
    """Convert a dollar amount to words via the SOAP NumberConversion service.

    Returns None (instead of raising) if the SOAP endpoint is unreachable,
    so a flaky third-party dependency never breaks report generation.
    """
    cents = int(round(amount * 100))
    try:
        client = _get_client()
        return client.service.NumberToDollars(dNum=cents / 100)
    except (Fault, TransportError, Exception) as exc:  # pragma: no cover - network dependent
        logger.warning("SOAP NumberConversion unavailable, skipping words form: %s", exc)
        return None
