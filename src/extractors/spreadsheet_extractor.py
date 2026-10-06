import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz, process

from src.extractors.base import BaseExtractor
from src.extractors.utils import COLUMN_ALIASES, is_valid_line_item, is_footer_row, is_my_company, extract_document_number, extract_total, extract_shipping, extract_tax
from src.schemas import ExtractedItem, ProcessingResult


class SpreadsheetExtractor(BaseExtractor):
    """
    Deterministic extractor for tabular data (XLS, XLSX, CSV).
    Extracts customer metadata from cell headers and maps DataFrame columns 
    to ExtractedItem attributes using fuzzy string matching.
    """

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
        doc_number = extract_document_number(combined_text)

        # Extract Customer / Supplier (select first external counterparty)
        pattern_counterparty = r"(?:CUSTOMER|SUPPLIER|VENDOR|CLIENT|BUYER|ISSUED\s*BY|SOLD\s*BY|FROM|BILL\s*TO|SHIP\s*TO)[\s:]+([^\n,;]+)"
        for match in re.finditer(pattern_counterparty, combined_text, re.IGNORECASE):
            candidate = match.group(1).strip()
            if candidate and not is_my_company(candidate):
                customer_raw = candidate
                break

        # Extract Tax / VAT
        tax_amount = extract_tax(combined_text)

        # Extract Shipping / Freight
        shipping_amount = extract_shipping(combined_text)

        # Extract Total
        total_amount = extract_total(combined_text)

        return doc_number, customer_raw, tax_amount, shipping_amount, total_amount

    def _score_row_for_headers(self, row: list) -> int:
        """Counts how many columns from the target schema are found in the provided row."""
        score = 0
        mapped_fields = set()
        for cell in row:
            if pd.isna(cell):
                continue
            cell_str = str(cell).lower().strip()
            if not cell_str or cell_str.startswith("unnamed:"):
                continue
            
            best_score = 0
            best_field = None

            for schema_field, aliases in COLUMN_ALIASES.items():
                if schema_field in mapped_fields:
                    continue
                
                match = process.extractOne(cell_str, aliases, scorer=fuzz.token_set_ratio)
                if match and match[1] > best_score:
                    best_score = match[1]
                    best_field = schema_field
            
            if best_field and best_score >= 80:
                score += 1
                mapped_fields.add(best_field)
                
        return score

    def _align_table_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Finds the actual header row, sets it as df.columns,
        and removes all garbage rows above it.
        """
        best_idx = -1
        max_score = self._score_row_for_headers(df.columns.tolist())

        for idx, row in enumerate(df.values.tolist()):
            score = self._score_row_for_headers(row)
            if score > max_score:
                max_score = score
                best_idx = idx

        if best_idx >= 0 and max_score >= 2:
            new_columns = df.values[best_idx].tolist()
            clean_columns = []
            
            for i, col in enumerate(new_columns):
                col_str = str(col).strip()
                if pd.isna(col) or not col_str or col_str.lower().startswith("unnamed:"):
                    clean_columns.append(f"unnamed_col_{i}")
                else:
                    clean_columns.append(col_str)

            df = pd.DataFrame(df.values[best_idx + 1:], columns=clean_columns)
        
        return df

    def _map_columns(self, df_cols: list[str]) -> dict[str, str]:
        """Maps DataFrame header names to target schema fields via fuzzy matching."""
        mapped = {}
        assigned_fields = set()
        
        for col in df_cols:
            clean_col = str(col).lower().strip()
            if not clean_col or clean_col.startswith("unnamed:"):
                continue
                
            best_field = None
            best_score = 0
            
            for schema_field, aliases in COLUMN_ALIASES.items():
                if schema_field in assigned_fields:
                    continue
                    
                match = process.extractOne(clean_col, aliases, scorer=fuzz.token_set_ratio)
                if match and match[1] > best_score:
                    best_score = match[1]
                    best_field = schema_field
            
            if best_field and best_score >= 80:
                mapped[col] = best_field
                assigned_fields.add(best_field)
                
        return mapped

    def _clean_numeric_value(self, val: Any) -> float:
        """Cleans the string from special characters ($, €, commas) and converts it to float."""
        if pd.isna(val) or val is None:
            return 0.0
        
        if isinstance(val, (int, float)):
            return float(val)
            
        val_str = str(val).strip()
        if not val_str:
            return 0.0
            
        # Replace commas with dots (for European formats like 1.234,56 or 120,00)
        # If both dot and comma are present (e.g., 1,234.56), remove commas.
        if ',' in val_str and '.' in val_str:
            val_str = val_str.replace(',', '')
        elif ',' in val_str:
            val_str = val_str.replace(',', '.')
            
        # Remove everything except digits, dots, and minus signs
        cleaned = re.sub(r'[^\d.-]', '', val_str)
        
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def extract(self, content: Any) -> ProcessingResult | None:
        """Parses pd.DataFrame directly into a structured ProcessingResult."""
        if not isinstance(content, pd.DataFrame) or content.empty:
            return None

        try:
            df_raw = content.dropna(how="all").copy()

            # 1. Extract metadata from the raw DataFrame BEFORE trimming
            doc_number, customer_raw, tax_amount, shipping_amount, total_amount = self._extract_header_metadata(df_raw)

            # 2. Find the actual header row and rebuild the table
            df_table = self._align_table_headers(df_raw)
            if df_table.empty:
                return None

            # 3. Now map the CLEANED columns
            col_map = self._map_columns(list(df_table.columns))

            df_renamed = df_table.rename(columns=col_map)

            items: list[ExtractedItem] = []
            for idx, row in df_renamed.iterrows():
                desc = str(row.get("raw_description", "")).strip()

                # Check the ENTIRE row for footer marker words, not just the description column
                row_text = " ".join([str(val) for val in row.values if pd.notna(val)]).lower()
                if is_footer_row(row_text):
                    break

                item_no = str(row.get("item_number", "")).strip()
                
                float_qty = self._clean_numeric_value(row.get("quantity"))
                float_price = self._clean_numeric_value(row.get("unit_price"))
                float_total = self._clean_numeric_value(row.get("total_line_amount"))

                # If the line total amount is not filled in (0.0), but quantity and price exist, calculate it
                if float_total == 0.0 and float_qty > 0 and float_price > 0:
                    float_total = round(float_qty * float_price, 2)

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
        except Exception as e:
            print(f"[ERROR] Exception during extraction: {e}")
            return None
        