from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.pipeline import DocumentPipeline
from src.schemas import DocumentType, ExtractedItem, ProcessingResult


@patch("src.pipeline.load_item_master")
@patch("src.pipeline.load_customer_master")
@patch("src.pipeline.DocumentExtractor.extract")
@patch("src.pipeline.read_input_document")
def test_pipeline_process_success(
    mock_read: MagicMock,
    mock_extract: MagicMock,
    mock_load_cust: MagicMock,
    mock_load_item: MagicMock,
) -> None:
    """Test the successful end-to-end execution of the document pipeline."""
    
    # Mock file ingestion returning dummy text content
    mock_read.return_value = {"content": "dummy text", "file_type": "pdf"}

    # Mock the LLM extraction result to avoid actual API calls during tests
    mock_extract.return_value = ProcessingResult(
        document_number="PO-TEST-123",
        document_type=DocumentType.PURCHASE_ORDER,
        customer_raw="ClearLine Hygiene GmbH",
        items=[
            ExtractedItem(
                item_number="IM-100001",
                raw_description="Heavy-duty cleaner 10l",
                quantity=2.0,
                unit_price=45.0,
                total_price=90.0,
            )
        ],
        total_amount=90.0,
        needs_review=False,
    )

    # Mock Master Data DataFrames to simulate a successful match
    mock_load_cust.return_value = pd.DataFrame(
        [{"Customer master ID": "CM-10001", "Legal name": "ClearLine Hygiene GmbH"}]
    )
    mock_load_item.return_value = pd.DataFrame(
        [{"Item master ID": "IM-100001", "Description": "Heavy-duty cleaner, 10 litres"}]
    )

    # Initialize the pipeline (initialization loads the mocked master data)
    pipeline = DocumentPipeline(
        customer_master_path="dummy_cust.xlsx", item_master_path="dummy_item.xlsx"
    )

    # Execute the processing lifecycle
    result = pipeline.process(Path("dummy_file.pdf"))

    # Assert correct routing and matching integration
    assert result.document_number == "PO-TEST-123"
    assert result.customer_matched == "ClearLine Hygiene GmbH"
    assert result.customer_id == "CM-10001"
    
    # Assert item matching modified the initial LLM output correctly
    assert result.items[0].match_confidence > 0.0
    assert result.items[0].matched_description == "Heavy-duty cleaner, 10 litres"