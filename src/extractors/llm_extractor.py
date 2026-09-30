import os
from typing import Any, cast

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import SecretStr

from src.extractors.base import BaseExtractor
from src.schemas import ProcessingResult

load_dotenv()

EXTRACTION_SYSTEM_PROMPT = """
You are an expert AI Document Processing Agent.
Your task is to extract structured data from raw business document text (Purchase Orders, Invoices, Delivery Notes).

Rules:
1. Extract document level details:
   - document_number: Document identifier (e.g., INV-2026-001, PO-2026-701, CN-9041, CP-2026-55, PO-SE-8812, PO-JP-3304, PO-IT-9921).
   - document_type: "invoice", "purchase_order", or "delivery_note".
   - customer_raw: Raw legal entity name of the supplier/vendor or customer/buyer mentioned on the document (e.g., "Penguin Random House", "Simon & Schuster", "HarperCollins Publishers", "Hachette Book Group").
   - tax_amount: Extracted tax, VAT, or HST amount if explicitly specified on the document (e.g., VAT, Tax 8%, HST 13%). Leave null if not present.
   - shipping_amount: Extracted shipping, freight, or handling fee if present. Leave null if not present.
   - total_amount: Final Grand Total / Total Due / Order Total specified in the header/footer.

2. Extract all line items into the items list:
   - item_number: Part number, SKU, or ISBN if present.
   - raw_description: Original line item text (e.g., "Harper Lee. To Kill a Mockingbird").
   - title: Parsed book title.
   - author: Parsed author name.
   - quantity: Item quantity as float.
   - unit_price: Price per unit as float.
   - total_price: Line item total amount.

3. Preserve numbers accurately without rounding.
4. If a field is missing or uncertain, leave it as null/None.
5. Always set needs_review to false and leave review_reasons as an empty list. Validation will be handled externally.
"""


class LLMExtractor(BaseExtractor):
    """
    Handles LLM-based fallback extraction from raw document text
    using LangChain and Pydantic schemas via Groq API.
    """

    def __init__(
        self,
        model_name: str = "qwen/qwen3.8-27b",
        temperature: float = 0.0,
        api_key: str | None = None,
    ) -> None:
        raw_key = api_key or os.getenv("GROQ_API_KEY")
        secret_key = SecretStr(raw_key) if raw_key else None

        self.llm = ChatGroq(
            model=model_name,
            temperature=temperature,
            api_key=secret_key,
            max_tokens=1024,
            max_retries=3,
        ).with_structured_output(ProcessingResult)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EXTRACTION_SYSTEM_PROMPT),
                ("user", "Document Text:\n{document_text}"),
            ]
        )

        self.chain = self.prompt | self.llm

    def extract(self, content: Any) -> ProcessingResult:
        """
        Processes raw text content and returns a validated ProcessingResult object.
        Accepts string or any object that can be cast to string.
        """
        document_text = str(content) if content is not None else ""

        if not document_text or not document_text.strip():
            return ProcessingResult(
                customer_raw="UNKNOWN",
                items=[],
                needs_review=True,
                review_reasons=["Empty document text provided"],
            )

        res = self.chain.invoke({"document_text": document_text})
        return cast(ProcessingResult, res)