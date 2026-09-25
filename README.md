# ¿Qué cocino hoy?

**Menos pensar. Más disfrutar.**

Asistente web para decidir qué cocinar hoy. Indicas qué ingredientes tienes, para cuántas personas cocinas, cuánto tiempo tienes y cuánto quieres gastar, y la app te propone hasta 3 recetas concretas. Te dice qué ingredientes te faltan y te deja agregarlos a tu lista de compras con un toque.

Está pensado para Ecuador: usa español latinoamericano y recetas caseras ecuatorianas (seco de pollo, encebollado, locro, bolón…), además de algunas internacionales sencillas.

> Los costos son **estimaciones de referencia**, no precios actuales de supermercado. Las recetas son orientativas.

## Funcionalidades

| Módulo | Ruta | Estado |
|---|---|---|
| Landing | `/` | ✅ |
| ¿Qué cocino? (funciona sin cuenta) | `/cook/` → `/cook/results` | ✅ |
| Cocina con lo que tengo | `/cook/pantry` | ✅ |
| Recetas: búsqueda y filtros | `/recipes` | ✅ |
| Detalle con cantidades escaladas y **"Me falta"** | `/recipes/<slug>` | ✅ |
| Registro, login, logout, onboarding | `/register`, `/login`, `/onboarding` | ✅ |
| Recuperación de contraseña | `/forgot-password` | ⚙️ Token listo; el envío de correo queda **Próximamente** (el enlace se escribe en el log) |
| Inventario con "Aprovecha primero" | `/inventory/` | ✅ |
| Lista de compras por categoría | `/shopping-list/` | ✅ |
| Plan semanal, generador y lista semanal consolidada | `/meal-plan/` | ✅ |
| Control de presupuesto semanal | `/meal-plan/` | ✅ |
| Favoritos e historial | `/favorites`, `/history` | ✅ |
| Perfil, preferencias, familia | `/profile`, `/profile/family` | ✅ |
| Exportar datos y eliminar cuenta o datos | `/profile` | ✅ |
| Contacto (guarda en la base de datos) | `/contact` | ✅ |
| Privacidad y términos | `/privacy`, `/terms` | ✅ (texto base; requiere revisión legal) |
| Administración | `/admin/` | ✅ |
| API JSON de lectura | `/api/...` | ✅ |

## Cómo recomienda (sin IA)

`app/services/recommendation_service.py` usa un sistema determinístico. Cada receta suma puntos por:

- **Ingredientes (hasta 40):** 30 por cobertura ponderada, donde pesan más la proteína y la base del plato que el culantro, y 10 por aprovechar lo que tienes.
- **Tiempo (hasta 20):** tolera hasta 15 minutos de más. Pasado eso, la receta no aparece.
- **Presupuesto (hasta 20):** se compara el costo estimado de **lo que falta comprar**, escalado al número de personas.
- **Preferencias (hasta 10)** y **tipo de comida (hasta 10).**

Reglas fijas:
- Las restricciones (vegetariano, sin cerdo, sin mariscos…) y los ingredientes que el usuario evita **excluyen** la receta; no restan puntos.
- La sal, el aceite, el ajo y los condimentos se asumen disponibles.
- Si tienes un sustituto válido (pollo en lugar de pechuga), el ingrediente cuenta como disponible.

Al usuario nunca se le muestra el puntaje. Solo ve "Tienes X de Y ingredientes (Z%)".

## Requisitos

- Python 3.10 o superior (probado con 3.11)
- pip y virtualenv

## Instalación local

```bash
git clone <url-del-repo> cocinaec
cd cocinaec

# 1. Entorno virtual
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Dependencias
pip install -r requirements.txt

# 3. Configuración
cp .env.example .env
# Edita .env: APP_ENV=development y una SECRET_KEY propia:
python -c "import secrets; print(secrets.token_hex(32))"

# 4. Base de datos + datos iniciales
python seed.py

# 5. Ejecutar
python run.py
```

Abre <http://127.0.0.1:5000>.

`seed.py` crea las tablas en `instance/quecocino.db` y carga 78 ingredientes (con costos de referencia), 49 recetas, 26 categorías, sustituciones y usuarios de prueba. Se puede ejecutar varias veces sin duplicar datos. Para recrear todo desde cero, borra `instance/quecocino.db` y vuelve a ejecutarlo.

### Usuarios de prueba

| Rol | Email | Contraseña |
|---|---|---|
| Usuario demo | `demo@quecocino.local` | `Demo1234!` |
| Administrador (solo en desarrollo) | `admin@quecocino.local` | `Admin1234!` |

El usuario demo ya tiene inventario, lista de compras, favoritos, historial y un plan semanal.

En **producción** (`APP_ENV=production`) el administrador solo se crea si defines `ADMIN_PASSWORD` en `.env`. **Cambia o elimina el usuario demo** antes de abrir la app al público.

