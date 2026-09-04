"""DRF serializers para os modelos de domínio."""
from __future__ import annotations

from rest_framework import serializers

from .models import Colaborador, EPC, Leitura, PecaEPI


class ColaboradorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colaborador
        fields = ("id", "nome", "matricula", "ativo")


class PecaEPISerializer(serializers.ModelSerializer):
    colaborador_matricula = serializers.CharField(
        source="colaborador.matricula", read_only=True, default=None
    )

    class Meta:
        model = PecaEPI
        fields = (
            "id",
            "tipo",
            "descricao",
            "colaborador",
            "colaborador_matricula",
            "ativa",
        )


class EPCSerializer(serializers.ModelSerializer):
    class Meta:
        model = EPC
        fields = ("id", "codigo", "peca", "ativo")


class LeituraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Leitura
        fields = (
            "id",
            "epc_lido",
            "conhecido",
            "peca",
            "colaborador",
            "valido_para_acesso",
            "lido_em",
        )
        read_only_fields = fields
