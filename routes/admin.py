# routes/admin.py
# The whole admin panel, reachable at /admin. This is the biggest blueprint
# since it covers customers, meter readings, billing, payments, complaints,
# reports, notifications, tariff settings, other admin accounts, the audit
# log, and backups.
#
# The admin login (/admin/login) checks the same users table as everywhere
# else, but the ONE built-in admin account's password always comes from
# ADMIN_PASSWORD in the .env file (see database._seed_admin_account) - so
# whoever controls the .env file controls the master admin login.

import os
from datetime import date

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    send_file, abort, jsonify,
)
from flask_login import login_user, current_user

import database
import logic
import pdf_gen
import email_utils
import config
import auth

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
def index():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("admin.login"))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = database.authenticate(username, password)

        if row is None:
            flash("Incorrect username or password.", "error")
            return render_template("admin/login.html", username=username)
        if row["role"] != config.ROLE_ADMIN:
            flash("That account isn't an admin account.", "error")
            return render_template("admin/login.html", username=username)

        login_user(auth.AppUser(row))
        database.log_action(row["id"], row["username"], "LOGIN", "role=admin")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html", username="")


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

@admin_bp.route("/dashboard")
@auth.admin_required
def dashboard():
    summary = database.dashboard_summary()
    trend = database.monthly_consumption(months=8)
    revenue = database.revenue_by_connection_type()
    return render_template("admin/dashboard.html", summary=summary, trend=trend, revenue=revenue)


# ---------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------

@admin_bp.route("/customers")
@auth.admin_required
def customers():
    search = request.args.get("q", "")
    ctype = request.args.get("type", "All")
    customer_list = database.list_customers(search=search, connection_type=ctype)
    return render_template("admin/customers.html", customers=customer_list, search=search, ctype=ctype,
                            connection_types=config.CONNECTION_TYPES)


@admin_bp.route("/customers/add", methods=["POST"])
@auth.admin_required
def add_customer():
    consumer_no = request.form.get("consumer_no", "").strip()
    meter_no = request.form.get("meter_no", "").strip()
    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    connection_type = request.form.get("connection_type", "Domestic")
    sanctioned_load = request.form.get("sanctioned_load", "").strip()

    if not (consumer_no and meter_no and name and address):
        flash("Consumer number, meter number, name and address are required.", "error")
        return redirect(url_for("admin.customers"))

    try:
        database.add_customer(consumer_no, meter_no, name, address, phone, email,
                               connection_type, sanctioned_load)
        database.log_action(current_user.id, current_user.username, "ADD_CUSTOMER", "consumer_no=" + consumer_no)
        flash("Customer added.", "success")
    except Exception:
        flash("Could not add customer - that consumer number or meter number may already exist.", "error")

    return redirect(url_for("admin.customers"))


@admin_bp.route("/customers/<int:customer_id>/edit", methods=["POST"])
@auth.admin_required
def edit_customer(customer_id):
    customer = database.get_customer(customer_id)
    if customer is None:
        abort(404)

    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    connection_type = request.form.get("connection_type", customer["connection_type"])
    sanctioned_load = request.form.get("sanctioned_load", "").strip()

    if not (name and address):
        flash("Name and address are required.", "error")
        return redirect(url_for("admin.customers"))

    database.update_customer_details(customer_id, name, address, phone, email, connection_type, sanctioned_load)
    database.log_action(current_user.id, current_user.username, "EDIT_CUSTOMER", "id=" + str(customer_id))
    flash("Customer updated.", "success")
    return redirect(url_for("admin.customers"))


@admin_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@auth.admin_required
def delete_customer(customer_id):
    database.delete_customer(customer_id)
    database.log_action(current_user.id, current_user.username, "DELETE_CUSTOMER", "id=" + str(customer_id))
    flash("Customer deleted.", "success")
    return redirect(url_for("admin.customers"))


@admin_bp.route("/customers/<int:customer_id>/history")
@auth.admin_required
def customer_history(customer_id):
    customer = database.get_customer(customer_id)
    if customer is None:
        abort(404)
    bills = database.bill_history_for_customer(customer_id)
    readings = database.list_readings(customer_id)
    return render_template("admin/customer_history.html", customer=customer, bills=bills, readings=readings)


