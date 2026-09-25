"""Despliegue automático desde GitHub (webhook).

Flujo: GitHub envía un POST firmado → se verifica la firma HMAC → se lanza
deploy.sh en segundo plano (git pull, pip install, recarga de la web app).
La salida queda en instance/deploy.log.
"""
import hashlib
import hmac
import os
import subprocess
import sys
from pathlib import Path

from flask import current_app

PROJECT_DIR = Path(__file__).resolve().parents[2]


def signature_is_valid(secret, body, header):
    """Compara la firma X-Hub-Signature-256 en tiempo constante."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def _venv_python():
    # En uWSGI (PythonAnywhere) sys.executable no es python; sys.prefix sí es el virtualenv.
    candidate = Path(sys.prefix) / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def launch():
    """Ejecuta deploy.sh sin bloquear la respuesta al webhook."""
    instance = Path(current_app.instance_path)
    instance.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "DEPLOY_BRANCH": current_app.config["DEPLOY_BRANCH"],
        "DEPLOY_PYTHON": os.environ.get("DEPLOY_PYTHON") or _venv_python(),
        "DEPLOY_WSGI_FILE": current_app.config.get("DEPLOY_WSGI_FILE") or "",
        "DEPLOY_LOCK": str(instance / "deploy.lock"),
    }
    log = open(instance / "deploy.log", "a")
    subprocess.Popen(
        ["bash", str(PROJECT_DIR / "deploy.sh")],
        cwd=PROJECT_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
