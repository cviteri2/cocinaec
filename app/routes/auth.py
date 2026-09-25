from flask import (Blueprint, current_app, flash, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import CITIES
from ..services import user_service
from ..utils import password_problem, safe_next_url

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form, errors = {}, {}
    if request.method == "POST":
        form, errors = user_service.validate_registration(request.form)
        if not errors:
            user = user_service.create_user(
                form["first_name"], form["last_name"], form["email"], form["password"], form["city"]
            )
            session.clear()
            login_user(user)
            flash(f"¡Bienvenido, {user.first_name}! Cuéntanos un poco de ti.", "success")
            return redirect(url_for("profile.onboarding"))
    form.pop("password", None)
    return render_template("auth/register.html", form=form, errors=errors, cities=CITIES)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = user_service.find_by_email(email)
        if user and user.active and user.check_password(password):
            next_url = safe_next_url(request.form.get("next") or request.args.get("next"))
            session.clear()  # evita fijación de sesión
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(next_url or url_for("main.index"))
        flash("El email o la contraseña no coinciden.", "error")
    return render_template("auth/login.html", email=email, next=request.args.get("next", ""))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Cerraste sesión. ¡Hasta pronto!", "info")
    return redirect(url_for("main.index"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Recuperación preparada: genera el enlace, pero aún no se envía correo.
    El enlace se escribe en el log del servidor."""
    if request.method == "POST":
        user = user_service.find_by_email(request.form.get("email"))
        if user and user.active:
            link = url_for("auth.reset_password", token=user_service.make_reset_token(user), _external=True)
            current_app.logger.info("Enlace de recuperación para usuario %s: %s", user.id, link)
            if current_app.debug:
                flash(f"Modo desarrollo: {link}", "info")
        # Mismo mensaje siempre, para no revelar qué emails existen
        flash("Si el email está registrado, te enviaremos un enlace para crear una nueva contraseña. "
              "(El envío de correos estará disponible próximamente.)", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = user_service.user_from_reset_token(token)
    if user is None:
        flash("El enlace expiró o no es válido. Solicita uno nuevo.", "error")
        return redirect(url_for("auth.forgot_password"))
    error = None
    if request.method == "POST":
        password = request.form.get("password") or ""
        error = password_problem(password)
        if not error and password != request.form.get("password_confirm"):
            error = "Las contraseñas no coinciden."
        if not error:
            user.set_password(password)
            db.session.commit()
            flash("Listo. Ya puedes ingresar con tu nueva contraseña.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", error=error)
