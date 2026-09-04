# routes/public.py
# Everything that doesn't need you to be logged in yet - the landing page,
# the customer login/register forms, Google sign-in, and logging out.
# The admin login form lives in routes/admin.py instead, since the whole
# point is that it's reached through the /admin link.

from flask import Blueprint, render_template, redirect, url_for, request, flash, Response
from flask_login import login_user, logout_user, current_user, login_required

import database
import config
import auth
import email_utils
from oauth import oauth

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def landing():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("portal.dashboard"))
    return render_template("public/landing.html")


@public_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard") if current_user.is_customer else url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = database.authenticate(username, password)

        if row is None:
            flash("Incorrect username or password.", "error")
            return render_template("public/login.html", username=username)

        if row["role"] != config.ROLE_CUSTOMER:
            flash("That account is not a customer account. Use the admin panel instead.", "error")
            return render_template("public/login.html", username=username)

        login_user(auth.AppUser(row))
        database.log_action(row["id"], row["username"], "LOGIN", "role=customer")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("portal.dashboard"))

    return render_template("public/login.html", username="")


@public_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard") if current_user.is_customer else url_for("admin.dashboard"))

    if request.method == "POST":
        consumer_no = request.form.get("consumer_no", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form_back = {"consumer_no": consumer_no, "username": username}

        if not (consumer_no and username and password):
            flash("All fields are required.", "error")
            return render_template("public/register.html", **form_back)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("public/register.html", **form_back)
        if len(password) < 4:
            flash("Password must be at least 4 characters.", "error")
            return render_template("public/register.html", **form_back)

        customer = database.get_customer_by_consumer_no(consumer_no)
        if customer is None:
            flash("No customer found with that consumer number. Ask your admin to add you first.", "error")
            return render_template("public/register.html", **form_back)
        if customer["user_id"] is not None:
            flash("This consumer account already has a login. Try logging in instead.", "error")
            return render_template("public/register.html", **form_back)
        if database.get_user_by_username(username):
            flash("That username is already taken.", "error")
            return render_template("public/register.html", **form_back)

        user_id = database.create_user(username, password, config.ROLE_CUSTOMER, customer["name"], customer["email"])
        database.link_customer_to_user(customer["id"], user_id)
        database.log_action(user_id, username, "REGISTER", "consumer_no=" + consumer_no)

        if customer["email"]:
            try:
                email_utils.send_welcome_email(customer["email"], customer["name"], username)
            except Exception:
                pass  # email is optional, never block registration on it

        flash("Account created! You can log in now.", "success")
        return redirect(url_for("public.login"))

    return render_template("public/register.html", consumer_no="", username="")


@public_bp.route("/logout")
@login_required
def logout():
    database.log_action(current_user.id, current_user.username, "LOGOUT")
    was_admin = current_user.is_admin
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("admin.login") if was_admin else url_for("public.login"))


# ---- Google sign-in (customers only) ----

@public_bp.route("/auth/google/login")
def google_login():
    if not config.GOOGLE_LOGIN_ENABLED:
        flash("Google sign-in isn't set up yet. Ask your admin to add GOOGLE_CLIENT_ID and "
              "GOOGLE_CLIENT_SECRET to the .env file.", "warning")
        return redirect(url_for("public.login"))
    redirect_uri = url_for("public.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@public_bp.route("/auth/google/callback")
def google_callback():
    if not config.GOOGLE_LOGIN_ENABLED:
        return redirect(url_for("public.login"))

    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    google_id = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or (email.split("@")[0] if email else "Google User")
    picture = userinfo.get("picture")

    if not google_id:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("public.login"))

    row = database.get_user_by_google_id(google_id)

    if row is None and email:
        # maybe they already have a normal account under the same email address
        row = database.get_user_by_email(email)

    if row is None:
        # brand new account - pick a free username based on their email
        base_username = (email.split("@")[0] if email else "google" + google_id[:8]).lower()
        username = base_username
        counter = 1
        while database.get_user_by_username(username) is not None:
            username = base_username + str(counter)
            counter += 1
        user_id = database.create_user(
            username, None, config.ROLE_CUSTOMER, name, email or "",
            google_id=google_id, avatar_url=picture,
        )
        row = database.get_user_by_id(user_id)
    elif not row["is_active"]:
        flash("This account has been deactivated.", "error")
        return redirect(url_for("public.login"))

    if row["role"] != config.ROLE_CUSTOMER:
        flash("This Google account is linked to an admin login, not a customer one.", "error")
        return redirect(url_for("public.login"))

    user = auth.AppUser(row)
    login_user(user)
    database.log_action(user.id, user.username, "LOGIN", "role=customer via Google")

    customer = database.get_customer_by_user(user.id)
    if customer is None:
        flash("Signed in with Google! One last step - link your consumer number to see your bills.", "info")
        return redirect(url_for("portal.link_account"))

    return redirect(url_for("portal.dashboard"))


@public_bp.route("/sitemap.xml")
def sitemap():
    pages = [
        {"loc": url_for("public.landing", _external=True), "priority": "1.0"},
        {"loc": url_for("public.login", _external=True), "priority": "0.8"},
        {"loc": url_for("public.register", _external=True), "priority": "0.8"},
        {"loc": url_for("admin.login", _external=True), "priority": "0.3"},
    ]
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        xml_parts.append("<url><loc>" + p["loc"] + "</loc><priority>" + p["priority"] + "</priority></url>")
    xml_parts.append("</urlset>")
    return Response("\n".join(xml_parts), mimetype="application/xml")


@public_bp.route("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /portal/",
        "Allow: /",
        "Sitemap: " + url_for("public.sitemap", _external=True),
    ]
    return Response("\n".join(lines), mimetype="text/plain")
