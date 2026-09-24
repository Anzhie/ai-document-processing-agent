import os
from typing import cast

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import SecretStr

from src.schemas import ProcessingResult

load_dotenv()

EXTRACTION_SYSTEM_PROMPT = """
You are an expert AI Document Processing Agent.
Your task is to extract structured data from raw business document text (Purchase Orders, Invoices, Delivery Notes).

Rules:
1. Extract document level details: document_number, document_type, customer_name, and total_amount.
2. Extract all line items with: raw_item_id (part number/SKU if present), raw_description, quantity, unit_price, and total_line_amount.
3. Preserve numbers accurately without rounding.
4. If a field is missing or uncertain, leave it as null/None.
"""


class DocumentExtractor:
    """
    Handles LLM-based structured extraction from raw document text
    using LangChain and Pydantic schemas via Groq Free API.
    """

    def __init__(
        self,
        model_name: str = "qwen/qwen3.8-27b",
        temperature: float = 0.0,
        api_key: str | None = None,
    ) -> None:
        raw_key = api_key or os.getenv("GROQ_API_KEY")
        secret_key = SecretStr(raw_key) if raw_key else None

        # Initialize LLM with structured output binding using Groq
        self.llm = ChatGroq(
            model=model_name,
            temperature=temperature,
            api_key=secret_key,
        ).with_structured_output(ProcessingResult)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EXTRACTION_SYSTEM_PROMPT),
                ("user", "Document Text:\n{document_text}"),
            ]
        )

        self.chain = self.prompt | self.llm

    def extract(self, document_text: str) -> ProcessingResult:
        """
        Processes raw text and returns a validated ProcessingResult object.
        """
        if not document_text or not document_text.strip():
            return ProcessingResult(
                document_number="UNKNOWN",
                items=[],
                needs_review=True,
                review_reasons=["Empty document text provided"],
            )

        res = self.chain.invoke({"document_text": document_text})
        return cast(ProcessingResult, res)


if __name__ == "__main__":
    # Quick sanity check with mock raw text
    mock_po_text = """
    PURCHASE ORDER: PO-2026-8891
    Customer: ClearLine Hygiene GmbH
    
    Items:
    1. SKU: SRC-99 | Heavy-duty cleaner 10l | Qty: 2 | Price: 45.00 EUR | Total: 90.00 EUR
    2. Microfiber Cloths 10 pack | Qty: 5 | Price: 12.00 EUR | Total: 60.00 EUR
    
    Grand Total: 150.00 EUR
    """

    extractor = DocumentExtractor()
    try:
        result = extractor.extract(mock_po_text)
        print("Extraction Successful:")
        print(result.model_dump_json(indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"Extraction failed (check API key): {e}")