from app.models import Category, Ingredient, Recipe
from app.services import pricing


def test_seed_has_enough_content(app):
    assert Ingredient.query.count() >= 60
    assert Recipe.query.count() >= 40
    assert Category.query.count() >= 10
    names = {r.name for r in Recipe.query.all()}
    for required in ["Seco de pollo", "Encebollado", "Locro de papa", "Bolón de verde", "Arroz con pollo",
                     "Pizza casera", "Ensalada de atún", "Llapingachos", "Guatita"]:
        assert required in names


def test_every_recipe_has_cost_steps_and_ingredients(app):
    for recipe in Recipe.query.all():
        assert recipe.estimated_cost > 0, recipe.name
        assert recipe.steps, recipe.name
        assert recipe.ingredients, recipe.name


def test_recipe_list(client):
    response = client.get("/recipes")
    assert response.status_code == 200
    assert "recetas" in response.get_data(as_text=True)


def test_search_by_recipe_and_ingredient(client):
    html = client.get("/recipes?q=pollo").get_data(as_text=True)
    for name in ["Arroz con pollo", "Seco de pollo", "Pollo al horno con papas", "Pollo apanado"]:
        assert name in html
    html = client.get("/recipes?q=platano").get_data(as_text=True)  # sin tilde también funciona
    assert "Bolón de verde" in html


def test_filters(client, recipe):
    html = client.get("/recipes?quick=rapido").get_data(as_text=True)
    assert "Ensalada de atún" in html
    assert "Seco de carne" not in html
    html = client.get("/recipes?category=sopas").get_data(as_text=True)
    assert "Locro de papa" in html and "Pollo apanado" not in html
    html = client.get("/recipes?r=vegetariano").get_data(as_text=True)
    assert "Seco de pollo" not in html
    html = client.get("/recipes?difficulty=Media&meal=almuerzo").get_data(as_text=True)
    assert "Guatita" in html and "Arroz con huevo" not in html


def test_recipe_detail_shows_steps_cost_note_and_missing(client):
    html = client.get("/recipes/seco-de-pollo?people=4").get_data(as_text=True)
    assert "Preparación" in html
    assert "estimado" in html
    assert "Te faltan" in html
    assert "Los tiempos y cantidades son aproximados" in html


def test_recipe_detail_scales_quantities(client):
    html4 = client.get("/recipes/seco-de-pollo?people=4").get_data(as_text=True)
    html8 = client.get("/recipes/seco-de-pollo?people=8").get_data(as_text=True)
    assert "1,2 kg" in html4
    assert "2,4 kg" in html8


def test_unknown_recipe_is_friendly_404(client):
    response = client.get("/recipes/no-existe")
    assert response.status_code == 404
    assert "No encontramos esa página" in response.get_data(as_text=True)


def test_price_update_recalculates_recipe_cost(app, recipe):
    seco = recipe("Seco de pollo")
    before = seco.estimated_cost
    pollo = Ingredient.query.filter_by(name="Pollo (presas)").one()
    from datetime import date
    pricing.set_price(pollo, 6.60, 1000, date(2026, 9, 20))
    assert recipe("Seco de pollo").estimated_cost > before
    assert pollo.current_price.price == 6.60
    assert len(pollo.prices) == 2  # se conserva el historial
