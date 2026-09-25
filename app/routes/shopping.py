from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import SHOPPING_GROUPS
from ..services import shopping_service
from ..utils import clean_text

bp = Blueprint("shopping", __name__, url_prefix="/shopping-list")


@bp.before_request
@login_required
def require_login():
    pass


def _wants_json():
    return request.accept_mimetypes.best == "application/json"


@bp.route("/")
def index():
    shopping_list = shopping_service.get_active_list(current_user)
    db.session.commit()
    return render_template(
        "shopping/index.html",
        groups=shopping_service.grouped_items(shopping_list),
        total=len(shopping_list.items),
        checked=sum(1 for i in shopping_list.items if i.checked),
        shopping_groups=SHOPPING_GROUPS,
    )


@bp.route("/add", methods=["POST"])
def add():
    name = clean_text(request.form.get("name"), 80)
    if not name:
        flash("Escribe qué quieres agregar.", "error")
    else:
        item = shopping_service.add_manual(current_user, name, request.form.get("category", "otros"))
        flash(f"{item.name} está en tu lista.", "success")
    return redirect(url_for("shopping.index"))


@bp.route("/<int:item_id>/toggle", methods=["POST"])
def toggle(item_id):
    item = shopping_service.get_item(current_user, item_id) or abort(404)
    item.checked = not item.checked
    db.session.commit()
    if _wants_json():
        return jsonify({"id": item.id, "checked": item.checked,
                        "pending": shopping_service.pending_count(current_user)})
    return redirect(url_for("shopping.index"))


@bp.route("/<int:item_id>/delete", methods=["POST"])
def delete(item_id):
    item = shopping_service.get_item(current_user, item_id) or abort(404)
    db.session.delete(item)
    db.session.commit()
    if _wants_json():
        return jsonify({"id": item_id, "deleted": True,
                        "pending": shopping_service.pending_count(current_user)})
    return redirect(url_for("shopping.index"))


@bp.route("/clear-checked", methods=["POST"])
def clear_checked():
    count = shopping_service.clear_checked(current_user)
    flash(f"Limpiamos {count} producto(s) comprado(s)." if count else "No había productos comprados.", "info")
    return redirect(url_for("shopping.index"))


@bp.route("/clear", methods=["POST"])
def clear():
    shopping_service.clear_all(current_user)
    flash("Tu lista quedó vacía.", "info")
    return redirect(url_for("shopping.index"))
