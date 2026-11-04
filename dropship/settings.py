from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_cargar_env()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-cambia-esto")
DEBUG = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
_dominio_railway = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if _dominio_railway:
    if "*" not in ALLOWED_HOSTS and _dominio_railway not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_dominio_railway)
    _origen = f"https://{_dominio_railway}"
    if _origen not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origen)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "vendedores.apps.VendedoresConfig",
    "productos.apps.ProductosConfig",
    "pedidos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "dropship.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "vendedores.context_processors.marketplace",
    ]},
}]

WSGI_APPLICATION = "dropship.wsgi.application"

_db_password = os.getenv("SUPABASE_DB_PASSWORD", "")
if _db_password:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("SUPABASE_DB_NAME", "postgres"),
        "USER": os.getenv("SUPABASE_DB_USER", "postgres"),
        "PASSWORD": _db_password,
        "HOST": os.getenv("SUPABASE_DB_HOST", ""),
        "PORT": os.getenv("SUPABASE_DB_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"sslmode": "require"},
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }}

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
STATICFILES_DIRS = [BASE_DIR / "static"]
# El contenedor que atiende la web no ve la carpeta generada por
# collectstatic. WhiteNoise sirve era.css y era.js desde static/.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "entrar_vendedor"
LOGIN_REDIRECT_URL = "panel_vendedor"

# --- Config dropshipping ---
MARGEN_DEFAULT = 40
COMISION_PCT = 10
COMISION_MAYOR_PCT = 5
WOMPI_PCT = "2.65"
WOMPI_FIJO_COP = 700
WOMPI_IVA_PCT = 19
DIAS_LIQUIDACION = 5
DIAS_RECLAMO = 5
FLETE_POR_LIBRA_USD = 8.00
IVA_COLOMBIA = 0.19
UMBRAL_IVA_USD = 200
TRM_APROX = 4000

DSERS_API_KEY = os.getenv("DSERS_API_KEY", "")
DSERS_BASE_URL = "https://api.dsers.com"
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# Cobro directo (sin pasarela). Pon tu Nequi / llave Bre-B.
PAGO_NEQUI = os.getenv("PAGO_NEQUI", "")
PAGO_LLAVE = os.getenv("PAGO_LLAVE", "")
PAGO_BANCOLOMBIA = os.getenv("PAGO_BANCOLOMBIA", "")

# Wompi queda opcional; el flujo normal es Nequi/llave directo.
WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY", "")
WOMPI_INTEGRITY_SECRET = os.getenv("WOMPI_INTEGRITY_SECRET", "")
WOMPI_EVENTS_SECRET = os.getenv("WOMPI_EVENTS_SECRET", "")
WOMPI_CHECKOUT_URL = "https://checkout.wompi.co/p/"

if os.getenv("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "ERA shop <no-responder@era.shop>")
