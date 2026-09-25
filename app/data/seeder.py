"""Carga de datos iniciales. Es idempotente: si ya hay recetas, no duplica."""
import os
from datetime import date, timedelta

from ..extensions import db
from ..models import (Category, CookingHistory, FavoriteRecipe, Ingredient, IngredientCategory,
                      IngredientPrice, InventoryItem, MealPlanItem, Recipe, RecipeIngredient,
                      RecipeStep, Substitution, Tag, utcnow)
from ..services import meal_plan_service, pricing, shopping_service, user_service
from ..utils import slugify, today_local
from . import seed_data as data

REFERENCE_DATE = date(2026, 9, 1)
FLAG_FIELDS = {"staple": "is_staple", "meat": "is_meat", "pork": "is_pork", "fish": "is_fish",
               "seafood": "is_seafood", "dairy": "is_dairy", "egg": "is_egg", "spicy": "is_spicy"}


def seed_catalog():
    if Recipe.query.first():
        return False

    categories = {}
    for order, (slug, name, emoji, group) in enumerate(data.INGREDIENT_CATEGORIES):
        categories[slug] = IngredientCategory(slug=slug, name=name, emoji=emoji,
                                              shopping_group=group, sort_order=order)
        db.session.add(categories[slug])

    ingredients = {}
    for name, emoji, cat, unit, price, per, flags, featured in data.INGREDIENTS:
        ingredient = Ingredient(name=name, emoji=emoji, category=categories[cat], unit=unit,
                                featured=featured)
        for flag in flags.split():
            setattr(ingredient, FLAG_FIELDS[flag], True)
        ingredient.prices.append(IngredientPrice(price=price, per_quantity=per, unit=unit,
                                                 reference_date=REFERENCE_DATE))
        ingredients[name] = ingredient
        db.session.add(ingredient)

    for original, substitute, note in data.SUBSTITUTIONS:
        db.session.add(Substitution(ingredient=ingredients[original],
                                    substitute=ingredients[substitute], note=note))

    recipe_categories = {}
    for order, (slug, name, emoji) in enumerate(data.CATEGORIES):
        recipe_categories[slug] = Category(slug=slug, name=name, emoji=emoji, sort_order=order)
        db.session.add(recipe_categories[slug])

    tags = {name: Tag(name=name, slug=slugify(name)) for name in data.TAGS}
    db.session.add_all(tags.values())

    for spec in data.RECIPES:
        recipe = Recipe(
            name=spec["name"], slug=slugify(spec["name"]), description=spec["description"],
            emoji=spec["emoji"], meal_types=spec["meals"], servings=spec["servings"],
            prep_minutes=spec["prep"], cook_minutes=spec["cook"], difficulty=spec["difficulty"],
            equipment=spec.get("equipment", ""),
            categories=[recipe_categories[s] for s in spec["categories"]],
            tags=[tags[t] for t in spec.get("tags", [])],
        )
        for position, (name, qty, note, optional) in enumerate(spec["ingredients"]):
            ingredient = ingredients[name]
            recipe.ingredients.append(RecipeIngredient(
                ingredient=ingredient, quantity=qty, unit=ingredient.unit, note=note,
                optional=optional, position=position,
            ))
        for position, text in enumerate(spec["steps"], start=1):
            recipe.steps.append(RecipeStep(position=position, text=text))
        db.session.add(recipe)

    db.session.commit()
    pricing.recompute_recipe_costs()
    return True


def _ingredient(name):
    return Ingredient.query.filter_by(name=name).one()


def _recipe(name):
    return Recipe.query.filter_by(name=name).one()


def seed_demo_user():
    if user_service.find_by_email(data.DEMO_USER["email"]):
        return None
    user = user_service.create_user(**data.DEMO_USER)
    user.onboarding_done = True
    pref = user.preference
    pref.people_count = 4
    pref.default_time = 45
    pref.default_budget = 5
    pref.food_preferences = ["ecuatoriana", "pollo", "sopas", "economica"]
    pref.excluded_ingredients = [_ingredient("Mondongo (panza de res)").id]

    today = today_local()
    for name, qty, unit, days in [
        ("Pollo (presas)", 1, "kg", 2), ("Arroz", 2, "kg", None), ("Papa", 2, "kg", 10),
        ("Tomate", 6, "unidad", 1), ("Cebolla colorada", 3, "unidad", 12), ("Huevo", 12, "unidad", 14),
        ("Plátano verde", 4, "unidad", 4), ("Queso fresco", 500, "g", 3),
    ]:
        db.session.add(InventoryItem(
            user_id=user.id, ingredient_id=_ingredient(name).id, quantity=qty, unit=unit,
            expiration_date=today + timedelta(days=days) if days is not None else None,
        ))

    for name in ["Limón", "Culantro", "Leche", "Zanahoria"]:
        shopping_service.add_ingredient(user, _ingredient(name))

    for name in ["Seco de pollo", "Locro de papa", "Bolón de verde"]:
        db.session.add(FavoriteRecipe(user_id=user.id, recipe_id=_recipe(name).id))

    for days_ago, name in [(1, "Arroz con pollo"), (3, "Sopa de lentejas"), (6, "Seco de pollo")]:
        recipe = _recipe(name)
        db.session.add(CookingHistory(
            user_id=user.id, recipe_id=recipe.id, servings=4, estimated_cost=recipe.estimated_cost,
            cooked_at=utcnow() - timedelta(days=days_ago),
        ))
    db.session.commit()

    plan = meal_plan_service.get_plan(user, create=True, people=4)
    plan.weekly_budget = 50
    for day, name in enumerate(["Seco de pollo", "Lentejas guisadas con arroz", "Pescado al horno",
                                "Tallarines con pollo", "Menestra con carne"]):
        db.session.add(MealPlanItem(meal_plan_id=plan.id, day=day, meal_type="almuerzo",
                                    recipe_id=_recipe(name).id, servings=4))
    db.session.commit()
    return user


def seed_admin_user(production=False):
    email = os.environ.get("ADMIN_EMAIL") or data.ADMIN_USER["email"]
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        if production:
            return None, "Define ADMIN_PASSWORD para crear el administrador en producción."
        password = data.ADMIN_USER["password"]
    if user_service.find_by_email(email):
        return None, None
    fields = {**data.ADMIN_USER, "email": email, "password": password}
    user = user_service.create_user(**fields, is_admin=True)
    user.onboarding_done = True
    db.session.commit()
    return user, None


def run(production=False, with_demo=True):
    db.create_all()
    created_catalog = seed_catalog()
    demo = seed_demo_user() if with_demo else None
    admin, warning = seed_admin_user(production=production)
    return {
        "catalog": created_catalog,
        "demo": demo is not None,
        "admin": admin is not None,
        "warning": warning,
        "ingredients": Ingredient.query.count(),
        "recipes": Recipe.query.count(),
        "categories": Category.query.count() + IngredientCategory.query.count(),
    }
