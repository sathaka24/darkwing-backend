"""All the 2FA logic. Views stay thin and call into here."""

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from .models import LoginChallenge, TOTPDevice

ISSUER = "Darkwing"
CHALLENGE_LIFETIME = timedelta(minutes=5)
MAX_ATTEMPTS = 5
BACKUP_CODE_COUNT = 8


# ---------- secret encryption ----------

def _fernet():
    return Fernet(settings.TOTP_ENCRYPTION_KEY.encode())


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ---------- enrollment ----------

def user_has_2fa(user) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def start_setup(user):
    """Create (or replace an unconfirmed) secret. Returns the otpauth:// URI for the QR."""
    secret = pyotp.random_base32()
    TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_encrypted": encrypt_secret(secret),
            "confirmed": False,
            "last_used_step": 0,
            "backup_codes": [],
        },
    )
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=ISSUER)


def confirm_setup(user, code: str):
    """Check the first code. On success, turn 2FA on and return plain backup codes (shown once)."""
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None or not _check_totp(device, code):
        return None
    plain_codes = [_new_backup_code() for _ in range(BACKUP_CODE_COUNT)]
    device.backup_codes = [make_password(c) for c in plain_codes]
    device.confirmed = True
    device.confirmed_at = timezone.now()
    device.save()
    return plain_codes

def disable_2fa(user, code: str) -> bool:
    """Turn 2FA off. Needs a current app code (or a backup code) as proof."""
    with transaction.atomic():
        device = TOTPDevice.objects.select_for_update().filter(user=user, confirmed=True).first()
        if device is None:
            return True  # already off
        if not (_check_totp(device, code) or _use_backup_code(device, code)):
            return False
        device.delete()
        LoginChallenge.objects.filter(user=user).delete()
        return True

# ---------- login challenge ----------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_challenge(user) -> str:
    LoginChallenge.objects.filter(expires_at__lt=timezone.now()).delete()  # housekeeping
    token = secrets.token_urlsafe(32)
    LoginChallenge.objects.create(
        user=user,
        token_hash=_hash(token),
        expires_at=timezone.now() + CHALLENGE_LIFETIME,
    )
    return token


def verify_challenge(mfa_token: str, code: str):
    """
    Returns (user, None) on success, or (None, error_message).
    Accepts a 6-digit app code or a backup code.
    """
    with transaction.atomic():
        ch = (
            LoginChallenge.objects.select_for_update()
            .select_related("user")
            .filter(token_hash=_hash(mfa_token or ""))
            .first()
        )
        if ch is None or ch.used or ch.expires_at < timezone.now():
            return None, "Login expired. Enter your password again."
        if ch.attempts >= MAX_ATTEMPTS:
            return None, "Too many wrong codes. Enter your password again."

        ch.attempts += 1
        device = TOTPDevice.objects.select_for_update().filter(user=ch.user, confirmed=True).first()
        ok = device is not None and (_check_totp(device, code) or _use_backup_code(device, code))

        if not ok:
            ch.save(update_fields=["attempts"])
            return None, "Invalid code."

        ch.used = True
        ch.save(update_fields=["attempts", "used"])
        return ch.user, None


# ---------- code checks ----------

def _check_totp(device: TOTPDevice, code: str) -> bool:
    code = (code or "").replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    totp = pyotp.TOTP(decrypt_secret(device.secret_encrypted))
    now = int(time.time())
    for drift in (-1, 0, 1):  # tolerate ±30s clock difference
        t = now + drift * 30
        step = t // 30
        if hmac.compare_digest(totp.at(t), code):
            if step <= device.last_used_step:  # already used -> replay
                return False
            device.last_used_step = step
            device.save(update_fields=["last_used_step"])
            return True
    return False


def _new_backup_code() -> str:
    raw = secrets.token_hex(4)  # 8 hex chars
    return f"{raw[:4]}-{raw[4:]}"


def _use_backup_code(device: TOTPDevice, code: str) -> bool:
    code = (code or "").strip().lower()
    if len(code) != 9 or code[4] != "-":
        return False
    for i, hashed in enumerate(device.backup_codes):
        if check_password(code, hashed):
            del device.backup_codes[i]  # one-time use
            device.save(update_fields=["backup_codes"])
            return True
    return False