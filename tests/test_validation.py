from src.schemas import ExtractedItem, ProcessingResult
from src.validation import DocumentValidator


def test_validation_valid_document() -> None:
    """Tests that a correctly calculated document passes validation without new flags."""
    validator = DocumentValidator()
    result = ProcessingResult(
        document_number="PO-100",
        customer_matched="Acme Corp",
        customer_id="CM-10001",  # Added customer_id
        confidence=1.0,
        items=[
            ExtractedItem(
                raw_description="Item A",
                quantity=2.0,
                unit_price=50.0,
                total_price=100.0,
                match_confidence=1.0,
            )
        ],
        total_amount=100.0,
        needs_review=False,
    )

    validated = validator.validate(result)
    assert validated.needs_review is False


def test_validation_line_item_mismatch() -> None:
    """Tests detection of arithmetic error in line item total."""
    validator = DocumentValidator()
    result = ProcessingResult(
        document_number="PO-101",
        items=[
            ExtractedItem(
                raw_description="Item B",
                quantity=3.0,
                unit_price=10.0,
                total_price=50.0,  # Incorrect: 3 * 10 != 50
            )
        ],
        total_amount=50.0,
        needs_review=False,
    )

    validated = validator.validate(result)

    assert validated.needs_review is True
    assert any("total mismatch" in reason for reason in validated.review_reasons)


def test_validation_grand_total_mismatch() -> None:
    """Tests detection of discrepancy between sum of line items and header grand total."""
    validator = DocumentValidator()
    result = ProcessingResult(
        document_number="PO-102",
        items=[
            ExtractedItem(
                raw_description="Item C",
                quantity=1.0,
                unit_price=20.0,
                total_price=20.0,
            )
        ],
        total_amount=100.0,  # Discrepancy: 20 != 100
        needs_review=False,
    )

    validated = validator.validate(result)

    assert validated.needs_review is True
    assert any("Grand total mismatch" in reason for reason in validated.review_reasons)


def test_validation_auto_fill_missing_totals() -> None:
    """Tests automatic computation of missing line and header totals."""
    validator = DocumentValidator()
    result = ProcessingResult(
        document_number="PO-103",
        customer_matched="Acme Corp",
        customer_id="CM-10001",  # Added customer_id
        confidence=1.0,
        items=[
            ExtractedItem(
                raw_description="Item D",
                quantity=4.0,
                unit_price=25.0,
                total_price=None,
                match_confidence=1.0, 
            )
        ],
        total_amount=None,
        needs_review=False,
    )

    validated = validator.validate(result)

    assert validated.items[0].total_price == 100.0
    assert validated.total_amount == 100.0
    assert validated.needs_review is False