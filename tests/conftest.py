import pytest

from app import create_app
from app.data import seeder
from app.extensions import db
from app.models import Ingredient, Recipe, User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        seeder.run(production=False, with_demo=True)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email="demo@quecocino.local", password="Demo1234!"):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture
def demo_client(client):
    login(client)
    return client


@pytest.fixture
def admin_client(client):
    login(client, "admin@quecocino.local", "Admin1234!")
    return client


@pytest.fixture
def demo_user(app):
    return User.query.filter_by(email="demo@quecocino.local").one()


@pytest.fixture
def ing(app):
    """ing("Tomate") -> id del ingrediente."""
    cache = {i.name: i.id for i in Ingredient.query.all()}
    return lambda name: cache[name]


@pytest.fixture
def recipe(app):
    return lambda name: Recipe.query.filter_by(name=name).one()