# ---------------------------------------------------------------------
# Meter readings
# ---------------------------------------------------------------------

@admin_bp.route("/readings")
@auth.admin_required
def readings():
    customer_list = database.list_customers()
    unbilled = database.get_unbilled_readings()
    unbilled_with_customer = []
    for r in unbilled:
        c = database.get_customer(r["customer_id"])
        unbilled_with_customer.append({"reading": r, "customer": c})
    return render_template("admin/readings.html", customers=customer_list, unbilled=unbilled_with_customer)


@admin_bp.route("/readings/latest/<int:customer_id>")
@auth.admin_required
def latest_reading_json(customer_id):
    # small AJAX helper the "add reading" form calls to pre-fill the
    # previous units box when you pick a customer from the dropdown
    latest = database.get_latest_reading(customer_id)
    return jsonify({"previous_units": latest["current_units"] if latest else 0})


@admin_bp.route("/readings/add", methods=["POST"])
@auth.admin_required
def add_reading():
    try:
        customer_id = int(request.form.get("customer_id"))
        previous_units = float(request.form.get("previous_units"))
        current_units = float(request.form.get("current_units"))
    except (TypeError, ValueError):
        flash("Please fill in the reading form correctly.", "error")
        return redirect(url_for("admin.readings"))

    if current_units < previous_units:
        flash("Current reading cannot be less than the previous reading.", "error")
        return redirect(url_for("admin.readings"))

    database.add_reading(customer_id, previous_units, current_units, recorded_by=current_user.id)
    database.log_action(current_user.id, current_user.username, "ADD_READING", "customer=" + str(customer_id))
    flash("Meter reading recorded.", "success")
    return redirect(url_for("admin.readings"))


# ---------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------

def _generate_bill_for_reading(reading, cfg):
    customer = database.get_customer(reading["customer_id"])
    result = logic.calculate_bill(reading["units_consumed"], customer["connection_type"], cfg)
    bill_date = date.today().isoformat()
    due_date = logic.calculate_due_date(bill_date, cfg)

    past_bills = database.bill_history_for_customer(customer["id"], limit=config.ANOMALY_LOOKBACK_BILLS)
    past_units = [b["units_consumed"] for b in past_bills]
    is_anomalous, avg = logic.detect_anomaly(
        reading["units_consumed"], past_units, config.ANOMALY_MULTIPLIER, config.ANOMALY_MIN_HISTORY)

    bill_id = database.insert_bill(
        customer["id"], reading["id"], bill_date, due_date, reading["units_consumed"],
        result["energy_charge"], result["fixed_charge"], result["surcharge"], result["tax"],
        result["subsidy"], result["total_amount"], is_anomalous=int(is_anomalous),
    )
    if customer["user_id"]:
        bill = database.get_bill(bill_id)
        database.add_notification(
            customer["user_id"], "New Bill Generated",
            "Bill " + bill["bill_no"] + " for " + logic.format_currency(result["total_amount"]) +
            " is due " + due_date + ".",
        )
    return bill_id, is_anomalous


@admin_bp.route("/billing")
@auth.admin_required
def billing():
    status = request.args.get("status", "All")
    ctype = request.args.get("type", "All")
    date_from = request.args.get("from") or None
    date_to = request.args.get("to") or None
    bill_list = database.list_bills(status=status, connection_type=ctype, date_from=date_from, date_to=date_to)
    return render_template("admin/billing.html", bills=bill_list, status=status, ctype=ctype,
                            date_from=date_from or "", date_to=date_to or "",
                            connection_types=config.CONNECTION_TYPES, statuses=config.PAYMENT_STATUSES)


