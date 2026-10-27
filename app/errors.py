"""Exception hierarchy for the reconciliation platform.

Every error that can surface from validation, the reconciliation engine, or
the database layer has a specific type here so callers can distinguish
"bad input" from "infrastructure failure" instead of catching bare
Exception. Messages must never include full record contents (see
`app.logging_config` for the redaction rule this hierarchy relies on).
"""


class ReconciliationError(Exception):
    """Base class for all errors raised by this platform."""


class ValidationError(ReconciliationError):
    """A dataset failed schema/type/required-field validation."""

    def __init__(self, message, record_index=None, field=None):
        super().__init__(message)
        self.record_index = record_index
        self.field = field


class SchemaConfigError(ReconciliationError):
    """The reconciliation config itself is invalid (bad key fields, rules)."""


class DatabaseError(ReconciliationError):
    """Base class for persistence-layer failures."""


class DatabaseConnectionError(DatabaseError):
    """Could not open or maintain a connection to the configured database."""


class TransactionError(DatabaseError):
    """A transaction failed and was rolled back."""
