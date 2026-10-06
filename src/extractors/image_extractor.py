from pathlib import Path
from typing import Any

from PIL import Image
import pytesseract

from src.extractors.base import BaseExtractor
from src.extractors.llm_extractor import LLMExtractor
from src.schemas import ProcessingResult


class ImageExtractor(BaseExtractor):
    """
    Extractor for image-based document formats (.png, .jpg, .jpeg, .tiff).
    
    Architecture Note:
    ------------------
    This extractor uses a hybrid OCR + LLM approach:
    1. Tesseract OCR (pytesseract.image_to_string) extracts raw unformatted text[span_1](start_span)[span_1](end_span).
    2. Because flat OCR drops spatial 2D grid context (bounding boxes, layout structure),
       deterministic regular expressions cannot reliably parse line items.
    3. Structured schema extraction is delegated to LLMExtractor[span_2](start_span)[span_2](end_span).

    Future Improvement:
    To make this fully deterministic without LLM dependencies, switch from image_to_string 
    to image_to_data (bounding box coordinates) and visual layout reconstruction.
    """

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

    def __init__(self, llm_extractor: LLMExtractor | None = None) -> None:
        self.llm_extractor = llm_extractor or LLMExtractor()

    def extract(self, content: Any) -> ProcessingResult | None:
        """
        Parses an image file into a structured ProcessingResult.
        
        Pipeline Step 1: Read image and perform OCR text extraction via Tesseract[span_3](start_span)[span_3](end_span).
        Pipeline Step 2: Delegate text-to-JSON parsing to LLMExtractor[span_4](start_span)[span_4](end_span).
        """
        path = Path(content) if isinstance(content, (str, Path)) else None
        if not path or not path.exists() or path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return None

        try:
            # 1. OCR Text Extraction via Tesseract / PIL
            image = Image.open(path)
            extracted_text = pytesseract.image_to_string(image)

            if not extracted_text or not extracted_text.strip():
                return None

            # 2. Structured Extraction via LLM Strategy (delegated due to layout loss)
            return self.llm_extractor.extract(extracted_text)

        except Exception:
            return None