## Pruebas

```bash
python -m pytest -q
```

Hay 85 pruebas que cubren registro, login, logout, recuperación de contraseña, recetas (listado, búsqueda, filtros, detalle), el motor de recomendaciones (ingredientes, tiempo, presupuesto, coincidencia, sustitutos, restricciones), inventario, lista de compras, "Me falta", favoritos, historial y plan semanal. También cubren seguridad (permisos entre usuarios, usuario no autenticado, CSRF, acceso admin, escape XSS, cabeceras), API, exportación de datos y eliminación de cuenta.

## Estructura

```
cocinaec/
├── app/
│   ├── __init__.py            # create_app, errores, cabeceras de seguridad
│   ├── extensions.py          # db, login_manager, csrf
│   ├── models.py              # todos los modelos
│   ├── utils.py               # formato ($4,30), fechas, validación
│   ├── data/
│   │   ├── seed_data.py       # ingredientes, precios, recetas, sustituciones
│   │   └── seeder.py          # carga idempotente
│   ├── services/              # lógica de negocio (la usan la web y la API)
│   │   ├── recommendation_service.py
│   │   ├── recipe_service.py
│   │   ├── shopping_service.py
│   │   ├── inventory_service.py
│   │   ├── meal_plan_service.py
│   │   ├── pricing.py
│   │   ├── user_service.py
│   │   └── metrics.py
│   ├── routes/                # blueprints
│   │   ├── main.py  auth.py  cook.py  recipes.py  inventory.py
│   │   ├── shopping.py  meal_plan.py  profile.py  admin.py  api.py
│   ├── templates/
│   │   ├── components/ui.html # macros: recipe_card, chip, button, alert, modal,
│   │   │                      #   empty_state, pagination, form_field, shopping_item
│   │   └── partials/          # navbar, footer, bottom_nav, flashes
│   └── static/  css/app.css  js/app.js  images/
├── tests/
├── config.py  run.py  seed.py  wsgi_pythonanywhere.py
├── requirements.txt  .env.example  .gitignore
```

### Modelos

`User`, `UserPreference`, `FamilyMember`, `Consent`, `IngredientCategory`, `Ingredient`, `IngredientPrice` (con historial y campo `source` para integrar supermercados en el futuro), `Substitution`, `Category`, `Tag`, `Recipe`, `RecipeIngredient`, `RecipeStep`, `InventoryItem`, `ShoppingList`, `ShoppingListItem`, `FavoriteRecipe`, `MealPlan`, `MealPlanItem`, `CookingHistory`, `ContactMessage` y `AnalyticsEvent` (métricas).

## API

Son endpoints JSON de solo lectura. Por ahora se autentican con la sesión del navegador; la app móvil necesitará tokens.

- Públicos: `GET /api/recipes?q=&time=&cost=&meal=&category=`, `GET /api/recipes/<slug>`, `GET /api/ingredients` y `GET /api/recommendations?i=1&i=2&people=4&time=45&budget=5&meal=almuerzo`
- Con sesión: `GET /api/inventory`, `/api/shopping-list`, `/api/meal-plan`, `/api/favorites` y `/api/profile`

## Despliegue en PythonAnywhere

Los pasos sirven para una cuenta gratuita o de pago. Reemplaza `TU_USUARIO` por tu usuario.

1. **Sube el código.** En una consola Bash de PythonAnywhere:
   ```bash
   git clone <url-del-repo> ~/cocinaec
   ```
2. **Crea el virtualenv** con la misma versión de Python que usarás en la Web App (por ejemplo, 3.11):
   ```bash
   mkvirtualenv --python=/usr/bin/python3.11 cocinaec-venv
   cd ~/cocinaec
   pip install -r requirements.txt
   ```
3. **Configura el entorno:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Los valores mínimos son:
   ```
   APP_ENV=production
   SECRET_KEY=<clave larga generada con secrets.token_hex(32)>
   SESSION_COOKIE_SECURE=true
   ADMIN_EMAIL=tu-correo@ejemplo.com
   ADMIN_PASSWORD=<contraseña segura>
   ```
4. **Inicializa SQLite y carga los datos:**
   ```bash
   cd ~/cocinaec && workon cocinaec-venv
   python seed.py            # o: python seed.py --no-demo
   ```
   La base queda en `~/cocinaec/instance/quecocino.db`.
