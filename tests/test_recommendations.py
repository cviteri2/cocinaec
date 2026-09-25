from app.services import recommendation_service as rec


def _names(matches):
    return [m.recipe.name for m in matches]


def test_uses_available_ingredients(app, ing):
    have = {ing(n) for n in ["Pollo (presas)", "Arroz", "Papa", "Tomate", "Cebolla colorada"]}
    matches = rec.recommend(rec.Criteria(have_ids=have, people=4, meal_type="almuerzo", max_minutes=45, budget=5))
    assert len(matches) == 3
    assert matches[0].recipe.name == "Arroz con pollo"
    assert all(m.have_count > 0 for m in matches)


def test_respects_time(app, ing):
    have = {ing(n) for n in ["Pollo (presas)", "Arroz", "Papa", "Tomate", "Cebolla colorada"]}
    matches = rec.recommend(rec.Criteria(have_ids=have, people=4, max_minutes=30), limit=10)
    assert matches
    for m in matches:
        assert m.recipe.total_minutes <= 30 + rec.TIME_TOLERANCE
    assert matches[0].fits_time


def test_respects_budget_on_missing_ingredients(app, ing):
    have = {ing("Arroz")}
    matches = rec.recommend(rec.Criteria(have_ids=have, people=4, budget=3), limit=3)
    assert matches
    assert all(m.missing_cost <= 3 for m in matches)


def test_cost_scales_with_people(app, ing, recipe):
    seco = recipe("Seco de pollo")
    four = rec.analyze_recipe(seco, set(), people=4)
    eight = rec.analyze_recipe(seco, set(), people=8)
    assert abs(eight.total_cost - 2 * four.total_cost) < 0.02


def test_coverage_and_missing(app, ing, recipe):
    seco = recipe("Seco de pollo")
    have = {ing(n) for n in ["Pollo (presas)", "Arroz", "Tomate", "Cebolla colorada"]}
    match = rec.analyze_recipe(seco, have, people=4)
    missing = {ri.ingredient.name for ri in match.missing}
    assert missing == {"Pimiento", "Culantro"}  # sal, ajo, aceite son básicos
    assert match.required_count == 6
    assert match.have_count == 4
    assert match.coverage_pct == 67


def test_substitutes_count_as_available(app, ing, recipe):
    salteado = recipe("Pollo salteado con verduras")  # usa pechuga
    match = rec.analyze_recipe(salteado, {ing("Pollo (presas)")})
    assert "Pechuga de pollo" not in {ri.ingredient.name for ri in match.missing}
    assert match.substitutions_used


def test_vegetarian_is_a_hard_filter(app, ing):
    have = {ing(n) for n in ["Pollo (presas)", "Arroz", "Papa", "Huevo"]}
    matches = rec.recommend(rec.Criteria(have_ids=have, restrictions=["vegetariano"]), limit=20)
    assert matches
    for m in matches:
        assert not any((ri.ingredient.is_meat or ri.ingredient.is_fish or ri.ingredient.is_seafood)
                       and not ri.optional for ri in m.recipe.ingredients)


def test_excluded_ingredients_are_filtered(app, ing):
    have = {ing("Pollo (presas)")}
    excluded = {ing("Pollo (presas)"), ing("Pechuga de pollo")}
    matches = rec.recommend(rec.Criteria(have_ids=have | {ing("Arroz")}, excluded_ids=excluded), limit=50)
    for m in matches:
        assert not ({ri.ingredient_id for ri in m.recipe.ingredients if not ri.optional} & excluded)


def test_meal_type_is_prioritised(app, ing):
    have = {ing(n) for n in ["Huevo", "Plátano verde", "Queso fresco"]}
    matches = rec.recommend(rec.Criteria(have_ids=have, meal_type="desayuno", max_minutes=45))
    assert all("desayuno" in m.recipe.meal_type_list for m in matches)


def test_cook_with_what_i_have_orders_by_fewest_missing(app, ing):
    have = {ing(n) for n in ["Huevo", "Papa", "Cebolla colorada"]}
    matches = rec.cook_with_what_i_have(have, people=4)
    assert matches[0].recipe.name == "Tortilla de papa"
    assert not matches[0].missing
    counts = [len(m.missing) for m in matches]
    assert counts == sorted(counts)


def test_results_page_and_validation(client, ing):
    response = client.get("/cook/results?people=4")
    assert response.status_code == 400
    assert "Agrega al menos un ingrediente" in response.get_data(as_text=True)
    response = client.get(f"/cook/results?i={ing('Pollo (presas)')}&i={ing('Arroz')}&people=4&time=45&budget=5&meal=almuerzo")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Encontramos estas ideas para ti" in html
    assert "Elegimos estas opciones según lo que tienes" in html
    assert "Tienes" in html and "ingredientes" in html
    assert "puntos" not in html.lower()


def test_free_text_ingredient(client):
    html = client.get("/cook/results?extra=pollo,arroz,xyzfoo&people=2").get_data(as_text=True)
    assert "Encontramos estas ideas" in html
    assert "xyzfoo" in html  # avisa lo que no reconoció


def test_pantry_page(client, ing):
    html = client.get(f"/cook/pantry?i={ing('Huevo')}&i={ing('Papa')}").get_data(as_text=True)
    assert "Puedes preparar" in html
    assert "Tortilla de papa" in html
