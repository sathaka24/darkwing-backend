from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from twofactor.models import LoginChallenge, TOTPDevice


class Command(BaseCommand):
    help = "Remove a user's Google Authenticator setup (e.g. lost phone)."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **opts):
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No user '{username}'")
        deleted, _ = TOTPDevice.objects.filter(user=user).delete()
        LoginChallenge.objects.filter(user=user).delete()
        msg = "2FA reset" if deleted else "User had no 2FA set up"
        self.stdout.write(self.style.SUCCESS(f"{msg} for {username}."))