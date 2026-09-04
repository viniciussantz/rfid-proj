"""
Cliente desktop de controle de EPIs via RFID.

Le tags do leitor (WebSocket) e consulta o backend Django para identificar
qual peca/colaborador foi detectado. A regra de "acesso liberado" e local:
o backend so sinaliza se cada peca e valida (`status: ok`); a combinacao
minima (quais tipos precisam ser vistos juntos) e decidida aqui.
"""
import os
import sys
import asyncio
import json
import logging
from typing import Optional

import httpx
import websockets
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout, QSizePolicy,
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# ==========================================
# CONFIGURACOES
# ==========================================
WS_URI = os.environ.get("RFID_WS_URI", "ws://192.168.4.1:8080/rfid")
API_URL = os.environ.get("RFID_API_URL", "http://localhost:8000").rstrip("/")
API_TIMEOUT_S = float(os.environ.get("RFID_API_TIMEOUT", "3"))

# Tipos de peca que esta tela exige para liberar acesso.
# (A combinacao minima pode virar regra do backend depois.)
TIPOS_OBRIGATORIOS = ("BOTA", "JAQUETA", "CAPACETE", "LUVA", "OCULOS")

# Tipo de peca -> arquivo de imagem + emoji fallback.
SLOT_CONFIG = {
    "BOTA":     {"imagem": "bota.png",     "emoji": "🥾"},
    "JAQUETA":  {"imagem": "jaqueta.png",  "emoji": "🧥"},
    "CAPACETE": {"imagem": "capacete.png", "emoji": "👷"},
    "LUVA":     {"imagem": "luva.png",     "emoji": "🧤"},
    "OCULOS":   {"imagem": "oculos.png",   "emoji": "🥽"},
    "OUTRO":    {"imagem": None,           "emoji": "📦"},
}

log = logging.getLogger("rfid-desktop")


# ==========================================
# THREAD DE LEITURA (Background)
# ==========================================
class RFIDWorker(QThread):
    """
    Roda WebSocket + chamadas HTTP em segundo plano para nao travar a GUI.
    Emite sinais por TIPO de peca (vindo da API), nao por EPC hardcoded.
    """

    slot_preenchido = pyqtSignal(str, dict)   # tipo_peca, info (peca + colaborador)
    slot_desconhecido = pyqtSignal(str)       # epc cru que a API nao reconheceu
    mensagem_status = pyqtSignal(str)         # texto para o label de conexao
    mensagem_erro_api = pyqtSignal(str)       # erro de rede/HTTP

    def __init__(self, api_url: str, timeout_s: float):
        super().__init__()
        self.api_url = api_url
        self.timeout_s = timeout_s
        self.is_running = True
        self.bloqueado = False
        # Estado: chave = tipo de peca. Se a API devolver dois EPCs do mesmo
        # tipo, o segundo sobrescreve o primeiro.
        self.slots: dict = {}

    def run(self):
        asyncio.run(self.escutar_rfid())

    async def escutar_rfid(self):
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            while self.is_running:
                try:
                    self.mensagem_status.emit("Conectando ao leitor RFID...")
                    async with websockets.connect(WS_URI) as websocket:
                        self.mensagem_status.emit("Conectado! Aguardando tags...")

                        while self.is_running:
                            if self.bloqueado:
                                await asyncio.sleep(0.5)
                                continue

                            try:
                                mensagem = await websocket.recv()
                                dados = json.loads(mensagem)
                                epc = (dados.get("epc") or "").strip()
                                if not epc:
                                    continue

                                await self.consultar_api(client, epc)
                            except json.JSONDecodeError:
                                pass  # payload invalido, ignora

                except Exception as e:
                    log.warning("Loop RFID reiniciando: %r", e)
                    self.mensagem_status.emit("Sem conexao. Tentando novamente...")
                    await asyncio.sleep(2)

    async def consultar_api(self, client: httpx.AsyncClient, epc: str):
        """POST /api/leituras/. Trata 200 ok/inativo/desconhecido e erros de rede."""
        url = f"{self.api_url}/api/leituras/"
        try:
            resp = await client.post(url, json={"epc": epc})
        except httpx.HTTPError as e:
            self.mensagem_erro_api.emit(f"Falha ao consultar API: {e.__class__.__name__}")
            return

        if resp.status_code != 200:
            self.mensagem_erro_api.emit(
                f"API retornou HTTP {resp.status_code} para EPC {epc}"
            )
            return

        try:
            payload = resp.json()
        except ValueError:
            self.mensagem_erro_api.emit("Resposta da API nao eh JSON valido.")
            return

        status_resposta = payload.get("status")
        if status_resposta in ("ok", "inativo"):
            peca = payload.get("peca") or {}
            tipo = peca.get("tipo")
            if not tipo:
                self.mensagem_erro_api.emit("API nao retornou 'peca.tipo'.")
                return
            info = {
                "status": status_resposta,
                "peca": peca,
                "colaborador": payload.get("colaborador"),
            }
            self.slots[tipo] = info
            self.slot_preenchido.emit(tipo, info)
            self._verificar_bloqueio()
        else:
            # "desconhecido" ou qualquer outro status
            self.slot_desconhecido.emit(epc)

    def _verificar_bloqueio(self):
        """Bloqueia o worker se todos os tipos obrigatorios ja foram vistos."""
        if all(t in self.slots for t in TIPOS_OBRIGATORIOS):
            self.bloqueado = True

    def resetar(self):
        self.slots.clear()
        self.bloqueado = False


