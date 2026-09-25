"""Recetas: búsqueda, filtros, favoritos e historial."""
import math
from dataclasses import dataclass

from ..extensions import db
from ..models import (RESTRICTIONS, Category, CookingHistory, FavoriteRecipe, Recipe,
                      Substitution)
from ..utils import normalize, parse_float, parse_int
from . import metrics, pricing
from .recommendation_service import is_allowed, load_recipes

QUICK_FILTERS = {
    "rapido": "⚡ Rápido",
    "economico": "💰 Económico",
    "ecuatoriano": "🇪🇨 Ecuatoriano",
    "facil": "⭐ Fácil",
}
QUICK_MINUTES = 30
CHEAP_PER_SERVING = 1.0


@dataclass
class Page:
    items: list
    page: int
    per_page: int
    total: int

    @property
    def pages(self):
        return max(1, math.ceil(self.total / self.per_page))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages


def get_by_slug(slug):
    return Recipe.query.filter_by(slug=slug, active=True).first()


def _matches_query(recipe, query):
    if normalize(recipe.name).find(query) >= 0 or query in normalize(recipe.description):
        return True
    return any(query in normalize(ri.ingredient.name) for ri in recipe.ingredients)


def filters_from_args(args):
    return {
        "q": (args.get("q") or "").strip()[:80],
        "max_minutes": parse_int(args.get("time"), minimum=1, maximum=600),
        "max_cost": parse_float(args.get("cost"), minimum=0, maximum=1000),
        "difficulty": args.get("difficulty") or None,
        "meal": args.get("meal") or None,
        "category": args.get("category") or None,
        "ingredient": parse_int(args.get("ingredient"), minimum=1),
        "quick": [q for q in args.getlist("quick") if q in QUICK_FILTERS],
        "restrictions": [r for r in args.getlist("r") if r in RESTRICTIONS],
    }


def search(filters, page=1, per_page=12):
    query = normalize(filters.get("q"))
    quick = set(filters.get("quick") or [])
    results = []
    for recipe in load_recipes():
        if query and not _matches_query(recipe, query):
            continue
        if filters.get("max_minutes") and recipe.total_minutes > filters["max_minutes"]:
            continue
        if filters.get("max_cost") is not None and recipe.estimated_cost > filters["max_cost"]:
            continue
        if filters.get("difficulty") and recipe.difficulty != filters["difficulty"]:
            continue
        if filters.get("meal") and filters["meal"] not in recipe.meal_type_list:
            continue
        if filters.get("category") and filters["category"] not in recipe.category_slugs:
            continue
        if filters.get("ingredient") and not any(
            ri.ingredient_id == filters["ingredient"] for ri in recipe.ingredients
        ):
            continue
        if filters.get("restrictions") and not is_allowed(recipe, filters["restrictions"], set()):
            continue
        if "rapido" in quick and recipe.total_minutes > QUICK_MINUTES:
            continue
        if "economico" in quick and recipe.estimated_cost / recipe.servings > CHEAP_PER_SERVING:
            continue
        if "ecuatoriano" in quick and "ecuatoriana" not in recipe.category_slugs:
            continue
        if "facil" in quick and recipe.difficulty != "Fácil":
            continue
        results.append(recipe)

    if query:  # primero las que tienen la búsqueda en el nombre
        results.sort(key=lambda r: (query not in normalize(r.name), r.name))

    page = max(1, page)
    start = (page - 1) * per_page
    return Page(items=results[start:start + per_page], page=page, per_page=per_page, total=len(results))


def categories():
    return Category.query.order_by(Category.sort_order, Category.name).all()


def substitutions_for(ingredient_ids):
    """{ingredient_id: [Substitution]} para mostrar "¿No tienes X?"."""
    result = {}
    if not ingredient_ids:
        return result
    for sub in Substitution.query.filter(Substitution.ingredient_id.in_(ingredient_ids)).all():
        result.setdefault(sub.ingredient_id, []).append(sub)
    return result


# --- Favoritos ------------------------------------------------------------

def favorite_ids(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    return {f.recipe_id for f in FavoriteRecipe.query.filter_by(user_id=user.id).all()}


def favorites(user):
    return (
        FavoriteRecipe.query.filter_by(user_id=user.id)
        .order_by(FavoriteRecipe.created_at.desc())
        .all()
    )


def toggle_favorite(user, recipe):
    """Devuelve True si quedó como favorita."""
    favorite = FavoriteRecipe.query.filter_by(user_id=user.id, recipe_id=recipe.id).first()
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        return False
    db.session.add(FavoriteRecipe(user_id=user.id, recipe_id=recipe.id))
    db.session.commit()
    metrics.track("favorite", user=user, recipe=recipe)
    return True


# --- Historial --------------------------------------------------------------

def mark_cooked(user, recipe, servings):
    scale = servings / recipe.servings if recipe.servings else 1
    entry = CookingHistory(
        user_id=user.id, recipe_id=recipe.id, servings=servings,
        estimated_cost=pricing.recipe_cost(recipe, scale=scale),
    )
    db.session.add(entry)
    db.session.commit()
    metrics.track("cooked", user=user, recipe=recipe)
    return entry


def history(user, limit=100):
    return (
        CookingHistory.query.filter_by(user_id=user.id)
        .order_by(CookingHistory.cooked_at.desc())
        .limit(limit)
        .all()
    )
