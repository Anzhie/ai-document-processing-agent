from typing import Any

from src.extractors.base import BaseExtractor
from src.schemas import ProcessingResult


class PDFExtractor(BaseExtractor):
    """
    Stub implementation for PDFExtractor.
    Returns None to trigger fallback to LLMExtractor in the pipeline.
    """

    def extract(self, content: Any) -> ProcessingResult | None:
        # Stub: Return None to force LLM fallback
        return None