# ==========================================
# WIDGET PERSONALIZADO PARA IMAGENS RESPONSIVAS
# ==========================================
class ResponsiveIconLabel(QLabel):
    """
    QLabel customizado que intercepta redimensionamentos e ajusta a imagem (QPixmap)
    internamente, mantendo a proporcao sem estourar o layout pai.
    """
    def __init__(self, caminho_imagem, emoji):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Define um tamanho minimo para que o layout consiga espremer o card ate um limite viavel
        self.setMinimumSize(60, 60) 

        self.pixmap_original = None
        if caminho_imagem:
            pixmap = QPixmap(caminho_imagem)
            if not pixmap.isNull():
                self.pixmap_original = pixmap

        # Se não carregou a imagem local, exibe o emoji (fallback)
        if not self.pixmap_original:
            self.setText(emoji)
            self.setFont(QFont("DejaVu Sans", 52))

    def resizeEvent(self, event):
        if self.pixmap_original:
            # Redimensiona o pixmap original para o tamanho atual disponivel no QLabel
            w = self.width()
            h = self.height()
            pixmap_redimensionado = self.pixmap_original.scaled(
                w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(pixmap_redimensionado)
        super().resizeEvent(event)


# ==========================================
# INTERFACE GRAFICA (Frontend)
# ==========================================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controle de EPIs - RFID")
        self.resize(1080, 720)
        self.setMinimumSize(820, 600)
        self.setStyleSheet("""
            QWidget#main_window {
                background-color: #101820;
                color: #f5f7fa;
            }
            QLabel { color: #f5f7fa; }
            QLabel#eyebrow {
                color: #ffb547;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#title {
                color: #ffffff;
                font-size: 30px;
                font-weight: bold;
            }
            QLabel#subtitle {
                color: #9eabb8;
                font-size: 13px;
            }
            QLabel#connection {
                color: #9eabb8;
                background-color: #182632;
                border: 1px solid #2a3a48;
                border-radius: 14px;
                padding: 7px 14px;
                font-size: 12px;
            }
            QLabel#error {
                color: #ffb4ab;
                background-color: #3a2023;
                border: 1px solid #71383c;
                border-radius: 7px;
                padding: 8px;
                font-size: 12px;
            }
            QFrame#equipment_card {
                background-color: #182632;
                border: 1px solid #2a3a48;
                border-radius: 12px;
            }
            QFrame#equipment_card[estado="ok"] {
                background-color: #153a39;
                border: 1px solid #2c8a7e;
            }
            QFrame#equipment_card[estado="inativo"] {
                background-color: #3b3020;
                border: 1px solid #9b7029;
            }
            QLabel#card_title {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
            }
            QLabel#card_status {
                color: #8393a1;
                font-size: 13px;
                font-weight: bold;
            }
            QLabel#card_status[estado="ok"] { color: #65d6c5; }
            QLabel#card_status[estado="inativo"] { color: #ffca68; }
            QLabel[role="owner"] { color: #9eabb8; font-size: 11px; }
            QLabel#access {
                color: #b8c4ce;
                background-color: #182632;
                border: 1px solid #2a3a48;
                border-radius: 10px;
                padding: 17px;
                font-size: 20px;
                font-weight: bold;
            }
            QLabel#access[liberado="true"] {
                color: #d9fff8;
                background-color: #176b61;
                border: 1px solid #51d1bd;
            }
            QPushButton#reset {
                color: #101820;
                background-color: #ffb547;
                border: none;
                border-radius: 7px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#reset:hover { background-color: #ffc96e; }
            QPushButton#reset:pressed { background-color: #e09a31; }
        """)
        self.setObjectName("main_window")

        # mapa tipo -> (card_frame, label_status)
        self.slots_gui: dict = {}

        self.init_ui()

        self.worker = RFIDWorker(api_url=API_URL, timeout_s=API_TIMEOUT_S)
        self.worker.slot_preenchido.connect(self.on_slot_preenchido)
        self.worker.slot_desconhecido.connect(self.on_slot_desconhecido)
        self.worker.mensagem_status.connect(self.atualizar_status_conexao)
        self.worker.mensagem_erro_api.connect(self.mostrar_erro_api)
        self.worker.start()

    def init_ui(self):
        layout_principal = QVBoxLayout()
        layout_principal.setContentsMargins(42, 34, 42, 34)
        layout_principal.setSpacing(18)

        cabecalho = QHBoxLayout()
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(4)
        eyebrow = QLabel("OPERAÇÃO • CONTROLE DE ACESSO")
        eyebrow.setObjectName("eyebrow")
        titulo = QLabel("Verificação de equipamentos")
        titulo.setObjectName("title")
        subtitulo = QLabel("Aproxime os EPIs do leitor para validar a entrada.")
        subtitulo.setObjectName("subtitle")
        bloco_titulo.addWidget(eyebrow)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()

        # Status da conexao no topo
        self.lbl_conexao = QLabel("Iniciando sistema...")
        self.lbl_conexao.setAlignment(Qt.AlignCenter)
        self.lbl_conexao.setObjectName("connection")
        cabecalho.addWidget(self.lbl_conexao, 0, Qt.AlignTop)
        layout_principal.addLayout(cabecalho)

        # Label de erro da API (oculto por padrao)
        self.lbl_erro_api = QLabel("")
        self.lbl_erro_api.setAlignment(Qt.AlignCenter)
        self.lbl_erro_api.setObjectName("error")
        self.lbl_erro_api.hide()
        layout_principal.addWidget(self.lbl_erro_api)

        # Layout horizontal para os cards
        layout_equipamentos = QGridLayout()
        layout_equipamentos.setHorizontalSpacing(12)
        layout_equipamentos.setVerticalSpacing(12)
        for indice, tipo in enumerate(TIPOS_OBRIGATORIOS):
            cfg = SLOT_CONFIG.get(tipo, SLOT_CONFIG["OUTRO"])
            card, lbl_status = self._criar_card(tipo, cfg["imagem"], cfg["emoji"])
            self.slots_gui[tipo] = (card, lbl_status)
            layout_equipamentos.addWidget(card, indice // 3, indice % 3)
        for coluna in range(3):
            layout_equipamentos.setColumnStretch(coluna, 1)
        layout_principal.addLayout(layout_equipamentos)

        # Mensagem de Acesso Liberado
        self.lbl_acesso = QLabel("AGUARDANDO LEITURA...")
        self.lbl_acesso.setAlignment(Qt.AlignCenter)
        self.lbl_acesso.setObjectName("access")
        self.lbl_acesso.setProperty("liberado", "false")
        layout_principal.addWidget(self.lbl_acesso)

        # Botao Reset
        self.btn_reset = QPushButton("Resetar e Nova Leitura")
        self.btn_reset.setObjectName("reset")
        self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_reset.clicked.connect(self.resetar_interface)
        rodape = QHBoxLayout()
        rodape.addStretch()
        rodape.addWidget(self.btn_reset)
        layout_principal.addLayout(rodape)

        self.setLayout(layout_principal)

    def _criar_card(self, tipo: str, caminho_imagem: Optional[str], emoji: str):
        frame = QFrame()
        frame.setObjectName("equipment_card")
        frame.setMinimumHeight(200)  # Altura reduzida para melhor redimensionamento
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(8)

        titulo = QLabel(tipo)
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setObjectName("card_title")
        layout.addWidget(titulo)

        # Usando a nossa nova classe responsiva!
        lbl_img = ResponsiveIconLabel(caminho_imagem, emoji)
        layout.addWidget(lbl_img)

        lbl_status = QLabel("PENDENTE")
        lbl_status.setAlignment(Qt.AlignCenter)
        lbl_status.setObjectName("card_status")
        lbl_status.setProperty("estado", "pendente")
        layout.addWidget(lbl_status)

        # linha extra com colaborador, preenchida quando a API responder
        lbl_dono = QLabel("")
        lbl_dono.setAlignment(Qt.AlignCenter)
        lbl_dono.setProperty("role", "owner")
        lbl_dono.setObjectName(f"dono_{tipo}")
        layout.addWidget(lbl_dono)

        frame.setLayout(layout)
        return frame, lbl_status

    # --- Slots chamados pela thread ---

    def atualizar_status_conexao(self, msg: str):
        self.lbl_conexao.setText(msg)

    def mostrar_erro_api(self, msg: str):
        self.lbl_erro_api.setText(f"⚠ {msg}")
        self.lbl_erro_api.show()

    @staticmethod
    def _atualizar_estado(widget, estado: str):
        widget.setProperty("estado", estado)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def on_slot_preenchido(self, tipo: str, info: dict):
        """Pinta o card do tipo de peca com a info vinda da API."""
        if tipo not in self.slots_gui:
            # tipo de peca nao obrigatorio -> ignora silenciosamente
            return

        # limpa erro anterior quando uma leitura volta a dar certo
        self.lbl_erro_api.hide()
        self.lbl_erro_api.clear()

        _, lbl_status = self.slots_gui[tipo]
        status_resposta = info.get("status")
        if status_resposta == "ok":
            lbl_status.setText("OK · VALIDADO")
            self._atualizar_estado(lbl_status, "ok")
            self._atualizar_estado(self.slots_gui[tipo][0], "ok")
        else:  # inativo
            lbl_status.setText("INATIVO")
            self._atualizar_estado(lbl_status, "inativo")
            self._atualizar_estado(self.slots_gui[tipo][0], "inativo")

        # mostra o colaborador embaixo do card
        card_frame, _ = self.slots_gui[tipo]
        lbl_dono = card_frame.findChild(QLabel, f"dono_{tipo}")
        colaborador = info.get("colaborador") or {}
        nome = colaborador.get("nome")
        matricula = colaborador.get("matricula")
        if nome and matricula:
            lbl_dono.setText(f"{nome} ({matricula})")
        else:
            lbl_dono.setText("(sem colaborador)")

        self.verificar_acesso()

    def on_slot_desconhecido(self, epc: str):
        # mostra um toast simples no label de erro
        self.mostrar_erro_api(f"EPC desconhecido: {epc}")

    def verificar_acesso(self):
        if all(
            t in self.worker.slots and self.worker.slots[t].get("status") == "ok"
            for t in TIPOS_OBRIGATORIOS
        ):
            self.lbl_acesso.setText("ACESSO LIBERADO")
            self._atualizar_estado(self.lbl_acesso, "true")
        else:
            # garante que o banner nao fique "verde preso" se algo mudar
            if self.lbl_acesso.text() == "ACESSO LIBERADO":
                self.lbl_acesso.setText("AGUARDANDO LEITURA...")
                self._atualizar_estado(self.lbl_acesso, "false")

    def resetar_interface(self):
        """Volta a interface para o estado inicial e libera a thread."""
        for tipo, (_, lbl_status) in self.slots_gui.items():
            card_frame, _ = self.slots_gui[tipo]
            lbl_status.setText("PENDENTE")
            self._atualizar_estado(lbl_status, "pendente")
            self._atualizar_estado(card_frame, "pendente")
            lbl_dono = card_frame.findChild(QLabel, f"dono_{tipo}")
            if lbl_dono:
                lbl_dono.setText("")

        self.lbl_acesso.setText("AGUARDANDO LEITURA...")
        self._atualizar_estado(self.lbl_acesso, "false")
        self.lbl_erro_api.hide()
        self.lbl_erro_api.clear()
        self.worker.resetar()

    def closeEvent(self, event):
        self.worker.is_running = False
        self.worker.quit()
        self.worker.wait()
        event.accept()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    app = QApplication(sys.argv)
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec_())