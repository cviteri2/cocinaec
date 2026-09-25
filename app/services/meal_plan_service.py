"""Plan semanal, generación automática y lista de compras consolidada."""
import random

from ..extensions import db
from ..models import MealPlan, MealPlanItem
from ..utils import DAY_NAMES, week_start
from . import inventory_service, metrics, pricing, shopping_service
from .recommendation_service import is_allowed, load_recipes

PLAN_MEALS = {"almuerzo": "Almuerzo", "cena": "Cena"}
PROTEIN_SLUGS = ("pollo", "carnes", "pescado", "vegetariana")


def get_plan(user, start=None, create=False, people=None):
    start = start or week_start()
    plan = MealPlan.query.filter_by(user_id=user.id, week_start=start).first()
    if plan is None and create:
        pref = user.preference
        plan = MealPlan(user_id=user.id, week_start=start,
                        people_count=people or (pref.people_count if pref else 2))
        db.session.add(plan)
        db.session.flush()
    return plan


def get_item(user, item_id):
    return (
        MealPlanItem.query.join(MealPlan)
        .filter(MealPlanItem.id == item_id, MealPlan.user_id == user.id)
        .first()
    )


def grid(plan):
    """[(indice, nombre_dia, {comida: item})] para los 7 días."""
    cells = {}
    if plan:
        for item in plan.items:
            cells[(item.day, item.meal_type)] = item
    return [(d, DAY_NAMES[d], {m: cells.get((d, m)) for m in PLAN_MEALS}) for d in range(7)]


def item_cost(item, costs=None):
    scale = item.servings / item.recipe.servings if item.recipe.servings else 1
    return pricing.recipe_cost(item.recipe, costs, scale)


def plan_cost(plan):
    if not plan:
        return 0
    costs = pricing.unit_costs()
    return round(sum(item_cost(item, costs) for item in plan.items), 2)


def budget_summary(plan):
    estimated = plan_cost(plan)
    budget = plan.weekly_budget if plan else None
    return {
        "budget": budget,
        "estimated": estimated,
        "available": round(budget - estimated, 2) if budget is not None else None,
    }


def set_item(plan, day, meal_type, recipe, servings=None):
    item = MealPlanItem.query.filter_by(meal_plan_id=plan.id, day=day, meal_type=meal_type).first()
    if item is None:
        item = MealPlanItem(meal_plan_id=plan.id, day=day, meal_type=meal_type)
        db.session.add(item)
    item.recipe_id = recipe.id
    item.recipe = recipe
    item.servings = servings or plan.people_count
    db.session.commit()
    return item


def _protein(recipe):
    for slug in PROTEIN_SLUGS:
        if slug in recipe.category_slugs:
            return slug
    return None


def generate(user, people, weekly_budget, meals, preferences=(), restrictions=(), start=None, rng=None):
    """Arma un plan variado que intenta respetar el presupuesto semanal.

    Algoritmo simple: recorre los espacios (día, comida) y elige la receta mejor
    valorada que no se haya repetido, que no repita la proteína del espacio
    anterior y cuyo costo no supere lo que queda de presupuesto por espacio.
    """
    rng = rng or random.Random()
    meals = [m for m in meals if m in PLAN_MEALS] or ["almuerzo"]
    preferences = set(preferences)
    pref = user.preference
    excluded = set(pref.excluded_ingredients) if pref else set()
    have = inventory_service.ingredient_ids(user)
    costs = pricing.unit_costs()

    candidates = [r for r in load_recipes() if is_allowed(r, restrictions, excluded)]
    rng.shuffle(candidates)  # variedad entre planes generados

    def cost_of(recipe):
        return pricing.recipe_cost(recipe, costs, people / recipe.servings)

    def appeal(recipe):
        pref_points = 10 if recipe.category_slugs & preferences else 0
        required = [ri for ri in recipe.ingredients if not ri.optional and not ri.ingredient.is_staple]
        inventory_points = 10 * sum(ri.ingredient_id in have for ri in required) / max(1, len(required))
        return pref_points + inventory_points

    plan = get_plan(user, start, create=True, people=people)
    plan.people_count = people
    plan.weekly_budget = weekly_budget
    MealPlanItem.query.filter_by(meal_plan_id=plan.id).delete()

    slots = [(d, m) for d in range(7) for m in meals]
    remaining = weekly_budget
    used, previous = set(), None
    for index, (day, meal) in enumerate(slots):
        options = [r for r in candidates if meal in r.meal_type_list]
        if not options:
            continue
        fresh = [r for r in options if r.id not in used] or options
        varied = [r for r in fresh if previous is None or _protein(r) != _protein(previous)] or fresh
        pool = varied
        if remaining is not None:
            target = remaining / (len(slots) - index)
            affordable = [r for r in varied if cost_of(r) <= target * 1.15]
            pool = affordable or sorted(varied, key=cost_of)[:3]
        choice = max(pool, key=lambda r: (appeal(r), -cost_of(r) if remaining is not None else 0))
        db.session.add(MealPlanItem(meal_plan_id=plan.id, day=day, meal_type=meal,
                                    recipe_id=choice.id, servings=people))
        used.add(choice.id)
        previous = choice
        if remaining is not None:
            remaining -= cost_of(choice)

    db.session.commit()
    metrics.track("plan_created", user=user, people=people, meals=meals)
    return plan


def weekly_shopping_list(user, plan):
    """Consolida los ingredientes del plan y los agrega a la lista de compras.

    Suma cantidades repetidas, omite los básicos de despensa y lo que ya está en
    el inventario. Devuelve la cantidad de productos agregados.
    """
    have = inventory_service.ingredient_ids(user)
    totals = {}
    for item in plan.items:
        scale = item.servings / item.recipe.servings if item.recipe.servings else 1
        for ri in item.recipe.ingredients:
            if ri.optional or ri.ingredient.is_staple or ri.ingredient_id in have:
                continue
            entry = totals.setdefault(ri.ingredient_id, [ri.ingredient, 0.0])
            entry[1] += ri.quantity * scale
    added = 0
    for ingredient, quantity in sorted(totals.values(), key=lambda e: e[0].name):
        _, created = shopping_service.add_ingredient(user, ingredient, quantity, ingredient.unit)
        added += int(created)
    db.session.commit()
    return added, len(totals)
