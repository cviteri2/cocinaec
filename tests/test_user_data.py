"""Inventario, lista de compras, favoritos, historial y plan semanal."""
from datetime import timedelta

from app.extensions import db
from app.models import (CookingHistory, FavoriteRecipe, InventoryItem, MealPlan, MealPlanItem,
                        ShoppingListItem)
from app.utils import today_local, week_start


# --- Inventario -------------------------------------------------------------

def test_inventory_add_edit_delete(demo_client, demo_user, ing):
    before = InventoryItem.query.filter_by(user_id=demo_user.id).count()
    exp = (today_local() + timedelta(days=1)).isoformat()
    demo_client.post("/inventory/add", data={"ingredient_id": ing("Zanahoria"), "quantity": "1", "unit": "kg",
                                             "expiration_date": exp})
    item = InventoryItem.query.filter_by(user_id=demo_user.id, ingredient_id=ing("Zanahoria")).one()
    assert InventoryItem.query.filter_by(user_id=demo_user.id).count() == before + 1
    assert "Zanahoria" in demo_client.get("/inventory/").get_data(as_text=True)

    demo_client.post(f"/inventory/{item.id}/edit", data={"ingredient_id": ing("Zanahoria"), "quantity": "2",
                                                         "unit": "kg", "expiration_date": ""})
    db.session.refresh(item)
    assert item.quantity == 2 and item.expiration_date is None

    demo_client.post(f"/inventory/{item.id}/delete")
    assert db.session.get(InventoryItem, item.id) is None


def test_inventory_rejects_invalid_ingredient(demo_client, demo_user):
    before = InventoryItem.query.filter_by(user_id=demo_user.id).count()
    response = demo_client.post("/inventory/add", data={"ingredient_id": "99999"}, follow_redirects=True)
    assert "Elige un ingrediente" in response.get_data(as_text=True)
    assert InventoryItem.query.filter_by(user_id=demo_user.id).count() == before


def test_use_first_shows_items_about_to_expire(demo_client):
    html = demo_client.get("/inventory/").get_data(as_text=True)
    assert "Aprovecha primero" in html
    assert "Tomate" in html


def test_inventory_empty_state(demo_client):
    demo_client.post("/inventory/clear")
    html = demo_client.get("/inventory/").get_data(as_text=True)
    assert "Tu refrigeradora está esperando una idea" in html


# --- Lista de compras y "Me falta" ------------------------------------------

def _items(user):
    return ShoppingListItem.query.join(ShoppingListItem.shopping_list).filter_by(user_id=user.id).all()


def test_missing_ingredients_go_to_shopping_list(demo_client, demo_user):
    demo_client.post("/shopping-list/clear")
    response = demo_client.post("/recipes/seco-de-pollo/missing-to-list", data={"people": "4"})
    assert response.status_code == 302
    names = {i.name for i in _items(demo_user)}
    # El demo tiene pollo, arroz, tomate y cebolla en su inventario
    assert names == {"Pimiento", "Culantro"}
    item = next(i for i in _items(demo_user) if i.name == "Pimiento")
    assert item.category == "verduras"


def test_missing_to_list_requires_login(client):
    response = client.post("/recipes/seco-de-pollo/missing-to-list")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_shopping_add_toggle_delete_clear(demo_client, demo_user):
    demo_client.post("/shopping-list/clear")
    demo_client.post("/shopping-list/add", data={"name": "Detergente", "category": "limpieza"})
    demo_client.post("/shopping-list/add", data={"name": "tomate", "category": "otros"})
    items = {i.name: i for i in _items(demo_user)}
    assert items["Detergente"].category == "limpieza"
    assert items["Tomate"].category == "verduras"  # se reconoce el ingrediente

    response = demo_client.post(f"/shopping-list/{items['Tomate'].id}/toggle", headers={"Accept": "application/json"})
    assert response.get_json()["checked"] is True
    html = demo_client.get("/shopping-list/").get_data(as_text=True)
    assert "Limpieza" in html and "Verduras" in html

    demo_client.post("/shopping-list/clear-checked")
    assert {i.name for i in _items(demo_user)} == {"Detergente"}

    demo_client.post(f"/shopping-list/{items['Detergente'].id}/delete")
    assert _items(demo_user) == []
    assert "Tu lista está vacía" in demo_client.get("/shopping-list/").get_data(as_text=True)


