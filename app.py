# app.py
# This is the file you run to start the website:
#   python3 app.py
#
# It creates the Flask app, hooks up the database, login system, Google
# sign-in, and all three blueprints (public pages, the customer portal,
# and the admin panel), then starts the dev server.

from datetime import datetime

from flask import Flask, render_template
from flask_login import current_user

import config
import database
import auth
import oauth
from routes.public import public_bp
from routes.customer import portal_bp
from routes.admin import admin_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit, just in case

    database.init_app(app)
    auth.init_app(app)
    oauth.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)

    # a few things every single template needs - rather than passing them
    # into every render_template() call, we make them available everywhere
    @app.context_processor
    def inject_globals():
        unread = 0
        topbar_notifications = []
        if current_user.is_authenticated:
            unread = database.unread_notification_count(current_user.id)
            topbar_notifications = database.list_notifications(current_user.id, limit=6)
        return {
            "app_name": config.APP_NAME,
            "app_tagline": config.APP_TAGLINE,
            "app_version": config.APP_VERSION,
            "current_year": datetime.now().year,
            "unread_notification_count": unread,
            "topbar_notifications": topbar_notifications,
            "google_login_enabled": config.GOOGLE_LOGIN_ENABLED,
        }

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
