import re
from typing import Any

# Patterns to identify our own company to avoid self-billing errors
MY_COMPANY_PATTERNS = [r"small book store.*"]

# Column aliases for matching table headers to ExtractedItem schema fields
COLUMN_ALIASES = {
    "item_number": ["sku", "item id", "part number", "item_number", "article", "code"],
    "raw_description": ["description", "item description", "name", "product", "details", "item"],
    "quantity": ["qty", "quantity", "count", "amount", "pieces"],
    "unit_price": ["unit price", "price", "unit_price", "rate"],
    "total_line_amount": [
        "total", "line total", "total_amount", "amount", 
        "amount eur", "amount gbp", "total ($)", "total (€)"
    ],
}

JUNK_KEYWORDS = {
    "qty", "quantity", "unit price", "price", "description", 
    "sku", "item", "item number", "part number", "amount"
}

FOOTER_KEYWORDS = {
    "total", "subtotal", "grand total", "vat", "tax", "amount due"
}

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+", re.IGNORECASE)
ADDRESS_REGEX = re.compile(r"\b\d{5}\b|avenue|street|broadway|road", re.IGNORECASE)


def safe_float(value: Any) -> float:
    """Safely converts string/numeric value into float, handling currency symbols and comma/dot decimal formats."""
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        import math
        return 0.0 if isinstance(value, float) and math.isnan(value) else float(value)

    val_str = str(value).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null", ""):
        return 0.0

    # Normalize decimal separators (1,234.56 vs 120,00)
    if "," in val_str and "." in val_str:
        val_str = val_str.replace(",", "")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    cleaned = re.sub(r"[^\d.-]", "", val_str)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def is_my_company(text: str) -> bool:
    """Checks if the provided text matches our own company patterns."""
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in MY_COMPANY_PATTERNS)


def is_valid_line_item(desc: str, qty: float, unit_price: float, total_price: float) -> bool:
    """Validates the line item based on rules 1, 2, and 3."""
    clean_desc = desc.strip().lower()

    if not clean_desc:
        return False

    # Rule 1: Exclude rows that have neither quantity nor prices
    if qty <= 0 and unit_price <= 0 and total_price <= 0:
        return False

    # Rule 2: Exclude column headers that leaked into the data
    if clean_desc in JUNK_KEYWORDS:
        return False

    # Rule 3: Exclude addresses and emails
    return not (EMAIL_REGEX.search(clean_desc) or ADDRESS_REGEX.search(clean_desc))

    return True


def is_footer_row(desc: str) -> bool:
    """Rule 4: Determines the start of the table's footer (totals) section."""
    clean_desc = desc.strip().lower()
    return any(keyword in clean_desc for keyword in FOOTER_KEYWORDS)

# --- Modular Header Field Extractors ---

def extract_document_number(text: str) -> str | None:
    """Extracts PO / Invoice / Order document number."""
    match = re.search(
        r"(?:PURCHASE\s*ORDER|PO|INVOICE|ORDER)[\s#:]*(?:NUMBER|#|NO\.?)?:?\s*([A-Z0-9-]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def extract_tax(text: str) -> float | None:
    """Extracts Tax / VAT / HST amount."""
    match = re.search(r"(?i)(?:TAX|VAT|HST)[^:\n]*[:\s]+[\$€£]?\s*([\d.,]+)", text)
    return safe_float(match.group(1)) if match else None


def extract_shipping(text: str) -> float | None:
    """Extracts Shipping / Freight / Handling amount."""
    match = re.search(
        r"(?:SHIPPING|FREIGHT|HANDLING|ESTIMATED\s*FREIGHT)[\s\w()]*[:\s|]+[$€£]?\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    return safe_float(match.group(1)) if match else None


def extract_total(text: str) -> float | None:
    """Extracts Total / Grand Total amount."""
    match = re.search(
        r"\b(?:TOTAL\s*AMOUNT|TOTAL\s*DUE|ORDER\s*TOTAL|GRAND\s*TOTAL|TOTAL)\b[\s:|]+[$€£]?\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    return safe_float(match.group(1)) if match else None