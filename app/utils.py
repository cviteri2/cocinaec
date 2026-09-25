"""Utilidades pequeñas: formato, validación y fechas."""
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import current_app

DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Formato ---------------------------------------------------------------

def money(value):
    """4.3 -> "$4,30" (coma decimal)."""
    if value is None:
        return "—"
    return "$" + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(value):
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def format_quantity(quantity, unit):
    """Cantidad legible: 1500 g -> "1,5 kg", 3 unidad -> "3 unidades"."""
    if quantity is None or quantity == 0:
        return ""
    if unit == "g":
        return f"{_num(quantity / 1000)} kg" if quantity >= 1000 else f"{_num(quantity)} g"
    if unit == "ml":
        return f"{_num(quantity / 1000)} l" if quantity >= 1000 else f"{_num(quantity)} ml"
    if unit in ("kg", "l"):
        return f"{_num(quantity)} {unit}"
    if unit == "unidad":
        # Las unidades se redondean hacia arriba a medias unidades
        rounded = max(0.5, round(quantity * 2) / 2)
        return f"{_num(rounded)} {'unidad' if rounded <= 1 else 'unidades'}"
    return f"{_num(quantity)} {unit or ''}".strip()


def format_minutes(minutes):
    if minutes is None:
        return "Más de 1 hora"
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    return f"{hours} h {mins} min" if mins else f"{hours} h"


def format_date_es(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = to_local(value).date()
    return f"{value.day} de {MONTHS[value.month - 1]} de {value.year}"


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize(text):
    """Para búsquedas: minúsculas y sin tildes."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return text.lower().strip()


# --- Fechas ----------------------------------------------------------------

def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(current_app.config.get("APP_TIMEZONE", "America/Guayaquil"))
    except Exception:  # sin base de zonas horarias: Ecuador continental es UTC-5
        return timezone(timedelta(hours=-5))


def to_local(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(_tz())


def today_local():
    return datetime.now(_tz()).date()


def week_start(day=None):
    day = day or today_local()
    return day - timedelta(days=day.weekday())


# --- Entrada del usuario -----------------------------------------------------

def parse_int(value, default=None, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and number < minimum:
        return default
    if maximum is not None and number > maximum:
        return default
    return number


def parse_float(value, default=None, minimum=None, maximum=None):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    if minimum is not None and number < minimum:
        return default
    if maximum is not None and number > maximum:
        return default
    return number


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def clean_text(value, max_length=255):
    """Recorta espacios y longitud. El escape de HTML lo hace Jinja."""
    return (value or "").strip()[:max_length]


def is_valid_email(email):
    return bool(email) and len(email) <= 255 and bool(EMAIL_RE.match(email))


def password_problem(password):
    if len(password or "") < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "La contraseña debe combinar letras y números."
    return None


def safe_next_url(target):
    """Solo permite redirecciones internas (evita open redirect)."""
    if not target or "\\" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target
