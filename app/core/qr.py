"""
QR Code generation with AES-256-CBC encryption for Precosquin inscriptions.

The QR contains encrypted artist data for festival accreditation.
Only devices with the encryption key can decrypt and read the data.
"""
import base64
import hashlib
import json
import os
from datetime import datetime

import qrcode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from app.core.config import settings


EVENT_TYPE = "PC2027"
FESTIVAL_DATE = "2027-01-15"


def _get_key() -> bytes:
    """Derive a 32-byte AES key from the passphrase using SHA-256."""
    passphrase = settings.QR_ENCRYPTION_KEY.encode("utf-8")
    return hashlib.sha256(passphrase).digest()


def _encrypt(plaintext: str) -> str:
    """Encrypt plaintext with AES-256-CBC. Returns base64(IV + ciphertext)."""
    key = _get_key()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ct).decode("utf-8")


def _decrypt(encrypted_b64: str) -> str:
    """Decrypt base64(IV + ciphertext) with AES-256-CBC. Returns plaintext."""
    key = _get_key()
    raw = base64.b64decode(encrypted_b64)
    iv = raw[:16]
    ct = raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return pt.decode("utf-8")


def generate_inscription_qr(
    inscription_id: str,
    full_name: str,
    stage_name: str | None,
    dni: str | None,
    category: str,
    subcategory: str,
    status: str,
) -> str:
    """
    Generate an encrypted QR code for an inscription.

    Returns base64-encoded PNG image of the QR code.
    """
    payload = {
        "t": EVENT_TYPE,
        "id": inscription_id,
        "n": stage_name or full_name or "",
        "dni": dni or "",
        "cat": category or "",
        "sub": subcategory or "",
        "e": status or "",
        "fn": FESTIVAL_DATE,
    }

    json_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    encrypted = _encrypt(json_str)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(encrypted)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def decrypt_qr_payload(encrypted_b64: str) -> dict:
    """
    Decrypt a QR payload string and return the artist data dict.

    Raises ValueError if decryption fails or JSON is invalid.
    """
    try:
        json_str = _decrypt(encrypted_b64)
        return json.loads(json_str)
    except Exception as e:
        raise ValueError(f"QR inválido o corrupto: {str(e)}")
