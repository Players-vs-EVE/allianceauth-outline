from django.urls import path

from . import views

app_name = "outline"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
]
