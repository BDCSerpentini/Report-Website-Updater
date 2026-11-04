class ReportError(Exception):
    """Base exception for user-facing reporting failures."""


class InvalidReportError(ReportError):
    """Raised when an uploaded file is not the expected report type."""


class ConfigurationError(ReportError):
    """Raised when report configuration is internally inconsistent."""


class GoogleSheetsError(ReportError):
    """Raised when a report cannot be written to Google Sheets."""
