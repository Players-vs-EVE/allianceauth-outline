import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from outline.views import webhook

SECRET = "s3cr3t"
OUTLINE_UID = "11111111-1111-1111-1111-111111111111"


def signed_request(body: dict, secret=SECRET, timestamp=None):
    raw = json.dumps(body)
    timestamp = timestamp or str(int(time.time() * 1000))
    signature = hmac.new(
        secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256
    ).hexdigest()
    return RequestFactory().post(
        "/outline/webhook/",
        data=raw,
        content_type="application/json",
        headers={"outline-signature": f"t={timestamp},s={signature}"},
    )


SIGNIN = {"event": "users.signin", "payload": {"model": {"id": OUTLINE_UID}}}


@override_settings(OUTLINE_WEBHOOK_SECRET=SECRET)
class WebhookTestCase(TestCase):
    def setUp(self):
        patcher = patch("outline.tasks.link_user.delay")
        self.link_user = patcher.start()
        self.addCleanup(patcher.stop)
        # app_settings reads the setting at import time.
        settings_patcher = patch("outline.app_settings.OUTLINE_WEBHOOK_SECRET", SECRET)
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

    def test_valid_signin_queues_the_link(self):
        response = webhook(signed_request(SIGNIN))

        self.assertEqual(response.status_code, 200)
        self.link_user.assert_called_once_with(OUTLINE_UID)

    def test_bad_signature_is_rejected(self):
        response = webhook(signed_request(SIGNIN, secret="wrong"))

        self.assertEqual(response.status_code, 403)
        self.link_user.assert_not_called()

    def test_stale_timestamp_is_rejected(self):
        stale = str(int((time.time() - 3600) * 1000))
        response = webhook(signed_request(SIGNIN, timestamp=stale))

        self.assertEqual(response.status_code, 403)
        self.link_user.assert_not_called()

    def test_unknown_event_is_accepted_but_queues_nothing(self):
        response = webhook(signed_request({"event": "documents.update"}))

        self.assertEqual(response.status_code, 200)
        self.link_user.assert_not_called()

    def test_missing_secret_rejects_everything(self):
        with patch("outline.app_settings.OUTLINE_WEBHOOK_SECRET", ""):
            response = webhook(signed_request(SIGNIN))

        self.assertEqual(response.status_code, 403)
        self.link_user.assert_not_called()
