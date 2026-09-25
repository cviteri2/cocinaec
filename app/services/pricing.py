"""Costos estimados de referencia y conversión de unidades.

Cada ingrediente tiene una unidad base ("g", "ml" o "unidad"). El inventario
admite kg y l, que se convierten aquí.
"""
from ..extensions import db
from ..models import Ingredient, IngredientPrice, Recipe

UNIT_FACTORS = {"g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "l": ("ml", 1000),
                "unidad": ("unidad", 1)}
UNIT_CHOICES = [("unidad", "unidades"), ("g", "g"), ("kg", "kg"), ("ml", "ml"), ("l", "litros")]


def to_base(quantity, unit):
    """Convierte (cantidad, unidad) a (cantidad, unidad_base)."""
    base, factor = UNIT_FACTORS.get(unit, (unit, 1))
    return (quantity or 0) * factor, base


def unit_costs():
    """{ingredient_id: costo por unidad base} con el precio más reciente."""
    costs = {}
    rows = (
        db.session.query(IngredientPrice)
        .order_by(IngredientPrice.ingredient_id, IngredientPrice.reference_date.desc(),
                  IngredientPrice.id.desc())
        .all()
    )
    for price in rows:
        costs.setdefault(price.ingredient_id, price.unit_cost)
    return costs


def line_cost(recipe_ingredient, costs, scale=1.0):
    return recipe_ingredient.quantity * scale * costs.get(recipe_ingredient.ingredient_id, 0)


def recipe_cost(recipe, costs=None, scale=1.0):
    """Costo de los ingredientes obligatorios de la receta."""
    costs = costs if costs is not None else unit_costs()
    return round(sum(line_cost(ri, costs, scale) for ri in recipe.ingredients if not ri.optional), 2)


def recompute_recipe_costs(recipes=None):
    costs = unit_costs()
    recipes = recipes if recipes is not None else Recipe.query.all()
    for recipe in recipes:
        recipe.estimated_cost = recipe_cost(recipe, costs)
    db.session.commit()


def recipes_using(ingredient):
    return Recipe.query.filter(Recipe.ingredients.any(ingredient_id=ingredient.id)).all()


def set_price(ingredient: Ingredient, price, per_quantity, reference_date, source="referencia"):
    """Agrega un precio nuevo (se conserva el historial) y recalcula recetas."""
    db.session.add(IngredientPrice(
        ingredient=ingredient, price=price, per_quantity=per_quantity,
        unit=ingredient.unit, reference_date=reference_date, source=source,
    ))
    db.session.flush()
    recompute_recipe_costs(recipes_using(ingredient))
