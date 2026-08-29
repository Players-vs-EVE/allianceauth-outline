from django.contrib import admin

from allianceauth.services.admin import ServicesUserAdmin

from .models import GroupSyncRule, OutlineUser


@admin.register(OutlineUser)
class OutlineUserAdmin(ServicesUserAdmin):
    list_display = ServicesUserAdmin.list_display + ("email", "last_sync")
    search_fields = ServicesUserAdmin.search_fields + ("email", "outline_user_id")
    readonly_fields = ("outline_user_id", "last_sync")


@admin.register(GroupSyncRule)
class GroupSyncRuleAdmin(admin.ModelAdmin):
    list_display = ("action", "match", "value", "enabled")
    list_filter = ("action", "match", "enabled")
    list_editable = ("enabled",)
