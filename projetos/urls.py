from django.urls import path
from . import views

app_name = "projetos"

urlpatterns = [
    path("centros/", views.centros_list, name="centros_list"),
    path("centros/novo/", views.centros_create, name="centros_create"),
    path("centros/<uuid:centro_id>/board/", views.board, name="board"),  

]
