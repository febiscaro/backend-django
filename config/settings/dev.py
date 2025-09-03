from .base import *
DEBUG = True
# Apenas para DESENVOLVIMENTO LOCAL
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1", "http://localhost"]

# Nomes de cookies diferentes do PROD (não compartilha sessão)
SESSION_COOKIE_NAME = "enprodes_dev_session"
CSRF_COOKIE_NAME    = "enprodes_dev_csrftoken"

# Nunca force HTTPS no DEV
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# (Opcional) E-mails vão para o console
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
