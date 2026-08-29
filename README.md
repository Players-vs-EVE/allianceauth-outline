# Alliance Auth Outline

Mirrors Alliance Auth group membership into [Outline](https://www.getoutline.com/).

Outline reads no group information from OIDC and has no SCIM endpoint, so membership has to be
pushed over its API. This app does that from AA's own signals: a group change reaches Outline in
seconds rather than at the next poll.

## Features

- AA group membership is pushed to Outline whenever it changes, and on state change.
- AA groups are matched to Outline groups by `externalId` (`allianceauth:<group pk>`), so renaming a
  group in AA renames it in Outline instead of creating a second one.
- An Outline group an admin created by hand is adopted by name on first sync rather than colliding
  with it.
- The `users.signin` webhook links an AA user to their Outline account the moment they first log in.
- A periodic reconcile task catches drift, including groups changed directly in Outline.
- Which AA groups sync is configured in the Django admin, not in settings.

## What it does not do

- **It never creates Outline accounts.** OIDC login does that. Users with no Outline account are
  skipped until they log in.
- It never deletes an Outline account, and never touches a group that has no `allianceauth:`
  `externalId`.
- **It never deletes an Outline group** — see below. It empties them instead.

## Requirements

- Alliance Auth >= 4.0.0
- An Outline instance and an API token belonging to an **Outline admin**, scoped `users:read` and
  `groups:write`. Admin membership and scopes are separate requirements — see
  [the API token section](#the-api-token) for both.

## If Outline ever grows group sync

Outline refuses API changes to a group it considers externally managed — one with `ExternalGroup`
rows. `groups.update` rejects a rename, and `groups.add_user`, `groups.remove_user` and
`groups.update_user` reject any membership change, each with a 400 and
`"This group is managed by an external provider and its membership cannot be modified"`.

As of v1.9.2 nothing can put a group in that state on a generic OIDC install: Outline has no SCIM,
and while `server/utils/GroupSyncProvider.ts` defines the interface, no shipped auth plugin
implements it. So this does not affect the install today. It is recorded here because if a future
Outline release ships group sync for OIDC, that feature and this app cannot both manage groups.

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

### 3. Make the webhook reachable

Alliance Auth wraps every plugin URL in `main_character_required`, which would make Outline's
webhook deliveries redirect to the login page. Exempt this app:

```python
APPS_WITH_PUBLIC_VIEWS = ["outline"]
```

Only `outline.views.webhook` is exempted; the app has no other public view.

### 4. Configure

```python
# Name shown on the services page
OUTLINE_APP_NAME = "Outline"

# Base URL of the Outline instance, no trailing slash
OUTLINE_URL = "https://wiki.example.com"

# API token belonging to an Outline admin
OUTLINE_API_TOKEN = ""

# Shared secret for the users.signin webhook
OUTLINE_WEBHOOK_SECRET = ""
```

### 5. Schedule the reconcile task

```python
CELERYBEAT_SCHEDULE["outline.reconcile"] = {
    "task": "outline.reconcile",
    "schedule": crontab(minute="0", hour="*/6"),
}
```

### 6. Run migrations and restart

```sh
python manage.py migrate
```

Restart the auth, worker and beat processes.

### 7. Register the webhook in Outline

In Outline's admin settings, add a webhook subscription pointing at
`https://auth.example.com/outline/webhook/`, subscribed to `users.signin`, using the same secret as
`OUTLINE_WEBHOOK_SECRET`.

### The API token

Under **Settings → API & Access** in Outline v1.9.2. Keys default to a 30-day expiry — pick
`No expiration` unless you plan to rotate. The value is shown once, and a key can only be revoked
from a browser session (`apiKeys.delete` rejects API-key auth), so store it when it is created.
`webhookSubscriptions.create` does accept API-key auth, so the webhook half can be scripted.

**Scopes.** Two are enough:

```
users:read
groups:write
```

`users:read` covers `users.list` and `users.info`. `groups:write` covers every group call the app
makes — Outline's `canAccess` short-circuits a namespaced `write` scope, so it grants the group reads
too and `groups:read` is redundant alongside it. Note `groups.add_user` and `groups.remove_user` are
absent from Outline's `methodToScope` map and so default to write; read-only group scopes are not
enough.

To be narrower, grant route scopes instead — one per call the app makes:

```
/api/users.list  /api/users.info
/api/groups.list  /api/groups.info  /api/groups.create  /api/groups.update
/api/groups.add_user  /api/groups.remove_user
```

Leaving scopes empty grants `*`. Don't.

**Scopes do not substitute for admin membership.** They gate which routes the key may call; whether
`users.list` returns email addresses at all depends on the account being an Outline admin. A
correctly scoped key on a non-admin account matches nobody.

Two things block delivery when Outline and Alliance Auth are on the same private network — for
example both in one Docker Compose stack, with Outline posting to `http://auth:8000/outline/webhook/`:

- **Outline refuses to deliver to private addresses.** The delivery fails with no HTTP status at all
  and a message like `DNS lookup 172.24.0.4(family:4, host:auth) is not allowed. Because, It is
  private IP address.` Set `ALLOWED_PRIVATE_IP_ADDRESSES` on the Outline container to the IPs or
  CIDRs it may reach (`172.16.0.0/12` covers a default Compose network).
- **Django's `ALLOWED_HOSTS` must contain the hostname Outline uses.** The request arrives with
  `Host: auth:8000`, so without `auth` in `ALLOWED_HOSTS` Django answers 400 with a `DisallowedHost`
  page. This one leaves no trace where you would look — the request never reaches the view, so the
  AA log has no `outline/webhook` line at all.

Both entries have to match whatever hostname you actually use.

### Reading webhook deliveries

Outline's UI has no delivery log. A rejected signature (403) and a `DisallowedHost` (400) both show
as a plain failure from Outline's side, so check its database directly:

```sh
psql -U outline -d outline -c \
  'select status, "statusCode", "requestHeaders", "responseBody" from webhook_deliveries order by "createdAt" desc limit 5;'
```

### 8. Grant the permission

Grant `outline.access_outline` to the states or groups that should sync.

## Choosing which groups sync

Add rules under **Outline → Group sync rules** in the Django admin. Each rule is an `allow` or a
`deny` plus a matcher:

| Matcher | Matches |
| --- | --- |
| Exact name | The group name, exactly. |
| Name prefix | Group names starting with the value. |
| Regex | Group names the pattern is found in. |
| Internal group flag | Groups where `AuthGroup.internal` is set — the corp, alliance and member groups. |

**Deny beats allow**, and **an empty rule table syncs nothing**. That default is deliberate: with
`eveonline.autogroups` installed, syncing everything would push every corp and alliance group into
Outline on first deploy. Use the internal group flag to exclude the autogroups rather than a name
prefix — the autogroup prefixes are themselves configurable.

Editing a rule triggers a reconcile, so a change takes effect within one task rather than at the next
scheduled run.

Note: an exact-name rule stores a name, and nothing revalidates rules on rename, so renaming that AA
group orphans the rule and its members stop syncing. Update the rule when you rename.

### Groups are never deleted

Deleting an AA group, or changing the rules so a group no longer syncs, does **not** delete the
Outline group. Members are removed by the next per-user sync, so access is still revoked correctly —
the empty Outline group is left behind for an admin to remove by hand.

This is deliberate for now. Deleting an Outline group takes any collection permissions granted to it
with it, and the triggers were too easy to hit by accident. Tracked in
[issue #1](https://github.com/Players-vs-EVE/allianceauth-outline/issues/1).

## Permissions

| Permission | Grants |
| --- | --- |
| `outline.access_outline` | Group membership is mirrored into Outline for this user. |

Upgrading from the scaffold release: the old `outline.basic_access` permission is removed by
migration `0002`, along with the placeholder page it gated. Grant `outline.access_outline` in its
place.

## Development

Tests need `requests-mock`:

```sh
pip install -e ".[test]"
python manage.py test outline
```
