import logging

from django.template.loader import render_to_string

from allianceauth import hooks
from allianceauth.services.hooks import ServicesHook, UrlHook

from . import app_settings, tasks, urls
from .models import has_account

logger = logging.getLogger(__name__)


class OutlineService(ServicesHook):
    """Mirrors Alliance Auth group membership into Outline."""

    def __init__(self):
        ServicesHook.__init__(self)
        self.name = "outline"
        # The webhook rides the UrlHook instead: everything on self.urlpatterns is
        # wrapped in main_character_required by allianceauth/urls.py.
        self.urlpatterns = []
        self.service_url = app_settings.OUTLINE_URL
        self.access_perm = "outline.access_outline"

    @property
    def title(self):
        return app_settings.OUTLINE_APP_NAME

    def service_active_for_user(self, user):
        return user.has_perm(self.access_perm)

    def validate_user(self, user):
        if has_account(user) and not self.service_active_for_user(user):
            self.delete_user(user)

    def delete_user(self, user, notify_user=False):
        if not has_account(user):
            return False
        logger.debug("Removing %s from Outline groups", user)
        tasks.delete_user.delay(user.pk)
        return True

    def update_groups(self, user):
        # No has_account guard: this is also how a user who signed into Outline
        # before the plugin knew about them gets linked.
        if self.service_active_for_user(user):
            tasks.update_groups.delay(user.pk)

    def update_all_groups(self):
        tasks.reconcile.delay()

    def render_services_ctrl(self, request):
        return render_to_string(
            self.service_ctrl_template,
            {
                "service_name": self.title,
                # No auth_* urls: OIDC login owns account creation, so the card
                # has nothing for the user to click.
                "urls": self.Urls(),
                "service_url": self.service_url,
                "username": (
                    request.user.outline.email
                    if has_account(request.user) else ""
                ),
            },
            request=request,
        )


@hooks.register("services_hook")
def register_service():
    return OutlineService()


@hooks.register("url_hook")
def register_url():
    # The webhook is public. This only takes effect when "outline" is listed in
    # settings.APPS_WITH_PUBLIC_VIEWS — see the README.
    return UrlHook(
        urls, "outline", r"^outline/",
        excluded_views=["outline.views.webhook"],
    )
