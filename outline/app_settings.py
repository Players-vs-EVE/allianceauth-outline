from django.conf import settings

OUTLINE_APP_NAME = getattr(settings, "OUTLINE_APP_NAME", "Outline")

# Base URL of the Outline instance, no trailing slash, e.g. https://wiki.example.com
OUTLINE_URL = getattr(settings, "OUTLINE_URL", "")

# Must belong to an Outline admin: a non-admin token gets no emails back from
# users.list and cannot create groups.
OUTLINE_API_TOKEN = getattr(settings, "OUTLINE_API_TOKEN", "")

# Shared secret for the users.signin webhook.
OUTLINE_WEBHOOK_SECRET = getattr(settings, "OUTLINE_WEBHOOK_SECRET", "")
