from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Ingredient
from ..services import inventory_service
from ..services.pricing import UNIT_CHOICES
from ..utils import parse_date, parse_float, parse_int, today_local

bp = Blueprint("inventory", __name__, url_prefix="/inventory")
VALID_UNITS = {u for u, _ in UNIT_CHOICES}


@bp.before_request
@login_required
def require_login():
    pass


def _read_form():
    ingredient = db.session.get(Ingredient, parse_int(request.form.get("ingredient_id"), default=0))
    quantity = parse_float(request.form.get("quantity"), default=None, minimum=0, maximum=100000)
    unit = request.form.get("unit") if request.form.get("unit") in VALID_UNITS else None
    raw_date = request.form.get("expiration_date")
    expiration = parse_date(raw_date)
    errors = []
    if ingredient is None or not ingredient.active:
        errors.append("Elige un ingrediente de la lista.")
    if raw_date and expiration is None:
        errors.append("La fecha de vencimiento no es válida.")
    return ingredient, quantity, unit or (ingredient.unit if ingredient else None), expiration, errors


@bp.route("/")
def index():
    return render_template(
        "inventory/index.html",
        items=inventory_service.items_for(current_user),
        use_first=inventory_service.use_first(current_user),
        catalog=inventory_service.grouped_catalog(include_staples=True),
        units=UNIT_CHOICES,
        today=today_local(),
    )


@bp.route("/add", methods=["POST"])
def add():
    ingredient, quantity, unit, expiration, errors = _read_form()
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        inventory_service.upsert(current_user, ingredient, quantity, unit, expiration)
        flash(f"{ingredient.name} agregado a tu inventario.", "success")
    return redirect(url_for("inventory.index"))


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id):
    item = inventory_service.get_item(current_user, item_id) or abort(404)
    if request.method == "POST":
        ingredient, quantity, unit, expiration, errors = _read_form()
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            item.ingredient_id = ingredient.id
            item.quantity = quantity
            item.unit = unit
            item.expiration_date = expiration
            db.session.commit()
            flash("Inventario actualizado.", "success")
            return redirect(url_for("inventory.index"))
    return render_template("inventory/edit.html", item=item, catalog=inventory_service.grouped_catalog(include_staples=True),
                           units=UNIT_CHOICES)


@bp.route("/<int:item_id>/delete", methods=["POST"])
def delete(item_id):
    item = inventory_service.get_item(current_user, item_id) or abort(404)
    name = item.ingredient.name
    db.session.delete(item)
    db.session.commit()
    flash(f"{name} eliminado del inventario.", "info")
    return redirect(url_for("inventory.index"))


@bp.route("/clear", methods=["POST"])
def clear():
    inventory_service.clear(current_user)
    flash("Vaciamos tu inventario.", "info")
    return redirect(url_for("inventory.index"))
