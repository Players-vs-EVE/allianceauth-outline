import requests_mock
from django.test import TestCase

from outline.manager import (
    OutlineApiError,
    OutlineClient,
    OutlineForbidden,
    OutlineNotFound,
    OutlineRateLimited,
)

URL = "https://wiki.example.com"


class OutlineClientTestCase(TestCase):
    def setUp(self):
        self.client_ = OutlineClient(URL + "/", "token123")

    def test_post_sends_bearer_token_and_json_body(self):
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/users.info", json={"data": {"email": "a@b.c"}})
            data = self.client_.user_info("uid")

        self.assertEqual(data["email"], "a@b.c")
        self.assertEqual(m.last_request.headers["Authorization"], "Bearer token123")
        self.assertEqual(m.last_request.json(), {"id": "uid"})

    def test_rate_limit_carries_retry_after(self):
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/groups.create", status_code=429,
                   headers={"Retry-After": "17"})
            with self.assertRaises(OutlineRateLimited) as ctx:
                self.client_.create_group("x", "allianceauth:1")

        self.assertEqual(ctx.exception.retry_after, 17)

    def test_forbidden_and_not_found_and_other_errors_map(self):
        for status, expected in (
            (403, OutlineForbidden),
            (404, OutlineNotFound),
            (500, OutlineApiError),
        ):
            with self.subTest(status=status), requests_mock.Mocker() as m:
                m.post(f"{URL}/api/users.info", status_code=status)
                with self.assertRaises(expected):
                    self.client_.user_info("uid")

    def test_group_by_external_id_returns_none_on_404(self):
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/groups.info", status_code=404)
            self.assertIsNone(self.client_.group_by_external_id("allianceauth:1"))

    def test_paginate_stops_on_a_short_page(self):
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/groups.list",
                   json={"data": {"groups": [{"id": "1"}]}})
            groups = self.client_.list_groups()

        self.assertEqual(len(groups), 1)
        self.assertEqual(m.call_count, 1)

    def test_paginate_continues_on_a_full_page(self):
        full = {"data": {"groups": [{"id": str(i)} for i in range(100)]}}
        rest = {"data": {"groups": [{"id": "last"}]}}
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/groups.list",
                   [{"json": full}, {"json": rest}])
            groups = self.client_.list_groups()

        self.assertEqual(len(groups), 101)
        self.assertEqual(m.call_count, 2)
        self.assertEqual(m.request_history[1].json()["offset"], 100)

    def test_user_by_email_returns_none_when_outline_has_no_account(self):
        with requests_mock.Mocker() as m:
            m.post(f"{URL}/api/users.list", json={"data": []})
            self.assertIsNone(self.client_.user_by_email("nobody@example.com"))
