import pytest
import pandas as pd
from src.matching import MasterDataMatcher


@pytest.fixture
def sample_master_data():
    """Provides mock DataFrames for customer and item master data."""
    df_customer = pd.DataFrame([
        {"Customer master ID": "CM-10001", "Legal name": "ClearLine Hygiene GmbH"},
        {"Customer master ID": "CM-10002", "Legal name": "Alpha Trade International Ltd"}
    ])
    
    df_item = pd.DataFrame([
        {
            "Item master ID": "IM-100001", 
            "Source item no.": "SRC-99", 
            "Manufacturer item no.": "MFG-001", 
            "Description": "Heavy-duty cleaner, 10 litres"
        },
        {
            "Item master ID": "IM-100002", 
            "Source item no.": "SRC-100", 
            "Manufacturer item no.": "MFG-002", 
            "Description": "Microfiber Cloth Pack of 10"
        }
    ])
    
    return df_customer, df_item


def test_match_customer_fuzzy(sample_master_data):
    df_cust, df_item = sample_master_data
    matcher = MasterDataMatcher(df_cust, df_item)
    
    # Test matching with slight name variation
    result = matcher.match_customer("Clearline Hygiene")
    
    assert result["customer_id"] == "CM-10001"
    assert result["matched_name"] == "ClearLine Hygiene GmbH"
    assert result["confidence"] > 0.80  # Real score is ~0.8205


def test_match_customer_empty_input(sample_master_data):
    df_cust, df_item = sample_master_data
    matcher = MasterDataMatcher(df_cust, df_item)
    
    result = matcher.match_customer(None)
    assert result["customer_id"] is None
    assert result["confidence"] == 0.0


def test_match_item_exact_id(sample_master_data):
    df_cust, df_item = sample_master_data
    matcher = MasterDataMatcher(df_cust, df_item)
    
    # Matching via exact Source Item Number
    result = matcher.match_item(raw_id="SRC-99", raw_desc="Random text that doesn't matter")
    
    assert result["item_id"] == "IM-100001"
    assert result["confidence"] == 1.0


def test_match_item_fuzzy_fallback_and_penalty(sample_master_data):
    df_cust, df_item = sample_master_data
    matcher = MasterDataMatcher(df_cust, df_item)
    
    # No ID provided, fuzzy match on description
    result = matcher.match_item(raw_id=None, raw_desc="Microfiber Cloths 10 pack")
    
    assert result["item_id"] == "IM-100002"
    # Verification of 0.9 confidence penalty for description-only match
    assert result["confidence"] <= 0.90
    assert result["confidence"] > 0.50


def test_match_item_no_match(sample_master_data):
    df_cust, df_item = sample_master_data
    matcher = MasterDataMatcher(df_cust, df_item)
    
    result = matcher.match_item(raw_id="NON-EXISTENT", raw_desc="Unrelated Product Name")
    assert result["item_id"] is None
    assert result["confidence"] == 0.0