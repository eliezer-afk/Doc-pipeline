from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineInfo:
    name: str
    type: str
    source_path: str
    source_code: str
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    @abstractmethod
    def parse(self, source: Path) -> PipelineInfo:
        """Parsea el source y retorna un PipelineInfo."""