# --- Favoritos e historial -------------------------------------------------

def test_favorites_add_and_remove(demo_client, demo_user, recipe):
    guatita = recipe("Guatita")
    demo_client.post("/recipes/guatita/favorite")
    assert FavoriteRecipe.query.filter_by(user_id=demo_user.id, recipe_id=guatita.id).count() == 1
    assert "Guatita" in demo_client.get("/favorites").get_data(as_text=True)
    demo_client.post("/recipes/guatita/favorite")
    assert FavoriteRecipe.query.filter_by(user_id=demo_user.id, recipe_id=guatita.id).count() == 0


def test_favorites_clear_and_empty_state(demo_client):
    demo_client.post("/favorites/clear")
    assert "Todavía no tienes recetas favoritas" in demo_client.get("/favorites").get_data(as_text=True)


def test_mark_cooked_adds_history(demo_client, demo_user):
    before = CookingHistory.query.filter_by(user_id=demo_user.id).count()
    demo_client.post("/recipes/locro-de-papa/cooked", data={"servings": "3"})
    entries = CookingHistory.query.filter_by(user_id=demo_user.id).order_by(CookingHistory.id.desc()).all()
    assert len(entries) == before + 1
    assert entries[0].servings == 3 and entries[0].estimated_cost > 0
    assert "Locro de papa" in demo_client.get("/history").get_data(as_text=True)


# --- Plan semanal ----------------------------------------------------------

def _plan(user):
    return MealPlan.query.filter_by(user_id=user.id, week_start=week_start()).first()


def test_meal_plan_add_edit_delete(demo_client, demo_user, recipe):
    demo_client.post("/meal-plan/clear")
    assert _plan(demo_user) is None
    guatita = recipe("Guatita")
    demo_client.post("/meal-plan/set", data={"day": "2", "meal": "cena", "recipe_id": guatita.id})
    plan = _plan(demo_user)
    item = MealPlanItem.query.filter_by(meal_plan_id=plan.id, day=2, meal_type="cena").one()
    assert item.recipe_id == guatita.id

    locro = recipe("Locro de papa")
    demo_client.post("/meal-plan/set", data={"day": "2", "meal": "cena", "recipe_id": locro.id})
    db.session.refresh(item)
    assert item.recipe_id == locro.id  # se reemplaza, no se duplica

    demo_client.post(f"/meal-plan/item/{item.id}/delete")
    assert MealPlanItem.query.filter_by(meal_plan_id=plan.id).count() == 0


def test_generate_plan_respects_budget_and_restrictions(demo_client, demo_user):
    demo_client.post("/meal-plan/generate", data={
        "people": "4", "weekly_budget": "40", "meals": ["almuerzo"], "restrictions": ["vegetariano"],
    })
    plan = _plan(demo_user)
    assert len(plan.items) == 7
    assert len({i.recipe_id for i in plan.items}) == 7  # sin repetir
    for item in plan.items:
        assert not any(ri.ingredient.is_meat and not ri.optional for ri in item.recipe.ingredients)
    html = demo_client.get("/meal-plan/").get_data(as_text=True)
    assert "Presupuesto semanal" in html and "Plan estimado" in html


def test_generate_plan_with_lunch_and_dinner(demo_client, demo_user):
    demo_client.post("/meal-plan/generate", data={"people": "2", "meals": ["almuerzo", "cena"]})
    assert len(_plan(demo_user).items) == 14


def test_weekly_shopping_list_consolidates(demo_client, demo_user, recipe):
    demo_client.post("/meal-plan/clear")
    demo_client.post("/shopping-list/clear")
    demo_client.post("/inventory/clear")
    for day in (0, 1):
        demo_client.post("/meal-plan/set", data={"day": day, "meal": "almuerzo", "recipe_id": recipe("Seco de pollo").id})
    demo_client.post("/meal-plan/shopping")
    items = {i.name: i for i in _items(demo_user)}
    assert "Pollo (presas)" in items
    # 2 veces 1200 g para 4 personas (el plan del demo es para 4)
    assert items["Pollo (presas)"].quantity == 2400
    assert "Sal" not in items  # los básicos se omiten
