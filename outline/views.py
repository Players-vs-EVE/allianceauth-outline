import hashlib
import hmac
import json
import logging
import time

from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import app_settings, tasks

logger = logging.getLogger(__name__)

# Outline sends a millisecond epoch in the signature header. Confirmed against a
# v1.9.2 delivery: t=1788031032640 for a webhook recorded at 19:17:12.635 UTC.
MAX_SKEW_SECONDS = 300


def _verify(request) -> bool:
    secret = app_settings.OUTLINE_WEBHOOK_SECRET
    if not secret:
        logger.error("OUTLINE_WEBHOOK_SECRET is not set, rejecting webhook")
        return False

    header = request.headers.get("outline-signature", "")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp, signature = parts.get("t"), parts.get("s")
    if not timestamp or not signature:
        return False

    try:
        sent_at = int(timestamp) / 1000
    except ValueError:
        return False
    if abs(time.time() - sent_at) > MAX_SKEW_SECONDS:
        logger.warning("Rejecting webhook with a stale timestamp")
        return False

    payload = f"{timestamp}.{request.body.decode()}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def webhook(request):
    """Outline's users.signin webhook.

    Queues the work and returns immediately, so Outline's delivery does not wait
    on the Outline API.
    """
    if not _verify(request):
        return HttpResponseForbidden()

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()

    if payload.get("event") == "users.signin":
        try:
            outline_user_id = payload["payload"]["model"]["id"]
        except (KeyError, TypeError):
            return HttpResponseBadRequest()
        tasks.link_user.delay(outline_user_id)

    return HttpResponse(status=200)
