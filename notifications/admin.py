from django.contrib import admin
from .models import Notification, NotificationOptOut


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("kind", "to_email", "is_sent", "created_at", "sent_at")
    list_filter = ("kind", "is_sent", "created_at")
    search_fields = ("to_email", "subject", "ref_app", "ref_model", "ref_pk")


@admin.register(NotificationOptOut)
class NotificationOptOutAdmin(admin.ModelAdmin):
    list_display = ("email", "kind")
    search_fields = ("email", "kind")
