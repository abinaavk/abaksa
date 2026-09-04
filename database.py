# database.py
# All the SQL for the web app lives here. We use Flask's "g" object so each
# request gets its own database connection, and it gets closed automatically
# at the end of the request - this is the normal way Flask apps use sqlite3.
#
# The tables are basically the same design as the desktop version:
#   users            -> login id, password hash, role (admin/customer), google_id
#   customers        -> one row per customer, links to users.id if they have a login
#   meter_readings   -> readings taken for a customer over time
#   bills            -> one bill per reading, links to customers and meter_readings
#   payments         -> payments made against a bill
#   complaints       -> tickets raised by a customer
#   audit_log        -> keeps a record of what admins did and when
#   notifications    -> messages shown to a user in the app
#   tariff_config    -> the rates etc, editable from the admin panel

import sqlite3
import json
import csv
import shutil
from datetime import datetime, date

from flask import g
from werkzeug.security import generate_password_hash, check_password_hash

import config


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(config.DB_PATH)
        g.db.execute("PRAGMA foreign_keys = ON;")
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    role            TEXT NOT NULL CHECK(role IN ('admin','customer')),
    full_name       TEXT NOT NULL,
    email           TEXT,
    google_id       TEXT UNIQUE,
    avatar_url      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    consumer_no     TEXT UNIQUE NOT NULL,
    meter_no        TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    address         TEXT NOT NULL,
    phone           TEXT,
    email           TEXT,
    connection_type TEXT NOT NULL CHECK(connection_type IN ('Domestic','Commercial','Industrial')),
    sanctioned_load TEXT,
    connection_date TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS meter_readings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    reading_date    TEXT NOT NULL,
    previous_units  REAL NOT NULL,
    current_units   REAL NOT NULL,
    units_consumed  REAL NOT NULL,
    recorded_by     INTEGER REFERENCES users(id),
    billed          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    reading_id      INTEGER REFERENCES meter_readings(id),
    bill_no         TEXT UNIQUE NOT NULL,
    bill_date       TEXT NOT NULL,
    due_date        TEXT NOT NULL,
    units_consumed  REAL NOT NULL,
    energy_charge   REAL NOT NULL,
    fixed_charge    REAL NOT NULL,
    surcharge       REAL NOT NULL,
    tax             REAL NOT NULL,
    subsidy         REAL NOT NULL DEFAULT 0,
    late_fine       REAL NOT NULL DEFAULT 0,
    total_amount    REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Unpaid' CHECK(status IN ('Paid','Unpaid','Overdue')),
    is_anomalous    INTEGER NOT NULL DEFAULT 0,
    pdf_path        TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id         INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    amount_paid     REAL NOT NULL,
    payment_date    TEXT NOT NULL,
    method          TEXT NOT NULL DEFAULT 'UPI',
    reference_no    TEXT
);

