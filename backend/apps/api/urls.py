"""Rotas da API de leituras RFID."""
from __future__ import annotations

from django.urls import path

from .views import LeituraDetailView, LeituraEventoView

app_name = "api"

urlpatterns = [
    path("leituras/", LeituraEventoView.as_view(), name="leituras"),
    path("leituras/<int:pk>/", LeituraDetailView.as_view(), name="leitura-detail"),
]
