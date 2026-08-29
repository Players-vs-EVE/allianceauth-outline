# Minimal Django settings for running makemigrations in this repo (no full AA install).
SECRET_KEY = "dev"
ESI_SSO_CLIENT_ID = ""
ESI_SSO_CLIENT_SECRET = ""
ESI_SSO_CALLBACK_URL = "http://localhost/callback"
ESI_USER_CONTACT_EMAIL = "dev@localhost"
LOGIN_TOKEN_SCOPES = ["publicData"]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "esi",
    "allianceauth.eveonline",
    "allianceauth.authentication",
    "allianceauth.notifications",
    "allianceauth.groupmanagement",
    "allianceauth.services",
    "outline",
]
CELERY_ONCE = {"backend": "allianceauth.services.tasks.DjangoBackend", "settings": {}}
# allianceauth.authentication's AppConfig.ready() asks for a raw redis client.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
    }
}
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
