"""Structured logging setup.

Configures a single root handler with a consistent format and provides
`redact_record` so log call sites can attach record-identifying context
(e.g. a business key) without ever emitting full record contents -- order
amounts, customer names, etc. have no business being in application logs.
"""
import logging
import sys

_CONFIGURED = False


def configure_logging(level=logging.INFO):
    """Idempotently configure the root logger. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True


def redact_keys(record, key_fields):
    """Return only the configured business-key fields from a record.

    Use this to log "which record" without logging what the record contains.
    """
    return {k: record.get(k) for k in key_fields if k in record}
