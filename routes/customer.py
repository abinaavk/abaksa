# routes/customer.py
# Everything a logged-in customer can do - their dashboard, bills,
# consumption history, complaints, notifications and profile.
# Every route here is protected by @auth.customer_required.

import os
from datetime import date

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    send_file, abort, jsonify,
)
from flask_login import current_user

import database
import logic
import pdf_gen
import email_utils
import config
import auth

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


def _get_my_customer_or_404():
    customer = database.get_customer_by_user(current_user.id)
    if customer is None:
        abort(404)
    return customer


@portal_bp.route("/link-account", methods=["GET", "POST"])
@auth.customer_required
def link_account():
    # used right after a brand new Google sign-in - the login exists but
    # isn't connected to a customer record yet
    existing = database.get_customer_by_user(current_user.id)
    if existing is not None:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        consumer_no = request.form.get("consumer_no", "").strip()
        customer = database.get_customer_by_consumer_no(consumer_no)
        if customer is None:
            flash("No customer found with that consumer number. Ask your admin to add you first.", "error")
            return render_template("customer/link_account.html", consumer_no=consumer_no)
        if customer["user_id"] is not None:
            flash("That consumer number is already linked to another login.", "error")
            return render_template("customer/link_account.html", consumer_no=consumer_no)
        database.link_customer_to_user(customer["id"], current_user.id)
        database.log_action(current_user.id, current_user.username, "LINK_ACCOUNT", "consumer_no=" + consumer_no)
        flash("Your account is all set up!", "success")
        return redirect(url_for("portal.dashboard"))

    return render_template("customer/link_account.html", consumer_no="")


@portal_bp.route("/")
@portal_bp.route("/dashboard")
@auth.customer_required
def dashboard():
    customer = database.get_customer_by_user(current_user.id)
    if customer is None:
        return redirect(url_for("portal.link_account"))

    bills = database.bill_history_for_customer(customer["id"])
    total_due = 0
    for b in bills:
        if b["status"] != "Paid":
            total_due = total_due + b["total_amount"]

    latest_bill = bills[0] if bills else None
    last_reading = database.get_latest_reading(customer["id"])
    trend = database.monthly_consumption(customer_id=customer["id"], months=12)
    unread = database.unread_notification_count(current_user.id)

    return render_template(
        "customer/dashboard.html",
        customer=customer, bills=bills, total_due=total_due,
        latest_bill=latest_bill, last_reading=last_reading, trend=trend,
        unread=unread,
    )


@portal_bp.route("/bills")
@auth.customer_required
def bills():
    customer = _get_my_customer_or_404()
    status = request.args.get("status", "All")
    bill_list = database.list_bills(customer_id=customer["id"], status=status)
    return render_template("customer/bills.html", customer=customer, bills=bill_list, status=status)


@portal_bp.route("/bills/<int:bill_id>")
@auth.customer_required
def bill_detail(bill_id):
    customer = _get_my_customer_or_404()
    bill = database.get_bill(bill_id)
    if bill is None or bill["customer_id"] != customer["id"]:
        abort(404)
    cfg = database.get_tariff_config()
    calc = logic.calculate_bill(bill["units_consumed"], customer["connection_type"], cfg)
    return render_template("customer/bill_detail.html", customer=customer, bill=bill,
                            breakdown=calc["slab_breakdown"])


def _ensure_pdf(bill, customer):
    if bill["pdf_path"] and os.path.exists(bill["pdf_path"]):
        return bill["pdf_path"]
    cfg = database.get_tariff_config()
    calc = logic.calculate_bill(bill["units_consumed"], customer["connection_type"], cfg)
    path = pdf_gen.generate_bill_pdf(bill, customer, calc["slab_breakdown"])
    database.set_bill_pdf_path(bill["id"], path)
    return path


@portal_bp.route("/bills/<int:bill_id>/pdf")
@auth.customer_required
def bill_pdf(bill_id):
    customer = _get_my_customer_or_404()
    bill = database.get_bill(bill_id)
    if bill is None or bill["customer_id"] != customer["id"]:
        abort(404)
    path = _ensure_pdf(bill, customer)
    return send_file(path, as_attachment=False, download_name=bill["bill_no"] + ".pdf")


