"""Configuración de la aplicación.

Los valores sensibles (SECRET_KEY, DATABASE_URL) se leen de variables de
entorno o de un archivo .env en la raíz del proyecto. Nunca se guardan en Git.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{BASE_DIR / 'instance' / 'quecocino.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sesiones y cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)

    # CSRF: el token vive lo mismo que la sesión
    WTF_CSRF_TIME_LIMIT = None

    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB, no hay subidas de archivos
    PASSWORD_RESET_MAX_AGE = 60 * 60  # 1 hora
    RECIPES_PER_PAGE = 12
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "America/Guayaquil")

    # Despliegue automático por webhook de GitHub (desactivado sin secreto)
    GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
    DEPLOY_BRANCH = os.environ.get("DEPLOY_BRANCH", "main")
    DEPLOY_WSGI_FILE = os.environ.get("DEPLOY_WSGI_FILE")


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = Config.SECRET_KEY or "solo-para-desarrollo-cambiar"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-de-pruebas"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name=None):
    name = name or os.environ.get("APP_ENV", "production")
    return CONFIGS.get(name, ProductionConfig)
