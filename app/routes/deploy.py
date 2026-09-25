"""Webhook de GitHub para desplegar automáticamente.

Queda desactivado (404) mientras GITHUB_WEBHOOK_SECRET no esté definido.
"""
from flask import Blueprint, abort, current_app, jsonify, request

from ..extensions import csrf
from ..services import deploy_service

bp = Blueprint("deploy", __name__, url_prefix="/deploy")


@bp.route("/github", methods=["POST"])
@csrf.exempt  # GitHub no envía token CSRF; la autenticidad la da la firma HMAC
def github():
    secret = current_app.config.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        abort(404)
    if not deploy_service.signature_is_valid(
        secret, request.get_data(), request.headers.get("X-Hub-Signature-256")
    ):
        return jsonify({"error": "Firma inválida."}), 403

    event = request.headers.get("X-GitHub-Event")
    if event == "ping":
        return jsonify({"status": "pong"})
    if event != "push":
        return jsonify({"status": "ignored", "reason": f"evento {event}"})

    payload = request.get_json(silent=True) or {}
    branch = current_app.config["DEPLOY_BRANCH"]
    if payload.get("ref") != f"refs/heads/{branch}":
        return jsonify({"status": "ignored", "reason": f"solo se despliega {branch}"})

    deploy_service.launch()
    current_app.logger.info("Despliegue lanzado para %s", payload.get("after"))
    return jsonify({"status": "deploying", "commit": payload.get("after")}), 202
