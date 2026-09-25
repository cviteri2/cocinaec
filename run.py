"""Punto de entrada. Local: `python run.py`. PythonAnywhere: ver wsgi_pythonanywhere.py."""
import os

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
