# oauth.py
# Sets up "Sign in with Google" using Authlib. If GOOGLE_CLIENT_ID and
# GOOGLE_CLIENT_SECRET are left blank in the .env file, we still register
# the client (Authlib is fine with empty strings) but config.GOOGLE_LOGIN_ENABLED
# will be False, and the routes that use this check that flag first and
# show a friendly message instead of trying to talk to Google with no
# credentials.

from authlib.integrations.flask_client import OAuth

import config

oauth = OAuth()


def init_app(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID or "not-configured",
        client_secret=config.GOOGLE_CLIENT_SECRET or "not-configured",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
