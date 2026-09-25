from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import DIFFICULTIES, RESTRICTIONS, CookingHistory, FavoriteRecipe, Ingredient
from ..services import (inventory_service, meal_plan_service, metrics, recipe_service,
                        recommendation_service, shopping_service)
from ..utils import DAY_NAMES, parse_int, safe_next_url

bp = Blueprint("recipes", __name__)


def _have_ids():
    """Lo que el usuario tiene: su inventario + su última búsqueda."""
    have = set(inventory_service.ingredient_ids(current_user))
    have |= set((session.get("last_search") or {}).get("have") or [])
    return have


def _analysis(recipe):
    pref = current_user.preference if current_user.is_authenticated else None
    last = session.get("last_search") or {}
    people = parse_int(request.values.get("people"), minimum=1, maximum=20) or last.get("people") \
        or (pref.people_count if pref else recipe.servings)
    return recommendation_service.analyze_recipe(
        recipe, _have_ids(), people=people,
        restrictions=pref.restrictions if pref else last.get("restrictions") or [],
        excluded_ids=pref.excluded_ingredients if pref else [],
    )


@bp.route("/recipes")
def list_recipes():
    filters = recipe_service.filters_from_args(request.args)
    page = recipe_service.search(
        filters, page=parse_int(request.args.get("page"), default=1, minimum=1),
        per_page=current_app.config["RECIPES_PER_PAGE"],
    )
    ingredient = db.session.get(Ingredient, filters["ingredient"]) if filters["ingredient"] else None
    return render_template(
        "recipes/list.html", page=page, filters=filters, ingredient=ingredient,
        categories=recipe_service.categories(), difficulties=DIFFICULTIES,
        quick_filters=recipe_service.QUICK_FILTERS, restrictions=RESTRICTIONS,
        favorite_ids=recipe_service.favorite_ids(current_user),
        all_ingredients=Ingredient.query.filter_by(active=True, is_staple=False).order_by(Ingredient.name).all(),
    )


@bp.route("/recipes/<slug>")
def detail(slug):
    recipe = recipe_service.get_by_slug(slug) or abort(404)
    match = _analysis(recipe)
    metrics.track("recipe_view", user=current_user, recipe=recipe)
    missing_ids = [ri.ingredient_id for ri in match.missing]
    return render_template(
        "recipes/detail.html",
        recipe=recipe,
        match=match,
        have_ids=_have_ids(),
        missing_ids=set(missing_ids),
        substitutions=recipe_service.substitutions_for(missing_ids),
        substituted={ri.ingredient_id: sub for ri, sub in match.substitutions_used},
        is_favorite=recipe.id in recipe_service.favorite_ids(current_user),
        day_names=DAY_NAMES,
        plan_meals=meal_plan_service.PLAN_MEALS,
    )


@bp.route("/recipes/<slug>/missing-to-list", methods=["POST"])
@login_required
def missing_to_list(slug):
    """Función "Me falta": agrega los faltantes a la lista de compras."""
    recipe = recipe_service.get_by_slug(slug) or abort(404)
    match = _analysis(recipe)
    if not match.missing:
        flash("Ya tienes todo lo necesario. ¡A cocinar!", "success")
    else:
        shopping_service.add_missing_from_match(current_user, match)
        names = ", ".join(ri.ingredient.name.lower() for ri in match.missing)
        flash(f"Agregamos a tu lista: {names}.", "success")
    return redirect(url_for("recipes.detail", slug=slug, people=match.people))


@bp.route("/recipes/<slug>/favorite", methods=["POST"])
@login_required
def toggle_favorite(slug):
    recipe = recipe_service.get_by_slug(slug) or abort(404)
    is_favorite = recipe_service.toggle_favorite(current_user, recipe)
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"favorite": is_favorite})
    flash("Guardada en tus favoritas ❤️" if is_favorite else "La quitamos de tus favoritas.", "success")
    return redirect(safe_next_url(request.form.get("next")) or url_for("recipes.detail", slug=slug))


@bp.route("/recipes/<slug>/cooked", methods=["POST"])
@login_required
def cooked(slug):
    recipe = recipe_service.get_by_slug(slug) or abort(404)
    servings = parse_int(request.form.get("servings"), default=recipe.servings, minimum=1, maximum=20)
    recipe_service.mark_cooked(current_user, recipe, servings)
    flash("¡Buen provecho! Lo guardamos en tu historial.", "success")
    return redirect(url_for("recipes.detail", slug=slug, people=servings))


@bp.route("/favorites")
@login_required
def favorites():
    return render_template("recipes/favorites.html", favorites=recipe_service.favorites(current_user))


@bp.route("/favorites/clear", methods=["POST"])
@login_required
def clear_favorites():
    FavoriteRecipe.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash("Eliminamos tus recetas favoritas.", "info")
    return redirect(url_for("recipes.favorites"))


@bp.route("/history")
@login_required
def history():
    return render_template("recipes/history.html", entries=recipe_service.history(current_user))


@bp.route("/history/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_history(entry_id):
    entry = CookingHistory.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash("Eliminado del historial.", "info")
    return redirect(url_for("recipes.history"))
