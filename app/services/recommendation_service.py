"""Motor determinístico de "¿Qué cocino hoy?".

No hay IA. Cada receta recibe puntos según:
    ingredientes disponibles  hasta 40:
        30 por cobertura ponderada (pesa más la proteína y la base del plato
           que el culantro o el pimiento)
        10 por aprovechar lo que tienes (cuántos de tus ingredientes usa)
    tiempo disponible         hasta 20
    presupuesto               hasta 20 (costo de lo que falta comprar)
    preferencias              hasta 10
    tipo de comida            hasta 10

Reglas duras (la receta no se muestra):
    - contiene un ingrediente que el usuario evita;
    - no respeta una restricción alimentaria (vegetariano, sin cerdo, ...).

Los básicos de despensa (sal, aceite, ajo, condimentos) se asumen disponibles.
Si el usuario tiene un sustituto válido (p. ej. pollo en lugar de pechuga),
el ingrediente cuenta como disponible.

Al usuario nunca se le muestra el puntaje; solo "Tienes X de Y ingredientes".
Una futura capa de IA solo tendría que traducir lenguaje natural a un
`Criteria`; el motor no cambia.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import MEAL_TYPES, RESTRICTIONS, Ingredient, Recipe, RecipeIngredient, Substitution
from ..utils import normalize, parse_float, parse_int
from . import pricing

TIME_OPTIONS = [(15, "15 min"), (30, "30 min"), (45, "45 min"), (60, "60 min"), (0, "Más de 1 hora")]
BUDGET_OPTIONS = [(3, "Hasta $3"), (5, "Hasta $5"), (8, "Hasta $8"), (10, "Hasta $10"),
                  (0, "Sin límite específico")]
PEOPLE_OPTIONS = [1, 2, 3, 4, 5, 6]
TIME_TOLERANCE = 15  # minutos


@dataclass
class Criteria:
    have_ids: set = field(default_factory=set)
    people: int = 2
    meal_type: str | None = None
    max_minutes: int | None = None  # None = sin límite
    budget: float | None = None  # sobre lo que falta comprar; None = sin límite
    restrictions: list = field(default_factory=list)
    excluded_ids: set = field(default_factory=set)
    preferences: set = field(default_factory=set)  # slugs de Category


@dataclass
class Match:
    recipe: Recipe
    people: int
    scale: float
    required_count: int
    have_count: int
    missing: list  # RecipeIngredient que faltan (obligatorios)
    substitutions_used: list  # (RecipeIngredient, Ingredient sustituto)
    skipped_optional: list  # opcionales que no respetan restricciones
    missing_cost: float
    total_cost: float
    fits_time: bool
    fits_budget: bool
    meal_ok: bool
    score: float

    @property
    def coverage_pct(self):
        if not self.required_count:
            return 100
        return round(100 * self.have_count / self.required_count)


class RecommendationContext:
    """Datos compartidos por todas las recetas en una misma búsqueda."""

    def __init__(self):
        self.costs = pricing.unit_costs()
        self.substitutes = {}
        for sub in Substitution.query.all():
            self.substitutes.setdefault(sub.ingredient_id, set()).add(sub.substitute_id)


MAIN_CATEGORIES = {"granos-cereales", "legumbres", "tuberculos-platanos"}


def ingredient_weight(ingredient):
    """Importancia de un ingrediente dentro de un plato."""
    if ingredient.is_meat or ingredient.is_fish or ingredient.is_seafood:
        return 3
    if ingredient.is_egg or (ingredient.category and ingredient.category.slug in MAIN_CATEGORIES):
        return 2
    return 1


def load_recipes():
    return (
        Recipe.query.filter_by(active=True)
        .options(selectinload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient))
        .order_by(Recipe.name)
        .all()
    )


def is_allowed(recipe, restrictions, excluded_ids):
    for ri in recipe.ingredients:
        if ri.optional:
            continue
        if ri.ingredient_id in excluded_ids:
            return False
        if any(ri.ingredient.violates(r) for r in restrictions):
            return False
    return True


def match_recipe(recipe, criteria, ctx):
    people = criteria.people or recipe.servings
    scale = people / recipe.servings if recipe.servings else 1

    required, missing, substitutions_used, skipped_optional = [], [], [], []
    have_count = 0
    have_weight = total_weight = 0
    used_have_ids = set()
    for ri in recipe.ingredients:
        ing = ri.ingredient
        if ri.optional:
            if ri.ingredient_id in criteria.excluded_ids or any(
                ing.violates(r) for r in criteria.restrictions
            ):
                skipped_optional.append(ri)
            continue
        if ing.is_staple:
            continue
        required.append(ri)
        weight = ingredient_weight(ing)
        total_weight += weight
        if ri.ingredient_id in criteria.have_ids:
            have_count += 1
            have_weight += weight
            used_have_ids.add(ri.ingredient_id)
            continue
        substitute_ids = ctx.substitutes.get(ri.ingredient_id, set()) & criteria.have_ids
        if substitute_ids:
            have_count += 1
            have_weight += weight
            substitute = db.session.get(Ingredient, min(substitute_ids))
            used_have_ids.add(substitute.id)
            substitutions_used.append((ri, substitute))
        else:
            missing.append(ri)

    coverage = have_weight / total_weight if total_weight else 1.0
    usage = len(used_have_ids) / len(criteria.have_ids) if criteria.have_ids else 0
    missing_cost = round(sum(pricing.line_cost(ri, ctx.costs, scale) for ri in missing), 2)
    total_cost = pricing.recipe_cost(recipe, ctx.costs, scale)

    # Tiempo
    total = recipe.total_minutes
    if criteria.max_minutes is None or total <= criteria.max_minutes:
        time_points, fits_time = 20, True
    elif total <= criteria.max_minutes + TIME_TOLERANCE:
        time_points, fits_time = 8, False
    else:
        time_points, fits_time = 0, False

    # Presupuesto (solo lo que hay que comprar)
    if criteria.budget is None or missing_cost <= criteria.budget:
        budget_points, fits_budget = 20, True
    elif missing_cost <= criteria.budget * 1.25:
        budget_points, fits_budget = 8, False
    else:
        budget_points, fits_budget = 0, False

    # Preferencias
    if criteria.preferences:
        pref_points = 10 if recipe.category_slugs & criteria.preferences else 0
    else:
        pref_points = 5

    # Tipo de comida
    meal_ok = criteria.meal_type is None or criteria.meal_type in recipe.meal_type_list
    meal_points = 10 if meal_ok else 0

    score = 30 * coverage + 10 * usage + time_points + budget_points + pref_points + meal_points

    return Match(
        recipe=recipe, people=people, scale=scale,
        required_count=len(required), have_count=have_count,
        missing=missing, substitutions_used=substitutions_used,
        skipped_optional=skipped_optional,
        missing_cost=missing_cost, total_cost=total_cost,
        fits_time=fits_time, fits_budget=fits_budget, meal_ok=meal_ok,
        score=round(score, 2),
    )


def _sort_key(match):
    return (
        match.meal_ok,
        match.fits_time,
        match.fits_budget,
        match.score,
        -len(match.missing),
        -match.recipe.total_minutes,
    )


def recommend(criteria, limit=3, recipes=None):
    """Devuelve las mejores coincidencias (máximo `limit`)."""
    ctx = RecommendationContext()
    recipes = recipes if recipes is not None else load_recipes()
    matches = []
    for recipe in recipes:
        if not is_allowed(recipe, criteria.restrictions, criteria.excluded_ids):
            continue
        match = match_recipe(recipe, criteria, ctx)
        if criteria.have_ids and match.required_count and match.have_count == 0:
            continue  # no usa nada de lo que tienes
        if criteria.max_minutes is not None and match.recipe.total_minutes > criteria.max_minutes + TIME_TOLERANCE:
            continue  # se pasa demasiado del tiempo disponible
        matches.append(match)
    matches.sort(key=_sort_key, reverse=True)
    return matches[:limit] if limit else matches


def cook_with_what_i_have(have_ids, people=2, restrictions=(), excluded_ids=(), limit=6):
    """"Cocina con lo que tengo": prioriza usar lo que hay y comprar lo mínimo."""
    criteria = Criteria(have_ids=set(have_ids), people=people,
                        restrictions=list(restrictions), excluded_ids=set(excluded_ids))
    ctx = RecommendationContext()
    matches = []
    for recipe in load_recipes():
        if not is_allowed(recipe, criteria.restrictions, criteria.excluded_ids):
            continue
        match = match_recipe(recipe, criteria, ctx)
        if match.have_count == 0:
            continue
        matches.append(match)
    matches.sort(key=lambda m: (len(m.missing), -m.coverage_pct, m.recipe.total_minutes))
    return matches[:limit]


def analyze_recipe(recipe, have_ids, people=None, restrictions=(), excluded_ids=()):
    """Coincidencia de una sola receta (para la página de detalle)."""
    criteria = Criteria(have_ids=set(have_ids), people=people or recipe.servings,
                        restrictions=list(restrictions), excluded_ids=set(excluded_ids))
    return match_recipe(recipe, criteria, RecommendationContext())


# --- Lectura de parámetros --------------------------------------------------

def resolve_ingredient_names(names):
    """Convierte nombres escritos a mano en ingredientes del catálogo."""
    catalog = {normalize(i.name): i for i in Ingredient.query.filter_by(active=True).all()}
    found, unknown = [], []
    for raw in names:
        key = normalize(raw)
        if not key:
            continue
        ingredient = catalog.get(key)
        if ingredient is None:
            # coincidencia parcial: "pollo" encuentra "Pollo (presas)"
            candidates = [
                (not name.startswith(key), len(name), ing)
                for name, ing in catalog.items()
                if len(key) >= 3 and (name.startswith(key) or key in name.split())
            ]
            ingredient = min(candidates, key=lambda c: c[:2])[2] if candidates else None
        if ingredient:
            found.append(ingredient)
        else:
            unknown.append(raw.strip()[:40])
    return found, unknown


def criteria_from_args(args, user=None):
    """Lee el formulario "¿Qué cocino?" (parámetros GET)."""
    pref = getattr(user, "preference", None) if user is not None else None

    have_ids = {i for i in (parse_int(v) for v in args.getlist("i")) if i}
    extra = [e for raw in args.getlist("extra") for e in raw.split(",")]
    found, unknown = resolve_ingredient_names(extra)
    have_ids |= {ing.id for ing in found}

    people = parse_int(args.get("people"), default=None, minimum=1, maximum=20)
    if people is None:
        people = pref.people_count if pref else 2

    meal_type = args.get("meal")
    meal_type = meal_type if meal_type in MEAL_TYPES else None

    minutes = parse_int(args.get("time"), default=None, minimum=0, maximum=600)
    max_minutes = None if not minutes else minutes

    budget = parse_float(args.get("budget"), default=None, minimum=0, maximum=1000)
    budget = None if not budget else budget

    if "r" in args or "rset" in args:
        restrictions = [r for r in args.getlist("r") if r in RESTRICTIONS]
    else:
        restrictions = list(pref.restrictions) if pref else []

    return Criteria(
        have_ids=have_ids,
        people=people,
        meal_type=meal_type,
        max_minutes=max_minutes,
        budget=budget,
        restrictions=restrictions,
        excluded_ids=set(pref.excluded_ingredients) if pref else set(),
        preferences=set(pref.food_preferences) if pref else set(),
    ), unknown
