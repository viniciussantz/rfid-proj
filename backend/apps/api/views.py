"""Views da API de leituras RFID.

Endpoint principal: `POST /api/leituras/`
- Body: `{"epc": "3034..."}`
- Comportamento: registra uma `Leitura` e devolve a peça/colaborador
  resolvidos (ou status `desconhecido`).
- Regra de "acesso liberado": delegada ao cliente desktop. O servidor só
  sinaliza `valido_para_acesso` quando a peça lida pertence a um colaborador
  ativo. O cliente é responsável por checar o conjunto mínimo.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import EPC, Leitura
from apps.core.serializers import (
    ColaboradorSerializer,
    LeituraSerializer,
    PecaEPISerializer,
)


class LeituraEventoView(APIView):
    """Registra a leitura de um EPC e devolve contexto útil ao cliente."""

    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        epc_bruto = (request.data.get("epc") or "").strip()
        if not epc_bruto:
            return Response(
                {"detail": "Campo 'epc' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        epc_obj = (
            EPC.objects.select_related("peca", "peca__colaborador")
            .filter(codigo=epc_bruto, ativo=True)
            .first()
        )

        if epc_obj is None:
            leitura = Leitura.objects.create(
                epc_lido=epc_bruto,
                conhecido=False,
                valido_para_acesso=False,
            )
            return Response(
                {
                    "status": "desconhecido",
                    "epc": epc_bruto,
                    "leitura": LeituraSerializer(leitura).data,
                },
                status=status.HTTP_200_OK,
            )

        peca = epc_obj.peca
        colaborador = peca.colaborador if peca.ativa else None
        valido = bool(colaborador and colaborador.ativo)

        leitura = Leitura.objects.create(
            epc_lido=epc_bruto,
            conhecido=True,
            peca=peca if peca.ativa else None,
            colaborador=colaborador,
            valido_para_acesso=valido,
        )

        return Response(
            {
                "status": "ok" if valido else "inativo",
                "epc": epc_bruto,
                "leitura": LeituraSerializer(leitura).data,
                "peca": PecaEPISerializer(peca).data,
                "colaborador": (
                    ColaboradorSerializer(colaborador).data if colaborador else None
                ),
            },
            status=status.HTTP_200_OK,
        )


class LeituraDetailView(APIView):
    """Detalhe de uma leitura já registrada."""

    http_method_names = ["get", "options"]

    def get(self, request: Request, pk: int) -> Response:  # noqa: ARG002
        leitura = get_object_or_404(Leitura, pk=pk)
        return Response(LeituraSerializer(leitura).data)
