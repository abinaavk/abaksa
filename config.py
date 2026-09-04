# config.py
# Reads all the settings from the .env file and also keeps the tariff
# defaults, same idea as the desktop version - these are just the starting
# values, the admin can change the actual rates later from the Tariff
# Settings page in the admin panel and those get saved in the database.

import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.path.join(BASE_DIR, "instance", "abaksa.db")
BILLS_DIR = os.path.join(BASE_DIR, "bills")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")

for folder in (os.path.join(BASE_DIR, "instance"), BILLS_DIR, BACKUP_DIR, EXPORT_DIR):
    os.makedirs(folder, exist_ok=True)


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "6991"))
FLASK_DEBUG = env_bool("FLASK_DEBUG", True)

BASE_URL = os.environ.get("BASE_URL", "https://abaksa.abinaavk.com")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
MAIL_PORT = int(os.environ.get("MAIL_PORT", "587") or 587)
MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "ABAKSA Billing")
MAIL_ENABLED = bool(MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD)

# ---- company details shown on the bill ----
UTILITY_NAME = "Bridge Power Utility Corporation"
UTILITY_ADDRESS = "Plot 42, Electric Avenue, New Delhi - 110001"
UTILITY_PHONE = "+91-11-4000-1234"
UTILITY_EMAIL = "billing@bridgepower.example"
UTILITY_UPI_ID = "bridgepower@upi"
UTILITY_GSTIN = "07ABCDE1234F1Z5"

# ---- tariff slabs (starting values, editable later from the admin panel) ----
DEFAULT_TARIFF_SLABS = {
    "Domestic": [
        (100, 3.50),
        (200, 4.50),
        (300, 6.00),
        (500, 7.50),
        (None, 8.75),
    ],
    "Commercial": [
        (100, 6.00),
        (300, 8.00),
        (500, 9.50),
        (None, 11.00),
    ],
    "Industrial": [
        (500, 7.00),
        (1500, 8.50),
        (None, 10.00),
    ],
}

DEFAULT_FIXED_CHARGES = {
    "Domestic": 50.0,
    "Commercial": 150.0,
    "Industrial": 500.0,
}

DEFAULT_TAX_RATE = 0.05
DEFAULT_SURCHARGE_RATE = 0.02
DEFAULT_SUBSIDY_UNIT_THRESHOLD = 100
DEFAULT_SUBSIDY_AMOUNT = 200.0
DEFAULT_LATE_FINE_RATE_PER_DAY = 0.01
DEFAULT_LATE_FINE_MAX_FRACTION = 0.30
DEFAULT_LATE_FINE_GRACE_DAYS = 5
DEFAULT_DUE_PERIOD_DAYS = 21

ANOMALY_MULTIPLIER = 1.6
ANOMALY_LOOKBACK_BILLS = 6
ANOMALY_MIN_HISTORY = 2

ROLE_ADMIN = "admin"
ROLE_CUSTOMER = "customer"

APP_NAME = "ABAKSA"
APP_TAGLINE = "Electricity Billing Management System"
APP_VERSION = "2.0.0"

CONNECTION_TYPES = ["Domestic", "Commercial", "Industrial"]
PAYMENT_STATUSES = ["Paid", "Unpaid", "Overdue"]
COMPLAINT_STATUSES = ["Open", "In Progress", "Resolved", "Closed"]
COMPLAINT_CATEGORIES = ["Meter Fault", "Billing Error", "Power Outage", "Wiring Issue", "Other"]
