from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import app_settings, urls


class OutlineMenu(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(
            self,
            app_settings.OUTLINE_APP_NAME,
            "fas fa-book fa-fw",
            "outline:index",
            navactive=["outline:"],
        )

    def render(self, request):
        if request.user.has_perm("outline.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return OutlineMenu()


@hooks.register("url_hook")
def register_url():
    return UrlHook(urls, "outline", r"^outline/")
