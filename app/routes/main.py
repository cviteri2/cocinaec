from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import ContactMessage
from ..services import (inventory_service, meal_plan_service, recipe_service,
                        recommendation_service, shopping_service)
from ..utils import clean_text, is_valid_email

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return home()
    return render_template("main/landing.html")


def home():
    user = current_user
    if not user.onboarding_done:
        return redirect(url_for("profile.onboarding"))

    have = inventory_service.ingredient_ids(user)
    suggestions = []
    if have:
        pref = user.preference
        criteria = recommendation_service.Criteria(
            have_ids=have,
            people=pref.people_count if pref else 2,
            max_minutes=pref.default_time if pref else None,
            budget=pref.default_budget if pref else None,
            restrictions=list(pref.restrictions) if pref else [],
            excluded_ids=set(pref.excluded_ingredients) if pref else set(),
            preferences=set(pref.food_preferences) if pref else set(),
        )
        suggestions = recommendation_service.recommend(criteria, limit=3)

    favorites = [f.recipe for f in recipe_service.favorites(user)[:3]]
    plan = meal_plan_service.get_plan(user)
    shopping_list = shopping_service.get_active_list(user, create=False)
    pending_items = [i for i in shopping_list.items if not i.checked][:4] if shopping_list else []
    return render_template(
        "main/home.html",
        suggestions=suggestions,
        favorites=favorites,
        favorite_ids=recipe_service.favorite_ids(user),
        plan=plan,
        plan_grid=meal_plan_service.grid(plan) if plan else None,
        use_first=inventory_service.use_first(user),
        pending_items=pending_items,
    )


@bp.route("/privacy")
def privacy():
    return render_template("main/privacy.html")


@bp.route("/terms")
def terms():
    return render_template("main/terms.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = {"name": "", "email": "", "message": ""}
    errors = {}
    if current_user.is_authenticated:
        form.update(name=current_user.full_name, email=current_user.email)
    if request.method == "POST":
        form = {
            "name": clean_text(request.form.get("name"), 80),
            "email": clean_text(request.form.get("email"), 255),
            "message": clean_text(request.form.get("message"), 3000),
        }
        if not form["name"]:
            errors["name"] = "Cuéntanos tu nombre."
        if not is_valid_email(form["email"]):
            errors["email"] = "Revisa tu email."
        if len(form["message"]) < 5:
            errors["message"] = "Escribe tu mensaje."
        if not errors:
            db.session.add(ContactMessage(
                **form, user_id=current_user.id if current_user.is_authenticated else None
            ))
            db.session.commit()
            flash("¡Gracias! Recibimos tu mensaje.", "success")
            return redirect(url_for("main.contact"))
    return render_template("main/contact.html", form=form, errors=errors)
