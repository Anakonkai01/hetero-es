#!/usr/bin/env bash
# Run on a fresh Ubuntu 24.04 CPU server with sudo. No GPU packages are installed.
set -euo pipefail
bundle=${1:?Provide the extracted release bundle directory}
private_config=${2:?Provide the private export directory}
domain=${3:?Provide the DuckDNS hostname}
[[ $EUID -eq 0 ]] || { echo 'Run this installer with sudo on the new CPU server.' >&2; exit 1; }
[[ "$domain" =~ ^[a-z0-9-]+\.duckdns\.org$ ]] || { echo 'Expected a DuckDNS hostname.' >&2; exit 1; }
[[ ! -e /opt/heteroes ]] || { echo '/opt/heteroes already exists; use the documented upgrade procedure.' >&2; exit 1; }
[[ -f "$private_config/state/product.sqlite" && -f "$private_config/credentials.json" && -f "$private_config/r2.json" && -f "$bundle/frontend/dist/index.html" ]] || { echo 'Release or private export is incomplete.' >&2; exit 1; }
apt-get update
apt-get install -y python3.12-venv curl gpg debian-keyring debian-archive-keyring apt-transport-https
curl --fail --silent --show-error --location https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl --fail --silent --show-error --location https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
chmod 0644 /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy
id heteroes >/dev/null 2>&1 || useradd --system --home /var/lib/heteroes --shell /usr/sbin/nologin heteroes
install -d -m 0755 /opt/heteroes
cp -a "$bundle/backend" "$bundle/frontend" "$bundle/deploy" /opt/heteroes/
python3.12 -m venv /opt/heteroes/.venv
/opt/heteroes/.venv/bin/pip install -r /opt/heteroes/backend/requirements-cloud.lock.txt
install -d -o heteroes -g heteroes -m 0700 /etc/heteroes /var/lib/heteroes
install -o heteroes -g heteroes -m 0600 "$private_config/state/product.sqlite" /var/lib/heteroes/product.sqlite
install -o heteroes -g heteroes -m 0600 "$private_config/credentials.json" /etc/heteroes/credentials.json
install -o heteroes -g heteroes -m 0600 "$private_config/r2.json" /etc/heteroes/r2.json
install -o heteroes -g heteroes -m 0600 /opt/heteroes/deploy/config.example.json /etc/heteroes/config.json
install -m 0644 /opt/heteroes/deploy/heteroes.service /etc/systemd/system/heteroes.service
install -m 0644 /opt/heteroes/deploy/Caddyfile /etc/caddy/Caddyfile
install -d -m 0755 /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironment=HETEROES_DOMAIN=%s\n' "$domain" > /etc/systemd/system/caddy.service.d/heteroes.conf
systemctl daemon-reload
HETEROES_DOMAIN="$domain" caddy validate --config /etc/caddy/Caddyfile
systemctl enable --now heteroes caddy
systemctl reload caddy
printf 'CPU control service installed at https://%s. Imported queue remains held.\n' "$domain"
