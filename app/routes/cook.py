"""Flujo principal: "¿Qué cocino?" y "Cocina con lo que tengo"."""
from flask import Blueprint, render_template, request, session
from flask_login import current_user

from ..models import RESTRICTIONS
from ..services import inventory_service, metrics, recipe_service, recommendation_service as rec

bp = Blueprint("cook", __name__, url_prefix="/cook")


def _user():
    return current_user if current_user.is_authenticated else None


def _form_defaults():
    """Valores iniciales: última búsqueda > inventario > preferencias."""
    user = _user()
    pref = user.preference if user else None
    last = session.get("last_search") or {}
    selected = set(last.get("have") or []) or inventory_service.ingredient_ids(user)
    return {
        "selected": selected,
        "people": last.get("people") or (pref.people_count if pref else 2),
        "meal": last.get("meal") or "almuerzo",
        "time": last.get("time") if last.get("time") is not None else (pref.default_time if pref else 45) or 0,
        "budget": last.get("budget") if last.get("budget") is not None else (pref.default_budget if pref else 5) or 0,
        "restrictions": set(last.get("restrictions") or (pref.restrictions if pref else [])),
    }


def _render_form(defaults, error=None):
    return render_template(
        "cook/form.html",
        d=defaults,
        error=error,
        catalog=inventory_service.grouped_catalog(),
        staples=inventory_service.staples(),
        restrictions=RESTRICTIONS,
        time_options=rec.TIME_OPTIONS,
        budget_options=rec.BUDGET_OPTIONS,
        people_options=rec.PEOPLE_OPTIONS,
        has_inventory=bool(inventory_service.ingredient_ids(_user())),
    ), (400 if error else 200)


@bp.route("/")
def form():
    return _render_form(_form_defaults())


@bp.route("/results")
def results():
    criteria, unknown = rec.criteria_from_args(request.args, _user())
    if not criteria.have_ids:
        defaults = _form_defaults()
        defaults["selected"] = set()
        return _render_form(defaults, error="Agrega al menos un ingrediente para encontrar recetas.")

    matches = rec.recommend(criteria, limit=3)
    session["last_search"] = {
        "have": sorted(criteria.have_ids), "people": criteria.people, "meal": criteria.meal_type,
        "time": criteria.max_minutes or 0, "budget": criteria.budget or 0,
        "restrictions": criteria.restrictions,
    }
    metrics.track("recommendation", user=current_user, ingredients=sorted(criteria.have_ids),
                  people=criteria.people, results=len(matches))
    return render_template(
        "cook/results.html",
        matches=matches,
        criteria=criteria,
        unknown=unknown,
        favorite_ids=recipe_service.favorite_ids(current_user),
    )


@bp.route("/pantry")
def pantry():
    """Cocina con lo que tengo: solo ingredientes, sin tiempo ni presupuesto."""
    user = _user()
    pref = user.preference if user else None
    submitted = "i" in request.args or "extra" in request.args
    matches, unknown = [], []
    if submitted:
        criteria, unknown = rec.criteria_from_args(request.args, user)
        selected = criteria.have_ids
        if selected:
            matches = rec.cook_with_what_i_have(
                selected, people=criteria.people, restrictions=criteria.restrictions,
                excluded_ids=criteria.excluded_ids,
            )
            session["last_search"] = {**(session.get("last_search") or {}),
                                      "have": sorted(selected), "people": criteria.people}
            metrics.track("pantry_search", user=current_user, ingredients=sorted(selected),
                          results=len(matches))
    else:
        selected = inventory_service.ingredient_ids(user)
    return render_template(
        "cook/pantry.html",
        submitted=submitted,
        selected=selected,
        matches=matches,
        unknown=unknown,
        people=pref.people_count if pref else 2,
        catalog=inventory_service.grouped_catalog(),
        staples=inventory_service.staples(),
    ), (400 if submitted and not selected else 200)
