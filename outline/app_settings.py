from django.conf import settings

OUTLINE_APP_NAME = getattr(settings, "OUTLINE_APP_NAME", "Outline")

# Base URL of the Outline instance, no trailing slash, e.g. https://wiki.example.com
OUTLINE_URL = getattr(settings, "OUTLINE_URL", "")

OUTLINE_API_TOKEN = getattr(settings, "OUTLINE_API_TOKEN", "")