CREATE TABLE IF NOT EXISTS complaints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Open',
    created_at      TEXT NOT NULL,
    resolved_at     TEXT,
    resolution_note TEXT,
    assigned_to     INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    username        TEXT,
    action          TEXT NOT NULL,
    details         TEXT,
    timestamp       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tariff_config (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bills_customer ON bills(customer_id);
CREATE INDEX IF NOT EXISTS idx_bills_status ON bills(status);
CREATE INDEX IF NOT EXISTS idx_readings_customer ON meter_readings(customer_id);
CREATE INDEX IF NOT EXISTS idx_complaints_customer ON complaints(customer_id);
"""


def init_app(app):
    # register the close_db function so Flask calls it automatically at
    # the end of every request
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


def init_db():
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.commit()
    _seed_tariff_defaults(db)
    _seed_admin_account(db)


def _seed_tariff_defaults(db):
    row = db.execute("SELECT COUNT(*) AS n FROM tariff_config").fetchone()
    if row["n"] > 0:
        return
    defaults = {
        "slabs": json.dumps(config.DEFAULT_TARIFF_SLABS),
        "fixed_charges": json.dumps(config.DEFAULT_FIXED_CHARGES),
        "tax_rate": str(config.DEFAULT_TAX_RATE),
        "surcharge_rate": str(config.DEFAULT_SURCHARGE_RATE),
        "subsidy_unit_threshold": str(config.DEFAULT_SUBSIDY_UNIT_THRESHOLD),
        "subsidy_amount": str(config.DEFAULT_SUBSIDY_AMOUNT),
        "late_fine_rate_per_day": str(config.DEFAULT_LATE_FINE_RATE_PER_DAY),
        "late_fine_max_fraction": str(config.DEFAULT_LATE_FINE_MAX_FRACTION),
        "late_fine_grace_days": str(config.DEFAULT_LATE_FINE_GRACE_DAYS),
        "due_period_days": str(config.DEFAULT_DUE_PERIOD_DAYS),
    }
    for k, v in defaults.items():
        db.execute("INSERT INTO tariff_config(key, value) VALUES (?,?)", (k, v))
    db.commit()


def _seed_admin_account(db):
    # the admin account credentials come from the .env file. If a user with
    # that username doesn't already exist, create it. If they already
    # changed ADMIN_PASSWORD in .env, we also refresh the stored password
    # for that account on every restart, so .env is always the source of
    # truth for the main admin login.
    row = db.execute("SELECT * FROM users WHERE username=?", (config.ADMIN_USERNAME,)).fetchone()
    pw_hash = generate_password_hash(config.ADMIN_PASSWORD)
    if row is None:
        db.execute(
            "INSERT INTO users(username, password_hash, role, full_name, email, created_at) VALUES (?,?,?,?,?,?)",
            (config.ADMIN_USERNAME, pw_hash, "admin", "System Administrator", "", datetime.now().isoformat()),
        )
    else:
        db.execute("UPDATE users SET password_hash=?, role='admin', is_active=1 WHERE id=?", (pw_hash, row["id"]))
    db.commit()


# ---------------------------------------------------------------------
# Users / auth
# ---------------------------------------------------------------------

def get_user_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def get_user_by_username(username):
    return get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def get_user_by_google_id(google_id):
    return get_db().execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone()


def get_user_by_email(email):
    return get_db().execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()


def authenticate(username, password):
    row = get_user_by_username(username)
    if row is None or not row["is_active"]:
        return None
    if not row["password_hash"]:
        return None
    if check_password_hash(row["password_hash"], password):
        return row
    return None


def create_user(username, password, role, full_name, email="", google_id=None, avatar_url=None):
    db = get_db()
    pw_hash = generate_password_hash(password) if password else None
    cur = db.execute(
        """INSERT INTO users(username, password_hash, role, full_name, email, google_id, avatar_url, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (username, pw_hash, role, full_name, email, google_id, avatar_url, datetime.now().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def set_password(user_id, new_password):
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
    db.commit()


def deactivate_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
    db.commit()


def list_admins():
    return get_db().execute("SELECT * FROM users WHERE role='admin' ORDER BY id").fetchall()


def log_action(user_id, username, action, details=""):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log(user_id, username, action, details, timestamp) VALUES (?,?,?,?,?)",
        (user_id, username, action, details, datetime.now().isoformat()),
    )
    db.commit()


def add_notification(user_id, title, message):
    if not user_id:
        return
    db = get_db()
    db.execute(
        "INSERT INTO notifications(user_id, title, message, created_at) VALUES (?,?,?,?)",
        (user_id, title, message, datetime.now().isoformat()),
    )
    db.commit()


def list_notifications(user_id, unread_only=False, limit=50):
    q = "SELECT * FROM notifications WHERE user_id=?"
    if unread_only:
        q += " AND is_read=0"
    q += " ORDER BY id DESC LIMIT ?"
    return get_db().execute(q, (user_id, limit)).fetchall()


def unread_notification_count(user_id):
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND is_read=0", (user_id,)
    ).fetchone()
    return row["n"] if row else 0


def mark_notification_read(notif_id):
    db = get_db()
    db.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notif_id,))
    db.commit()


def mark_all_notifications_read(user_id):
    db = get_db()
    db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
    db.commit()


# ---------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------

