import json

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from ..extensions import db
from ..models import (CITIES, RESTRICTIONS, CookingHistory, FamilyMember, FavoriteRecipe,
                      Ingredient)
from ..services import inventory_service, recipe_service, shopping_service, user_service
from ..services.recommendation_service import BUDGET_OPTIONS, PEOPLE_OPTIONS, TIME_OPTIONS
from ..utils import clean_text, password_problem

bp = Blueprint("profile", __name__)


@bp.before_request
@login_required
def require_login():
    pass


def _preference_context():
    return {
        "categories": recipe_service.categories(),
        "restrictions": RESTRICTIONS,
        "catalog": inventory_service.grouped_catalog(include_staples=True),
        "time_options": TIME_OPTIONS,
        "budget_options": BUDGET_OPTIONS,
        "people_options": PEOPLE_OPTIONS,
        "pref": current_user.preference,
    }


@bp.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if request.method == "POST":
        user_service.update_preferences(current_user, request.form)
        current_user.onboarding_done = True
        db.session.commit()
        flash("¡Listo! Ya podemos ayudarte a decidir qué cocinar.", "success")
        return redirect(url_for("main.index"))
    return render_template("profile/onboarding.html", **_preference_context())


@bp.route("/profile", methods=["GET", "POST"])
def profile():
    errors = {}
    if request.method == "POST":
        section = request.form.get("section")
        if section == "personal":
            first = clean_text(request.form.get("first_name"), 60)
            last = clean_text(request.form.get("last_name"), 60)
            city = request.form.get("city")
            if not first or not last:
                errors["personal"] = "Nombre y apellido son necesarios."
            elif city not in CITIES:
                errors["personal"] = "Elige una ciudad de la lista."
            else:
                current_user.first_name, current_user.last_name, current_user.city = first, last, city
                db.session.commit()
                flash("Datos actualizados.", "success")
                return redirect(url_for("profile.profile"))
        elif section == "preferences":
            user_service.update_preferences(current_user, request.form)
            flash("Preferencias guardadas.", "success")
            return redirect(url_for("profile.profile"))
        elif section == "password":
            if not current_user.check_password(request.form.get("current_password") or ""):
                errors["password"] = "La contraseña actual no es correcta."
            else:
                new = request.form.get("new_password") or ""
                problem = password_problem(new)
                if problem:
                    errors["password"] = problem
                elif new != request.form.get("new_password_confirm"):
                    errors["password"] = "Las contraseñas no coinciden."
                else:
                    current_user.set_password(new)
                    db.session.commit()
                    flash("Contraseña actualizada.", "success")
                    return redirect(url_for("profile.profile"))
    pref = current_user.preference
    excluded = Ingredient.query.filter(Ingredient.id.in_(pref.excluded_ingredients or [])).all() if pref else []
    return render_template("profile/profile.html", errors=errors, cities=CITIES, excluded=excluded,
                           **_preference_context())


@bp.route("/profile/family", methods=["GET", "POST"])
def family():
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 60)
        if not name:
            flash("Escribe el nombre.", "error")
        else:
            db.session.add(FamilyMember(
                user_id=current_user.id, name=name,
                relationship=clean_text(request.form.get("relationship"), 40),
                food_preferences=clean_text(request.form.get("food_preferences"), 255),
                avoided_foods=clean_text(request.form.get("avoided_foods"), 255),
            ))
            db.session.commit()
            flash(f"{name} se unió a tu familia en la app.", "success")
        return redirect(url_for("profile.family"))
    members = FamilyMember.query.filter_by(user_id=current_user.id).order_by(FamilyMember.name).all()
    return render_template("profile/family.html", members=members)


@bp.route("/profile/family/<int:member_id>/delete", methods=["POST"])
def delete_family_member(member_id):
    member = FamilyMember.query.filter_by(id=member_id, user_id=current_user.id).first() or abort(404)
    db.session.delete(member)
    db.session.commit()
    flash("Eliminado.", "info")
    return redirect(url_for("profile.family"))


@bp.route("/profile/export")
def export():
    data = json.dumps(user_service.export_data(current_user), ensure_ascii=False, indent=2)
    return Response(data, mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=mis-datos-quecocinohoy.json"})


@bp.route("/profile/delete-data", methods=["POST"])
def delete_data():
    what = request.form.get("what")
    if what == "inventory":
        inventory_service.clear(current_user)
        flash("Eliminamos tu inventario.", "info")
    elif what == "shopping":
        shopping_service.clear_all(current_user)
        flash("Eliminamos tu lista de compras.", "info")
    elif what == "favorites":
        FavoriteRecipe.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash("Eliminamos tus favoritas.", "info")
    elif what == "history":
        CookingHistory.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash("Eliminamos tu historial.", "info")
    else:
        abort(400)
    return redirect(url_for("profile.profile") + "#privacidad")


@bp.route("/profile/delete", methods=["GET", "POST"])
def delete_account():
    error = None
    if request.method == "POST":
        if not current_user.check_password(request.form.get("password") or ""):
            error = "La contraseña no es correcta."
        elif request.form.get("confirm") != "ELIMINAR":
            error = "Escribe ELIMINAR para confirmar."
        else:
            user = current_user._get_current_object()
            logout_user()
            user_service.delete_account(user)
            flash("Tu cuenta y tus datos fueron eliminados. Gracias por haber cocinado con nosotros.", "info")
            return redirect(url_for("main.index"))
    return render_template("profile/delete.html", error=error)
