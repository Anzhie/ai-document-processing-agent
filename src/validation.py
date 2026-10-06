import logging

from src.schemas import ProcessingResult

logger = logging.getLogger(__name__)


class DocumentValidator:
    """
    Validates business rules and arithmetic consistency for extracted document data.
    Takes into account taxes, VAT, shipping, and freight fees.
    """

    def __init__(self, tolerance: float = 0.01) -> None:
        self.tolerance = tolerance

    def validate(self, result: ProcessingResult) -> ProcessingResult:
        """
        Validates line item arithmetic and document total consistency including tax and shipping.
        Updates review_reasons and needs_review status accordingly.
        """
        reasons: list[str] = list(result.review_reasons)
        computed_items_total = 0.0

        # 1. Validate line item arithmetic
        for idx, item in enumerate(result.items, start=1):
            if item.quantity is not None and item.unit_price is not None:
                expected_line_total = round(item.quantity * item.unit_price, 2)

                if item.total_price is not None:
                    if abs(expected_line_total - item.total_price) > self.tolerance:
                        reasons.append(
                            f"Line item {idx} ({item.raw_description or 'Unknown'}): "
                            f"total mismatch. Expected {expected_line_total:.2f}, got {item.total_price:.2f}"
                        )
                    computed_items_total += item.total_price
                else:
                    item.total_price = expected_line_total
                    computed_items_total += item.total_price
            elif item.total_price is not None:
                computed_items_total += item.total_price

        # 2. Account for tax and shipping fees in total calculation
        tax = result.tax_amount or 0.0
        shipping = result.shipping_amount or 0.0
        expected_grand_total = round(computed_items_total + tax + shipping, 2)

        # 3. Validate header total_amount against sum of line items + tax + shipping
        if result.total_amount is not None and result.items:
            if abs(expected_grand_total - result.total_amount) > self.tolerance:
                reasons.append(
                    f"Grand total mismatch: document header is {result.total_amount:.2f}, "
                    f"sum of line items ({computed_items_total:.2f}) + tax ({tax:.2f}) + "
                    f"shipping ({shipping:.2f}) is {expected_grand_total:.2f}"
                )
        elif result.total_amount is None and result.items:
            result.total_amount = expected_grand_total

        # 4. Update status and deduplicate reasons
        if reasons:
            result.needs_review = True
            result.review_reasons = sorted(set(reasons))

        return result