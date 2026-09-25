"""API REST de solo lectura (fase 1).

Reutiliza los mismos servicios que las vistas web. Hoy se autentica con la
sesión del navegador; para la app móvil (fase 3/4) se agregará autenticación
por token sin cambiar los servicios.
"""
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..extensions import db
from ..models import Ingredient, IngredientCategory
from ..services import (inventory_service, meal_plan_service, recipe_service,
                        recommendation_service, shopping_service)
from ..utils import parse_int

bp = Blueprint("api", __name__, url_prefix="/api")


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Inicia sesión para continuar."}), 401
        return view(*args, **kwargs)
    return wrapper


# --- Serializadores -------------------------------------------------------

def recipe_summary(recipe):
    return {
        "id": recipe.id, "slug": recipe.slug, "name": recipe.name, "emoji": recipe.emoji,
        "description": recipe.description, "meal_types": recipe.meal_type_list,
        "servings": recipe.servings, "total_minutes": recipe.total_minutes,
        "difficulty": recipe.difficulty,
        "estimated_cost": recipe.estimated_cost, "cost_note": "Costo estimado de referencia",
        "categories": [c.slug for c in recipe.categories],
    }


def recipe_detail(recipe):
    data = recipe_summary(recipe)
    data.update({
        "prep_minutes": recipe.prep_minutes, "cook_minutes": recipe.cook_minutes,
        "equipment": recipe.equipment,
        "ingredients": [
            {"ingredient_id": ri.ingredient_id, "name": ri.ingredient.name, "quantity": ri.quantity,
             "unit": ri.unit, "note": ri.note, "optional": ri.optional, "staple": ri.ingredient.is_staple}
            for ri in recipe.ingredients
        ],
        "steps": [s.text for s in recipe.steps],
    })
    return data


def match_json(match):
    return {
        "recipe": recipe_summary(match.recipe),
        "people": match.people,
        "coverage_pct": match.coverage_pct,
        "have": match.have_count,
        "required": match.required_count,
        "missing": [{"ingredient_id": ri.ingredient_id, "name": ri.ingredient.name} for ri in match.missing],
        "missing_cost": match.missing_cost,
        "total_cost": match.total_cost,
        "fits_time": match.fits_time,
        "fits_budget": match.fits_budget,
    }


# --- Endpoints públicos ---------------------------------------------------

@bp.route("/recipes")
def recipes():
    filters = recipe_service.filters_from_args(request.args)
    page = recipe_service.search(filters, page=parse_int(request.args.get("page"), default=1, minimum=1),
                                 per_page=parse_int(request.args.get("per_page"), default=20, minimum=1, maximum=100))
    return jsonify({"items": [recipe_summary(r) for r in page.items], "page": page.page,
                    "pages": page.pages, "total": page.total})


@bp.route("/recipes/<slug>")
def recipe(slug):
    item = recipe_service.get_by_slug(slug)
    if item is None:
        return jsonify({"error": "No encontramos esa receta."}), 404
    return jsonify(recipe_detail(item))


@bp.route("/ingredients")
def ingredients():
    categories = IngredientCategory.query.order_by(IngredientCategory.sort_order).all()
    return jsonify([
        {"category": c.name, "slug": c.slug, "items": [
            {"id": i.id, "name": i.name, "emoji": i.emoji, "unit": i.unit, "staple": i.is_staple}
            for i in sorted(c.ingredients, key=lambda i: i.name) if i.active
        ]} for c in categories
    ])


@bp.route("/recommendations")
def recommendations():
    user = current_user if current_user.is_authenticated else None
    criteria, unknown = recommendation_service.criteria_from_args(request.args, user)
    if not criteria.have_ids:
        return jsonify({"error": "Agrega al menos un ingrediente para encontrar recetas."}), 400
    limit = parse_int(request.args.get("limit"), default=3, minimum=1, maximum=10)
    matches = recommendation_service.recommend(criteria, limit=limit)
    return jsonify({"items": [match_json(m) for m in matches], "unknown_ingredients": unknown,
                    "message": "Elegimos estas opciones según lo que tienes y tus preferencias."})


# --- Endpoints del usuario ------------------------------------------------

@bp.route("/inventory")
@api_login_required
def inventory():
    return jsonify([
        {"id": i.id, "ingredient_id": i.ingredient_id, "name": i.ingredient.name, "quantity": i.quantity,
         "unit": i.unit, "expiration_date": i.expiration_date.isoformat() if i.expiration_date else None}
        for i in inventory_service.items_for(current_user)
    ])


@bp.route("/shopping-list")
@api_login_required
def shopping_list():
    active = shopping_service.get_active_list(current_user)
    db.session.commit()
    return jsonify([
        {"id": i.id, "name": i.name, "quantity": i.quantity, "unit": i.unit, "category": i.category,
         "checked": i.checked}
        for i in active.items
    ])


@bp.route("/meal-plan")
@api_login_required
def meal_plan():
    plan = meal_plan_service.get_plan(current_user)
    if plan is None:
        return jsonify({"plan": None})
    return jsonify({
        "week_start": plan.week_start.isoformat(), "people": plan.people_count,
        "budget": meal_plan_service.budget_summary(plan),
        "items": [{"id": i.id, "day": i.day, "meal": i.meal_type, "servings": i.servings,
                   "recipe": recipe_summary(i.recipe)} for i in plan.items],
    })


@bp.route("/favorites")
@api_login_required
def favorites():
    return jsonify([recipe_summary(f.recipe) for f in recipe_service.favorites(current_user)])


@bp.route("/profile")
@api_login_required
def profile():
    pref = current_user.preference
    excluded = Ingredient.query.filter(Ingredient.id.in_(pref.excluded_ingredients or [])).all() if pref else []
    return jsonify({
        "first_name": current_user.first_name, "last_name": current_user.last_name,
        "city": current_user.city,
        "preferences": {
            "people_count": pref.people_count if pref else None,
            "default_time": pref.default_time if pref else None,
            "default_budget": pref.default_budget if pref else None,
            "food_preferences": pref.food_preferences if pref else [],
            "restrictions": pref.restrictions if pref else [],
            "excluded_ingredients": [i.name for i in excluded],
        },
    })
