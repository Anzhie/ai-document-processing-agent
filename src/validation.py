import logging

from src.schemas import ProcessingResult

logger = logging.getLogger(__name__)


class DocumentValidator:
    """
    Validates business rules and arithmetic consistency for extracted document data.
    """

    def __init__(self, tolerance: float = 0.01) -> None:
        self.tolerance = tolerance

    def validate(self, result: ProcessingResult) -> ProcessingResult:
        """
        Validates line item arithmetic and document total consistency.
        Updates review_reasons and needs_review status accordingly.
        """
        reasons: list[str] = list(result.review_reasons)
        computed_total = 0.0

        # 1. Validate line item arithmetic
        for idx, item in enumerate(result.items, start=1):
            if item.quantity is not None and item.unit_price is not None:
                expected_line_total = item.quantity * item.unit_price

                if item.total_price is not None:
                    if abs(expected_line_total - item.total_price) > self.tolerance:
                        reasons.append(
                            f"Line item {idx} ({item.raw_description or 'Unknown'}): "
                            f"total mismatch. Expected {expected_line_total:.2f}, got {item.total_price:.2f}"
                        )
                    computed_total += item.total_price
                else:
                    item.total_price = round(expected_line_total, 2)
                    computed_total += item.total_price
            elif item.total_price is not None:
                computed_total += item.total_price

        # 2. Validate header total_amount against sum of line items
        if result.total_amount is not None and result.items:
            if abs(computed_total - result.total_amount) > self.tolerance:
                reasons.append(
                    f"Grand total mismatch: document header is {result.total_amount:.2f}, "
                    f"sum of line items is {computed_total:.2f}"
                )
        elif result.total_amount is None and result.items:
            result.total_amount = round(computed_total, 2)

        # 3. Update status and deduplicate reasons
        if reasons:
            result.needs_review = True
            result.review_reasons = sorted(set(reasons))

        return result


if __name__ == "__main__":
    from src.schemas import ExtractedItem

    # Create a sample result with an intentional total mismatch
    sample_result = ProcessingResult(
        document_number="PO-TEST-999",
        items=[
            ExtractedItem(
                raw_description="Test Item A",
                quantity=3.0,
                unit_price=10.0,
                total_price=50.0,  # Mismatch: 3 * 10 = 30
            )
        ],
        total_amount=50.0,
        needs_review=False,
    )

    validator = DocumentValidator()
    validated_result = validator.validate(sample_result)

    print("Validation Execution Result:")
    print(validated_result.model_dump_json(indent=2))