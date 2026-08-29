"""The only module that talks to Outline's API."""

import logging
import math

import requests

from . import app_settings

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


class OutlineApiError(Exception):
    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class OutlineNotFound(OutlineApiError):
    pass


class OutlineForbidden(OutlineApiError):
    """Permanent — retrying will not help. Usually the API token's scopes are
    too narrow, or it does not belong to an Outline admin."""


class OutlineRateLimited(OutlineApiError):
    def __init__(self, message, retry_after=60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


def _retry_after(response, default=60) -> int:
    """Outline sends a fractional Retry-After, e.g. `33.01`."""
    try:
        return math.ceil(float(response.headers["Retry-After"]))
    except (KeyError, ValueError):
        return default


class OutlineClient:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _post(self, endpoint: str, **body):
        response = self.session.post(
            f"{self.url}/api/{endpoint}", json=body, timeout=30
        )
        if response.status_code == 429:
            raise OutlineRateLimited(
                f"{endpoint} rate limited",
                retry_after=_retry_after(response),
                status=429,
                body=response.text,
            )
        if response.status_code == 403:
            raise OutlineForbidden(
                f"{endpoint} forbidden", status=403, body=response.text
            )
        if response.status_code == 404:
            raise OutlineNotFound(
                f"{endpoint} not found", status=404, body=response.text
            )
        if response.status_code >= 400:
            raise OutlineApiError(
                f"{endpoint} failed with {response.status_code}",
                status=response.status_code,
                body=response.text,
            )
        # groups.delete and friends answer {"success": true} with no data key.
        try:
            return response.json().get("data")
        except ValueError:
            return None

    def _paginate(self, endpoint: str, key=None, **body):
        offset = 0
        while True:
            data = self._post(endpoint, limit=PAGE_SIZE, offset=offset, **body)
            items = data[key] if key else data
            yield from items
            if len(items) < PAGE_SIZE:
                return
            offset += PAGE_SIZE

    def user_by_email(self, email: str):
        users = self._post("users.list", emails=[email], limit=1)
        return users[0] if users else None

    def user_info(self, user_id: str):
        return self._post("users.info", id=user_id)

    def list_groups(self) -> list:
        return list(self._paginate("groups.list", "groups"))

    def list_groups_for_user(self, user_id: str) -> list:
        return list(self._paginate("groups.list", "groups", userId=user_id))

    def group_by_external_id(self, external_id: str):
        try:
            return self._post("groups.info", externalId=external_id)
        except OutlineNotFound:
            return None

    def create_group(self, name: str, external_id: str):
        return self._post("groups.create", name=name, externalId=external_id)

    def update_group(self, group_id: str, **fields):
        return self._post("groups.update", id=group_id, **fields)

    def delete_group(self, group_id: str):
        return self._post("groups.delete", id=group_id)

    def add_user(self, group_id: str, user_id: str):
        return self._post("groups.add_user", id=group_id, userId=user_id)

    def remove_user(self, group_id: str, user_id: str):
        return self._post("groups.remove_user", id=group_id, userId=user_id)


def outline_client() -> OutlineClient:
    return OutlineClient(app_settings.OUTLINE_URL, app_settings.OUTLINE_API_TOKEN)