@admin_bp.route("/billing/bulk-generate", methods=["POST"])
@auth.admin_required
def bulk_generate():
    readings = database.get_unbilled_readings()
    if not readings:
        flash("No unbilled meter readings found.", "warning")
        return redirect(url_for("admin.billing"))

    cfg = database.get_tariff_config()
    count = 0
    anomalies = 0
    for reading in readings:
        _, is_anom = _generate_bill_for_reading(reading, cfg)
        count += 1
        anomalies += int(is_anom)

    database.log_action(current_user.id, current_user.username, "BULK_GENERATE_BILLS", "count=" + str(count))
    msg = "Generated " + str(count) + " bill(s)."
    if anomalies:
        msg += " " + str(anomalies) + " flagged for unusual consumption."
    flash(msg, "success")
    return redirect(url_for("admin.billing"))


@admin_bp.route("/billing/recompute-fines", methods=["POST"])
@auth.admin_required
def recompute_fines():
    cfg = database.get_tariff_config()
    pending = database.list_bills(status="Unpaid") + database.list_bills(status="Overdue")
    updated = 0
    for b in pending:
        base_total = b["total_amount"] - b["late_fine"]
        fine, days, status = logic.calculate_late_fine(base_total, b["due_date"], cfg)
        new_total = round(base_total + fine, 2)
        if fine != b["late_fine"] or status != b["status"]:
            database.update_bill_late_fine(b["id"], fine, new_total, status)
            updated += 1

    database.log_action(current_user.id, current_user.username, "RECOMPUTE_FINES", "updated=" + str(updated))
    flash("Updated late fines on " + str(updated) + " bill(s).", "success")
    return redirect(url_for("admin.billing"))


@admin_bp.route("/bills/<int:bill_id>")
@auth.admin_required
def bill_detail(bill_id):
    bill = database.get_bill(bill_id)
    if bill is None:
        abort(404)
    customer = database.get_customer(bill["customer_id"])
    cfg = database.get_tariff_config()
    calc = logic.calculate_bill(bill["units_consumed"], customer["connection_type"], cfg)
    return render_template("admin/bill_detail.html", bill=bill, customer=customer,
                            breakdown=calc["slab_breakdown"])


def _ensure_pdf(bill, customer):
    if bill["pdf_path"] and os.path.exists(bill["pdf_path"]):
        return bill["pdf_path"]
    cfg = database.get_tariff_config()
    calc = logic.calculate_bill(bill["units_consumed"], customer["connection_type"], cfg)
    path = pdf_gen.generate_bill_pdf(bill, customer, calc["slab_breakdown"])
    database.set_bill_pdf_path(bill["id"], path)
    return path


@admin_bp.route("/bills/<int:bill_id>/pdf")
@auth.admin_required
def bill_pdf(bill_id):
    bill = database.get_bill(bill_id)
    if bill is None:
        abort(404)
    customer = database.get_customer(bill["customer_id"])
    path = _ensure_pdf(bill, customer)
    return send_file(path, as_attachment=False, download_name=bill["bill_no"] + ".pdf")


@admin_bp.route("/bills/<int:bill_id>/email", methods=["POST"])
@auth.admin_required
def bill_email(bill_id):
    bill = database.get_bill(bill_id)
    if bill is None:
        abort(404)
    customer = database.get_customer(bill["customer_id"])
    if not customer["email"]:
        flash("This customer has no email address on file.", "warning")
        return redirect(url_for("admin.bill_detail", bill_id=bill_id))
    try:
        path = _ensure_pdf(bill, customer)
        email_utils.send_bill_email(customer, bill, path)
        flash("Bill emailed to " + customer["email"], "success")
    except email_utils.EmailNotConfigured:
        flash("Email isn't set up yet - add MAIL_* settings to the .env file.", "warning")
    except Exception as e:
        flash("Could not send email: " + str(e), "error")
    return redirect(url_for("admin.bill_detail", bill_id=bill_id))


