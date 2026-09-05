"""Project-specific exceptions."""


class MiniAECError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(MiniAECError):
    """Raised when required application configuration is invalid or missing."""


class DataSourceError(MiniAECError):
    """Raised when a project data source cannot be loaded or validated."""


class IFCModelError(DataSourceError):
    """Raised when an IFC model cannot be opened or queried safely."""


class UnsupportedRuleOperatorError(MiniAECError):
    """Raised when a compliance rule contains an unsupported operator."""
