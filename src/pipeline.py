from pathlib import Path

import pandas as pd

from src.config import CUSTOMER_MASTER_PATH, ITEM_MASTER_PATH
from src.extractors.image_extractor import ImageExtractor
from src.extractors.llm_extractor import LLMExtractor
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.spreadsheet_extractor import SpreadsheetExtractor
from src.ingestion import load_customer_master, load_item_master, read_input_document
from src.matching import MasterDataMatcher
from src.schemas import ProcessingResult
from src.validation import DocumentValidator


class DocumentPipeline:
    """
    End-to-end document processing pipeline orchestration.
    Handles ingestion, extraction, master data matching, and validation.
    """

    def __init__(
        self,
        customer_master_path: str | Path = CUSTOMER_MASTER_PATH,
        item_master_path: str | Path = ITEM_MASTER_PATH,
    ) -> None:
        # 1. Load Master Data tables strictly using specified paths
        self.df_customer = load_customer_master(customer_master_path)
        self.df_item = load_item_master(item_master_path)

        # 2. Initialize processing components
        self.spreadsheet_extractor = SpreadsheetExtractor()
        self.pdf_extractor = PDFExtractor()
        self.llm_extractor = LLMExtractor()
        self.image_extractor = ImageExtractor(llm_extractor=self.llm_extractor)
        self.matcher = MasterDataMatcher(
            df_customer=self.df_customer,
            df_item=self.df_item,
        )
        self.validator = DocumentValidator()

    def process(self, filepath: str | Path) -> ProcessingResult:
        """Runs the complete processing lifecycle for a single document."""

        # Step 1: Ingestion
        doc_payload = read_input_document(filepath)

        # Step 2: Extraction (Cascading Route: Format-Specific -> LLM Fallback)
        file_type = doc_payload.get("file_type")
        content = doc_payload.get("content")
        raw_result = None

        # Route to dedicated extractor based on identified file type
        if file_type == "spreadsheet" and isinstance(content, pd.DataFrame):
            raw_result = self.spreadsheet_extractor.extract(content)
        elif file_type == "pdf":
            raw_result = self.pdf_extractor.extract(filepath)
        elif file_type == "image":
            raw_result = self.image_extractor.extract(filepath)

        # Fallback to LLM if format-specific extraction failed or returned None
        if raw_result is None:
            if isinstance(content, pd.DataFrame):
                document_text = content.to_string()
            else:
                document_text = str(content) if content is not None else ""

            raw_result = self.llm_extractor.extract(document_text)

        # Step 3: Matching
        # Resolve customer against Master Data
        cust_match = self.matcher.match_customer(raw_result.customer_raw)
        raw_result.customer_id = cust_match.get("customer_id")
        raw_result.customer_matched = cust_match.get("matched_name")

        # Resolve line items and calculate overall document confidence
        total_confidence = cust_match.get("confidence", 0.0)
        match_count = 1  # Base count starts at 1 for the customer match

        for item in raw_result.items:
            item_match = self.matcher.match_item(
                raw_id=item.item_number,
                raw_desc=item.raw_description,
            )
            # Update item data if a match is successfully found
            if item_match.get("item_id"):
                item.item_number = item_match["item_id"]
            item.matched_description = item_match.get("matched_description")
            item.match_confidence = item_match.get("confidence", 0.0)

            total_confidence += item.match_confidence
            match_count += 1

        # Set aggregated average confidence for the entire document
        raw_result.confidence = round(total_confidence / match_count, 4)

        # Step 4: Validation (Arithmetic and business rules)
        raw_result.review_reasons = []
        raw_result.needs_review = False
        # Validate line item math and totals using DocumentValidator
        validated_result = self.validator.validate(raw_result)

        # Re-validate through Pydantic to trigger business rules
        final_result = ProcessingResult.model_validate(validated_result.model_dump())

        return final_result