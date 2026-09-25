import pytest

from app import create_app
from app.data import seeder
from app.extensions import db
from app.models import InventoryItem, ShoppingListItem, User
from app.services import shopping_service, user_service

from .conftest import login

PRIVATE_PAGES = ["/inventory/", "/shopping-list/", "/meal-plan/", "/favorites", "/history", "/profile",
                 "/onboarding", "/profile/export", "/profile/family"]


@pytest.mark.parametrize("url", PRIVATE_PAGES)
def test_anonymous_is_redirected_to_login(client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


@pytest.mark.parametrize("url", ["/api/inventory", "/api/shopping-list", "/api/meal-plan", "/api/favorites", "/api/profile"])
def test_api_requires_login(client, url):
    response = client.get(url)
    assert response.status_code == 401
    assert "error" in response.get_json()


def test_public_pages_work_without_account(client):
    for url in ["/", "/cook/", "/recipes", "/recipes/seco-de-pollo", "/privacy", "/terms", "/contact"]:
        assert client.get(url).status_code == 200


def _other_user():
    other = user_service.create_user("Otro", "Usuario", "otro@example.com", "Otro12345", "Loja")
    other.onboarding_done = True
    db.session.commit()
    return other


def test_users_cannot_touch_each_others_data(demo_client, demo_user, ing):
    other = _other_user()
    item = InventoryItem(user_id=other.id, ingredient_id=ing("Tomate"), quantity=1, unit="kg")
    db.session.add(item)
    shop_item, _ = shopping_service.add_ingredient(other, db.session.get(__import__("app").models.Ingredient, ing("Limón")))
    db.session.commit()

    assert demo_client.post(f"/inventory/{item.id}/delete").status_code == 404
    assert demo_client.get(f"/inventory/{item.id}/edit").status_code == 404
    assert demo_client.post(f"/shopping-list/{shop_item.id}/toggle").status_code == 404
    assert demo_client.post(f"/shopping-list/{shop_item.id}/delete").status_code == 404
    assert db.session.get(InventoryItem, item.id) is not None
    assert db.session.get(ShoppingListItem, shop_item.id).checked is False


def test_admin_requires_admin_role(client, demo_client):
    assert demo_client.get("/admin/").status_code == 403
    assert demo_client.get("/admin/recipes").status_code == 403
    assert demo_client.post("/admin/users/1/delete").status_code == 403


def test_admin_anonymous_redirects(app):
    anon = app.test_client()
    response = anon.get("/admin/")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_admin_can_access_panel_and_crud(admin_client, recipe):
    assert admin_client.get("/admin/").status_code == 200
    response = admin_client.post("/admin/recipes/new", data={
        "name": "Huevos pericos", "description": "Rápidos", "emoji": "🍳", "meal_types": ["desayuno"],
        "servings": "2", "prep_minutes": "5", "cook_minutes": "5", "difficulty": "Fácil",
        "categories": ["desayunos"], "active": "1",
        "ingredients_text": "Huevo | 4\nTomate | 100 | picado\nCebolla blanca (larga) | 30\nSal | 2 | al gusto",
        "steps_text": "Sofríe tomate y cebolla.\nAgrega los huevos y revuelve.",
    })
    assert response.status_code == 302
    created = recipe("Huevos pericos")
    assert created.estimated_cost > 0 and len(created.steps) == 2

    response = admin_client.post("/admin/recipes/new", data={
        "name": "Mala", "meal_types": ["cena"], "servings": "2", "prep_minutes": "5", "cook_minutes": "5",
        "ingredients_text": "Ingrediente inventado | 10", "steps_text": "Paso",
    })
    assert "no existe el ingrediente" in response.get_data(as_text=True)


def test_admin_cannot_modify_self(admin_client):
    admin = User.query.filter_by(email="admin@quecocino.local").one()
    admin_client.post(f"/admin/users/{admin.id}/toggle-active")
    db.session.refresh(admin)
    assert admin.active


def test_passwords_are_hashed(app):
    for user in User.query.all():
        assert user.password_hash.startswith(("scrypt:", "pbkdf2:"))


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_templates_escape_user_input(client):
    html = client.get("/recipes?q=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.fixture
def csrf_client():
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        seeder.run(with_demo=True)
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_csrf_blocks_posts_without_token(csrf_client):
    response = csrf_client.post("/login", data={"email": "demo@quecocino.local", "password": "Demo1234!"})
    assert response.status_code == 400
    assert "Tu sesión expiró" in response.get_data(as_text=True)


def test_csrf_accepts_valid_token(csrf_client):
    import re
    html = csrf_client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    response = csrf_client.post("/login", data={"email": "demo@quecocino.local", "password": "Demo1234!",
                                                 "csrf_token": token})
    assert response.status_code == 302


def test_logout_requires_post(demo_client):
    assert demo_client.get("/logout").status_code == 405
