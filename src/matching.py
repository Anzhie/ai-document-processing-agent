import pandas as pd
from typing import Optional, Dict, Any
from rapidfuzz import process, fuzz

class MasterDataMatcher:
    """
    A unified matcher class to map raw extracted entities (customers, items)
    against the loaded Master Data DataFrames using exact and fuzzy matching.
    """
    
    def __init__(self, df_customer: pd.DataFrame, df_item: pd.DataFrame):
        # Fill NaNs with empty strings to avoid RapidFuzz type errors
        self.df_customer = df_customer.fillna("")
        self.df_item = df_item.fillna("")
        
        # Pre-compute dictionaries for faster fuzzy search mapping (Index -> Value)
        # Using index as the dictionary key allows easy row retrieval later
        if "Legal name" in self.df_customer.columns:
            self.customer_names = self.df_customer['Legal name'].to_dict()
        else:
            self.customer_names = {}

        if "Description" in self.df_item.columns:
            self.item_descriptions = self.df_item['Description'].to_dict()
        else:
            self.item_descriptions = {}

    def match_customer(self, raw_name: Optional[str]) -> Dict[str, Any]:
        """
        Attempts to find the closest matching customer in the Master Data.
        Returns a normalized confidence score (0.0 to 1.0).
        """
        if not raw_name or not self.customer_names:
            return {"customer_id": None, "matched_name": None, "confidence": 0.0}
        
        match_result = process.extractOne(
            raw_name, 
            self.customer_names, 
            scorer=fuzz.WRatio,
            score_cutoff=40.0  # Ignore matches with score below 40%
        )
        
        if match_result:
            best_str, score, idx = match_result
            confidence = round(score / 100.0, 4)
            row = self.df_customer.loc[idx]
            
            return {
                "customer_id": str(row.get("Customer master ID", "")),
                "matched_name": str(row.get("Legal name", "")),
                "confidence": confidence
            }
            
        return {"customer_id": None, "matched_name": None, "confidence": 0.0}
    
    def match_item(self, raw_id: Optional[str], raw_desc: Optional[str]) -> Dict[str, Any]:
        """
        Matches an item using a fallback strategy:
        1. Exact match on standard ID columns (1.0 confidence).
        2. Fuzzy match on item description with score penalty and minimum threshold.
        """
        # Strategy 1: Exact match on IDs
        if raw_id:
            raw_id_lower = str(raw_id).strip().lower()
            id_columns = ["Item master ID", "Source item no.", "Manufacturer item no."]
            
            for col in id_columns:
                if col in self.df_item.columns:
                    exact_match = self.df_item[self.df_item[col].astype(str).str.lower() == raw_id_lower]
                    if not exact_match.empty:
                        row = exact_match.iloc[0]
                        return {
                            "item_id": str(row.get("Item master ID", "")),
                            "matched_description": str(row.get("Description", "")),
                            "confidence": 1.0
                        }
        
        # Strategy 2: Fallback to Fuzzy search on Description
        if raw_desc and self.item_descriptions:
            match_result = process.extractOne(
                raw_desc,
                self.item_descriptions,
                scorer=fuzz.WRatio,
                score_cutoff=40.0  # Ignore matches with score below 40%
            )
            
            if match_result:
                best_str, score, idx = match_result
                confidence = round((score / 100.0) * 0.9, 4)
                row = self.df_item.loc[idx]
                
                return {
                    "item_id": str(row.get("Item master ID", "")),
                    "matched_description": str(row.get("Description", "")),
                    "confidence": confidence
                }
                
        return {"item_id": None, "matched_description": None, "confidence": 0.0}


if __name__ == "__main__":
    from ingestion import load_customer_master, load_item_master
    
    # Load actual master data
    customer_path = "data/master/fictional_customer_master.xlsx"
    item_path = "data/master/fictional_item_master.xlsx"
    
    df_customers = load_customer_master(customer_path)
    df_items = load_item_master(item_path)
    
    matcher = MasterDataMatcher(df_customers, df_items)
    
    # Test customer matching (fuzzy)
    print("--- Customer Match Test ---")
    print(matcher.match_customer("Clearline Hygiene"))  # Intentional typo/short form
    
    # Test item matching (exact ID & fuzzy description)
    print("\n--- Item Match Tests ---")
    print("Exact ID:", matcher.match_item(raw_id="IM-100001", raw_desc=None))
    print("Fuzzy Desc:", matcher.match_item(raw_id=None, raw_desc="Cleaner heavy duty 10l"))