#!/bin/bash
# ONDA SONIKA · actualiza el servidor de felicitaciones (en /opt/dedica)
set -e
cd /opt/dedica
B=https://raw.githubusercontent.com/AngelChiva/onda-sonika/main/server
for f in app.py tune.py moderar.py Dockerfile docker-compose.yml requirements.txt; do
  curl -fsSL "$B/$f?v=$(date +%s)" -o "$f"
done
echo "Construyendo (tarda unos minutos la primera vez)..."
docker compose up -d --build
sleep 8
curl -sk https://localhost:9443/health && echo && echo "LISTO"
free -m
