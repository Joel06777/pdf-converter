#!/usr/bin/env bash
# bootstrap.sh — Reconstruye el convertidor en un servidor Ubuntu 24.04 nuevo.
#
# Uso:
#   bash scripts/bootstrap.sh tu-dominio.duckdns.org
#   DUCKDNS_TOKEN=tu-token bash scripts/bootstrap.sh tu-dominio.duckdns.org
#
# Qué hace (en orden): instala Docker si falta, clona el repositorio (o hace
# git pull si ya existe) en ~/pdf-converter, genera el .env si no existe
# (con API_KEY y DOWNLOAD_SECRET aleatorios), crea el Caddyfile con tu
# dominio si no existe, levanta el servicio y el contenedor de Caddy, y si
# le pasas DUCKDNS_TOKEN programa la actualización del dominio cada 5 min.
#
# Idempotente en lo posible: se puede ejecutar dos veces sin romper nada.
# NO regenera el .env si ya existe (para no invalidar las claves de Vercel).
# NO toca la consola de Oracle: la instancia y los puertos 80/443 en la
# lista de seguridad hay que crearlos a mano (ver docs/DESPLIEGUE_GRATIS.md).
#
# Se ejecuta como usuario normal con sudo disponible (el usuario 'ubuntu'
# de Oracle sirve). No lo ejecutes como root: los archivos quedarían de root
# y luego Docker no podría leerlos como usuario normal.
set -euo pipefail

DOMAIN="${1:-}"
REPO_URL="${REPO_URL:-https://github.com/Joel06777/pdf-converter.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/pdf-converter}"
DUCKDNS_TOKEN="${DUCKDNS_TOKEN:-}"

if [ -z "$DOMAIN" ]; then
  echo "Uso: bash scripts/bootstrap.sh tu-dominio.duckdns.org" >&2
  echo "Ejemplo: bash scripts/bootstrap.sh convertidor-pdf-fabian.duckdns.org" >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  echo "No ejecutes este script como root. Usa el usuario normal (p. ej. 'ubuntu') con sudo." >&2
  exit 1
fi

command -v sudo >/dev/null 2>&1 || { echo "Hace falta 'sudo'." >&2; exit 1; }

echo "==> 1/6 Comprobando Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker no está instalado. Instalándolo desde el repositorio oficial..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER" || true
  echo "Docker instalado. Si 'docker ps' te da un error de permisos, cierra la sesión y vuelve a entrar."
else
  echo "Docker ya está instalado: $(docker --version)"
fi

# Docker Compose puede ser 'docker compose' (plugin) o 'docker-compose' (binario viejo).
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "No se encontró Docker Compose (ni 'docker compose' ni 'docker-compose')." >&2
  exit 1
fi

echo "==> 2/6 Repositorio en $INSTALL_DIR..."
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "El repositorio ya existe. Actualizando con git pull..."
  git -C "$INSTALL_DIR" pull --ff-only || echo "AVISO: 'git pull' falló (puede haber cambios locales). Sigo con el código que hay."
else
  if [ -e "$INSTALL_DIR" ]; then
    echo "AVISO: $INSTALL_DIR existe pero no es un repositorio git. Lo dejo como está y no lo toco." >&2
    exit 1
  fi
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "==> 3/6 Archivo .env..."
if [ -f .env ]; then
  echo ".env ya existe. NO lo toco (para no invalidar las claves de Vercel)."
else
  if [ ! -f .env.example ]; then
    echo "No encuentro .env.example en el repositorio." >&2
    exit 1
  fi
  cp .env.example .env
  API_KEY="$(openssl rand -hex 32)"
  DOWNLOAD_SECRET="$(openssl rand -hex 32)"
  # Sustituye solo las líneas de API_KEY y DOWNLOAD_SECRET; el resto queda
  # como viene en .env.example.
  sed -i "s|^API_KEY=.*|API_KEY=$API_KEY|" .env
  sed -i "s|^DOWNLOAD_SECRET=.*|DOWNLOAD_SECRET=$DOWNLOAD_SECRET|" .env
  echo "Se generó un .env nuevo con claves aleatorias."
  echo "GUARDA ESTAS CLAVES EN UN LUGAR SEGURO (gestor de contraseñas):"
  echo "  API_KEY=$API_KEY"
  echo "  DOWNLOAD_SECRET=$DOWNLOAD_SECRET"
  echo "Y pon el mismo API_KEY en Vercel como CONVERTER_API_KEY."
  echo "ACUÉRDATE: cambia ALLOWED_ORIGINS en .env por el dominio de tu web en Vercel."
fi

echo "==> 4/6 Caddyfile para $DOMAIN..."
if [ -f Caddyfile ]; then
  echo "Caddyfile ya existe. NO lo toco."
else
  printf '%s {\n    reverse_proxy localhost:8000\n}\n' "$DOMAIN" > Caddyfile
  echo "Caddyfile creado."
fi

echo "==> 5/6 Levantando el servicio..."
$COMPOSE up -d --build
echo "Esperando 15 segundos a que la API arranque..."
sleep 15
$COMPOSE ps
if curl -fsS --max-time 10 "http://localhost:8000/health" >/dev/null 2>&1; then
  echo "La API responde en http://localhost:8000/health"
else
  echo "AVISO: la API aún no responde en localhost:8000. Mira los logs con: $COMPOSE logs --tail=50 api" >&2
fi

echo "==> 6/6 Caddy (HTTPS automático)..."
if docker ps -a --format '{{.Names}}' | grep -qx caddy; then
  echo "Ya existe un contenedor llamado 'caddy'. Lo reinicio con el Caddyfile actual."
  docker restart caddy >/dev/null
else
  docker run -d --name caddy --network host --restart unless-stopped \
    -v "$PWD/Caddyfile:/etc/caddy/Caddyfile" caddy:2
fi
docker ps --filter name=caddy --format '{{.Names}}: {{.Status}}'

if [ -n "$DUCKDNS_TOKEN" ]; then
  echo "==> Extra: actualizador de DuckDNS cada 5 minutos..."
  CRON_LINE="*/5 * * * * curl -fsS 'https://www.duckdns.org/update?domains=${DOMAIN%.duckdns.org}&token=$DUCKDNS_TOKEN&ip=' >/dev/null 2>&1"
  if crontab -l 2>/dev/null | grep -q "duckdns.org/update"; then
    echo "Ya hay una tarea de DuckDNS en el cron. NO la duplico."
  else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Tarea de DuckDNS programada."
  fi
  # Actualiza el dominio ahora mismo, sin esperar al cron.
  curl -fsS "https://www.duckdns.org/update?domains=${DOMAIN%.duckdns.org}&token=$DUCKDNS_TOKEN&ip=" || echo "AVISO: la actualización de DuckDNS falló. Revisa el dominio y el token." >&2
else
  echo "Sin DUCKDNS_TOKEN: no programo la actualización de DuckDNS."
  echo "Si tu IP cambia, actualiza el dominio a mano en https://www.duckdns.org/"
fi

echo ""
echo "Listo. Comprueba en tu navegador:"
echo "  https://$DOMAIN/health"
echo "Si no responde, revisa: puertos 80/443 en la lista de seguridad de Oracle (paso 2.1),"
echo "iptables en el servidor (paso 2.2) y los logs con: $COMPOSE logs --tail=100 api"
