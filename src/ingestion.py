import os
from pathlib import Path
from typing import Dict, Any, Union
import pandas as pd


def find_header_row(
    filepath: Union[str, Path], 
    sheet_name: Union[str, int] = 0, 
    target_keyword: str = "master ID"
) -> int:
    """
    Automatically locates the header row index in an Excel sheet by scanning 
    the first 10 rows for a target keyword.
    """
    df_raw = pd.read_excel(filepath, sheet_name=sheet_name, nrows=10, header=None)
    for idx, row in df_raw.iterrows():
        row_str = row.astype(str).str.cat(sep=" ")
        if target_keyword.lower() in row_str.lower():
            return idx
    return 0


def load_customer_master(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    Loads and prepares the Customer Master Data table.
    Cleans column names and filters empty records.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Customer master file not found: {filepath}")

    header_row = find_header_row(
        filepath, 
        sheet_name="Customer Master", 
        target_keyword="Customer master ID"
    )
    df = pd.read_excel(filepath, sheet_name="Customer Master", header=header_row, dtype=str)

    # Strip whitespace from column headers
    df.columns = df.columns.str.strip()

    # Filter out rows missing primary ID
    if "Customer master ID" in df.columns:
        df = df.dropna(subset=["Customer master ID"])

    return df


def load_item_master(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    Loads and prepares the Item Master Data table.
    Cleans column names and filters empty records.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Item master file not found: {filepath}")

    header_row = find_header_row(
        filepath, 
        sheet_name="Item Master", 
        target_keyword="Item master ID"
    )
    df = pd.read_excel(filepath, sheet_name="Item Master", header=header_row, dtype=str)

    # Strip whitespace from column headers
    df.columns = df.columns.str.strip()

    # Filter out rows missing primary ID
    if "Item master ID" in df.columns:
        df = df.dropna(subset=["Item master ID"])

    return df


def read_input_document(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Universal ingestion router for incoming documents.
    Identifies file type by extension and returns structured content.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input document not found: {filepath}")

    ext = path.suffix.lower()

    result = {
        "filename": path.name,
        "extension": ext,
        "file_type": "unknown",
        "content": None
    }

    # 1. Tabular Formats (Excel / CSV)
    if ext in [".xlsx", ".xls"]:
        result["file_type"] = "spreadsheet"
        result["content"] = pd.read_excel(path)
    elif ext == ".csv":
        result["file_type"] = "spreadsheet"
        result["content"] = pd.read_csv(path)

    # 2. PDF Documents
    elif ext == ".pdf":
        result["file_type"] = "pdf"
        result["content"] = str(path)

    # 3. Images / Scans
    elif ext in [".png", ".jpg", ".jpeg", ".tiff"]:
        result["file_type"] = "image"
        result["content"] = str(path)

    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    return result


if __name__ == "__main__":
    # Self-test execution
    cust_path = "data/master/fictional_customer_master.xlsx"
    item_path = "data/master/fictional_item_master.xlsx"

    if os.path.exists(cust_path) and os.path.exists(item_path):
        df_cust = load_customer_master(cust_path)
        df_item = load_item_master(item_path)
        print(f"✅ Customer Master loaded successfully: {len(df_cust)} records.")
        print(f"✅ Item Master loaded successfully: {len(df_item)} records.")
        print("\nCustomer columns:", list(df_cust.columns[:5]))
        print("Item columns:", list(df_item.columns[:5]))