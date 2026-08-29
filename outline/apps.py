from django.apps import AppConfig

from . import __version__


class OutlineConfig(AppConfig):
    name = "outline"
    label = "outline"

    verbose_name = f"Outline v{__version__}"
