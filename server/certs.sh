#!/bin/bash
# Copia el certificado de AzuraCast (radio.ondasonika.com) para el servidor de felicitaciones.
# En el volumen de AzuraCast ssl.crt/ssl.key suelen ser enlaces a rutas de DENTRO del contenedor
# (/var/azuracast/storage/acme/...), así que se traducen a la ruta del volumen.
D=/opt/dedica/certs; mkdir -p $D
V=$(docker volume inspect -f '{{.Mountpoint}}' azuracast_acme 2>/dev/null || ls -d /var/lib/docker/volumes/*acme*/_data 2>/dev/null | head -1)
res(){ local f="$1" i=0; while [ -L "$f" ] && [ $i -lt 8 ]; do local t; t=$(readlink "$f");
  case "$t" in /var/azuracast/storage/acme/*) t="$V/${t#/var/azuracast/storage/acme/}";; /*) ;; *) t="$(dirname "$f")/$t";; esac; f="$t"; i=$((i+1)); done; echo "$f"; }
for pair in "radio.ondasonika.com.crt radio.ondasonika.com.key" "ssl.crt ssl.key" "default.crt default.key"; do
  set -- $pair
  C=$(find "$V" -name "$1" 2>/dev/null | head -1); K=$(find "$V" -name "$2" 2>/dev/null | head -1)
  [ -n "$C" ] && [ -n "$K" ] || continue
  C=$(res "$C"); K=$(res "$K")
  if [ -s "$C" ] && [ -s "$K" ]; then cp "$C" $D/ssl.crt && cp "$K" $D/ssl.key && echo "Certificado OK: $C" && exit 0; fi
done
echo "AVISO: no encuentro el certificado de AzuraCast en $V"; ls -laR "$V" 2>/dev/null | head -40; exit 1
