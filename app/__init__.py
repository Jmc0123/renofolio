"""Application factory for Renofolio, the interior design project (IDP) matching platform."""
import os
import posixpath
import secrets

from flask import Flask, abort, request

from app.common.text import plural, friendly_date, friendly_datetime
from app.entity.database import init_db, DatabaseConnection
from app.entity.interior_design_projects import InteriorDesignProjects

SECRET_KEY_FILE = ".renofolio_secret_key"


# Builds the Flask app: settings, database, routes and the template helpers.
def create_app(db_path=None, testing=False):
    app = Flask(__name__)
    db_path = db_path or os.environ.get("IDP_DB_PATH") or DatabaseConnection.path
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or load_secret_key(db_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        TESTING=testing,
    )
    init_db(db_path)

    from app.boundary.routes import register_routes
    register_routes(app)

    # Serves only uploaded photos that a project still references, including after a replacement.
    @app.before_request
    def reject_unreferenced_upload():
        if request.endpoint == "static":
            filename = posixpath.normpath(request.view_args["filename"])
            if filename.startswith("uploads/idp/") and not InteriorDesignProjects().hasPhotoReference(f"/static/{filename}"):
                abort(404)

    # Shows the same cent-precision budget used by filtering, dropping only a zero cents part.
    @app.template_filter("money")
    def money(value):
        try:
            amount = float(value)
            return f"S${amount:,.2f}".removesuffix(".00")
        except (TypeError, ValueError):
            return "-"

    # Shows a stored date or timestamp as "28 Oct 2026".
    @app.template_filter("day")
    def day(value):
        return friendly_date(value)

    # Shows a stored timestamp as "28 Oct 2026, 9:15 AM".
    @app.template_filter("datetime")
    def datetime_text(value):
        return friendly_datetime(value)

    # Shows a count with the right noun, e.g. {{ 1|plural('account') }} gives "1 account".
    @app.template_filter("plural")
    def plural_text(count, word):
        return plural(count, word)

    return app


# Reads the secret key saved next to the database, creating it on the first start (8 November).
# Keeping the same key means a restart does not log everyone out. The file is excluded from Git.
def load_secret_key(db_path):
    folder = os.path.dirname(os.path.abspath(db_path))
    path = os.path.join(folder, SECRET_KEY_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            key = handle.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(key)
        os.chmod(path, 0o600)
    except OSError:
        pass  # A read-only folder still works; the key just changes on the next start.
    return key
