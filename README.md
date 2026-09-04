# RFID-Proj — Gestão de EPIs via RFID

Stack completa: **app desktop PyQt5** que lê tags de um leitor RFID via WebSocket e consulta um **backend Django** para identificar a peça/colaborador antes de liberar o acesso.

- **Desktop**: PyQt5 + `websockets` + `httpx` (cliente HTTP async)
- **Backend**: Django 5 + Django REST Framework
- **Banco**: PostgreSQL 16 (em container)
- **Orquestração**: Docker Compose

---

## Estrutura

```text
rfid-proj/
├── main.py                    # app PyQt5 desktop (chama a API)
├── requirements.txt           # deps do desktop (PyQt5, websockets, httpx)
├── docker-compose.yml
├── .env.example
└── backend/
    ├── Dockerfile
    ├── pyproject.toml         # deps do backend via uv
    ├── manage.py
    ├── entrypoint.sh
    ├── config/                # projeto Django
    └── apps/
        ├── core/              # models, admin, serializers
        └── api/               # /api/leituras/
```

---

## Subir a stack

```bash
# 1. Copie as variáveis de ambiente
cp .env.example .env

# 2. Sobe Postgres + Django (migrations são rodadas automaticamente)
docker compose up --build
```

Serviços expostos:

| Serviço | URL                      | Descrição                  |
| ------- | ------------------------ | -------------------------- |
| web     | http://localhost:8000    | Django (admin + API)       |
| db      | localhost:5432           | PostgreSQL 16              |

> O `entrypoint.sh` aplica `migrate --noinput` e, se `DJANGO_SUPERUSER_*` estiver definido no `.env`, garante um superuser. Sem isso, crie manualmente:
>
> ```bash
> docker compose exec web uv run python manage.py createsuperuser
> ```

---

## Django Admin

Acesse **http://localhost:8000/admin/** e gerencie:

- **Colaboradores**: nome, matrícula, ativo.
- **Peças de EPI**: tipo (Bota/Jaqueta/Capacete/Luva/Óculos/Outro), descrição, colaborador dono, ativa. Uma peça pode ter **vários EPCs** vinculados.
- **EPCs (tags RFID)**: código + peça vinculada + ativo. Busca por código e por matrícula.
- **Leituras**: log somente leitura do que o endpoint recebeu.

---

## App desktop (`main.py`)

O cliente PyQt5 lê tags do leitor (WebSocket) e, **a cada tag detectada**, faz `POST /api/leituras/` para identificar a peça. A regra de "acesso liberado" é local: o servidor só diz se a peça é válida (`status: ok`); a combinação mínima (hoje `BOTA + JAQUETA`) é decidida no cliente.

### Instalação

```bash
# Crie um venv e instale as deps (fora do Docker — o desktop roda no host)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Variáveis de ambiente

| Var                 | Default                       | Descrição                                          |
| ------------------- | ----------------------------- | -------------------------------------------------- |
| `RFID_WS_URI`       | `ws://192.168.4.1:8080/rfid`  | WebSocket do leitor RFID                           |
| `RFID_API_URL`      | `http://localhost:8000`       | Base URL do backend Django                         |
| `RFID_API_TIMEOUT`  | `3` (segundos)                | Timeout do `POST /api/leituras/`                   |

Exemplo:

```bash
export RFID_API_URL="http://192.168.0.10:8000"   # backend em outra máquina
python main.py
```

### Fluxo da tela

1. Lê tag via WebSocket → `POST /api/leituras/ {"epc": "..."}`.
2. Resposta `status: ok` + `peca.tipo` → pinta o card do tipo (`BOTA`, `JAQUETA`) com o nome/matrícula do colaborador.
3. Resposta `status: inativo` → card em **amarelo** ("⚠ INATIVO").
4. Resposta `status: desconhecido` → toast de aviso, card não muda.
5. Quando todos os tipos em `TIPOS_OBRIGATORIOS` estão com `status: ok` → banner **"ACESSO LIBERADO"** (verde) e a thread para de ler até o reset.
6. Botão **"Resetar e Nova Leitura"** limpa slots, banner e libera a thread.

---

## API — `POST /api/leituras/`

Endpoint que o app desktop chama a cada tag lida.

**Request**

```http
POST /api/leituras/
Content-Type: application/json

{"epc": "3034000000000C400000007F"}
```

**Resposta — EPC conhecido e ativo**

```json
{
  "status": "ok",
  "epc": "3034000000000C400000007F",
  "leitura": { "id": 42, "conhecido": true, "valido_para_acesso": true, "...": "..." },
  "peca":   { "id": 1, "tipo": "BOTA", "descricao": "Bota de segurança", "...": "..." },
  "colaborador": { "id": 7, "nome": "Fulano", "matricula": "1234", "ativo": true }
}
```

**Resposta — EPC desconhecido**

```json
{
  "status": "desconhecido",
  "epc": "9999",
  "leitura": { "id": 43, "conhecido": false, "valido_para_acesso": false, "...": "..." }
}
```

**Exemplo via curl**

```bash
curl -X POST http://localhost:8000/api/leituras/ \
  -H 'Content-Type: application/json' \
  -d '{"epc":"3034000000000C400000007F"}'
```

> A regra de **"acesso liberado"** é responsabilidade do cliente (desktop): o servidor só informa qual peça/colaborador foi identificado. O cliente decide se a combinação cobre as peças obrigatórias (ex.: bota + jaqueta).

---

## Detalhes — dev

- Credenciais do Postgres e do `DJANGO_SECRET_KEY` ficam em `.env` (não commitar).
- `ALLOWED_HOSTS = ['*']` e DRF sem auth são **apenas para dev local**. Em produção, restrinja `ALLOWED_HOSTS` e habilite `TokenAuthentication` no `settings.py`.
- Para destruir o volume do banco: `docker compose down -v`.

---

## Roadmap (próximas iterações)

- Regras de combinação mínima por colaborador (servidor) e deduplicação de sessão.
- Autenticação no endpoint (Token / JWT) e paginação no admin.
- Suporte a outros tipos de EPI além de BOTA/JAQUETA (já previsto no `SLOT_CONFIG` do `main.py`).
