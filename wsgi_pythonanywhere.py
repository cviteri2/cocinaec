"""Archivo WSGI para PythonAnywhere.

Copia este contenido en el archivo WSGI de tu Web App
(pestaña Web > "WSGI configuration file") y ajusta PROJECT_DIR.
"""
import os
import sys

# Cambia esto por la ruta real de tu proyecto, por ejemplo:
#   /home/TU_USUARIO/cocinaec
PROJECT_DIR = os.path.expanduser("~/cocinaec")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# config.py carga PROJECT_DIR/.env automáticamente (SECRET_KEY, APP_ENV, ...)
os.environ.setdefault("APP_ENV", "production")

from run import app as application  # noqa: E402
