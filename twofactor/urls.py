from django.urls import path

from .views import ConfirmView, DisableView, SetupView, StatusView, VerifyView

# Mounted at api/auth/2fa/ in config/urls.py
urlpatterns = [
    path("status/", StatusView.as_view(), name="2fa_status"),    # token
    path("setup/", SetupView.as_view(), name="2fa_setup"),       # token
    path("confirm/", ConfirmView.as_view(), name="2fa_confirm"), # token
    path("disable/", DisableView.as_view(), name="2fa_disable"), # token
    path("verify/", VerifyView.as_view(), name="2fa_verify"),    # PUBLIC (login step 2)
]