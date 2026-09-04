# email_utils.py
# Sends bills and notifications to customers by email using python's
# built-in smtplib. Unlike the desktop version, the mail server settings
# come from the .env file (see config.py) instead of a separate json file
# -- that fits better with how a web app is normally deployed.
#
# If MAIL_ENABLED is False (because the .env fields were left blank), we
# raise a friendly error instead of trying to connect anywhere, so the rest
# of the app keeps working fine even with no mail server set up.

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import config


class EmailNotConfigured(Exception):
    pass


def send_email(to_address, subject, body, attachment_path=None):
    if not config.MAIL_ENABLED:
        raise EmailNotConfigured(
            "Email sending is not set up yet. Fill in MAIL_SERVER, MAIL_USERNAME and "
            "MAIL_PASSWORD in the .env file to enable this."
        )

    msg = MIMEMultipart()
    msg["From"] = config.MAIL_FROM_NAME + " <" + config.MAIL_USERNAME + ">"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            file_data = f.read()
        filename = os.path.basename(attachment_path)
        part = MIMEApplication(file_data, Name=filename)
        part["Content-Disposition"] = 'attachment; filename="' + filename + '"'
        msg.attach(part)

    server = smtplib.SMTP(config.MAIL_SERVER, config.MAIL_PORT, timeout=15)
    try:
        if config.MAIL_USE_TLS:
            server.starttls()
        server.login(config.MAIL_USERNAME, config.MAIL_PASSWORD)
        server.sendmail(config.MAIL_USERNAME, to_address, msg.as_string())
    finally:
        server.quit()


def send_bill_email(customer_row, bill_row, pdf_path):
    subject = "Your Electricity Bill " + bill_row["bill_no"] + " - " + config.UTILITY_NAME

    body_lines = [
        "Dear " + customer_row["name"] + ",",
        "",
        "Your electricity bill for consumer number " + customer_row["consumer_no"] + " has been generated.",
        "",
        "Bill No: " + bill_row["bill_no"],
        "Bill Date: " + bill_row["bill_date"],
        "Units Consumed: " + str(bill_row["units_consumed"]) + " kWh",
        "Total Amount Due: Rs. " + format(bill_row["total_amount"], ".2f"),
        "Due Date: " + bill_row["due_date"],
        "",
        "You can view and pay this bill any time by logging in to your ABAKSA account.",
        "",
        "Thank you,",
        config.UTILITY_NAME,
    ]
    body = "\n".join(body_lines)

    send_email(customer_row["email"], subject, body, attachment_path=pdf_path)


def send_notification_email(to_address, title, message):
    send_email(to_address, title, message)


def send_welcome_email(to_address, name, username):
    subject = "Welcome to " + config.APP_NAME
    body = (
        "Hi " + name + ",\n\n"
        "Your " + config.APP_NAME + " account has been created.\n"
        "Username: " + username + "\n\n"
        "You can now log in and view your electricity bills, track your usage, "
        "and raise support tickets any time.\n\n"
        "Thank you,\n" + config.UTILITY_NAME
    )
    send_email(to_address, subject, body)
