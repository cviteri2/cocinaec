#!/usr/bin/env bash
# Despliegue: actualiza el código, instala dependencias y recarga la web app.
# Lo lanza el webhook (/deploy/github); también se puede ejecutar a mano:
#   DEPLOY_WSGI_FILE=/var/www/cocinaec_pythonanywhere_com_wsgi.py bash deploy.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
PYTHON="${DEPLOY_PYTHON:-python3}"
LOCK="${DEPLOY_LOCK:-$PROJECT_DIR/instance/deploy.lock}"

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
flock 9   # un despliegue a la vez

cd "$PROJECT_DIR"
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S') UTC · desplegando rama $BRANCH"

git fetch --quiet origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"
echo "Código en: $(git log -1 --format='%h %s')"

"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements.txt
echo "Dependencias al día."

if [ -n "${DEPLOY_WSGI_FILE:-}" ] && [ -f "$DEPLOY_WSGI_FILE" ]; then
  touch "$DEPLOY_WSGI_FILE"   # PythonAnywhere recarga la web app al tocar el archivo WSGI
  echo "Web app recargada."
else
  echo "Aviso: DEPLOY_WSGI_FILE no está definido; recarga la web app a mano."
fi
echo "=== Listo"
