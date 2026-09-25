"""Lista de compras."""
from ..extensions import db
from ..models import SHOPPING_GROUPS, ShoppingList, ShoppingListItem
from . import metrics


def get_active_list(user, create=True):
    shopping_list = ShoppingList.query.filter_by(user_id=user.id, is_active=True).first()
    if shopping_list is None and create:
        shopping_list = ShoppingList(user_id=user.id)
        db.session.add(shopping_list)
        db.session.flush()
    return shopping_list


def pending_count(user):
    shopping_list = get_active_list(user, create=False)
    if shopping_list is None:
        return 0
    return ShoppingListItem.query.filter_by(shopping_list_id=shopping_list.id, checked=False).count()


def grouped_items(shopping_list):
    """[(clave, nombre, [items])] en el orden de SHOPPING_GROUPS."""
    groups = {key: [] for key in SHOPPING_GROUPS}
    for item in shopping_list.items:
        groups.setdefault(item.category if item.category in groups else "otros", []).append(item)
    return [(key, SHOPPING_GROUPS[key], sorted(items, key=lambda i: (i.checked, i.name.lower())))
            for key, items in groups.items() if items]


def add_ingredient(user, ingredient, quantity=None, unit=None, recipe=None):
    """Agrega un ingrediente; si ya está pendiente, suma la cantidad."""
    shopping_list = get_active_list(user)
    existing = ShoppingListItem.query.filter_by(
        shopping_list_id=shopping_list.id, ingredient_id=ingredient.id, checked=False
    ).first()
    if existing:
        if quantity and existing.unit == (unit or ingredient.unit):
            existing.quantity = (existing.quantity or 0) + quantity
        return existing, False
    item = ShoppingListItem(
        shopping_list=shopping_list,
        ingredient_id=ingredient.id,
        name=ingredient.name,
        quantity=quantity,
        unit=unit or ingredient.unit,
        category=ingredient.category.shopping_group if ingredient.category else "otros",
        source_recipe_id=recipe.id if recipe else None,
    )
    db.session.add(item)
    return item, True


def add_missing_from_match(user, match):
    """Función "Me falta": agrega todos los faltantes de una receta."""
    added = 0
    for ri in match.missing:
        _, created = add_ingredient(user, ri.ingredient, ri.quantity * match.scale, ri.unit, match.recipe)
        added += int(created)
    db.session.commit()
    metrics.track("shopping_add", user=user, recipe=match.recipe, count=len(match.missing))
    return added


def add_manual(user, name, category="otros"):
    from ..models import Ingredient
    shopping_list = get_active_list(user)
    ingredient = Ingredient.query.filter(db.func.lower(Ingredient.name) == name.lower()).first()
    if ingredient:
        item, _ = add_ingredient(user, ingredient)
    else:
        item = ShoppingListItem(
            shopping_list=shopping_list, name=name,
            category=category if category in SHOPPING_GROUPS else "otros",
        )
        db.session.add(item)
    db.session.commit()
    return item


def get_item(user, item_id):
    """Solo devuelve ítems del usuario (control de acceso)."""
    return (
        ShoppingListItem.query.join(ShoppingList)
        .filter(ShoppingListItem.id == item_id, ShoppingList.user_id == user.id)
        .first()
    )


def clear_checked(user):
    shopping_list = get_active_list(user, create=False)
    if not shopping_list:
        return 0
    count = ShoppingListItem.query.filter_by(shopping_list_id=shopping_list.id, checked=True).delete()
    db.session.commit()
    return count


def clear_all(user):
    shopping_list = get_active_list(user, create=False)
    if not shopping_list:
        return 0
    count = ShoppingListItem.query.filter_by(shopping_list_id=shopping_list.id).delete()
    db.session.commit()
    return count
