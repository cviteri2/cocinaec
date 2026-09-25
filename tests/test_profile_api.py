from app.extensions import db
from app.models import AnalyticsEvent, ContactMessage, InventoryItem, User

from .conftest import login


def test_profile_update(demo_client, demo_user):
    demo_client.post("/profile", data={"section": "personal", "first_name": "César", "last_name": "Nuevo",
                                       "city": "Cuenca"})
    db.session.refresh(demo_user)
    assert demo_user.last_name == "Nuevo" and demo_user.city == "Cuenca"


def test_profile_preferences_no_restrictions(demo_client, demo_user):
    demo_client.post("/profile", data={"section": "preferences", "people_count": "3", "default_time": "0",
                                       "default_budget": "8", "no_restrictions": "1", "restrictions": ["sin_huevo"]})
    db.session.refresh(demo_user)
    pref = demo_user.preference
    assert pref.people_count == 3 and pref.default_time is None and pref.default_budget == 8
    assert pref.restrictions == [] and pref.excluded_ingredients == []


def test_change_password(demo_client, client):
    demo_client.post("/profile", data={"section": "password", "current_password": "Demo1234!",
                                       "new_password": "OtraClave99", "new_password_confirm": "OtraClave99"})
    demo_client.post("/logout")
    assert login(client, password="OtraClave99").status_code == 302


def test_export_data(demo_client):
    response = demo_client.get("/profile/export")
    data = response.get_json(force=True)
    assert data["usuario"]["email"] == "demo@quecocino.local"
    assert data["inventario"] and data["favoritos"] and data["consentimientos"]
    assert "password" not in response.get_data(as_text=True).lower()


def test_delete_account_removes_personal_data(demo_client, demo_user):
    user_id = demo_user.id
    demo_client.get("/recipes/seco-de-pollo")  # genera un evento de métricas
    response = demo_client.post("/profile/delete", data={"password": "Demo1234!", "confirm": "ELIMINAR"})
    assert response.status_code == 302
    assert db.session.get(User, user_id) is None
    assert InventoryItem.query.filter_by(user_id=user_id).count() == 0
    assert AnalyticsEvent.query.filter_by(user_id=user_id).count() == 0
    assert AnalyticsEvent.query.filter_by(event_type="recipe_view").count() >= 1  # métricas anónimas


def test_delete_account_requires_confirmation(demo_client, demo_user):
    demo_client.post("/profile/delete", data={"password": "Demo1234!", "confirm": "no"})
    assert db.session.get(User, demo_user.id) is not None


def test_family_member(demo_client, demo_user):
    demo_client.post("/profile/family", data={"name": "Sofía", "relationship": "hija", "avoided_foods": "pescado"})
    assert "Sofía" in demo_client.get("/profile/family").get_data(as_text=True)


def test_contact_saves_message(client):
    client.post("/contact", data={"name": "Luis", "email": "luis@example.com", "message": "Falta el hornado"})
    assert ContactMessage.query.filter_by(email="luis@example.com").count() == 1


def test_contact_validation(client):
    html = client.post("/contact", data={"name": "", "email": "x", "message": ""}).get_data(as_text=True)
    assert "Revisa tu email" in html


def test_api_recipes_and_recommendations(client, ing):
    data = client.get("/api/recipes?q=pollo").get_json()
    assert data["total"] >= 4
    assert data["items"][0]["cost_note"] == "Costo estimado de referencia"
    detail = client.get("/api/recipes/seco-de-pollo").get_json()
    assert detail["steps"] and detail["ingredients"]
    assert client.get("/api/recipes/nada").status_code == 404
    rec = client.get(f"/api/recommendations?i={ing('Pollo (presas)')}&i={ing('Arroz')}&people=4").get_json()
    assert len(rec["items"]) == 3 and "coverage_pct" in rec["items"][0]
    assert client.get("/api/recommendations").status_code == 400


def test_api_user_endpoints(demo_client):
    assert demo_client.get("/api/inventory").get_json()
    assert demo_client.get("/api/favorites").get_json()
    assert demo_client.get("/api/meal-plan").get_json()["items"]
    assert demo_client.get("/api/profile").get_json()["preferences"]["people_count"] == 4


def test_home_after_login(demo_client):
    html = demo_client.get("/").get_data(as_text=True)
    assert "Hola, César" in html
    assert "Según lo que tienes" in html
    assert "Tus favoritas" in html and "Esta semana" in html and "Tu lista" in html
