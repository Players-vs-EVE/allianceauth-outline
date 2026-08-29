# Alliance Auth Outline

Outline wiki integration for Alliance Auth.

Scaffold only at this stage — the app registers a menu item and a placeholder page. No Outline API
calls yet.

## Features

- Menu item and page, gated on the `outline.basic_access` permission.

## Requirements

- Alliance Auth >= 4.0.0
- An Outline instance and an API token

## Installation

### 1. Install the package

```sh
pip install allianceauth-outline
```

### 2. Add to `INSTALLED_APPS`

In `myauth/settings/local.py`:

```python
INSTALLED_APPS += ["outline"]
```

### 3. Run migrations

```sh
python manage.py migrate
```

### 4. Restart services

Restart the auth, worker and beat processes.

## Configuration

All settings go in `local.py`.

```python
# Name shown in the sidebar
OUTLINE_APP_NAME = "Outline"

# Base URL of the Outline instance, no trailing slash
OUTLINE_URL = "https://wiki.example.com"

# Outline API token
OUTLINE_API_TOKEN = ""
```

## Permissions

| Permission | Grants |
| --- | --- |
| `outline.basic_access` | Access to the Outline app. |
