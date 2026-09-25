"""¿Qué cocino hoy? — fábrica de la aplicación Flask."""
import logging
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from flask_wtf.csrf import CSRFError

from config import get_config
from .extensions import csrf, db, login_manager


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "Falta SECRET_KEY. Defínela en el archivo .env o en las variables de entorno."
        )

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registra los modelos)

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(models.User, int(user_id))
        return user if user and user.active else None

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_cli(app)

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    return app


def _register_blueprints(app):
    from .routes.admin import bp as admin_bp
    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.cook import bp as cook_bp
    from .routes.inventory import bp as inventory_bp
    from .routes.main import bp as main_bp
    from .routes.meal_plan import bp as meal_plan_bp
    from .routes.profile import bp as profile_bp
    from .routes.recipes import bp as recipes_bp
    from .routes.shopping import bp as shopping_bp

    for bp in (main_bp, auth_bp, cook_bp, recipes_bp, inventory_bp, shopping_bp,
               meal_plan_bp, profile_bp, admin_bp, api_bp):
        app.register_blueprint(bp)


def _register_template_helpers(app):
    from . import utils
    from .models import MEAL_TYPES, SHOPPING_GROUPS

    app.jinja_env.filters["money"] = utils.money
    app.jinja_env.filters["qty"] = utils.format_quantity
    app.jinja_env.filters["minutes"] = utils.format_minutes
    app.jinja_env.filters["date_es"] = utils.format_date_es

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from .services import shopping_service

        pending = 0
        if current_user.is_authenticated:
            pending = shopping_service.pending_count(current_user)
        return {
            "MEAL_TYPES": MEAL_TYPES,
            "SHOPPING_GROUPS": SHOPPING_GROUPS,
            "shopping_pending": pending,
            "today": utils.today_local(),
        }


def _wants_json():
    return request.path.startswith("/api/") or (
        request.accept_mimetypes.best == "application/json"
    )


def _register_error_handlers(app):
    messages = {
        400: ("Algo no cuadra", "No pudimos entender esa solicitud. Intenta nuevamente."),
        403: ("No tienes acceso", "Esta sección no está disponible para tu cuenta."),
        404: ("No encontramos esa página", "Puede que el enlace haya cambiado. Volvamos a la cocina."),
        405: ("Algo no cuadra", "Esa acción no está permitida aquí."),
        413: ("Es demasiado", "La información enviada es demasiado grande."),
        500: ("Algo salió mal", "Algo salió mal. Intenta nuevamente."),
    }

    def render_error(code):
        title, text = messages.get(code, messages[500])
        if _wants_json():
            return jsonify({"error": text}), code
        return render_template("errors/error.html", code=code, title=title, text=text), code

    for code in messages:
        app.register_error_handler(code, lambda e, code=code: render_error(code))

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if _wants_json():
            return jsonify({"error": "Tu sesión expiró. Recarga la página."}), 400
        return render_template(
            "errors/error.html", code=400, title="Tu sesión expiró",
            text="Por seguridad, recarga la página e intenta nuevamente.",
        ), 400


def _register_security_headers(app):
    csp = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )

    @app.after_request
    def set_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Crea las tablas de la base de datos."""
        db.create_all()
        print("Base de datos lista.")
