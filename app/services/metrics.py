"""Métricas de producto.

La métrica principal: ¿cuántas veces ayudamos a alguien a decidir qué cocinar?
Se cuenta cada búsqueda con resultados ("recommendation") y cada receta
marcada como preparada ("cooked").

No se guarda IP, ubicación ni datos del dispositivo.
"""
from collections import Counter

from ..extensions import db
from ..models import AnalyticsEvent, Ingredient, Recipe

DECISION_EVENTS = ("recommendation", "pantry_search")


def track(event_type, user=None, recipe=None, **payload):
    try:
        db.session.add(AnalyticsEvent(
            event_type=event_type,
            user_id=getattr(user, "id", None) if user is not None and getattr(user, "is_authenticated", False) else None,
            recipe_id=getattr(recipe, "id", None),
            payload=payload or None,
        ))
        db.session.commit()
    except Exception:  # las métricas nunca deben romper la experiencia
        db.session.rollback()


def count(event_type):
    return AnalyticsEvent.query.filter_by(event_type=event_type).count()


def decisions_helped():
    return AnalyticsEvent.query.filter(AnalyticsEvent.event_type.in_(DECISION_EVENTS)).count()


def top_recipes(event_type, limit=5):
    rows = (
        db.session.query(AnalyticsEvent.recipe_id, db.func.count(AnalyticsEvent.id))
        .filter(AnalyticsEvent.event_type == event_type, AnalyticsEvent.recipe_id.isnot(None))
        .group_by(AnalyticsEvent.recipe_id)
        .order_by(db.func.count(AnalyticsEvent.id).desc())
        .limit(limit)
        .all()
    )
    return [(db.session.get(Recipe, rid), n) for rid, n in rows if db.session.get(Recipe, rid)]


def top_searched_ingredients(limit=8):
    counter = Counter()
    events = AnalyticsEvent.query.filter(AnalyticsEvent.event_type.in_(DECISION_EVENTS)).all()
    for event in events:
        for ingredient_id in (event.payload or {}).get("ingredients", []):
            counter[ingredient_id] += 1
    result = []
    for ingredient_id, n in counter.most_common(limit):
        ingredient = db.session.get(Ingredient, ingredient_id)
        if ingredient:
            result.append((ingredient, n))
    return result
