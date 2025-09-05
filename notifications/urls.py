from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("count/", views.count_unread, name="count"),
    path("dropdown/", views.dropdown, name="dropdown"),
    path("mark-read/<int:pk>/", views.mark_read, name="mark_read"),
    path("", views.list_notifications, name="list"), 
]