@admin_bp.route("/bills/<int:bill_id>/mark-paid", methods=["POST"])
@auth.admin_required
def mark_paid(bill_id):
    bill = database.get_bill(bill_id)
    if bill is None:
        abort(404)
    customer = database.get_customer(bill["customer_id"])
    database.record_payment(bill_id, bill["total_amount"], method="Manual/Admin")
    if customer["user_id"]:
        database.add_notification(
            customer["user_id"], "Payment Received",
            "Payment of " + logic.format_currency(bill["total_amount"]) + " received for bill " + bill["bill_no"] + ".",
        )
    database.log_action(current_user.id, current_user.username, "MARK_PAID", "bill=" + bill["bill_no"])
    flash("Bill marked as paid.", "success")
    return redirect(url_for("admin.bill_detail", bill_id=bill_id))


# ---------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------

@admin_bp.route("/payments")
@auth.admin_required
def payments():
    payment_list = database.list_payments()
    return render_template("admin/payments.html", payments=payment_list)


# ---------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------

@admin_bp.route("/complaints", methods=["GET"])
@auth.admin_required
def complaints():
    status = request.args.get("status", "All")
    complaint_list = database.list_complaints(status=status)
    return render_template("admin/complaints.html", complaints=complaint_list, status=status,
                            statuses=config.COMPLAINT_STATUSES)


@admin_bp.route("/complaints/<int:complaint_id>/update", methods=["POST"])
@auth.admin_required
def update_complaint(complaint_id):
    complaint = database.get_complaint(complaint_id)
    if complaint is None:
        abort(404)

    new_status = request.form.get("status", "Open")
    note = request.form.get("note", "").strip()

    database.update_complaint_status(complaint_id, new_status, note, assigned_to=current_user.id)
    database.log_action(current_user.id, current_user.username, "UPDATE_COMPLAINT",
                         "id=" + str(complaint_id) + " status=" + new_status)

    customer = database.get_customer(complaint["customer_id"])
    if customer["user_id"]:
        database.add_notification(customer["user_id"], "Complaint Updated",
                                   "Your complaint #" + str(complaint_id) + " is now '" + new_status + "'.")

    flash("Complaint updated.", "success")
    return redirect(url_for("admin.complaints"))


# ---------------------------------------------------------------------
# Reports & analytics
# ---------------------------------------------------------------------

@admin_bp.route("/reports")
@auth.admin_required
def reports():
    customer_list = database.list_customers()
    selected_customer_id = request.args.get("customer_id", type=int)
    trend = database.monthly_consumption(customer_id=selected_customer_id, months=12)
    anomalies = database.anomalous_bills()
    return render_template("admin/reports.html", customers=customer_list, trend=trend,
                            anomalies=anomalies, selected_customer_id=selected_customer_id)


# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------

@admin_bp.route("/notifications", methods=["GET", "POST"])
@auth.admin_required
def notifications():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        if not (title and message):
            flash("Enter both a title and a message.", "error")
            return redirect(url_for("admin.notifications"))

        customer_list = database.list_customers()
        count = 0
        for c in customer_list:
            if c["user_id"]:
                database.add_notification(c["user_id"], title, message)
                count += 1

        database.log_action(current_user.id, current_user.username, "BROADCAST_NOTIFICATION", "count=" + str(count))
        flash("Sent to " + str(count) + " customer(s) with an active login.", "success")
        return redirect(url_for("admin.notifications"))

    my_notifs = database.list_notifications(current_user.id)
    return render_template("admin/notifications.html", notifications=my_notifs)


@admin_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@auth.admin_required
def mark_notification_read(notif_id):
    database.mark_notification_read(notif_id)
    return redirect(url_for("admin.notifications"))


# ---------------------------------------------------------------------
# Tariff settings
# ---------------------------------------------------------------------

