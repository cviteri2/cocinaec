"""Crea las tablas y carga los datos iniciales.

Uso:
    python seed.py            # catálogo + usuario demo + administrador
    python seed.py --no-demo  # sin usuario demo
"""
import os
import sys

from app import create_app
from app.data import seeder

if __name__ == "__main__":
    app = create_app()
    production = os.environ.get("APP_ENV", "production") == "production"
    with app.app_context():
        result = seeder.run(production=production, with_demo="--no-demo" not in sys.argv)

    print("¿Qué cocino hoy? — datos iniciales")
    print(f"  Catálogo creado ahora: {'sí' if result['catalog'] else 'ya existía'}")
    print(f"  Ingredientes: {result['ingredients']}")
    print(f"  Recetas: {result['recipes']}")
    print(f"  Categorías: {result['categories']}")
    if result["demo"]:
        print("  Usuario demo: demo@quecocino.local / Demo1234!")
    if result["admin"]:
        print("  Administrador creado (ver README).")
    if result["warning"]:
        print(f"  Aviso: {result['warning']}")