@portal_bp.route("/bills/<int:bill_id>/email", methods=["POST"])
@auth.customer_required
def bill_email(bill_id):
    customer = _get_my_customer_or_404()
    bill = database.get_bill(bill_id)
    if bill is None or bill["customer_id"] != customer["id"]:
        abort(404)
    if not customer["email"]:
        flash("There's no email address on your account yet.", "warning")
        return redirect(url_for("portal.bill_detail", bill_id=bill_id))
    try:
        path = _ensure_pdf(bill, customer)
        email_utils.send_bill_email(customer, bill, path)
        flash("Bill emailed to " + customer["email"], "success")
    except email_utils.EmailNotConfigured:
        flash("Email isn't set up yet - ask your admin to configure it.", "warning")
    except Exception as e:
        flash("Could not send email: " + str(e), "error")
    return redirect(url_for("portal.bill_detail", bill_id=bill_id))


@portal_bp.route("/bills/<int:bill_id>/pay", methods=["POST"])
@auth.customer_required
def bill_pay(bill_id):
    # simulated "pay now" button - in a real deployment this would go
    # through an actual payment gateway before calling record_payment
    customer = _get_my_customer_or_404()
    bill = database.get_bill(bill_id)
    if bill is None or bill["customer_id"] != customer["id"]:
        abort(404)
    if bill["status"] == "Paid":
        flash("This bill is already paid.", "info")
        return redirect(url_for("portal.bill_detail", bill_id=bill_id))

    database.record_payment(bill_id, bill["total_amount"], method="UPI (simulated)")
    database.log_action(current_user.id, current_user.username, "SELF_PAYMENT", "bill=" + bill["bill_no"])
    flash("Payment successful! Thank you.", "success")
    return redirect(url_for("portal.bill_detail", bill_id=bill_id))


@portal_bp.route("/readings")
@auth.customer_required
def readings():
    customer = _get_my_customer_or_404()
    reading_list = database.list_readings(customer["id"])
    trend = database.monthly_consumption(customer_id=customer["id"], months=12)
    return render_template("customer/readings.html", customer=customer, readings=reading_list, trend=trend)


@portal_bp.route("/complaints", methods=["GET", "POST"])
@auth.customer_required
def complaints():
    customer = _get_my_customer_or_404()

    if request.method == "POST":
        category = request.form.get("category", "Other")
        description = request.form.get("description", "").strip()
        if not description:
            flash("Please describe the issue.", "error")
        else:
            database.add_complaint(customer["id"], category, description)
            database.log_action(current_user.id, current_user.username, "ADD_COMPLAINT")
            flash("Complaint submitted. Our team will review it shortly.", "success")
        return redirect(url_for("portal.complaints"))

    complaint_list = database.list_complaints(customer_id=customer["id"])
    return render_template("customer/complaints.html", customer=customer, complaints=complaint_list,
                            categories=config.COMPLAINT_CATEGORIES)


@portal_bp.route("/notifications")
@auth.customer_required
def notifications():
    notifs = database.list_notifications(current_user.id)
    return render_template("customer/notifications.html", notifications=notifs)


@portal_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@auth.customer_required
def mark_notification_read(notif_id):
    database.mark_notification_read(notif_id)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect(url_for("portal.notifications"))


@portal_bp.route("/notifications/read-all", methods=["POST"])
@auth.customer_required
def mark_all_notifications_read():
    database.mark_all_notifications_read(current_user.id)
    return redirect(url_for("portal.notifications"))


@portal_bp.route("/profile", methods=["GET", "POST"])
@auth.customer_required
def profile():
    customer = database.get_customer_by_user(current_user.id)

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 4:
            flash("Password must be at least 4 characters.", "error")
        elif new_password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            database.set_password(current_user.id, new_password)
            database.log_action(current_user.id, current_user.username, "CHANGE_PASSWORD")
            flash("Password updated.", "success")
        return redirect(url_for("portal.profile"))

    return render_template("customer/profile.html", customer=customer)
