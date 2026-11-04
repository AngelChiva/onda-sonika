#!/bin/bash
# ONDA SONIKA - instalación de AzuraCast (swap 2 GB + Docker + AzuraCast)
exec > >(tee -a /root/instalacion-onda-sonika.log) 2>&1
set -e
echo "=== ONDA SONIKA: inicio $(date) ==="
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
free -h
mkdir -p /var/azuracast
cd /var/azuracast
curl -fsSL https://raw.githubusercontent.com/AzuraCast/AzuraCast/main/docker.sh > docker.sh
chmod a+x docker.sh
yes '' | ./docker.sh install
echo "=== ONDA SONIKA: FIN OK $(date) ==="
