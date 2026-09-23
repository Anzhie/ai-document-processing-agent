import pytest
import pandas as pd
from pathlib import Path
from src.ingestion import find_header_row, load_customer_master


def test_find_header_row(tmp_path: Path):
    """Verify that find_header_row locates header index despite leading metadata rows."""
    file_path = tmp_path / "test_customer_master.xlsx"
    
    # Create mock dataset with 2 metadata rows before actual headers
    mock_data = [
        ["Report Title", None, None],
        ["Generated on 2026-09-23", None, None],
        ["Customer master ID", "Customer no.", "Legal name"],  # Target header row (index 2)
        ["CM-10001", "0048326", "Test Company GmbH"]
    ]
    
    df_raw = pd.DataFrame(mock_data)
    df_raw.to_excel(file_path, sheet_name="Customer Master", index=False, header=False)
    
    detected_idx = find_header_row(
        file_path, 
        sheet_name="Customer Master", 
        target_keyword="Customer master ID"
    )
    
    assert detected_idx == 2


def test_load_customer_master_preserves_string_dtypes(tmp_path: Path):
    """Verify that numeric identifiers keep leading zeros and are loaded as strings."""
    file_path = tmp_path / "test_customers.xlsx"
    
    mock_data = [
        ["Customer master ID", "Customer no.", "Legal name"],
        ["CM-10001", "0048326", "Test Company GmbH"]  # Leading zeros in Customer no.
    ]
    
    df_raw = pd.DataFrame(mock_data[1:], columns=mock_data[0])
    df_raw.to_excel(file_path, sheet_name="Customer Master", index=False)
    
    df_loaded = load_customer_master(file_path)
    
    # Verify exact string match and type preservation
    assert isinstance(df_loaded["Customer no."].iloc[0], str)
    assert df_loaded["Customer no."].iloc[0] == "0048326"