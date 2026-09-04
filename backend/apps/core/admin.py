"""Registro dos modelos no Django Admin."""
from __future__ import annotations

from django.contrib import admin

from .models import Colaborador, EPC, Leitura, PecaEPI


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ("nome", "matricula", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "matricula")
    ordering = ("nome",)


@admin.register(PecaEPI)
class PecaEPIAdmin(admin.ModelAdmin):
    list_display = ("tipo", "descricao", "colaborador", "ativa", "atualizado_em")
    list_filter = ("tipo", "ativa")
    search_fields = ("descricao", "colaborador__nome", "colaborador__matricula")
    autocomplete_fields = ("colaborador",)
    list_select_related = ("colaborador",)


@admin.register(EPC)
class EPCAdmin(admin.ModelAdmin):
    list_display = ("codigo", "peca", "peca__colaborador", "ativo", "criado_em")
    list_filter = ("ativo", "peca__tipo")
    search_fields = ("codigo", "peca__descricao", "peca__colaborador__matricula")
    autocomplete_fields = ("peca",)
    list_select_related = ("peca", "peca__colaborador")


@admin.register(Leitura)
class LeituraAdmin(admin.ModelAdmin):
    list_display = (
        "lido_em",
        "epc_lido",
        "conhecido",
        "peca",
        "colaborador",
        "valido_para_acesso",
    )
    list_filter = ("conhecido", "valido_para_acesso", "peca__tipo")
    search_fields = ("epc_lido", "colaborador__matricula")
    date_hierarchy = "lido_em"
    readonly_fields = (
        "epc_lido",
        "conhecido",
        "peca",
        "colaborador",
        "valido_para_acesso",
        "lido_em",
        "criado_em",
        "atualizado_em",
    )
    list_select_related = ("peca", "colaborador")

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False
