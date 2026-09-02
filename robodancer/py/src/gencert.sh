#!/bin/bash
# Generate the certificate the HTTPS server needs.
#
#   ./gencert.sh [IP]        self-signed; browsers warn once, and Chrome will
#                            refuse to register the service worker
#   ./gencert.sh --ca [IP]   create a local CA and sign with it; install the
#                            CA once on each controlling device and the warning
#                            goes away, service workers and PWA install work
#
# The IP goes in a subjectAltName either way: browsers ignore CN for IP
# addresses entirely, so without the SAN the certificate is rejected no matter
# what you click.
set -e

cd "$(dirname "$0")"
mkdir -p certs

USE_CA=0
if [ "$1" = "--ca" ] || [ "$1" = "-ca" ]; then
    USE_CA=1
    shift
fi

IP="${1:-$(hostname -I | awk '{print $1}')}"
if [ -z "$IP" ]; then
    echo "Could not determine the LAN IP. Pass it: ./gencert.sh 192.168.1.97" >&2
    exit 1
fi

SAN="subjectAltName=IP:${IP},DNS:robodancer.local,DNS:localhost"

if [ "$USE_CA" = "1" ]; then
    if [ ! -f certs/ca.pem ]; then
        echo "Creating a local CA (certs/ca.pem)"
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -keyout certs/ca-key.pem -out certs/ca.pem \
            -subj "/CN=Robodancer Local CA" \
            -addext "basicConstraints=critical,CA:TRUE" \
            -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
        chmod 600 certs/ca-key.pem
    else
        echo "Reusing existing CA (certs/ca.pem)"
    fi

    echo "Signing a server certificate for IP:${IP}"
    openssl req -newkey rsa:2048 -nodes \
        -keyout certs/key.pem -out certs/server.csr \
        -subj "/CN=robodancer" 2>/dev/null
    openssl x509 -req -in certs/server.csr -days 3650 \
        -CA certs/ca.pem -CAkey certs/ca-key.pem -CAcreateserial \
        -out certs/cert.pem \
        -extfile <(printf "%s\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n" "$SAN") \
        2>/dev/null
    rm -f certs/server.csr
else
    echo "Generating a self-signed certificate for IP:${IP} (valid 10 years)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout certs/key.pem -out certs/cert.pem \
        -subj "/CN=robodancer" \
        -addext "$SAN" 2>/dev/null
fi

chmod 600 certs/key.pem
echo
echo "Wrote certs/cert.pem and certs/key.pem"
openssl x509 -in certs/cert.pem -noout -subject -ext subjectAltName

if [ "$USE_CA" = "1" ]; then
    cat <<MSG

Now install certs/ca.pem on each device you control the drone from:

  Android : copy ca.pem across, Settings > Security > Encryption & credentials
            > Install a certificate > CA certificate
  Linux   : sudo cp certs/ca.pem /usr/local/share/ca-certificates/robodancer.crt
            && sudo update-ca-certificates      (then restart Chrome)
  macOS   : open it in Keychain Access, System keychain, set to Always Trust
  Windows : certmgr.msc > Trusted Root Certification Authorities > Import

After that https://${IP}:9081/ is trusted: no warning, service worker
registers, and the app can be installed. ca-key.pem never leaves the Pi.
MSG
else
    cat <<MSG

Browsers will warn once (self-signed): accept it and driving works.
Chrome will still refuse to register the service worker, so there is no
offline mode or PWA install. Run './gencert.sh --ca' if you want those.
MSG
fi