@admin_bp.route("/tariff", methods=["GET", "POST"])
@auth.admin_required
def tariff():
    if request.method == "POST":
        try:
            slabs = {}
            for ctype in config.CONNECTION_TYPES:
                slab_list = []
                uptos = request.form.getlist("slab_upto_" + ctype)
                rates = request.form.getlist("slab_rate_" + ctype)
                for upto_s, rate_s in zip(uptos, rates):
                    rate_s = rate_s.strip()
                    if not rate_s:
                        continue
                    upto_val = None if not upto_s.strip() else float(upto_s)
                    slab_list.append([upto_val, float(rate_s)])
                if not slab_list:
                    raise ValueError("At least one slab is required for " + ctype)
                slabs[ctype] = slab_list

            fixed = {}
            for ctype in config.CONNECTION_TYPES:
                fixed[ctype] = float(request.form.get("fixed_" + ctype))

            database.set_tariff_config("slabs", slabs)
            database.set_tariff_config("fixed_charges", fixed)
            database.set_tariff_config("tax_rate", float(request.form.get("tax_rate")) / 100)
            database.set_tariff_config("surcharge_rate", float(request.form.get("surcharge_rate")) / 100)
            database.set_tariff_config("subsidy_unit_threshold", int(float(request.form.get("subsidy_units"))))
            database.set_tariff_config("subsidy_amount", float(request.form.get("subsidy_amount")))
            database.set_tariff_config("late_fine_rate_per_day", float(request.form.get("fine_rate")) / 100)
            database.set_tariff_config("late_fine_max_fraction", float(request.form.get("fine_cap")) / 100)
            database.set_tariff_config("late_fine_grace_days", int(float(request.form.get("grace_days"))))
            database.set_tariff_config("due_period_days", int(float(request.form.get("due_days"))))

            database.log_action(current_user.id, current_user.username, "UPDATE_TARIFF_CONFIG")
            flash("Tariff settings saved.", "success")
        except (ValueError, TypeError) as e:
            flash("Invalid input: " + str(e), "error")

        return redirect(url_for("admin.tariff"))

    cfg = database.get_tariff_config()
    return render_template("admin/tariff.html", cfg=cfg, connection_types=config.CONNECTION_TYPES)


# ---------------------------------------------------------------------
# Admin accounts
# ---------------------------------------------------------------------

@admin_bp.route("/accounts", methods=["GET", "POST"])
@auth.admin_required
def accounts():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not (name and username and password):
            flash("Name, username, and password are required.", "error")
            return redirect(url_for("admin.accounts"))

        if database.get_user_by_username(username):
            flash("Username already exists.", "error")
            return redirect(url_for("admin.accounts"))

        database.create_user(username, password, config.ROLE_ADMIN, name, email)
        database.log_action(current_user.id, current_user.username, "CREATE_ADMIN", "username=" + username)
        flash("Admin account created.", "success")
        return redirect(url_for("admin.accounts"))

    admin_list = database.list_admins()
    return render_template("admin/accounts.html", admins=admin_list)


@admin_bp.route("/accounts/<int:user_id>/deactivate", methods=["POST"])
@auth.admin_required
def deactivate_account(user_id):
    if user_id == current_user.id:
        flash("You can't deactivate your own account.", "error")
        return redirect(url_for("admin.accounts"))
    database.deactivate_user(user_id)
    database.log_action(current_user.id, current_user.username, "DEACTIVATE_ADMIN", "id=" + str(user_id))
    flash("Admin deactivated.", "success")
    return redirect(url_for("admin.accounts"))


# ---------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------

@admin_bp.route("/audit")
@auth.admin_required
def audit():
    db = database.get_db()
    rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 500").fetchall()
    return render_template("admin/audit.html", logs=rows)


# ---------------------------------------------------------------------
# Backup & export
# ---------------------------------------------------------------------

@admin_bp.route("/backup")
@auth.admin_required
def backup():
    return render_template("admin/backup.html")


@admin_bp.route("/backup/create", methods=["POST"])
@auth.admin_required
def create_backup():
    path = database.backup_database()
    database.log_action(current_user.id, current_user.username, "BACKUP_DB", path)
    flash("Backup created: " + os.path.basename(path), "success")
    return redirect(url_for("admin.backup"))


@admin_bp.route("/backup/export/<table_name>")
@auth.admin_required
def export_csv(table_name):
    try:
        path = database.export_table_csv(table_name)
    except ValueError:
        abort(404)
    database.log_action(current_user.id, current_user.username, "EXPORT_CSV", "table=" + table_name)
    return send_file(path, as_attachment=True, download_name=table_name + ".csv")
