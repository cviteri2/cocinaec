"""Panel de administración, protegido por rol."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (DIFFICULTIES, MEAL_TYPES, SHOPPING_GROUPS, Category, ContactMessage,
                      FavoriteRecipe, Ingredient, IngredientCategory, MealPlan, Recipe,
                      RecipeIngredient, RecipeStep, ShoppingList, User)
from ..services import metrics, pricing, user_service
from ..utils import clean_text, normalize, parse_float, parse_int, slugify, today_local

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


@bp.before_request
@admin_required
def guard():
    pass


# --- Dashboard ------------------------------------------------------------

@bp.route("/")
def dashboard():
    stats = {
        "decisions": metrics.decisions_helped(),
        "users": User.query.count(),
        "recipes": Recipe.query.count(),
        "ingredients": Ingredient.query.count(),
        "plans": MealPlan.query.count(),
        "lists": ShoppingList.query.count(),
        "favorites": FavoriteRecipe.query.count(),
        "cooked": metrics.count("cooked"),
        "views": metrics.count("recipe_view"),
        "messages": ContactMessage.query.filter_by(read=False).count(),
    }
    return render_template(
        "admin/dashboard.html", stats=stats,
        top_viewed=metrics.top_recipes("recipe_view"),
        top_favorites=metrics.top_recipes("favorite"),
        top_cooked=metrics.top_recipes("cooked"),
        top_ingredients=metrics.top_searched_ingredients(),
    )


# --- Recetas --------------------------------------------------------------

@bp.route("/recipes")
def recipes():
    q = normalize(request.args.get("q"))
    items = Recipe.query.order_by(Recipe.name).all()
    if q:
        items = [r for r in items if q in normalize(r.name)]
    return render_template("admin/recipes.html", recipes=items, q=request.args.get("q", ""))


def _recipe_form_data(recipe):
    return {
        "name": recipe.name if recipe else "",
        "description": recipe.description if recipe else "",
        "emoji": recipe.emoji if recipe else "🍽️",
        "meal_types": recipe.meal_type_list if recipe else ["almuerzo"],
        "servings": recipe.servings if recipe else 4,
        "prep_minutes": recipe.prep_minutes if recipe else 10,
        "cook_minutes": recipe.cook_minutes if recipe else 20,
        "difficulty": recipe.difficulty if recipe else "Fácil",
        "equipment": recipe.equipment if recipe else "",
        "categories": [c.slug for c in recipe.categories] if recipe else [],
        "active": recipe.active if recipe else True,
        "ingredients_text": "\n".join(
            " | ".join([ri.ingredient.name, f"{ri.quantity:g}", ri.note or "", "opcional" if ri.optional else ""]).rstrip(" |")
            for ri in recipe.ingredients
        ) if recipe else "",
        "steps_text": "\n".join(s.text for s in recipe.steps) if recipe else "",
    }


def _parse_ingredient_lines(text):
    catalog = {normalize(i.name): i for i in Ingredient.query.all()}
    rows, errors = [], []
    for number, line in enumerate((text or "").splitlines(), start=1):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        ingredient = catalog.get(normalize(parts[0]))
        quantity = parse_float(parts[1] if len(parts) > 1 else None, minimum=0, maximum=100000)
        if ingredient is None:
            errors.append(f"Línea {number}: no existe el ingrediente «{parts[0]}».")
            continue
        if quantity is None:
            errors.append(f"Línea {number}: la cantidad no es válida.")
            continue
        note = parts[2][:80] if len(parts) > 2 and parts[2] else None
        optional = len(parts) > 3 and normalize(parts[3]) in {"opcional", "si", "x"}
        rows.append((ingredient, quantity, note, optional))
    if not rows and not errors:
        errors.append("Agrega al menos un ingrediente.")
    return rows, errors


@bp.route("/recipes/new", methods=["GET", "POST"])
@bp.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
def recipe_form(recipe_id=None):
    recipe = db.session.get(Recipe, recipe_id) if recipe_id else None
    if recipe_id and recipe is None:
        abort(404)
    form = _recipe_form_data(recipe)
    errors = []
    if request.method == "POST":
        f = request.form
        form = {
            "name": clean_text(f.get("name"), 120),
            "description": clean_text(f.get("description"), 1000),
            "emoji": clean_text(f.get("emoji"), 8) or "🍽️",
            "meal_types": [m for m in f.getlist("meal_types") if m in MEAL_TYPES],
            "servings": parse_int(f.get("servings"), minimum=1, maximum=50),
            "prep_minutes": parse_int(f.get("prep_minutes"), minimum=0, maximum=1000),
            "cook_minutes": parse_int(f.get("cook_minutes"), minimum=0, maximum=1000),
            "difficulty": f.get("difficulty") if f.get("difficulty") in DIFFICULTIES else "Fácil",
            "equipment": clean_text(f.get("equipment"), 80),
            "categories": f.getlist("categories"),
            "active": bool(f.get("active")),
            "ingredients_text": f.get("ingredients_text", "")[:5000],
            "steps_text": f.get("steps_text", "")[:10000],
        }
        if not form["name"]:
            errors.append("El nombre es obligatorio.")
        existing = Recipe.query.filter_by(slug=slugify(form["name"])).first()
        if existing and existing is not recipe:
            errors.append("Ya existe una receta con ese nombre.")
        if not form["meal_types"]:
            errors.append("Elige al menos un tipo de comida.")
        if None in (form["servings"], form["prep_minutes"], form["cook_minutes"]):
            errors.append("Revisa porciones y tiempos.")
        rows, line_errors = _parse_ingredient_lines(form["ingredients_text"])
        errors += line_errors
        steps = [s.strip()[:1000] for s in form["steps_text"].splitlines() if s.strip()]
        if not steps:
            errors.append("Agrega al menos un paso.")
        if not errors:
            recipe = recipe or Recipe()
            recipe.name, recipe.slug = form["name"], slugify(form["name"])
            recipe.description, recipe.emoji = form["description"], form["emoji"]
            recipe.meal_types = ",".join(form["meal_types"])
            recipe.servings, recipe.prep_minutes = form["servings"], form["prep_minutes"]
            recipe.cook_minutes, recipe.difficulty = form["cook_minutes"], form["difficulty"]
            recipe.equipment, recipe.active = form["equipment"], form["active"]
            recipe.categories = Category.query.filter(Category.slug.in_(form["categories"])).all()
            recipe.ingredients = [
                RecipeIngredient(ingredient=ing, quantity=qty, unit=ing.unit, note=note, optional=opt, position=i)
                for i, (ing, qty, note, opt) in enumerate(rows)
            ]
            recipe.steps = [RecipeStep(position=i, text=text) for i, text in enumerate(steps, start=1)]
            db.session.add(recipe)
            db.session.flush()
            recipe.estimated_cost = pricing.recipe_cost(recipe)
            db.session.commit()
            flash("Receta guardada.", "success")
            return redirect(url_for("admin.recipes"))
    return render_template(
        "admin/recipe_form.html", recipe=recipe, form=form, errors=errors,
        categories=Category.query.order_by(Category.sort_order).all(),
        difficulties=DIFFICULTIES, meal_types=MEAL_TYPES,
        ingredient_names=[i.name for i in Ingredient.query.order_by(Ingredient.name).all()],
    )


@bp.route("/recipes/<int:recipe_id>/toggle", methods=["POST"])
def toggle_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id) or abort(404)
    recipe.active = not recipe.active
    db.session.commit()
    flash(f"{recipe.name}: {'activa' if recipe.active else 'oculta'}.", "success")
    return redirect(url_for("admin.recipes"))


# --- Ingredientes ---------------------------------------------------------

FLAGS = [("is_staple", "Básico de despensa"), ("is_meat", "Carne"), ("is_pork", "Cerdo"),
         ("is_fish", "Pescado"), ("is_seafood", "Mariscos"), ("is_dairy", "Lácteo"),
         ("is_egg", "Huevo"), ("is_spicy", "Picante"), ("featured", "Destacado"), ("active", "Activo")]


@bp.route("/ingredients")
def ingredients():
    items = Ingredient.query.join(IngredientCategory).order_by(IngredientCategory.sort_order, Ingredient.name).all()
    return render_template("admin/ingredients.html", ingredients=items)


@bp.route("/ingredients/new", methods=["GET", "POST"])
@bp.route("/ingredients/<int:ingredient_id>/edit", methods=["GET", "POST"])
def ingredient_form(ingredient_id=None):
    ingredient = db.session.get(Ingredient, ingredient_id) if ingredient_id else None
    if ingredient_id and ingredient is None:
        abort(404)
    errors = []
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 80)
        category = db.session.get(IngredientCategory, parse_int(request.form.get("category_id"), default=0))
        unit = request.form.get("unit")
        if not name:
            errors.append("El nombre es obligatorio.")
        duplicate = Ingredient.query.filter(db.func.lower(Ingredient.name) == name.lower()).first()
        if duplicate and duplicate is not ingredient:
            errors.append("Ya existe un ingrediente con ese nombre.")
        if category is None:
            errors.append("Elige una categoría.")
        if unit not in ("g", "ml", "unidad"):
            errors.append("La unidad base debe ser g, ml o unidad.")
        if ingredient and unit != ingredient.unit and RecipeIngredient.query.filter_by(ingredient_id=ingredient.id).first():
            errors.append("No se puede cambiar la unidad de un ingrediente usado en recetas.")
        if not errors:
            is_new = ingredient is None
            ingredient = ingredient or Ingredient()
            ingredient.name, ingredient.category, ingredient.unit = name, category, unit
            ingredient.emoji = clean_text(request.form.get("emoji"), 8)
            for field, _ in FLAGS:
                setattr(ingredient, field, bool(request.form.get(field)))
            db.session.add(ingredient)
            db.session.flush()
            price = parse_float(request.form.get("price"), minimum=0, maximum=10000)
            if is_new and price is not None:
                per = parse_float(request.form.get("per_quantity"), default=1, minimum=0.001, maximum=100000)
                pricing.set_price(ingredient, price, per, today_local())
            db.session.commit()
            flash("Ingrediente guardado.", "success")
            return redirect(url_for("admin.ingredients"))
    return render_template(
        "admin/ingredient_form.html", ingredient=ingredient, errors=errors, flags=FLAGS,
        categories=IngredientCategory.query.order_by(IngredientCategory.sort_order).all(),
    )


# --- Categorías -----------------------------------------------------------

@bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        kind = request.form.get("kind")
        name = clean_text(request.form.get("name"), 60)
        emoji = clean_text(request.form.get("emoji"), 8)
        if not name:
            flash("Escribe un nombre.", "error")
        elif kind == "recipe":
            if Category.query.filter_by(slug=slugify(name)).first():
                flash("Esa categoría ya existe.", "error")
            else:
                db.session.add(Category(name=name, slug=slugify(name), emoji=emoji or "🍽️",
                                        sort_order=Category.query.count()))
                db.session.commit()
                flash("Categoría creada.", "success")
        elif kind == "ingredient":
            group = request.form.get("shopping_group")
            if IngredientCategory.query.filter_by(slug=slugify(name)).first():
                flash("Esa categoría ya existe.", "error")
            else:
                db.session.add(IngredientCategory(
                    name=name, slug=slugify(name), emoji=emoji or "🥫",
                    shopping_group=group if group in SHOPPING_GROUPS else "otros",
                    sort_order=IngredientCategory.query.count(),
                ))
                db.session.commit()
                flash("Categoría creada.", "success")
        return redirect(url_for("admin.categories"))
    return render_template(
        "admin/categories.html",
        recipe_categories=Category.query.order_by(Category.sort_order).all(),
        ingredient_categories=IngredientCategory.query.order_by(IngredientCategory.sort_order).all(),
        shopping_groups=SHOPPING_GROUPS,
    )


@bp.route("/categories/<kind>/<int:category_id>/edit", methods=["POST"])
def edit_category(kind, category_id):
    model = {"recipe": Category, "ingredient": IngredientCategory}.get(kind) or abort(404)
    category = db.session.get(model, category_id) or abort(404)
    name = clean_text(request.form.get("name"), 60)
    if name:
        category.name = name
        category.emoji = clean_text(request.form.get("emoji"), 8) or category.emoji
        if kind == "ingredient" and request.form.get("shopping_group") in SHOPPING_GROUPS:
            category.shopping_group = request.form.get("shopping_group")
        db.session.commit()
        flash("Categoría actualizada.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<kind>/<int:category_id>/delete", methods=["POST"])
def delete_category(kind, category_id):
    if kind == "recipe":
        category = db.session.get(Category, category_id) or abort(404)
        for recipe in Recipe.query.filter(Recipe.categories.contains(category)).all():
            recipe.categories.remove(category)
    elif kind == "ingredient":
        category = db.session.get(IngredientCategory, category_id) or abort(404)
        if category.ingredients:
            flash("No se puede eliminar: tiene ingredientes.", "error")
            return redirect(url_for("admin.categories"))
    else:
        abort(404)
    db.session.delete(category)
    db.session.commit()
    flash("Categoría eliminada.", "info")
    return redirect(url_for("admin.categories"))


# --- Precios --------------------------------------------------------------

@bp.route("/prices", methods=["GET", "POST"])
def prices():
    if request.method == "POST":
        ingredient = db.session.get(Ingredient, parse_int(request.form.get("ingredient_id"), default=0)) or abort(404)
        price = parse_float(request.form.get("price"), minimum=0, maximum=10000)
        per = parse_float(request.form.get("per_quantity"), minimum=0.001, maximum=100000)
        if price is None or per is None:
            flash("Revisa el precio y la cantidad.", "error")
        else:
            pricing.set_price(ingredient, price, per, today_local(), source="admin")
            flash(f"Costo de referencia de {ingredient.name} actualizado. Recetas recalculadas.", "success")
        return redirect(url_for("admin.prices", q=request.form.get("q", "")))
    q = normalize(request.args.get("q"))
    items = Ingredient.query.order_by(Ingredient.name).all()
    if q:
        items = [i for i in items if q in normalize(i.name)]
    return render_template("admin/prices.html", ingredients=items, q=request.args.get("q", ""))


# --- Usuarios -------------------------------------------------------------

@bp.route("/users")
def users():
    return render_template("admin/users.html", users=User.query.order_by(User.created_at.desc()).all())


@bp.route("/users/<int:user_id>/<action>", methods=["POST"])
def user_action(user_id, action):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("No puedes modificar tu propia cuenta desde aquí.", "error")
        return redirect(url_for("admin.users"))
    if action == "toggle-active":
        user.active = not user.active
        flash(f"{user.email}: {'activo' if user.active else 'desactivado'}.", "success")
    elif action == "toggle-admin":
        user.is_admin = not user.is_admin
        flash(f"{user.email}: {'ahora es administrador' if user.is_admin else 'ya no es administrador'}.", "success")
    elif action == "delete":
        user_service.delete_account(user)
        flash("Usuario eliminado con todos sus datos.", "info")
        return redirect(url_for("admin.users"))
    else:
        abort(404)
    db.session.commit()
    return redirect(url_for("admin.users"))


# --- Mensajes de contacto -------------------------------------------------

@bp.route("/messages")
def messages():
    items = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    response = render_template("admin/messages.html", messages=items)
    for message in items:
        message.read = True
    db.session.commit()
    return response
