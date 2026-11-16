#!/bin/bash
# ONDA SONIKA · instala el servidor de felicitaciones en el VPS (junto a AzuraCast)
# Uso: curl -fsSL https://raw.githubusercontent.com/AngelChiva/onda-sonika/main/server/instalar.sh -o /root/i.sh && bash /root/i.sh
set -e
D=/opt/dedica; mkdir -p $D/certs $D/data; cd $D
B=https://raw.githubusercontent.com/AngelChiva/onda-sonika/main/server
for f in app.py tune.py moderar.py requirements.txt Dockerfile docker-compose.yml certs.sh actualizar.sh; do
  curl -fsSL "$B/$f?v=$(date +%s)" -o $f
done
chmod +x certs.sh
./certs.sh
if [ ! -f .env ]; then
  PASS=$(tr -dc 'a-km-z2-9' </dev/urandom | head -c 10)
  cat > .env <<EOF
ADMIN_PASS=$PASS
AZ_URL=https://radio.ondasonika.com
AZ_STATION=1
PUBLIC_URL=https://radio.ondasonika.com:9443
ALLOWED_ORIGINS=https://ondasonika.com,https://www.ondasonika.com
EOF
fi
docker compose up -d --build
echo "30 4 * * * root $D/certs.sh && docker restart dedica >/dev/null" > /etc/cron.d/dedica
sleep 5
echo
echo "=============================================="
echo " LISTO. Mini app:  https://radio.ondasonika.com:9443/admin"
echo " Usuario: angel   Contraseña: $(grep ADMIN_PASS .env | cut -d= -f2)"
echo " (apúntala)"
echo "=============================================="
