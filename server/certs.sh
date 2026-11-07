#!/bin/bash
# Copia el certificado de AzuraCast (radio.ondasonika.com) para el servidor de felicitaciones
D=/opt/dedica/certs; mkdir -p $D
V=$(docker volume inspect -f '{{.Mountpoint}}' azuracast_acme 2>/dev/null || ls -d /var/lib/docker/volumes/*acme*/_data 2>/dev/null | head -1)
for pair in "ssl.crt ssl.key" "radio.ondasonika.com.crt radio.ondasonika.com.key" "default.crt default.key"; do
  set -- $pair
  C=$(find "$V" -name "$1" 2>/dev/null | head -1); K=$(find "$V" -name "$2" 2>/dev/null | head -1)
  if [ -n "$C" ] && [ -n "$K" ]; then cp -L "$C" $D/ssl.crt; cp -L "$K" $D/ssl.key; echo "Certificado: $C"; exit 0; fi
done
echo "AVISO: no encuentro el certificado de AzuraCast en $V"; ls -la "$V" 2>/dev/null; exit 1
