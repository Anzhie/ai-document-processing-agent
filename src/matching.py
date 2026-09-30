import re
from typing import Any, cast
import pandas as pd
from rapidfuzz import fuzz, process


class MasterDataMatcher:
    """
    Unified matcher class for Bookstore entities (books, suppliers/customers)
    supporting exact matches on ISBN/Item IDs and fuzzy matches on Title + Author / Supplier Legal Name.
    """

    def __init__(self, df_customer: pd.DataFrame, df_item: pd.DataFrame):
        self.df_customer = df_customer.fillna("")
        self.df_item = df_item.fillna("")

        if "Legal name" in self.df_customer.columns:
            self.customer_names = self.df_customer["Legal name"].to_dict()
        else:
            self.customer_names = {}

        self.item_search_dict = {}
        if not self.df_item.empty:
            for idx, row in self.df_item.iterrows():
                title = str(row.get("Title", "") or row.get("Description", "")).strip()
                author = str(row.get("Author", "")).strip()
                
                combined = f"{title} {author}".strip() if author else title
                if combined:
                    self.item_search_dict[idx] = combined

    def _clean_raw_name(self, raw_name: str) -> str:
        """
        Extracts supplier name only, discarding buyer/recipient info (Ship To / Customer / Small Book Store).
        """
        if not raw_name:
            return ""

        cleaned = raw_name

        if any(marker in cleaned.lower() for marker in ["customer:", "ship to:", "billed to:"]):
            parts = re.split(r"(?i)(customer|ship to|billed to):", cleaned)
            cleaned = parts[0]

        cleaned = re.sub(r"(?i)(supplier|vendor):?", "", cleaned)
        cleaned = re.sub(r"[\r\n]+", " ", cleaned).strip()
    
        return cleaned.strip(", \"'").strip()

    def match_customer(self, raw_name: str | None) -> dict[str, Any]:
        """Matches incoming supplier name against Supplier Master Data using token_set_ratio."""
        if not raw_name or not self.customer_names:
            return {"customer_id": None, "matched_name": None, "confidence": 0.0}

        cleaned_name = self._clean_raw_name(raw_name)

        if not cleaned_name:
            return {"customer_id": None, "matched_name": None, "confidence": 0.0}

        match_result = process.extractOne(
            cleaned_name,
            self.customer_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=50.0,
        )

        if match_result:
            _, score, idx = match_result
            confidence = round(score / 100.0, 4)
            row = self.df_customer.loc[cast(int, idx)]

            # Search for ID across possible column names
            possible_id_cols = [
                "Supplier master ID", "Customer master ID", 
                "Supplier ID", "Customer ID", "Master ID", "ID"
            ]
            cust_id = None
            for col in possible_id_cols:
                if col in row and pd.notna(row[col]) and str(row[col]).strip():
                    cust_id = str(row[col]).strip()
                    break

            return {
                "customer_id": cust_id,
                "matched_name": str(row.get("Legal name", "")),
                "confidence": confidence,
            }

        return {"customer_id": None, "matched_name": None, "confidence": 0.0}

    def match_item(self, raw_id: str | None, raw_desc: str | None) -> dict[str, Any]:
        """
        Matches line items using a 2-step strategy:
        1. Exact match on Item ID / ISBN-13 / EAN (1.0 confidence).
        2. Fuzzy match on Title + Author using token_set_ratio.
        """
        if raw_id:
            raw_id_clean = str(raw_id).strip().lower()
            id_columns = ["Item ID", "ISBN-13", "Item master ID", "ISBN", "EAN", "Source item no."]

            for col in id_columns:
                if col in self.df_item.columns:
                    exact_match = self.df_item[
                        self.df_item[col].astype(str).str.strip().str.lower() == raw_id_clean
                    ]
                    if not exact_match.empty:
                        row = exact_match.iloc[0]
                        idx = exact_match.index[0]
                        
                        item_id = str(row.get("Item ID", "") or row.get("Item master ID", ""))
                        matched_desc = self.item_search_dict.get(idx, str(row.get("Title", "")))

                        return {
                            "item_id": item_id,
                            "matched_description": matched_desc,
                            "confidence": 1.0,
                        }

        if raw_desc and self.item_search_dict:
            match_result = process.extractOne(
                raw_desc,
                self.item_search_dict,
                scorer=fuzz.token_set_ratio,
                score_cutoff=60.0,
            )

            if match_result:
                _, score, idx = match_result
                # Use raw fuzzy match confidence score without artificial reduction (* 0.95)
                confidence = round(score / 100.0, 4)
                row = self.df_item.loc[cast(Any, idx)]

                item_id = str(row.get("Item ID", "") or row.get("Item master ID", ""))

                return {
                    "item_id": item_id,
                    "matched_description": self.item_search_dict[idx],
                    "confidence": confidence,
                }

        return {"item_id": None, "matched_description": None, "confidence": 0.0}