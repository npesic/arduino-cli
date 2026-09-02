#!/bin/bash
# Generate the self-signed certificate the HTTPS server needs.
#
# The IP goes in a subjectAltName because browsers ignore CN for IP addresses
# entirely -- without the SAN, Chrome rejects the certificate no matter what
# you click on the warning page.
set -e

cd "$(dirname "$0")"
mkdir -p certs

IP="${1:-$(hostname -I | awk '{print $1}')}"
if [ -z "$IP" ]; then
    echo "Could not determine the LAN IP. Pass it explicitly: ./gencert.sh 192.168.1.42" >&2
    exit 1
fi

echo "Generating a certificate for IP:$IP (valid 10 years)"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout certs/key.pem -out certs/cert.pem \
    -subj "/CN=robodancer" \
    -addext "subjectAltName=IP:${IP},DNS:robodancer.local,DNS:localhost" \
    2>/dev/null

chmod 600 certs/key.pem
echo
echo "Wrote certs/cert.pem and certs/key.pem"
openssl x509 -in certs/cert.pem -noout -subject -ext subjectAltName
echo
echo "Browsers will warn once (self-signed): accept it, and the gamepad API"
echo "and PWA install will both work from https://${IP}:9081/"
