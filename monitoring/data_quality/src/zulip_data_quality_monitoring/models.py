from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    name: str
    status: str
    metrics: dict[str, Any]
    summary: str
    recommendations: list[str] = field(default_factory=list)


@dataclass
class Report:
    generated_at: str
    overall_status: str
    checks: list[CheckResult]
