from enum import Enum

from pydantic import BaseModel, Field, model_validator


class DocumentType(str, Enum):
    """Supported document types for extraction."""
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    DELIVERY_NOTE = "delivery_note"
    UNKNOWN = "unknown"


class ExtractedItem(BaseModel):
    """Schema representing a single line item (book) extracted from a document."""
    item_number: str | None = Field(
        default=None, 
        description="Matched item master ID (e.g. IM-10001)"
    )
    isbn: str | None = Field(
        default=None,
        description="Extracted ISBN or EAN bar code if present on invoice/order"
    )
    raw_description: str | None = Field(
        default=None, 
        description="Original line text from the document (e.g. 'J.K. Rowling / Harry Potter')"
    )
    title: str | None = Field(
        default=None,
        description="Extracted or parsed book title"
    )
    author: str | None = Field(
        default=None,
        description="Extracted or parsed author name"
    )
    matched_description: str | None = Field(
        default=None, 
        description="Canonical book title and author from Master Data"
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
        description="Raw customer/supplier name extracted from the document"
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
    tax_amount: float | None = Field(
        default=None,
        description="Extracted tax, VAT, or HST amount"
    )
    shipping_amount: float | None = Field(
        default=None,
        description="Extracted shipping, freight, or handling fee"
    )
    total_amount: float | None = Field(
        default=None,
        description="Extracted or calculated total document amount"
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
            reasons.append("Customer/Supplier could not be matched to Master Data.")
        if not self.items:
            reasons.append("No line items extracted.")

        # 2. Verify item-level completeness and mathematical consistency
        for idx, item in enumerate(self.items):
            if item.quantity is None or item.quantity <= 0:
                reasons.append(f"Item {idx}: Missing or invalid quantity.")
            
            # Mathematical consistency check (Qty * Unit Price vs Total Price)
            if item.quantity is not None and item.unit_price is not None and item.total_price is not None:
                expected_total = round(item.quantity * item.unit_price, 2)
                actual_total = round(item.total_price, 2)
                if abs(expected_total - actual_total) > 0.05:
                    reasons.append(
                        f"Item {idx} ('{item.title or item.raw_description}'): Math inconsistency "
                        f"({item.quantity} * {item.unit_price} = {expected_total}, but document has {actual_total})."
                    )
            
            # Confidence threshold per line item
            if item.match_confidence < 0.80:
                item_label = item.title or item.raw_description or f"Index {idx}"
                reasons.append(f"Item '{item_label}': Low match confidence ({item.match_confidence:.2f}).")

        # 3. Check overall document confidence threshold
        if self.confidence < 0.80:
            reasons.append(f"Low overall document confidence ({self.confidence:.2f}).")

        # 4. Route to manual review if any rule violations were captured
        if reasons:
            self.needs_review = True
            self.review_reasons = list(dict.fromkeys(reasons))  # Remove duplicates
        else:
            self.needs_review = False

        return self