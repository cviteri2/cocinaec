"""Modelos de base de datos.

Convenciones:
- Las cantidades de ingredientes se guardan en la unidad base del ingrediente
  ("g", "ml" o "unidad").
- Los costos son estimaciones de referencia, nunca precios actuales.
- Las fechas se guardan en UTC sin zona horaria.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

RESTRICTIONS = {
    "vegetariano": "Vegetariano",
    "sin_cerdo": "Sin cerdo",
    "sin_pescado": "Sin pescado",
    "sin_mariscos": "Sin mariscos",
    "sin_lacteos": "Sin lácteos",
    "sin_huevo": "Sin huevo",
    "sin_picante": "Sin picante",
}

CITIES = [
    "Guayaquil", "Quito", "Cuenca", "Ambato", "Manta", "Loja", "Machala",
    "Portoviejo", "Riobamba", "Santo Domingo", "Otra",
]


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(60))
    active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_done = db.Column(db.Boolean, default=False, nullable=False)
    # Plan conceptual: "free" | "premium". No hay pagos en esta versión.
    plan = db.Column(db.String(20), default="free", nullable=False)

    preference = db.relationship(
        "UserPreference", uselist=False, back_populates="user", cascade="all, delete-orphan"
    )
    family_members = db.relationship("FamilyMember", back_populates="user", cascade="all, delete-orphan")
    inventory_items = db.relationship("InventoryItem", back_populates="user", cascade="all, delete-orphan")
    shopping_lists = db.relationship("ShoppingList", back_populates="user", cascade="all, delete-orphan")
    favorites = db.relationship("FavoriteRecipe", back_populates="user", cascade="all, delete-orphan")
    meal_plans = db.relationship("MealPlan", back_populates="user", cascade="all, delete-orphan")
    history = db.relationship("CookingHistory", back_populates="user", cascade="all, delete-orphan")
    consents = db.relationship("Consent", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class UserPreference(TimestampMixin, db.Model):
    __tablename__ = "user_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    people_count = db.Column(db.Integer, default=2, nullable=False)
    default_time = db.Column(db.Integer, default=45)  # minutos; None = más de 1 hora
    default_budget = db.Column(db.Float)  # None = sin límite específico
    food_preferences = db.Column(db.JSON, default=list, nullable=False)  # slugs de Category
    excluded_ingredients = db.Column(db.JSON, default=list, nullable=False)  # ids de Ingredient
    restrictions = db.Column(db.JSON, default=list, nullable=False)  # claves de RESTRICTIONS

    user = db.relationship("User", back_populates="preference")


class FamilyMember(TimestampMixin, db.Model):
    """Estructura para "Mi familia". No guarda información médica."""

    __tablename__ = "family_members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    relationship = db.Column(db.String(40))
    food_preferences = db.Column(db.String(255))
    avoided_foods = db.Column(db.String(255))

    user = db.relationship("User", back_populates="family_members")


class Consent(db.Model):
    """Registro de consentimientos (términos, privacidad). Base para LOPDP."""

    __tablename__ = "consents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    consent_type = db.Column(db.String(30), nullable=False)  # "terms" | "privacy"
    version = db.Column(db.String(20), nullable=False)
    granted = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="consents")


# ---------------------------------------------------------------------------
# Ingredientes y precios
# ---------------------------------------------------------------------------

SHOPPING_GROUPS = {
    "frutas": "Frutas",
    "verduras": "Verduras",
    "carnes": "Carnes y pescados",
    "lacteos": "Lácteos y huevos",
    "granos": "Granos y cereales",
    "bebidas": "Bebidas",
    "limpieza": "Limpieza",
    "otros": "Otros",
}


class IngredientCategory(db.Model):
    __tablename__ = "ingredient_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    emoji = db.Column(db.String(8), default="🥫")
    shopping_group = db.Column(db.String(20), default="otros", nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    ingredients = db.relationship("Ingredient", back_populates="category")


class Ingredient(TimestampMixin, db.Model):
    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    emoji = db.Column(db.String(8), default="")
    category_id = db.Column(db.Integer, db.ForeignKey("ingredient_categories.id"), nullable=False)
    unit = db.Column(db.String(10), nullable=False, default="g")  # unidad base
    active = db.Column(db.Boolean, default=True, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    # Básicos que se asume que hay en casa (sal, aceite, ajo...)
    is_staple = db.Column(db.Boolean, default=False, nullable=False)
    # Banderas para restricciones alimentarias
    is_meat = db.Column(db.Boolean, default=False, nullable=False)
    is_pork = db.Column(db.Boolean, default=False, nullable=False)
    is_fish = db.Column(db.Boolean, default=False, nullable=False)
    is_seafood = db.Column(db.Boolean, default=False, nullable=False)
    is_dairy = db.Column(db.Boolean, default=False, nullable=False)
    is_egg = db.Column(db.Boolean, default=False, nullable=False)
    is_spicy = db.Column(db.Boolean, default=False, nullable=False)

    category = db.relationship("IngredientCategory", back_populates="ingredients")
    prices = db.relationship(
        "IngredientPrice", back_populates="ingredient", cascade="all, delete-orphan",
        order_by="IngredientPrice.reference_date.desc(), IngredientPrice.id.desc()",
    )

    @property
    def label(self):
        return f"{self.emoji} {self.name}".strip()

    @property
    def current_price(self):
        return self.prices[0] if self.prices else None

    def violates(self, restriction):
        return {
            "vegetariano": self.is_meat or self.is_fish or self.is_seafood,
            "sin_cerdo": self.is_pork,
            "sin_pescado": self.is_fish,
            "sin_mariscos": self.is_seafood,
            "sin_lacteos": self.is_dairy,
            "sin_huevo": self.is_egg,
            "sin_picante": self.is_spicy,
        }.get(restriction, False)


class IngredientPrice(db.Model):
    """Costo estimado de referencia. Preparado para integrar precios de
    supermercados en el futuro (campo `source`)."""

    __tablename__ = "ingredient_prices"

    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)
    per_quantity = db.Column(db.Float, nullable=False, default=1)  # en la unidad base
    unit = db.Column(db.String(10), nullable=False)
    reference_date = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(60), default="referencia", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    ingredient = db.relationship("Ingredient", back_populates="prices")

    @property
    def unit_cost(self):
        return self.price / self.per_quantity if self.per_quantity else 0


class Substitution(db.Model):
    """"¿No tienes X? Puedes usar Y". Tabla simple, sin IA."""

    __tablename__ = "substitutions"

    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False, index=True)
    substitute_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    note = db.Column(db.String(160))

    ingredient = db.relationship("Ingredient", foreign_keys=[ingredient_id])
    substitute = db.relationship("Ingredient", foreign_keys=[substitute_id])

    __table_args__ = (db.UniqueConstraint("ingredient_id", "substitute_id"),)


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------

MEAL_TYPES = {
    "desayuno": "Desayuno",
    "almuerzo": "Almuerzo",
    "cena": "Cena",
    "merienda": "Merienda",
}

DIFFICULTIES = ["Fácil", "Media", "Difícil"]

recipe_categories = db.Table(
    "recipe_categories",
    db.Column("recipe_id", db.Integer, db.ForeignKey("recipes.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.id"), primary_key=True),
)

recipe_tags = db.Table(
    "recipe_tags",
    db.Column("recipe_id", db.Integer, db.ForeignKey("recipes.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class Category(db.Model):
    """Categoría de receta (ecuatoriana, sopas, pollo...). Coincide con las
    preferencias de comida del onboarding."""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    emoji = db.Column(db.String(8), default="🍽️")
    sort_order = db.Column(db.Integer, default=0, nullable=False)


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    slug = db.Column(db.String(40), unique=True, nullable=False)


class Recipe(TimestampMixin, db.Model):
    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    emoji = db.Column(db.String(8), default="🍽️")
    meal_types = db.Column(db.String(80), nullable=False, default="almuerzo")  # separados por coma
    servings = db.Column(db.Integer, nullable=False, default=4)
    prep_minutes = db.Column(db.Integer, nullable=False, default=10)
    cook_minutes = db.Column(db.Integer, nullable=False, default=20)
    difficulty = db.Column(db.String(20), nullable=False, default="Fácil")
    estimated_cost = db.Column(db.Float, nullable=False, default=0)  # por `servings` porciones
    equipment = db.Column(db.String(80), default="")  # p. ej. "horno"
    image = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False)

    categories = db.relationship("Category", secondary=recipe_categories, lazy="selectin")
    tags = db.relationship("Tag", secondary=recipe_tags, lazy="selectin")
    ingredients = db.relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
    )
    steps = db.relationship(
        "RecipeStep", back_populates="recipe", cascade="all, delete-orphan",
        order_by="RecipeStep.position",
    )

    @property
    def total_minutes(self):
        return (self.prep_minutes or 0) + (self.cook_minutes or 0)

    @property
    def meal_type_list(self):
        return [m for m in (self.meal_types or "").split(",") if m]

    @property
    def category(self):
        return self.categories[0] if self.categories else None

    @property
    def category_slugs(self):
        return {c.slug for c in self.categories}


class RecipeIngredient(db.Model):
    __tablename__ = "recipe_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False, default=0)  # en unidad base
    unit = db.Column(db.String(10), nullable=False)
    note = db.Column(db.String(80))  # "al gusto", "picado", ...
    optional = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)

    recipe = db.relationship("Recipe", back_populates="ingredients")
    ingredient = db.relationship("Ingredient", lazy="joined")


class RecipeStep(db.Model):
    __tablename__ = "recipe_steps"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)

    recipe = db.relationship("Recipe", back_populates="steps")


# ---------------------------------------------------------------------------
# Datos del usuario
# ---------------------------------------------------------------------------

class InventoryItem(TimestampMixin, db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(10))
    expiration_date = db.Column(db.Date)

    user = db.relationship("User", back_populates="inventory_items")
    ingredient = db.relationship("Ingredient", lazy="joined")


class ShoppingList(TimestampMixin, db.Model):
    __tablename__ = "shopping_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(80), default="Mi lista de compras", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship("User", back_populates="shopping_lists")
    items = db.relationship(
        "ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan",
        order_by="ShoppingListItem.id",
    )


class ShoppingListItem(TimestampMixin, db.Model):
    __tablename__ = "shopping_list_items"

    id = db.Column(db.Integer, primary_key=True)
    shopping_list_id = db.Column(db.Integer, db.ForeignKey("shopping_lists.id"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"))
    name = db.Column(db.String(80), nullable=False)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(10))
    category = db.Column(db.String(20), default="otros", nullable=False)  # clave de SHOPPING_GROUPS
    checked = db.Column(db.Boolean, default=False, nullable=False)
    source_recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"))

    shopping_list = db.relationship("ShoppingList", back_populates="items")
    ingredient = db.relationship("Ingredient")
    source_recipe = db.relationship("Recipe")


class FavoriteRecipe(db.Model):
    __tablename__ = "favorite_recipes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="favorites")
    recipe = db.relationship("Recipe")

    __table_args__ = (db.UniqueConstraint("user_id", "recipe_id"),)


class MealPlan(TimestampMixin, db.Model):
    __tablename__ = "meal_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False)  # lunes
    people_count = db.Column(db.Integer, default=2, nullable=False)
    weekly_budget = db.Column(db.Float)

    user = db.relationship("User", back_populates="meal_plans")
    items = db.relationship("MealPlanItem", back_populates="meal_plan", cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("user_id", "week_start"),)


class MealPlanItem(db.Model):
    __tablename__ = "meal_plan_items"

    id = db.Column(db.Integer, primary_key=True)
    meal_plan_id = db.Column(db.Integer, db.ForeignKey("meal_plans.id"), nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)  # 0 = lunes ... 6 = domingo
    meal_type = db.Column(db.String(20), nullable=False)  # "almuerzo" | "cena"
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    servings = db.Column(db.Integer, nullable=False, default=2)

    meal_plan = db.relationship("MealPlan", back_populates="items")
    recipe = db.relationship("Recipe", lazy="joined")

    __table_args__ = (db.UniqueConstraint("meal_plan_id", "day", "meal_type"),)


class CookingHistory(db.Model):
    __tablename__ = "cooking_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    cooked_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    servings = db.Column(db.Integer)
    estimated_cost = db.Column(db.Float)

    user = db.relationship("User", back_populates="history")
    recipe = db.relationship("Recipe")


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class AnalyticsEvent(db.Model):
    """Eventos para métricas de producto. La métrica principal es cuántas
    veces ayudamos a alguien a decidir qué cocinar."""

    __tablename__ = "analytics_events"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"))
    payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
