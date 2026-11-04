from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class UploadRequirement:
    key: str
    label: str
    required: bool = True
    accepted_extensions: tuple[str, ...] = (".csv",)


class ReportProcessor(Protocol):
    report_type: str
    upload_requirements: tuple[UploadRequirement, ...]

    def validate_upload(self, upload_key: str, path: Path) -> None:
        """Validate one uploaded file without processing the complete report."""