def add_customer(consumer_no, meter_no, name, address, phone, email,
                  connection_type, sanctioned_load, user_id=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO customers(user_id, consumer_no, meter_no, name, address, phone, email,
                                  connection_type, sanctioned_load, connection_date)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (user_id, consumer_no, meter_no, name, address, phone, email,
         connection_type, sanctioned_load, date.today().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def update_customer_details(customer_id, name, address, phone, email, connection_type, sanctioned_load):
    db = get_db()
    db.execute(
        """UPDATE customers
           SET name=?, address=?, phone=?, email=?, connection_type=?, sanctioned_load=?
           WHERE id=?""",
        (name, address, phone, email, connection_type, sanctioned_load, customer_id),
    )
    db.commit()


def link_customer_to_user(customer_id, user_id):
    db = get_db()
    db.execute("UPDATE customers SET user_id=? WHERE id=?", (user_id, customer_id))
    db.commit()


def delete_customer(customer_id):
    db = get_db()
    db.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    db.commit()


def get_customer(customer_id):
    return get_db().execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()


def get_customer_by_consumer_no(consumer_no):
    return get_db().execute("SELECT * FROM customers WHERE consumer_no=?", (consumer_no,)).fetchone()


def get_customer_by_user(user_id):
    return get_db().execute("SELECT * FROM customers WHERE user_id=?", (user_id,)).fetchone()


def list_customers(search="", connection_type=None, active_only=True):
    q = "SELECT * FROM customers WHERE 1=1"
    params = []
    if active_only:
        q += " AND is_active=1"
    if search:
        q += " AND (name LIKE ? OR consumer_no LIKE ? OR meter_no LIKE ? OR address LIKE ?)"
        like = "%" + search + "%"
        params += [like, like, like, like]
    if connection_type and connection_type != "All":
        q += " AND connection_type=?"
        params.append(connection_type)
    q += " ORDER BY id DESC"
    return get_db().execute(q, params).fetchall()


# ---------------------------------------------------------------------
# Meter readings
# ---------------------------------------------------------------------

def add_reading(customer_id, previous_units, current_units, recorded_by=None, reading_date=None):
    units_consumed = round(current_units - previous_units, 2)
    db = get_db()
    cur = db.execute(
        """INSERT INTO meter_readings(customer_id, reading_date, previous_units, current_units,
                                       units_consumed, recorded_by)
           VALUES (?,?,?,?,?,?)""",
        (customer_id, reading_date or date.today().isoformat(), previous_units,
         current_units, units_consumed, recorded_by),
    )
    db.commit()
    return cur.lastrowid


def get_latest_reading(customer_id):
    return get_db().execute(
        "SELECT * FROM meter_readings WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
    ).fetchone()


def get_unbilled_readings():
    return get_db().execute("SELECT * FROM meter_readings WHERE billed=0 ORDER BY customer_id").fetchall()


def mark_reading_billed(reading_id):
    db = get_db()
    db.execute("UPDATE meter_readings SET billed=1 WHERE id=?", (reading_id,))
    db.commit()


def list_readings(customer_id):
    return get_db().execute(
        "SELECT * FROM meter_readings WHERE customer_id=? ORDER BY reading_date", (customer_id,)
    ).fetchall()


# ---------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------

def next_bill_no():
    c = get_db().execute("SELECT COUNT(*) AS n FROM bills").fetchone()["n"]
    return "BILL-" + str(datetime.now().year) + "-" + str(c + 1).zfill(6)


def insert_bill(customer_id, reading_id, bill_date, due_date, units_consumed,
                 energy_charge, fixed_charge, surcharge, tax, subsidy, total_amount, is_anomalous=0):
    db = get_db()
    bill_no = next_bill_no()
    cur = db.execute(
        """INSERT INTO bills(customer_id, reading_id, bill_no, bill_date, due_date, units_consumed,
                              energy_charge, fixed_charge, surcharge, tax, subsidy, late_fine,
                              total_amount, status, is_anomalous, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,'Unpaid',?,?)""",
        (customer_id, reading_id, bill_no, bill_date, due_date, units_consumed,
         energy_charge, fixed_charge, surcharge, tax, subsidy, total_amount,
         is_anomalous, datetime.now().isoformat()),
    )
    db.commit()
    if reading_id:
        mark_reading_billed(reading_id)
    return cur.lastrowid


def get_bill(bill_id):
    return get_db().execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()


def set_bill_pdf_path(bill_id, path):
    db = get_db()
    db.execute("UPDATE bills SET pdf_path=? WHERE id=?", (path, bill_id))
    db.commit()


def update_bill_late_fine(bill_id, late_fine, total_amount, status):
    db = get_db()
    db.execute(
        "UPDATE bills SET late_fine=?, total_amount=?, status=? WHERE id=?",
        (late_fine, total_amount, status, bill_id),
    )
    db.commit()


def mark_bill_paid(bill_id):
    db = get_db()
    db.execute("UPDATE bills SET status='Paid' WHERE id=?", (bill_id,))
    db.commit()


def list_bills(customer_id=None, status=None, connection_type=None, date_from=None, date_to=None):
    q = """SELECT bills.*, customers.name AS customer_name, customers.consumer_no,
                  customers.connection_type, customers.email AS customer_email
           FROM bills JOIN customers ON bills.customer_id = customers.id
           WHERE 1=1"""
    params = []
    if customer_id:
        q += " AND bills.customer_id=?"
        params.append(customer_id)
    if status and status != "All":
        q += " AND bills.status=?"
        params.append(status)
    if connection_type and connection_type != "All":
        q += " AND customers.connection_type=?"
        params.append(connection_type)
    if date_from:
        q += " AND bills.bill_date>=?"
        params.append(date_from)
    if date_to:
        q += " AND bills.bill_date<=?"
        params.append(date_to)
    q += " ORDER BY bills.id DESC"
    return get_db().execute(q, params).fetchall()


def bill_history_for_customer(customer_id, limit=None):
    q = "SELECT * FROM bills WHERE customer_id=? ORDER BY bill_date DESC"
    if limit:
        q += " LIMIT " + str(int(limit))
    return get_db().execute(q, (customer_id,)).fetchall()


# ---------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------

def record_payment(bill_id, amount_paid, method="UPI", reference_no=""):
    db = get_db()
    db.execute(
        "INSERT INTO payments(bill_id, amount_paid, payment_date, method, reference_no) VALUES (?,?,?,?,?)",
        (bill_id, amount_paid, datetime.now().isoformat(), method, reference_no),
    )
    mark_bill_paid(bill_id)
    db.commit()


def list_payments(bill_id=None):
    if bill_id:
        return get_db().execute("SELECT * FROM payments WHERE bill_id=? ORDER BY id DESC", (bill_id,)).fetchall()
    return get_db().execute(
        """SELECT payments.*, bills.bill_no, customers.name AS customer_name
           FROM payments JOIN bills ON payments.bill_id = bills.id
                         JOIN customers ON bills.customer_id = customers.id
           ORDER BY payments.id DESC"""
    ).fetchall()


# ---------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------

def add_complaint(customer_id, category, description):
    db = get_db()
    cur = db.execute(
        "INSERT INTO complaints(customer_id, category, description, created_at) VALUES (?,?,?,?)",
        (customer_id, category, description, datetime.now().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def get_complaint(complaint_id):
    return get_db().execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()


def list_complaints(customer_id=None, status=None):
    q = """SELECT complaints.*, customers.name AS customer_name, customers.consumer_no
           FROM complaints JOIN customers ON complaints.customer_id = customers.id WHERE 1=1"""
    params = []
    if customer_id:
        q += " AND complaints.customer_id=?"
        params.append(customer_id)
    if status and status != "All":
        q += " AND complaints.status=?"
        params.append(status)
    q += " ORDER BY complaints.id DESC"
    return get_db().execute(q, params).fetchall()


def update_complaint_status(complaint_id, status, resolution_note="", assigned_to=None):
    resolved_at = datetime.now().isoformat() if status in ("Resolved", "Closed") else None
    db = get_db()
    db.execute(
        "UPDATE complaints SET status=?, resolution_note=?, resolved_at=?, assigned_to=? WHERE id=?",
        (status, resolution_note, resolved_at, assigned_to, complaint_id),
    )
    db.commit()


# ---------------------------------------------------------------------
# Tariff config
# ---------------------------------------------------------------------

def get_tariff_config():
    rows = get_db().execute("SELECT key, value FROM tariff_config").fetchall()
    cfg = {}
    for r in rows:
        cfg[r["key"]] = r["value"]

    cfg["slabs"] = json.loads(cfg["slabs"])
    cfg["fixed_charges"] = json.loads(cfg["fixed_charges"])

    float_keys = ["tax_rate", "surcharge_rate", "subsidy_amount",
                  "late_fine_rate_per_day", "late_fine_max_fraction"]
    for k in float_keys:
        cfg[k] = float(cfg[k])

    int_keys = ["subsidy_unit_threshold", "late_fine_grace_days", "due_period_days"]
    for k in int_keys:
        cfg[k] = int(float(cfg[k]))

    return cfg


def set_tariff_config(key, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    else:
        value = str(value)
    db = get_db()
    db.execute(
        "INSERT INTO tariff_config(key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    db.commit()


# ---------------------------------------------------------------------
# Dashboard / analytics
# ---------------------------------------------------------------------

def dashboard_summary():
    db = get_db()
    n_customers = db.execute("SELECT COUNT(*) AS n FROM customers WHERE is_active=1").fetchone()["n"]
    month_prefix = date.today().strftime("%Y-%m")
    month_revenue = db.execute(
        "SELECT COALESCE(SUM(amount_paid),0) AS s FROM payments WHERE payment_date LIKE ?",
        (month_prefix + "%",),
    ).fetchone()["s"]
    pending_dues = db.execute(
        "SELECT COALESCE(SUM(total_amount),0) AS s FROM bills WHERE status IN ('Unpaid','Overdue')"
    ).fetchone()["s"]
    overdue_count = db.execute("SELECT COUNT(*) AS n FROM bills WHERE status='Overdue'").fetchone()["n"]
    open_complaints = db.execute(
        "SELECT COUNT(*) AS n FROM complaints WHERE status IN ('Open','In Progress')"
    ).fetchone()["n"]
    top_consumers = db.execute(
        """SELECT customers.name, customers.consumer_no, SUM(bills.units_consumed) AS total_units
           FROM bills JOIN customers ON bills.customer_id = customers.id
           GROUP BY bills.customer_id ORDER BY total_units DESC LIMIT 5"""
    ).fetchall()
    return {
        "n_customers": n_customers,
        "month_revenue": month_revenue,
        "pending_dues": pending_dues,
        "overdue_count": overdue_count,
        "open_complaints": open_complaints,
        "top_consumers": top_consumers,
    }


def monthly_consumption(customer_id=None, months=12):
    q = "SELECT strftime('%Y-%m', bill_date) AS ym, SUM(units_consumed) AS units FROM bills WHERE 1=1"
    params = []
    if customer_id:
        q += " AND customer_id=?"
        params.append(customer_id)
    q += " GROUP BY ym ORDER BY ym DESC LIMIT ?"
    params.append(months)
    rows = get_db().execute(q, params).fetchall()
    return list(reversed(rows))


def revenue_by_connection_type():
    return get_db().execute(
        """SELECT customers.connection_type, COALESCE(SUM(payments.amount_paid),0) AS revenue
           FROM payments JOIN bills ON payments.bill_id = bills.id
                         JOIN customers ON bills.customer_id = customers.id
           GROUP BY customers.connection_type"""
    ).fetchall()


def anomalous_bills(limit=30):
    return get_db().execute(
        """SELECT bills.*, customers.name AS customer_name FROM bills
           JOIN customers ON bills.customer_id = customers.id
           WHERE bills.is_anomalous=1 ORDER BY bills.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()


# ---------------------------------------------------------------------
# Backup / export
# ---------------------------------------------------------------------

def backup_database():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = config.BACKUP_DIR + "/abaksa_backup_" + ts + ".db"
    get_db().commit()
    shutil.copy2(config.DB_PATH, dest)
    return dest


def export_table_csv(table_name, path=None):
    allowed = {"users", "customers", "meter_readings", "bills", "payments",
               "complaints", "audit_log", "notifications"}
    if table_name not in allowed:
        raise ValueError("Invalid table name")

    db = get_db()
    rows = db.execute("SELECT * FROM " + table_name).fetchall()
    if not rows:
        cols = [d[1] for d in db.execute("PRAGMA table_info(" + table_name + ")").fetchall()]
    else:
        cols = rows[0].keys()

    path = path or (config.EXPORT_DIR + "/" + table_name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for r in rows:
            writer.writerow([r[c] for c in cols])
    return path
