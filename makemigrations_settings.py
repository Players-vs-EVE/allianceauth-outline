# Minimal Django settings for running makemigrations in this repo (no full AA install).
SECRET_KEY = "dev"
ESI_SSO_CLIENT_ID = ""
ESI_SSO_CLIENT_SECRET = ""
ESI_SSO_CALLBACK_URL = "http://localhost/callback"
ESI_USER_CONTACT_EMAIL = "dev@localhost"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "esi",
    "allianceauth.eveonline",
    "outline",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
