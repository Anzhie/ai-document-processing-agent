from pathlib import Path

import pandas as pd

from src.extraction import DocumentExtractor
from src.ingestion import load_customer_master, load_item_master, read_input_document
from src.matching import MasterDataMatcher
from src.schemas import ProcessingResult
from src.validation import DocumentValidator


class DocumentPipeline:
    """
    End-to-end document processing pipeline orchestration.
    Matches the Case Study requirements for extraction, validation, and routing[span_0](start_span)[span_0](end_span).
    """

    def __init__(
        self,
        customer_master_path: str | Path = "data/master/fictional_customer_master.xlsx",
        item_master_path: str | Path = "data/master/fictional_item_master.xlsx",
    ) -> None:
        # 1. Load Master Data tables into memory
        self.df_customer = load_customer_master(customer_master_path)
        self.df_item = load_item_master(item_master_path)

        # 2. Initialize processing components
        self.extractor = DocumentExtractor()
        self.matcher = MasterDataMatcher(
            df_customer=self.df_customer,
            df_item=self.df_item,
        )
        self.validator = DocumentValidator()

    def process(self, filepath: str | Path) -> ProcessingResult:
        """Runs the complete processing lifecycle for a single document."""
        
        # Step 1: Ingestion
        doc_payload = read_input_document(filepath)
        
        # Step 2: Extraction
        # Adapt for extraction.py which expects a string input[span_1](start_span)[span_1](end_span)
        content = doc_payload.get("content")
        if isinstance(content, pd.DataFrame):
            document_text = content.to_string()
        else:
            document_text = str(content) if content is not None else ""
            
        raw_result = self.extractor.extract(document_text)

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
                raw_desc=item.raw_description
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
        #Clean LLM halutinations
        raw_result.review_reasons = []
        raw_result.needs_review = False

        # First, validate line item math and totals using DocumentValidator[span_2](start_span)[span_2](end_span)
        validated_result = self.validator.validate(raw_result)
        
        # Then, re-validate through Pydantic to trigger @model_validator(mode="after")
        # This ensures the business logic in schemas.py updates the needs_review flag 
        # based on the final confidence score and the presence of customer_id[span_3](start_span)[span_3](end_span).
        final_result = ProcessingResult.model_validate(validated_result.model_dump())

        return final_result