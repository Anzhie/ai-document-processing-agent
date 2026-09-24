from enum import Enum

from pydantic import BaseModel, Field, model_validator


class DocumentType(str, Enum):
    """Supported document types for extraction."""
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    DELIVERY_NOTE = "delivery_note"
    UNKNOWN = "unknown"


class ExtractedItem(BaseModel):
    """Schema representing a single line item extracted from a document."""
    item_number: str | None = Field(
        default=None, 
        description="Matched item master ID or manufacturer item number"
    )
    raw_description: str | None = Field(
        default=None, 
        description="Original item description text from the input document"
    )
    matched_description: str | None = Field(
        default=None, 
        description="Canonical item description from Master Data"
    )
    quantity: float | None = Field(
        default=None, 
        description="Extracted item quantity"
        )
    unit_price: float | None = Field(
        default=None, 
        description="Extracted price per unit"
    )
    total_price: float | None = Field(
        default=None, 
        description="Extracted or computed line total amount"
    )
    match_confidence: float = Field(
        default=0.0, 
        description="Master Data matching confidence score (0.0 to 1.0)"
    )


class ProcessingResult(BaseModel):
    """Final output schema for document extraction and routing decision."""
    document_number: str | None = Field(
        default=None, 
        description="Extracted Purchase Order / Invoice document identifier"
    )
    document_type: DocumentType = Field(
        default=DocumentType.UNKNOWN, 
        description="Type of processed document"
    )
    customer_raw: str | None = Field(
        default=None, 
        description="Raw customer name extracted from the document"
    )
    customer_matched: str | None = Field(
        default=None, 
        description="Matched customer legal name from Master Data"
    )
    customer_id: str | None = Field(
        default=None, 
        description="Customer Master ID (e.g., CM-10001)"
    )
    items: list[ExtractedItem] = Field(
        default_factory=list, 
        description="List of extracted and matched line items"
    )
    confidence: float = Field(
        default=0.0, 
        description="Overall aggregated document confidence score (0.0 to 1.0)"
    )
    needs_review: bool = Field(
        default=True, 
        description="Flag indicating if manual human review is required"
    )
    review_reasons: list[str] = Field(
        default_factory=list, 
        description="List of issues or reasons forcing manual review"
    )

    @model_validator(mode="after")
    def enforce_business_rules(self) -> "ProcessingResult":
        """
        Evaluates business rules against extracted data to determine 
        if the document qualifies for automatic processing or requires human review.
        """
        reasons = list(self.review_reasons)

        # 1. Verify mandatory document-level fields
        if not self.document_number:
            reasons.append("Missing mandatory document number.")
        if not self.customer_id:
            reasons.append("Customer could not be matched to Master Data.")
        if not self.items:
            reasons.append("No line items extracted.")

        # 2. Verify item-level completeness and mathematical consistency
        for idx, item in enumerate(self.items):
            if item.quantity is None or item.quantity <= 0:
                reasons.append(f"Item {idx}: Missing or invalid quantity.")
            
            # Check for obvious inconsistencies (Qty * Price vs Total)
            if item.quantity and item.unit_price and item.total_price:
                expected_total = item.quantity * item.unit_price
                if abs(expected_total - item.total_price) > 0.05: # Tolerance for rounding
                    reasons.append(f"Item {idx}: Math inconsistency (Qty * Price != Total).")

        # 3. Check overall confidence threshold
        if self.confidence < 0.8:
            reasons.append(f"Low overall document confidence ({self.confidence}).")

        # 4. Route to manual review if any rules are violated
        if reasons:
            self.needs_review = True
            self.review_reasons = reasons
        else:
            self.needs_review = False # All fields valid, safe for straight-through processing

        return self