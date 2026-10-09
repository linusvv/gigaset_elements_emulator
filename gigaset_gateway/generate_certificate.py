from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def is_certificate_valid(cert_path: Path, key_path: Path, dns_names: list[str]) -> bool:
    if not cert_path.exists() or not key_path.exists():
        return False
    try:
        cert_data = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)
        max_safe_date = dt.datetime(2038, 1, 1, tzinfo=dt.timezone.utc)
        if cert.not_valid_after_utc > max_safe_date:
            return False
        min_safe_date = dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc)
        if cert.not_valid_before_utc > min_safe_date:
            return False
        key_data = key_path.read_bytes()
        key = serialization.load_pem_private_key(key_data, password=None)
        if cert.public_key().public_numbers() != key.public_key().public_numbers():
            return False
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Vytvoří lokální certifikát pro Gigaset Base")
    # Zakladna se pripojuje pres jmeno, ne pres IP, a self-signed certifikat
    # prijima bez overeni retezce.  IP adresy jsou tedy jen pojistka - vypisuji
    # se vsechny, na kterych brana muze bezet, aby se certifikat nemusel po
    # kazdem prestehovani generovat znovu.  Wildcard lze pouzit jen pro DNS
    # jmeno; pro IP adresu zadny wildcard v X.509 neexistuje.
    parser.add_argument(
        "--ip",
        action="append",
        default=None,
        help="IP adresa do SAN, lze uvest vicekrat",
    )
    parser.add_argument(
        "--dns",
        action="append",
        default=None,
        help="DNS jmeno do SAN, lze uvest vicekrat",
    )
    parser.add_argument("--cert", default="lab.cert.pem")
    parser.add_argument("--key", default="lab.key.pem")
    args = parser.parse_args()

    dns_names = args.dns or [
        "api-bs.gigaset-elements.de",
        "*.gigaset-elements.de",
        "gigaset-elements.de",
    ]
    ip_addresses = args.ip or []

    cert_path = Path(args.cert)
    key_path = Path(args.key)

    if is_certificate_valid(cert_path, key_path, dns_names):
        print(f"Platny certifikat zachovan: {args.cert}, {args.key}")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0])]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime(2010, 1, 1, tzinfo=dt.timezone.utc))
        .not_valid_after(dt.datetime(2037, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(item) for item in dns_names]
                + [
                    x509.IPAddress(ipaddress.ip_address(item))
                    for item in ip_addresses
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    print(f"Vytvoreno: {args.cert}, {args.key}")


if __name__ == "__main__":
    main()

