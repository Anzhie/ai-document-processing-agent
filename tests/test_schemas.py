import pytest
from src.schemas import ExtractedItem, ProcessingResult, DocumentType


def test_processing_result_auto_approval():
    """Verify that valid document data passes without triggering manual review."""
    item = ExtractedItem(
        item_number="IM-100001",
        raw_description="Heavy-duty cleaner, 10 litres",
        matched_description="Heavy-duty cleaner, 10 litres",
        quantity=2.0,
        unit_price=56.25,
        total_price=112.50,
        match_confidence=1.0
    )
    
    result = ProcessingResult(
        document_number="PO-2026-001",
        document_type=DocumentType.PURCHASE_ORDER,
        customer_raw="ClearLine Hygiene GmbH",
        customer_matched="ClearLine Hygiene GmbH",
        customer_id="CM-10001",
        items=[item],
        confidence=0.95
    )
    
    assert result.needs_review is False
    assert len(result.review_reasons) == 0


def test_processing_result_missing_customer_triggers_review():
    """Verify that missing customer_id automatically sets needs_review to True."""
    result = ProcessingResult(
        document_number="PO-2026-002",
        customer_id=None,  # Missing customer ID
        confidence=0.90
    )
    
    assert result.needs_review is True
    assert any("Customer could not be matched" in reason for reason in result.review_reasons)


def test_processing_result_math_mismatch_triggers_review():
    """Verify that a discrepancy between Qty * Unit Price and Total Price forces manual review."""
    item = ExtractedItem(
        item_number="IM-100002",
        quantity=3.0,
        unit_price=10.00,
        total_price=50.00  # Incorrect total amount (3 * 10 != 50)
    )
    
    result = ProcessingResult(
        document_number="PO-2026-003",
        customer_id="CM-10001",
        items=[item],
        confidence=0.95
    )
    
    assert result.needs_review is True
    assert any("Math inconsistency" in reason for reason in result.review_reasons)


def test_processing_result_low_confidence_triggers_review():
    """Verify that low confidence scores route document to manual review."""
    result = ProcessingResult(
        document_number="PO-2026-004",
        customer_id="CM-10001",
        items=[ExtractedItem(quantity=1.0, unit_price=10.0, total_price=10.0)],
        confidence=0.65  # Below 0.8 threshold
    )
    
    assert result.needs_review is True
    assert any("Low overall document confidence" in reason for reason in result.review_reasons)