5. **Crea la Web App.** En la pestaña **Web**, elige *Add a new web app* → *Manual configuration* (no "Flask") → la misma versión de Python.
6. **Virtualenv:** en la sección *Virtualenv* escribe `/home/TU_USUARIO/.virtualenvs/cocinaec-venv`.
7. **Archivo WSGI:** abre el enlace *WSGI configuration file*, borra su contenido y pega el de `wsgi_pythonanywhere.py`. Revisa que `PROJECT_DIR` apunte a `/home/TU_USUARIO/cocinaec`.
8. **Archivos estáticos (opcional, recomendado):** en *Static files* agrega la URL `/static/` con el directorio `/home/TU_USUARIO/cocinaec/app/static`.
9. **Forzar HTTPS:** activa *Force HTTPS* en la pestaña Web.
10. Pulsa **Reload** y abre `https://TU_USUARIO.pythonanywhere.com`.

Para actualizar después: `git pull`, `pip install -r requirements.txt` si cambió y luego **Reload**. Si algo falla, revisa el *error log* en la pestaña Web.

## Despliegue automático (webhook de GitHub)

Con cada `push` a `main`, GitHub llama a `https://cocinaec.pythonanywhere.com/deploy/github`. La app:

1. verifica la firma HMAC (`X-Hub-Signature-256`) con `GITHUB_WEBHOOK_SECRET`;
2. ignora los eventos que no son `push` y las ramas distintas de `DEPLOY_BRANCH`;
3. lanza `deploy.sh` en segundo plano: `git fetch` + `merge --ff-only`, `pip install -r requirements.txt` y `touch` del archivo WSGI, lo que hace que PythonAnywhere recargue la app.

El log queda en `instance/deploy.log`. Sin `GITHUB_WEBHOOK_SECRET`, el endpoint responde 404.

Variables en `.env` del servidor:
```
GITHUB_WEBHOOK_SECRET=<secreto largo>
DEPLOY_BRANCH=main
DEPLOY_WSGI_FILE=/var/www/cocinaec_pythonanywhere_com_wsgi.py
```

En GitHub: *Settings → Webhooks → Add webhook*
- Payload URL: `https://cocinaec.pythonanywhere.com/deploy/github`
- Content type: `application/json`
- Secret: el mismo `GITHUB_WEBHOOK_SECRET`
- Evento: *Just the push event*

Límites:
- Los cambios de esquema de base de datos no se migran solos. `db.create_all()` crea tablas nuevas, pero no modifica las existentes.
- Si editas archivos directamente en el servidor, `merge --ff-only` puede fallar. El error queda en el log.

## Git básico

```bash
git init
git add .
git commit -m "Primera versión de ¿Qué cocino hoy?"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/cocinaec.git
git push -u origin main
```

`.env`, `instance/`, las bases `.db` y `__pycache__/` están en `.gitignore`. Nunca subas secretos.

## Seguridad y privacidad

- Contraseñas con hash (Werkzeug/scrypt) y sesión reiniciada al iniciar sesión.
- CSRF en todos los formularios (Flask-WTF), incluidas las acciones hechas con JavaScript.
- Cookies `HttpOnly`, `SameSite=Lax` y `Secure` en producción.
- Cabeceras CSP, X-Frame-Options, nosniff y Referrer-Policy.
- Solo se usa el ORM de SQLAlchemy (consultas parametrizadas) y Jinja escapa todo por defecto.
- Cada consulta de datos personales filtra por `user_id` y el panel admin está protegido por rol.
- Las redirecciones `next` solo aceptan rutas internas.
- Los mensajes de error son amables y no muestran detalles técnicos.
- Se aplica minimización de datos: no se piden GPS, contactos, cámara ni datos médicos.
- Se registran los consentimientos, con fechas de creación y actualización.
- El usuario puede exportar sus datos en JSON y eliminar su cuenta o sus datos.

## Preparado para una segunda fase

- **Correo:** envío del enlace de recuperación. El token ya existe en `user_service`.
- **PWA:** agregar `manifest.json` y un service worker. El diseño ya es mobile-first.
- **API REST completa:** endpoints de escritura y autenticación por token para la app móvil (React Native/Expo o Flutter). La lógica ya vive en `services/`.
- **PostgreSQL:** basta cambiar `DATABASE_URL`. Para migraciones de esquema conviene sumar Flask-Migrate/Alembic, porque hoy se usa `db.create_all()`.
- **Precios de supermercados:** `IngredientPrice.source` y el historial de precios están listos para esa integración.
- **IA opcional:** un intérprete de lenguaje natural ("somos 5 y quiero algo barato") solo tendría que producir un `Criteria`; el motor no cambia.
- **Recomendaciones familiares:** usar `FamilyMember` al filtrar.
- **Planes Gratis y Premium:** existe el campo `User.plan`, pero no hay pagos implementados.
- **Métricas:** `AnalyticsEvent` ya registra búsquedas, recetas vistas, preparadas, favoritas, planes y listas. La métrica principal, "decisiones resueltas", aparece en `/admin/`.
- **Alergias:** si se agregan, mostrar la advertencia de contaminación cruzada, que ya está en el onboarding y en los términos.
- **Límite de intentos de login:** pendiente (por ejemplo, con Flask-Limiter).
