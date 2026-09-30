import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz, process

from src.extractors.base import BaseExtractor
from src.extractors.extraction_utils import is_valid_line_item, is_footer_row
from src.schemas import ExtractedItem, ProcessingResult


class SpreadsheetExtractor(BaseExtractor):
    """
    Deterministic extractor for tabular data (XLS, XLSX, CSV).
    Extracts customer metadata from cell headers and maps DataFrame columns 
    to ExtractedItem attributes using fuzzy string matching.
    """

    # Company patterns to identify our own company
    MY_COMPANY_PATTERNS = [r"small book store.*"]

    # Synonyms for standard PO/Invoice table columns
    COLUMN_ALIASES = {
        "item_number": ["sku", "item id", "part number", "item_number", "article", "code"],
        "raw_description": ["description", "item description", "name", "product"],
        "quantity": ["qty", "quantity", "count", "amount"],
        "unit_price": ["unit price", "price", "unit_price", "rate"],
        "total_line_amount": ["total", "line total", "total_amount", "amount eur"],
    }

    def _extract_header_metadata(self, df: pd.DataFrame) -> tuple[str | None, str | None, float | None, float | None, float | None]:
        """
        Scans DataFrame headers and non-tabular cells to extract document number, customer, tax, shipping, and total.
        """
        doc_number = None
        customer_raw = None
        tax_amount = None
        shipping_amount = None
        total_amount = None

        full_cell_text = []
        for col in df.columns:
            full_cell_text.append(str(col))

        for _, row in df.iterrows():
            for val in row.values:
                if pd.notna(val):
                    full_cell_text.append(str(val))

        combined_text = "\n".join(full_cell_text)

        # Extract Document Number
        doc_match = re.search(r"(?:INVOICE|PO|ORDER|INVOICE\s*NUMBER|PO\s*NUMBER)[\s#:]*([A-Z0-9-]+)", combined_text, re.IGNORECASE)
        if doc_match:
            doc_number = doc_match.group(1).strip()

        # Extract Customer / Supplier (select first external counterparty)
        pattern_counterparty = r"(?:CUSTOMER|SUPPLIER|VENDOR|CLIENT|BUYER|ISSUED\s*BY|SOLD\s*BY|FROM|BILL\s*TO|SHIP\s*TO)[\s:]+([^\n,;]+)"
        for match in re.finditer(pattern_counterparty, combined_text, re.IGNORECASE):
            candidate = match.group(1).strip()
            # Pick the first match that does not match our company name
            if candidate and not self._is_my_company(candidate):
                customer_raw = candidate
                break

        # Extract Tax / VAT
        tax_match = re.search(r"(?:TAX|VAT|HST)[\s\w()]*[:\s]+[$€£]?\s*([\d.,]+)", combined_text, re.IGNORECASE)
        if tax_match:
            try:
                tax_amount = float(re.sub(r"[^\d.-]", "", tax_match.group(1).replace(",", ".")))
            except ValueError:
                pass

        # Extract Shipping / Freight
        ship_match = re.search(r"(?:SHIPPING|FREIGHT|HANDLING)[\s\w()]*[:\s]+[$€£]?\s*([\d.,]+)", combined_text, re.IGNORECASE)
        if ship_match:
            try:
                shipping_amount = float(re.sub(r"[^\d.-]", "", ship_match.group(1).replace(",", ".")))
            except ValueError:
                pass

        # Extract Total
        tot_match = re.search(r"(?:TOTAL\s*DUE|ORDER\s*TOTAL|TOTAL\s*AMOUNT)[\s:]+[$€£]?\s*([\d.,]+)", combined_text, re.IGNORECASE)
        if tot_match:
            try:
                total_amount = float(re.sub(r"[^\d.-]", "", tot_match.group(1).replace(",", ".")))
            except ValueError:
                pass

        return doc_number, customer_raw, tax_amount, shipping_amount, total_amount

    def _map_columns(self, df_cols: list[str]) -> dict[str, str]:
        """Maps DataFrame header names to target schema fields via fuzzy matching."""
        mapped = {}
        for col in df_cols:
            clean_col = str(col).lower().strip()
            for schema_field, aliases in self.COLUMN_ALIASES.items():
                if schema_field in mapped.values():
                    continue
                match = process.extractOne(clean_col, aliases, scorer=fuzz.partial_ratio)
                if match and match[1] >= 80:
                    mapped[col] = schema_field
                    break
        return mapped

    def _is_my_company(self, text: str) -> bool:
        """Check if the text matches our company name."""
        if not text:
            return False
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.MY_COMPANY_PATTERNS)

    def extract(self, content: Any) -> ProcessingResult | None:
        """Parses pd.DataFrame directly into a structured ProcessingResult."""
        if not isinstance(content, pd.DataFrame) or content.empty:
            return None

        try:
            df = content.dropna(how="all").copy()

            # Attempt to extract metadata from non-tabular cells
            doc_number, customer_raw, tax_amount, shipping_amount, total_amount = self._extract_header_metadata(df)

            col_map = self._map_columns(list(df.columns))
            df_renamed = df.rename(columns=col_map)

            items: list[ExtractedItem] = []
            for _, row in df_renamed.iterrows():
                desc = str(row.get("raw_description", "")).strip()

                # Rule 4: Stop parsing when "Grand Total" or similar is reached
                if is_footer_row(desc):
                    break

                item_no = str(row.get("item_number", "")).strip()
                qty = pd.to_numeric(row.get("quantity"), errors="coerce")
                unit_price = pd.to_numeric(row.get("unit_price"), errors="coerce")
                line_total = pd.to_numeric(row.get("total_line_amount"), errors="coerce")

                float_qty = float(qty) if pd.notna(qty) else 0.0
                float_price = float(unit_price) if pd.notna(unit_price) else 0.0
                float_total = float(line_total) if pd.notna(line_total) else 0.0

                # Rules 1-3: General validation
                if not is_valid_line_item(desc, float_qty, float_price, float_total):
                    continue

                items.append(
                    ExtractedItem(
                        item_number=item_no if item_no and item_no != "nan" else None,
                        raw_description=desc if desc and desc != "nan" else "",
                        quantity=float_qty,
                        unit_price=float_price,
                        total_price=float_total,
                    )
                )

            # If no items were mapped, return None to trigger LLM Fallback
            if not items:
                return None

            return ProcessingResult(
                document_number=doc_number,
                customer_raw=customer_raw or "UNKNOWN",
                items=items,
                tax_amount=tax_amount,
                shipping_amount=shipping_amount,
                total_amount=total_amount,
                needs_review=False,
                review_reasons=[],
            )
        except Exception:
            # Fallback to LLM if structured dataframe processing fails
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run deterministic extraction on a CSV or Excel file."
    )
    parser.add_argument(
        "filepath",
        type=str,
        help="Path to the input spreadsheet file (.xlsx, .xls, .csv)",
    )
    args = parser.parse_args()

    input_path = Path(args.filepath)

    if not input_path.exists():
        print(f"Error: File not found at '{input_path}'")
        raise SystemExit(1)

    ext = input_path.suffix.lower()
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(input_path)
        elif ext == ".csv":
            df = pd.read_csv(input_path)
        else:
            print(f"Error: Unsupported file format '{ext}'")
            raise SystemExit(1)

        extractor = SpreadsheetExtractor()
        result = extractor.extract(df)

        if result:
            print("Extraction Successful:")
            print(result.model_dump_json(indent=2))
        else:
            print("Extraction failed: Unable to parse DataFrame structure.")

    except Exception as e:
        print(f"Error processing file: {e}")