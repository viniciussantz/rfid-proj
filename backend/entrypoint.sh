#!/usr/bin/env bash
set -euo pipefail

cd /app

echo "[entrypoint] Gerando migrations pendentes..."
uv run python manage.py makemigrations --noinput || true

echo "[entrypoint] Aplicando migrations..."
uv run python manage.py migrate --noinput

# Cria superuser automaticamente se as envs estiverem definidas
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "[entrypoint] Garantindo superuser '${DJANGO_SUPERUSER_USERNAME}'..."
  uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
u, created = U.objects.get_or_create(
    username='${DJANGO_SUPERUSER_USERNAME}',
    defaults={'email': '${DJANGO_SUPERUSER_EMAIL}', 'is_staff': True, 'is_superuser': True},
)
u.is_staff = True
u.is_superuser = True
if created or not u.has_usable_password():
    u.set_password('${DJANGO_SUPERUSER_PASSWORD}')
u.save()
print('superuser ok' if created else 'superuser jÃ¡ existia; senha resetada se estava vazia')
"
fi

echo "[entrypoint] Subindo runserver em 0.0.0.0:8000..."
exec uv run python manage.py runserver 0.0.0.0:8000
