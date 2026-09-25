from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import RESTRICTIONS, Recipe
from ..services import meal_plan_service as mps, recipe_service
from ..utils import DAY_NAMES, parse_date, parse_float, parse_int, week_start

bp = Blueprint("meal_plan", __name__, url_prefix="/meal-plan")


@bp.before_request
@login_required
def require_login():
    pass


def _week():
    requested = parse_date(request.values.get("week"))
    return week_start(requested) if requested else week_start()


def _redirect(week):
    return redirect(url_for("meal_plan.index", week=week.isoformat()))


@bp.route("/")
def index():
    week = _week()
    plan = mps.get_plan(current_user, week)
    pref = current_user.preference
    return render_template(
        "meal_plan/index.html",
        week=week,
        prev_week=week - timedelta(days=7),
        next_week=week + timedelta(days=7),
        is_current=week == week_start(),
        plan=plan,
        grid=mps.grid(plan),
        plan_meals=mps.PLAN_MEALS,
        summary=mps.budget_summary(plan) if plan else None,
        costs={item.id: mps.item_cost(item) for item in plan.items} if plan else {},
        categories=recipe_service.categories(),
        restrictions=RESTRICTIONS,
        pref=pref,
    )


@bp.route("/generate", methods=["POST"])
def generate():
    people = parse_int(request.form.get("people"), default=2, minimum=1, maximum=20)
    budget = parse_float(request.form.get("weekly_budget"), default=None, minimum=1, maximum=10000)
    meals = request.form.getlist("meals") or ["almuerzo"]
    preferences = request.form.getlist("preferences")
    restrictions = [r for r in request.form.getlist("restrictions") if r in RESTRICTIONS]
    plan = mps.generate(current_user, people, budget, meals, preferences, restrictions, start=_week())
    summary = mps.budget_summary(plan)
    if budget is not None and summary["available"] < 0:
        flash("Armamos tu menú, pero se pasa un poco del presupuesto. Puedes cambiar algunas comidas.", "info")
    else:
        flash("¡Listo! Este es tu menú de la semana.", "success")
    return _redirect(plan.week_start)


@bp.route("/settings", methods=["POST"])
def settings():
    week = _week()
    plan = mps.get_plan(current_user, week, create=True)
    plan.people_count = parse_int(request.form.get("people"), default=plan.people_count, minimum=1, maximum=20)
    plan.weekly_budget = parse_float(request.form.get("weekly_budget"), default=None, minimum=1, maximum=10000)
    if request.form.get("apply_people"):
        for item in plan.items:
            item.servings = plan.people_count
    db.session.commit()
    flash("Plan actualizado.", "success")
    return _redirect(week)


@bp.route("/pick")
def pick():
    week = _week()
    day = parse_int(request.args.get("day"), minimum=0, maximum=6)
    meal = request.args.get("meal")
    if day is None or meal not in mps.PLAN_MEALS:
        abort(404)
    filters = recipe_service.filters_from_args(request.args)
    filters["meal"] = meal
    page = recipe_service.search(filters, page=1, per_page=60)
    return render_template("meal_plan/pick.html", week=week, day=day, day_name=DAY_NAMES[day],
                           meal=meal, meal_name=mps.PLAN_MEALS[meal], recipes=page.items, q=filters["q"])


@bp.route("/set", methods=["POST"])
def set_item():
    week = _week()
    day = parse_int(request.form.get("day"), minimum=0, maximum=6)
    meal = request.form.get("meal")
    recipe = db.session.get(Recipe, parse_int(request.form.get("recipe_id"), default=0))
    if day is None or meal not in mps.PLAN_MEALS or recipe is None or not recipe.active:
        flash("No pudimos agregar esa receta. Intenta nuevamente.", "error")
        return _redirect(week)
    plan = mps.get_plan(current_user, week, create=True)
    mps.set_item(plan, day, meal, recipe)
    flash(f"{recipe.name} quedó para el {DAY_NAMES[day].lower()} ({mps.PLAN_MEALS[meal].lower()}).", "success")
    return _redirect(week)


@bp.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    item = mps.get_item(current_user, item_id) or abort(404)
    week = item.meal_plan.week_start
    db.session.delete(item)
    db.session.commit()
    flash("Quitamos esa comida del plan.", "info")
    return _redirect(week)


@bp.route("/shopping", methods=["POST"])
def weekly_shopping():
    week = _week()
    plan = mps.get_plan(current_user, week)
    if not plan or not plan.items:
        flash("Primero agrega recetas a tu plan.", "error")
        return _redirect(week)
    added, total = mps.weekly_shopping_list(current_user, plan)
    flash(f"Tu lista semanal está lista: {total} producto(s) consolidados, {added} nuevo(s).", "success")
    return redirect(url_for("shopping.index"))


@bp.route("/clear", methods=["POST"])
def clear():
    week = _week()
    plan = mps.get_plan(current_user, week)
    if plan:
        db.session.delete(plan)
        db.session.commit()
    flash("Borramos el plan de esa semana.", "info")
    return _redirect(week)
