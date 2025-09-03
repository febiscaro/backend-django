from .base import *
import os
import environ

DEBUG = False

# ---------- .env ----------
env = environ.Env()
# permite mudar o arquivo por ENV_FILE, senão usa .env
env_file = os.path.join(BASE_DIR, os.environ.get("ENV_FILE", ".env"))
environ.Env.read_env(env_file)

# ALLOWED_HOSTS: se no base você já lê do .env, pode remover esta linha
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# SECRET_KEY: aceita SECRET_KEY ou DJANGO_SECRET_KEY
SECRET_KEY = env("SECRET_KEY", default=env("DJANGO_SECRET_KEY", default=SECRET_KEY))

# ---------- HTTPS controlado por variável ----------
USE_HTTPS = env.bool("USE_HTTPS", default=False)

SECURE_SSL_REDIRECT   = USE_HTTPS
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE    = USE_HTTPS

if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=True)
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Se quiser explicitar as origens de CSRF (não é obrigatório aqui, pois já monto abaixo)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[f"http://{h}" for h in ALLOWED_HOSTS] + [f"https://{h}" for h in ALLOWED_HOSTS],
)

# ---------- WhiteNoise p/ estáticos ----------
STATIC_ROOT = BASE_DIR / "staticfiles"
MIDDLEWARE = list(MIDDLEWARE)
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    # insere logo após o SecurityMiddleware (se existir)
    idx = 0
    if "django.middleware.security.SecurityMiddleware" in MIDDLEWARE:
        idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1
    MIDDLEWARE.insert(idx, "whitenoise.middleware.WhiteNoiseMiddleware")

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


SESSION_COOKIE_NAME = "enprodes_prod_session"
CSRF_COOKIE_NAME    = "enprodes_prod_csrftoken"
