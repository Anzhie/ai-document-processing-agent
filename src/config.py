import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Master data file paths
CUSTOMER_MASTER_PATH = Path(
    os.getenv("CUSTOMER_MASTER_PATH", BASE_DIR / "data/master/Master_Customer_Data.xlsx")
)
ITEM_MASTER_PATH = Path(
    os.getenv("ITEM_MASTER_PATH", BASE_DIR / "data/master/Master_Item_Data.xlsx")
)