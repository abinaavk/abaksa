# auth.py
# Handles logins for the whole site using Flask-Login. Flask-Login needs a
# "User" class with a few specific methods on it (get_id, is_authenticated
# etc) - rather than writing our own User class from scratch, we just wrap
# the sqlite3.Row we get back from the database in a small class that
# Flask-Login knows how to talk to.

from functools import wraps

from flask import redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, current_user

import database
import config

login_manager = LoginManager()
login_manager.login_view = "public.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"


class AppUser(UserMixin):
    # small wrapper around a users table row so Flask-Login can use it
    def __init__(self, row):
        self.row = row

    def get_id(self):
        return str(self.row["id"])

    @property
    def id(self):
        return self.row["id"]

    @property
    def username(self):
        return self.row["username"]

    @property
    def full_name(self):
        return self.row["full_name"]

    @property
    def email(self):
        return self.row["email"]

    @property
    def role(self):
        return self.row["role"]

    @property
    def avatar_url(self):
        return self.row["avatar_url"]

    @property
    def is_admin(self):
        return self.row["role"] == config.ROLE_ADMIN

    @property
    def is_customer(self):
        return self.row["role"] == config.ROLE_CUSTOMER

    def __getitem__(self, key):
        # lets templates/code do current_user["email"] like a normal db row too
        return self.row[key]


@login_manager.user_loader
def load_user(user_id):
    row = database.get_user_by_id(int(user_id))
    if row is None or not row["is_active"]:
        return None
    return AppUser(row)


def init_app(app):
    login_manager.init_app(app)


def admin_required(view_func):
    # use this on any admin panel route - blocks anyone who isn't logged
    # in as an admin, and sends customers back to their own portal
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("admin.login"))
        if not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def customer_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("public.login"))
        if not current_user.is_customer:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped
