from django.apps import AppConfig


class TwofactorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "twofactor"
    verbose_name = "Two-factor authentication"