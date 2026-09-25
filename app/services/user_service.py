"""Usuarios: registro, preferencias, exportación y eliminación de datos."""
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..extensions import db
from ..models import (CITIES, RESTRICTIONS, AnalyticsEvent, Category, ContactMessage, Consent,
                      Ingredient, User, UserPreference)
from ..utils import clean_text, is_valid_email, password_problem

TERMS_VERSION = "2026-09"
PRIVACY_VERSION = "2026-09"


def find_by_email(email):
    return User.query.filter(db.func.lower(User.email) == (email or "").strip().lower()).first()


def validate_registration(form):
    data = {
        "first_name": clean_text(form.get("first_name"), 60),
        "last_name": clean_text(form.get("last_name"), 60),
        "email": clean_text(form.get("email"), 255).lower(),
        "city": form.get("city") if form.get("city") in CITIES else "",
        "password": form.get("password") or "",
    }
    errors = {}
    if not data["first_name"]:
        errors["first_name"] = "Cuéntanos tu nombre."
    if not data["last_name"]:
        errors["last_name"] = "Cuéntanos tu apellido."
    if not is_valid_email(data["email"]):
        errors["email"] = "Revisa tu email, parece que falta algo."
    elif find_by_email(data["email"]):
        errors["email"] = "Ya existe una cuenta con este email."
    problem = password_problem(data["password"])
    if problem:
        errors["password"] = problem
    elif data["password"] != (form.get("password_confirm") or ""):
        errors["password_confirm"] = "Las contraseñas no coinciden."
    if not data["city"]:
        errors["city"] = "Elige tu ciudad."
    if not form.get("accept_terms"):
        errors["accept_terms"] = "Necesitas aceptar los términos para crear tu cuenta."
    if not form.get("accept_privacy"):
        errors["accept_privacy"] = "Necesitas aceptar la política de privacidad."
    return data, errors


def create_user(first_name, last_name, email, password, city, is_admin=False):
    user = User(first_name=first_name, last_name=last_name, email=email.lower(), city=city,
                is_admin=is_admin)
    user.set_password(password)
    user.preference = UserPreference(people_count=2, default_time=45, food_preferences=[],
                                     excluded_ingredients=[], restrictions=[])
    user.consents = [
        Consent(consent_type="terms", version=TERMS_VERSION, granted=True),
        Consent(consent_type="privacy", version=PRIVACY_VERSION, granted=True),
    ]
    db.session.add(user)
    db.session.commit()
    return user


def update_preferences(user, form):
    """Actualiza preferencias desde un formulario (onboarding o perfil)."""
    from ..utils import parse_float, parse_int

    pref = user.preference or UserPreference(user=user)
    pref.people_count = parse_int(form.get("people_count"), default=pref.people_count or 2, minimum=1, maximum=20)
    minutes = parse_int(form.get("default_time"), default=None, minimum=0, maximum=600)
    pref.default_time = minutes or None
    budget = parse_float(form.get("default_budget"), default=None, minimum=0, maximum=1000)
    pref.default_budget = budget or None
    valid_categories = {c.slug for c in Category.query.all()}
    pref.food_preferences = [s for s in form.getlist("food_preferences") if s in valid_categories]
    if form.get("no_restrictions"):
        pref.excluded_ingredients = []
        pref.restrictions = []
    else:
        valid_ids = {i.id for i in Ingredient.query.with_entities(Ingredient.id).all()}
        ids = []
        for raw in form.getlist("excluded_ingredients"):
            if raw.isdigit() and int(raw) in valid_ids:
                ids.append(int(raw))
        pref.excluded_ingredients = sorted(set(ids))
        pref.restrictions = [r for r in form.getlist("restrictions") if r in RESTRICTIONS]
    db.session.add(pref)
    db.session.commit()
    return pref


# --- Recuperación de contraseña (preparada, sin envío de correo) -------------

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def make_reset_token(user):
    # Incluye parte del hash: el token deja de servir después de cambiar la contraseña.
    return _serializer().dumps({"id": user.id, "h": user.password_hash[-12:]})


def user_from_reset_token(token):
    try:
        data = _serializer().loads(token, max_age=current_app.config["PASSWORD_RESET_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("id"))
    if user and user.active and user.password_hash[-12:] == data.get("h"):
        return user
    return None


# --- Privacidad ---------------------------------------------------------------

def export_data(user):
    """Datos del usuario en formato portable (base para LOPDP)."""
    pref = user.preference
    return {
        "usuario": {
            "nombre": user.first_name, "apellido": user.last_name, "email": user.email,
            "ciudad": user.city, "creado": user.created_at.isoformat(),
            "actualizado": user.updated_at.isoformat(),
        },
        "preferencias": {
            "personas": pref.people_count if pref else None,
            "tiempo_habitual_min": pref.default_time if pref else None,
            "presupuesto_habitual": pref.default_budget if pref else None,
            "comidas_preferidas": pref.food_preferences if pref else [],
            "restricciones": pref.restrictions if pref else [],
            "ingredientes_evitados": [
                i.name for i in Ingredient.query.filter(Ingredient.id.in_(pref.excluded_ingredients or [])).all()
            ] if pref else [],
        },
        "familia": [
            {"nombre": m.name, "relacion": m.relationship, "preferencias": m.food_preferences,
             "no_consume": m.avoided_foods} for m in user.family_members
        ],
        "inventario": [
            {"ingrediente": i.ingredient.name, "cantidad": i.quantity, "unidad": i.unit,
             "vence": i.expiration_date.isoformat() if i.expiration_date else None}
            for i in user.inventory_items
        ],
        "lista_de_compras": [
            {"producto": item.name, "cantidad": item.quantity, "unidad": item.unit, "comprado": item.checked}
            for sl in user.shopping_lists for item in sl.items
        ],
        "favoritos": [f.recipe.name for f in user.favorites],
        "historial": [
            {"receta": h.recipe.name, "fecha": h.cooked_at.isoformat(), "porciones": h.servings}
            for h in user.history
        ],
        "planes": [
            {"semana": p.week_start.isoformat(), "personas": p.people_count, "presupuesto": p.weekly_budget,
             "comidas": [{"dia": i.day, "comida": i.meal_type, "receta": i.recipe.name} for i in p.items]}
            for p in user.meal_plans
        ],
        "consentimientos": [
            {"tipo": c.consent_type, "version": c.version, "otorgado": c.granted,
             "fecha": c.created_at.isoformat()} for c in user.consents
        ],
    }


def delete_account(user):
    """Elimina la cuenta y todos sus datos personales. Las métricas quedan
    anónimas (sin user_id)."""
    AnalyticsEvent.query.filter_by(user_id=user.id).update({"user_id": None})
    ContactMessage.query.filter_by(user_id=user.id).update({"user_id": None})
    db.session.delete(user)
    db.session.commit()
