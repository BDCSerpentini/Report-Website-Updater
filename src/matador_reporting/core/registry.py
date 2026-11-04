from __future__ import annotations

from matador_reporting.core.contracts import ReportProcessor
from matador_reporting.core.errors import ConfigurationError


class ReportRegistry:
    def __init__(self) -> None:
        self._processors: dict[str, ReportProcessor] = {}

    def register(self, processor: ReportProcessor) -> None:
        if processor.report_type in self._processors:
            raise ConfigurationError(
                f"Report type already registered: {processor.report_type}"
            )
        self._processors[processor.report_type] = processor

    def get(self, report_type: str) -> ReportProcessor:
        try:
            return self._processors[report_type]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown report type: {report_type}") from exc

    def available_report_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._processors))

