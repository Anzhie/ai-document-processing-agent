import argparse
import re
from pathlib import Path
from typing import Any

import pdfplumber
from rapidfuzz import fuzz, process

from src.extractors.base import BaseExtractor
from src.extractors.utils import COLUMN_ALIASES, is_valid_line_item, is_footer_row, is_my_company, safe_float, extract_document_number, extract_total, extract_shipping, extract_tax
from src.schemas import ExtractedItem, ProcessingResult


class PDFExtractor(BaseExtractor):
    """
    Deterministic extractor for digital (native) PDF documents.
    Extracts header metadata via Regex and table line items via pdfplumber layout parsing.
    """

    def _map_columns(self, header_row: list[str]) -> dict[int, str]:
        """Maps table column indices to target schema fields via fuzzy string matching."""
        mapped = {}
        for idx, col in enumerate(header_row):
            clean_col = str(col).lower().strip()
            for schema_field, aliases in COLUMN_ALIASES.items():
                if schema_field in mapped.values():
                    continue
                match = process.extractOne(clean_col, aliases, scorer=fuzz.partial_ratio)
                if match and match[1] >= 80:
                    mapped[idx] = schema_field
                    break
        return mapped

    def _extract_header_info(self, text: str) -> tuple[str | None, str | None, float | None, float | None, float | None]:
        """Extracts document number, customer name, tax, shipping, and total amount using regular expressions."""
        doc_number = None
        customer_raw = None
        tax_amount = None
        shipping_amount = None
        total_amount = None

        # Extract PO / Invoice / Document Number
        doc_number = extract_document_number(text)

        # Extract Customer / Supplier (skip our own company)
        pattern_counterparty = r"(?:CUSTOMER|SUPPLIER|VENDOR|CLIENT|BUYER|ISSUED\s*BY|SOLD\s*BY|FROM|BILL\s*TO|SHIP\s*TO)[\s:]+([^\n,;]+)"
        for match in re.finditer(pattern_counterparty, text, re.IGNORECASE):
            candidate = match.group(1).strip()
            # Remove leading/trailing quotes if any
            candidate = re.sub(r"^['\"]|['\"]$", "", candidate).strip()
            if candidate and not is_my_company(candidate):
                customer_raw = candidate
                break

        # Fallback for letterhead (e.g., vendor name at the top of the document without a prefix)
        if not customer_raw:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            for line in lines[:5]:
                clean_line = line.lower()
                if clean_line in ["invoice", "purchase order", "po", "order"]:
                    continue
                if not is_my_company(line) and len(line) > 3:
                    customer_raw = line
                    break

        # Extract Tax / VAT / HST
        tax_amount = extract_tax(text)

        # Extract Shipping / Freight / Handling
        shipping_amount = extract_shipping(text)

        # Extract Total Amount (use \b to prevent matching 'SUBTOTAL')
        total_amount = extract_total(text)

        return doc_number, customer_raw, tax_amount, shipping_amount, total_amount

    def _parse_text_lines(self, full_text: str) -> list[ExtractedItem]:
        """Fallback line parser for PDF documents without explicit table grid structures."""
        items = []
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        in_table = False

        for line in lines:
            lower_line = line.lower()

            # Detect table header row
            if ("item" in lower_line or "description" in lower_line) and "qty" in lower_line:
                in_table = True
                continue

            if in_table:
                # Detect end of line item section
                if is_footer_row(lower_line) or "subtotal" in lower_line or "total" in lower_line:
                    break

                desc, qty, price, total = None, 0.0, 0.0, 0.0

                # Layout 1: Pipe-separated values (e.g., purchase_order_05641.pdf)
                if "|" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 4:
                        desc = parts[0]
                        qty = safe_float(parts[1])
                        price = safe_float(parts[2])
                        total =  safe_float(parts[3])

                # Layout 2: Space-separated values (e.g., invoice_supplier_D45391_2.pdf)
                else:
                    # Regex pattern matching item description followed by 3 numeric columns
                    match = re.search(r"^(.*?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$", line)
                    if match:
                        desc = match.group(1).strip()
                        qty = safe_float(match.group(2))
                        price = safe_float(match.group(3))
                        total = safe_float(match.group(4))

                if desc and is_valid_line_item(desc, qty, price, total):
                    items.append(
                        ExtractedItem(
                            raw_description=desc,
                            quantity=qty,
                            unit_price=price,
                            total_price=total,
                        )
                    )

        return items

    def extract(self, content: Any) -> ProcessingResult | None:
        """
        Parses a PDF file into a structured ProcessingResult.
        Accepts a file path string or Path object.
        Returns None if extraction fails or no structured tables/data are found.
        """
        path = Path(content) if isinstance(content, (str, Path)) else None
        if not path or not path.exists() or path.suffix.lower() != ".pdf":
            return None

        try:
            full_text = ""
            extracted_items: list[ExtractedItem] = []

            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"

                    # Extract native tables from current page
                    tables = page.extract_tables()
                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        # Header row candidate
                        header_row = [str(cell or "").strip() for cell in table[0]]
                        col_map = self._map_columns(header_row)

                        # Parse data rows
                        for row in table[1:]:
                            if not any(row):
                                continue

                            row_dict = {}
                            for idx, val in enumerate(row):
                                if idx in col_map and val is not None:
                                    row_dict[col_map[idx]] = str(val).strip()

                            if not row_dict:
                                continue

                            desc = row_dict.get("raw_description", "")
                            
                            # Rule 4: Stop table processing if footer totals ("Total", "VAT") are reached
                            if is_footer_row(desc):
                                break

                            item_no = row_dict.get("item_number")
                            qty = safe_float(row_dict.get("quantity"))
                            price = safe_float(row_dict.get("unit_price"))
                            total = safe_float(row_dict.get("total_line_amount"))

                            # Rules 1-3: Validate the line item
                            if not is_valid_line_item(desc, qty, price, total):
                                continue

                            extracted_items.append(
                                ExtractedItem(
                                    item_number=item_no if item_no else None,
                                    raw_description=desc,
                                    quantity=qty,
                                    unit_price=price,
                                    total_price=total,
                                )
                            )

            # Extract header metadata from combined text
            doc_number, customer_raw, tax_amount, shipping_amount, total_amount = self._extract_header_info(full_text)

            # Fallback to plain text parsing if pdfplumber native table extraction fails
            if not extracted_items:
                extracted_items = self._parse_text_lines(full_text)

            # Trigger LLM Fallback only if no line items were extracted
            if not extracted_items:
                return None

            return ProcessingResult(
                document_number=doc_number,
                customer_raw=customer_raw or "UNKNOWN",
                items=extracted_items,
                tax_amount=tax_amount,
                shipping_amount=shipping_amount,
                total_amount=total_amount,
                needs_review=False,
                review_reasons=[],
            )

        except Exception:
            # Fallback to LLM if pdfplumber fails
            return None
