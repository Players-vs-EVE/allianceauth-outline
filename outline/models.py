from django.db import models


class General(models.Model):
    """Permission container only — no table rows are ever created."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access the Outline app"),
        )
