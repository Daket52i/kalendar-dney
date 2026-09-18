#!/usr/bin/env python3
"""Создаёт ключ, которым подписывается APK.

Зачем он вообще нужен. Android ставит обновление поверх старой версии только
тогда, когда обе подписаны одним и тем же ключом. Отладочный ключ на сервере
сборки создаётся заново каждый раз — значит, каждая сборка была бы «другим
приложением», и обновиться можно было бы только через удаление со всеми
записями. Поэтому ключ создаётся один раз и живёт в секретах репозитория.

Пароль не хранится в коде: он передаётся в переменной окружения. Готовый
файл .p12 кладётся в секреты как base64 — так его можно передать одной
строкой.

Запуск:

    KEYSTORE_PASSWORD=<пароль> python3 tools/make_keystore.py cyclease.p12
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

#: Имя ключа внутри файла. Android обращается к нему по этому имени.
ALIAS = "cyclease"

#: Сколько лет живёт ключ. Приложение, подписанное просроченным ключом,
#: всё равно ставится: Android не проверяет срок годности сертификата, — но
#: пусть срок будет таким, чтобы об этом не думать.
YEARS = 30


def build(common_name: str = "Календарь дней"):
    """Возвращает пару: закрытый ключ и самоподписанный сертификат.

    Сертификат подписывает сам себя — для Android это норма: он проверяет
    только то, что обновление подписано тем же ключом, что и первая версия.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kalendar Dney"),
        ]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365 * YEARS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    password = os.environ.get("KEYSTORE_PASSWORD")
    if not password:
        print("Не задан пароль: KEYSTORE_PASSWORD=<пароль> python3 tools/make_keystore.py <файл>")
        return 2

    key, certificate = build()
    blob = pkcs12.serialize_key_and_certificates(
        name=ALIAS.encode(),
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    with open(sys.argv[1], "wb") as handle:
        handle.write(blob)
    print(f"{sys.argv[1]}: ключ готов, имя ключа внутри — {ALIAS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
