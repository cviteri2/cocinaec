"""Inventario de casa: "esto es lo que tengo"."""
from datetime import timedelta

from ..extensions import db
from ..models import Ingredient, IngredientCategory, InventoryItem
from ..utils import today_local

USE_FIRST_DAYS = 3


def items_for(user):
    return (
        InventoryItem.query.filter_by(user_id=user.id)
        .join(Ingredient)
        .order_by(InventoryItem.expiration_date.is_(None), InventoryItem.expiration_date, Ingredient.name)
        .all()
    )


def ingredient_ids(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    return {row.ingredient_id for row in InventoryItem.query.filter_by(user_id=user.id).all()}


def use_first(user, days=USE_FIRST_DAYS):
    """Ingredientes vencidos o que vencen en los próximos `days` días."""
    limit = today_local() + timedelta(days=days)
    return (
        InventoryItem.query.filter(
            InventoryItem.user_id == user.id,
            InventoryItem.expiration_date.isnot(None),
            InventoryItem.expiration_date <= limit,
        )
        .order_by(InventoryItem.expiration_date)
        .all()
    )


def get_item(user, item_id):
    return InventoryItem.query.filter_by(id=item_id, user_id=user.id).first()


def upsert(user, ingredient, quantity, unit, expiration_date):
    """Si el ingrediente ya está (misma unidad y vencimiento), suma cantidades."""
    item = InventoryItem.query.filter_by(
        user_id=user.id, ingredient_id=ingredient.id, unit=unit, expiration_date=expiration_date
    ).first()
    if item:
        if quantity:
            item.quantity = (item.quantity or 0) + quantity
    else:
        item = InventoryItem(user_id=user.id, ingredient_id=ingredient.id, quantity=quantity,
                             unit=unit, expiration_date=expiration_date)
        db.session.add(item)
    db.session.commit()
    return item


def clear(user):
    count = InventoryItem.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return count


def grouped_catalog(include_staples=False):
    """Categorías con sus ingredientes activos, para el selector de chips."""
    categories = IngredientCategory.query.order_by(IngredientCategory.sort_order).all()
    result = []
    for category in categories:
        ingredients = [
            i for i in sorted(category.ingredients, key=lambda i: (not i.featured, i.name))
            if i.active and (include_staples or not i.is_staple)
        ]
        if ingredients:
            result.append((category, ingredients))
    return result


def staples():
    return Ingredient.query.filter_by(is_staple=True, active=True).order_by(Ingredient.name).all()
