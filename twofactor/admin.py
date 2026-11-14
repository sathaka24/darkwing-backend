from django.contrib import admin

from .models import TOTPDevice


@admin.register(TOTPDevice)
class TOTPDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed", "confirmed_at")
    readonly_fields = ("user", "secret_encrypted", "last_used_step", "backup_codes", "created_at", "confirmed_at")
    # Deleting a row here = resetting that user's 2FA.