from abc import ABC, abstractmethod
from typing import Any

from src.schemas import ProcessingResult


class BaseExtractor(ABC):
    """
    Abstract base class for all document extraction strategies.
    Decouples file formats (Excel, PDF, Scans) from the core extraction logic.
    """

    @abstractmethod
    def extract(self, content: Any) -> ProcessingResult | None:
        """
        Extracts structured data from the provided content.

        Args:
            content: Format-specific payload (e.g., pd.DataFrame, file path, or raw text).

        Returns:
            ProcessingResult if extraction succeeds, or None if the parser cannot handle the data.
        """
