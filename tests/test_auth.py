from app.models import Consent, User

from .conftest import login

VALID = {
    "first_name": "Ana", "last_name": "Pérez", "email": "ana@example.com",
    "password": "Cocina123", "password_confirm": "Cocina123", "city": "Quito",
    "accept_terms": "1", "accept_privacy": "1",
}


def test_register_creates_user_with_hashed_password_and_consents(client):
    response = client.post("/register", data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/onboarding")
    user = User.query.filter_by(email="ana@example.com").one()
    assert user.password_hash != "Cocina123"
    assert user.check_password("Cocina123")
    assert {c.consent_type for c in Consent.query.filter_by(user_id=user.id)} == {"terms", "privacy"}


def test_register_requires_terms_and_privacy(client):
    data = {**VALID, "accept_terms": "", "accept_privacy": ""}
    response = client.post("/register", data=data)
    assert response.status_code == 200
    assert "Necesitas aceptar los términos" in response.get_data(as_text=True)
    assert User.query.filter_by(email="ana@example.com").first() is None


def test_register_rejects_weak_password_and_duplicate_email(client):
    response = client.post("/register", data={**VALID, "password": "123", "password_confirm": "123"})
    assert "al menos 8 caracteres" in response.get_data(as_text=True)
    response = client.post("/register", data={**VALID, "email": "demo@quecocino.local"})
    assert "Ya existe una cuenta" in response.get_data(as_text=True)


def test_login_and_logout(client):
    response = login(client)
    assert response.status_code == 302
    home = client.get("/")
    assert "Hola, César" in home.get_data(as_text=True)
    response = client.post("/logout")
    assert response.status_code == 302
    assert "Hola, César" not in client.get("/").get_data(as_text=True)


def test_login_wrong_password(client):
    response = login(client, password="incorrecta1")
    assert response.status_code == 200
    assert "no coinciden" in response.get_data(as_text=True)


def test_login_ignores_external_next(client):
    response = client.post("/login?next=https://malicioso.com",
                           data={"email": "demo@quecocino.local", "password": "Demo1234!"})
    assert response.headers["Location"] == "/"


def test_inactive_user_cannot_login(client, demo_user):
    demo_user.active = False
    from app.extensions import db
    db.session.commit()
    response = login(client)
    assert response.status_code == 200


def test_password_reset_flow(client, app, demo_user):
    from app.services import user_service
    token = user_service.make_reset_token(demo_user)
    response = client.post(f"/reset-password/{token}",
                           data={"password": "Nueva1234", "password_confirm": "Nueva1234"})
    assert response.status_code == 302
    assert login(client, password="Nueva1234").status_code == 302
    # El token ya no sirve después del cambio
    response = client.get(f"/reset-password/{token}")
    assert response.status_code == 302


def test_forgot_password_does_not_reveal_emails(client):
    a = client.post("/forgot-password", data={"email": "demo@quecocino.local"}, follow_redirects=True)
    b = client.post("/forgot-password", data={"email": "nadie@example.com"}, follow_redirects=True)
    assert "Si el email está registrado" in a.get_data(as_text=True)
    assert "Si el email está registrado" in b.get_data(as_text=True)


def test_onboarding_saves_preferences(client, ing):
    client.post("/register", data=VALID)
    response = client.post("/onboarding", data={
        "people_count": "5", "default_time": "30", "food_preferences": ["sopas", "pollo"],
        "excluded_ingredients": [str(ing("Mondongo (panza de res)"))], "restrictions": ["sin_picante"],
    })
    assert response.status_code == 302
    user = User.query.filter_by(email="ana@example.com").one()
    assert user.onboarding_done
    assert user.preference.people_count == 5
    assert user.preference.default_time == 30
    assert set(user.preference.food_preferences) == {"sopas", "pollo"}
    assert user.preference.restrictions == ["sin_picante"]
    assert user.preference.excluded_ingredients == [ing("Mondongo (panza de res)")]


def test_new_user_is_sent_to_onboarding(client):
    client.post("/register", data=VALID)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/onboarding")
