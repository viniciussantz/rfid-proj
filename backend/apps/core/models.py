"""Modelos de domínio: Colaborador, PecaEPI, EPC e log de Leitura."""
from __future__ import annotations

from django.db import models


class TimestampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Colaborador(TimestampedModel):
    nome = models.CharField(max_length=120)
    matricula = models.CharField(max_length=40, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Colaborador"
        verbose_name_plural = "Colaboradores"

    def __str__(self) -> str:
        return f"{self.nome} ({self.matricula})"


class PecaEPI(TimestampedModel):
    class Tipo(models.TextChoices):
        BOTA = "BOTA", "Bota (Genérica)"
        BOTA_ESQ = "BOTA_ESQ", "Bota Esquerda"
        BOTA_DIR = "BOTA_DIR", "Bota Direita"
        CALCA = "CALCA", "Calça"
        JAQUETA = "JAQUETA", "Jaqueta"
        CAPACETE = "CAPACETE", "Capacete"
        CRACHA = "CRACHA", "Crachá"
        LUVA = "LUVA", "Luva"
        OCULOS = "OCULOS", "Óculos"
        OUTRO = "OUTRO", "Outro"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descricao = models.CharField(max_length=140, blank=True)
    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pecas",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ("tipo", "descricao", "id")
        verbose_name = "Peça de EPI"
        verbose_name_plural = "Peças de EPI"
        indexes = [
            models.Index(fields=["tipo", "ativa"]),
        ]

    def __str__(self) -> str:
        if self.descricao:
            return f"{self.get_tipo_display()} - {self.descricao}"
        return self.get_tipo_display()


class EPC(TimestampedModel):
    """Tag RFID (Electronic Product Code) vinculada a uma PeçaEPI."""

    codigo = models.CharField(max_length=64, unique=True, db_index=True)
    peca = models.ForeignKey(
        PecaEPI,
        on_delete=models.CASCADE,
        related_name="epcs",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "EPC (tag RFID)"
        verbose_name_plural = "EPCs (tags RFID)"

    def __str__(self) -> str:
        return self.codigo


class Leitura(TimestampedModel):
    """Registro (log) de cada EPC lido pelo leitor."""

    epc_lido = models.CharField(max_length=64, db_index=True)
    conhecido = models.BooleanField(default=False)
    peca = models.ForeignKey(
        PecaEPI,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leituras",
    )
    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leituras",
    )
    valido_para_acesso = models.BooleanField(default=False)
    lido_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-lido_em",)
        verbose_name = "Leitura"
        verbose_name_plural = "Leituras"

    def __str__(self) -> str:
        tag = f" ({self.epc_lido})"
        if self.colaborador:
            return f"{self.colaborador.matricula}{tag}"
        return f"?{tag}"
