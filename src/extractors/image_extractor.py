from typing import Any

from src.extractors.base import BaseExtractor
from src.extractors.llm_extractor import LLMExtractor
from src.schemas import ProcessingResult


class ImageExtractor(BaseExtractor):
    """
    Stub implementation for ImageExtractor.
    Returns None to trigger fallback to LLMExtractor in the pipeline.
    """

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

    def __init__(self, llm_extractor: LLMExtractor | None = None) -> None:
        self.llm_extractor = llm_extractor or LLMExtractor()

    def extract(self, content: Any) -> ProcessingResult | None:
        # Stub: Return None to force LLM fallback
        return None