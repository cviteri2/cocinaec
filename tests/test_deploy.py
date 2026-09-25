import hashlib
import hmac
import json

import pytest

from app.services import deploy_service

SECRET = "secreto-de-prueba"


def _post(client, payload, event="push", secret=SECRET):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/deploy/github", data=body, content_type="application/json",
                       headers={"X-GitHub-Event": event, "X-Hub-Signature-256": signature})


@pytest.fixture
def launched(app, monkeypatch):
    app.config["GITHUB_WEBHOOK_SECRET"] = SECRET
    app.config["DEPLOY_BRANCH"] = "main"
    calls = []
    monkeypatch.setattr(deploy_service, "launch", lambda: calls.append(True))
    return calls


def test_webhook_disabled_without_secret(client, app):
    app.config["GITHUB_WEBHOOK_SECRET"] = None
    assert _post(client, {"ref": "refs/heads/main"}).status_code == 404


def test_webhook_rejects_bad_signature(client, launched):
    response = _post(client, {"ref": "refs/heads/main"}, secret="otro")
    assert response.status_code == 403
    assert not launched


def test_webhook_rejects_missing_signature(client, launched):
    response = client.post("/deploy/github", json={"ref": "refs/heads/main"}, headers={"X-GitHub-Event": "push"})
    assert response.status_code == 403
    assert not launched


def test_webhook_ping(client, launched):
    assert _post(client, {"zen": "hola"}, event="ping").get_json() == {"status": "pong"}
    assert not launched


def test_webhook_ignores_other_branches(client, launched):
    response = _post(client, {"ref": "refs/heads/feature-x"})
    assert response.get_json()["status"] == "ignored"
    assert not launched


def test_webhook_deploys_main(client, launched):
    response = _post(client, {"ref": "refs/heads/main", "after": "abc123"})
    assert response.status_code == 202
    assert response.get_json() == {"status": "deploying", "commit": "abc123"}
    assert launched == [True]


def test_webhook_works_with_csrf_enabled(client, app, launched):
    app.config["WTF_CSRF_ENABLED"] = True
    assert _post(client, {"ref": "refs/heads/main"}).status_code == 202


def test_signature_helper():
    body = b"{}"
    good = "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert deploy_service.signature_is_valid("k", body, good)
    assert not deploy_service.signature_is_valid("k", body, "sha1=abc")
    assert not deploy_service.signature_is_valid("", body, good)
