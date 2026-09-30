import re

JUNK_KEYWORDS = {
    "qty", "quantity", "unit price", "price", "description", 
    "sku", "item", "item number", "part number", "amount"
}

FOOTER_KEYWORDS = {
    "total", "subtotal", "grand total", "vat", "tax", "amount due"
}

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+", re.IGNORECASE)
ADDRESS_REGEX = re.compile(r"\b\d{5}\b|avenue|street|broadway|road", re.IGNORECASE)


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
    if EMAIL_REGEX.search(clean_desc) or ADDRESS_REGEX.search(clean_desc):
        return False

    return True


def is_footer_row(desc: str) -> bool:
    """Rule 4: Determines the start of the table's footer (totals) section."""
    clean_desc = desc.strip().lower()
    return any(keyword in clean_desc for keyword in FOOTER_KEYWORDS)