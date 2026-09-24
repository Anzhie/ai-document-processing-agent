from pathlib import Path
import pandas as pd
import pytest

from src.ingestion import (
    find_header_row,
    load_customer_master,
    load_item_master,
    read_input_document,
)


def test_find_header_row_default_fallback(tmp_path: Path) -> None:
    """Verify that find_header_row returns 0 if target keyword is not found."""
    file_path = tmp_path / "no_header.xlsx"
    pd.DataFrame([["A", "B"], ["C", "D"]]).to_excel(file_path, index=False, header=False)

    detected_idx = find_header_row(file_path, target_keyword="NonExistentKeyword")
    assert detected_idx == 0


def test_find_header_row_locates_header(tmp_path: Path) -> None:
    """Verify that find_header_row locates header index despite leading metadata rows."""
    file_path = tmp_path / "test_customer_master.xlsx"
    mock_data = [
        ["Report Title", None, None],
        ["Generated on 2026-09-23", None, None],
        ["Customer master ID", "Customer no.", "Legal name"],
        ["CM-10001", "0048326", "Test Company GmbH"],
    ]
    pd.DataFrame(mock_data).to_excel(file_path, sheet_name="Customer Master", index=False, header=False)

    detected_idx = find_header_row(
        file_path, sheet_name="Customer Master", target_keyword="Customer master ID"
    )
    assert detected_idx == 2


def test_load_customer_master_file_not_found() -> None:
    """Verify that load_customer_master raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        load_customer_master("non_existent_file.xlsx")


def test_load_customer_master_preserves_string_dtypes(tmp_path: Path) -> None:
    """Verify that numeric identifiers keep leading zeros and are loaded as strings."""
    file_path = tmp_path / "test_customers.xlsx"
    mock_data = [
        ["Customer master ID", "Customer no.", "Legal name"],
        ["CM-10001", "0048326", "Test Company GmbH"],
    ]
    pd.DataFrame(mock_data[1:], columns=mock_data[0]).to_excel(file_path, sheet_name="Customer Master", index=False)

    df_loaded = load_customer_master(file_path)
    assert isinstance(df_loaded["Customer no."].iloc[0], str)
    assert df_loaded["Customer no."].iloc[0] == "0048326"


def test_load_item_master_file_not_found() -> None:
    """Verify that load_item_master raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        load_item_master("non_existent_file.xlsx")


def test_load_item_master_success(tmp_path: Path) -> None:
    """Verify that load_item_master correctly cleans headers and filters rows."""
    file_path = tmp_path / "test_items.xlsx"
    mock_data = [
        ["Item master ID ", "SKU", "Description"],
        ["ITM-001", "SKU-123", "Widget A"],
        [None, "SKU-999", "Invalid Row"],
    ]
    pd.DataFrame(mock_data[1:], columns=mock_data[0]).to_excel(file_path, sheet_name="Item Master", index=False)

    df_loaded = load_item_master(file_path)
    assert "Item master ID" in df_loaded.columns
    assert len(df_loaded) == 1
    assert df_loaded["SKU"].iloc[0] == "SKU-123"


def test_read_input_document_file_not_found() -> None:
    """Verify read_input_document raises FileNotFoundError when file is missing."""
    with pytest.raises(FileNotFoundError):
        read_input_document("missing.csv")


def test_read_input_document_xlsx(tmp_path: Path) -> None:
    """Verify reading Excel documents in read_input_document."""
    file_path = tmp_path / "test.xlsx"
    pd.DataFrame({"col": [1, 2]}).to_excel(file_path, index=False)

    res = read_input_document(file_path)
    assert res["file_type"] == "spreadsheet"
    assert isinstance(res["content"], pd.DataFrame)


def test_read_input_document_csv(tmp_path: Path) -> None:
    """Verify reading CSV documents in read_input_document."""
    file_path = tmp_path / "test.csv"
    file_path.write_text("a,b\n1,2", encoding="utf-8")

    res = read_input_document(file_path)
    assert res["file_type"] == "spreadsheet"
    assert isinstance(res["content"], pd.DataFrame)


def test_read_input_document_pdf(tmp_path: Path) -> None:
    """Verify routing PDF documents in read_input_document."""
    file_path = tmp_path / "test.pdf"
    file_path.write_bytes(b"%PDF-1.4 fake pdf")

    res = read_input_document(file_path)
    assert res["file_type"] == "pdf"
    assert res["content"] == str(file_path)


def test_read_input_document_image(tmp_path: Path) -> None:
    """Verify routing Image documents in read_input_document."""
    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake image")

    res = read_input_document(file_path)
    assert res["file_type"] == "image"
    assert res["content"] == str(file_path)


def test_read_input_document_unsupported(tmp_path: Path) -> None:
    """Verify exception for unsupported file extension in read_input_document."""
    file_path = tmp_path / "test.unknown"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file extension"):
        read_input_document(file_path)