from django.conf import settings
from django.db import models


class TOTPDevice(models.Model):
    """One Google Authenticator registration per user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp"
    )
    # The shared secret, encrypted with TOTP_ENCRYPTION_KEY (never stored in plain text).
    secret_encrypted = models.TextField()
    # False until the user types a first valid code from the app.
    confirmed = models.BooleanField(default=False)
    # Last 30-second time step that was accepted, so a code can't be used twice.
    last_used_step = models.BigIntegerField(default=0)
    # Hashed one-time backup codes (for a lost phone).
    backup_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_totp"

    def __str__(self):
        return f"{self.user.username} ({'on' if self.confirmed else 'pending'})"


class LoginChallenge(models.Model):
    """Issued after a correct password; exchanged for real tokens once the code is right."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)  # sha256 of the mfa_token
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_challenge"