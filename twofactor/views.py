import base64
import json
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import services


def _body(request):
    try:
        return json.loads(request.body or b"{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)


def _qr_data_uri(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


@method_decorator(csrf_exempt, name="dispatch")
class StatusView(View):
    """GET /api/auth/2fa/status/  (token)  ->  {enabled}"""

    def get(self, request):
        return JsonResponse({"enabled": services.user_has_2fa(request.user)})


@method_decorator(csrf_exempt, name="dispatch")
class SetupView(View):
    """POST /api/auth/2fa/setup/  (token)  ->  {otpauth_uri, qr}"""

    def post(self, request):
        if services.user_has_2fa(request.user):
            # Re-enrolling would let a stolen access token swap the phone. Reset via manage.py instead.
            return JsonResponse({"error": "2FA is already enabled."}, status=409)
        uri = services.start_setup(request.user)
        return JsonResponse({"otpauth_uri": uri, "qr": _qr_data_uri(uri)})


@method_decorator(csrf_exempt, name="dispatch")
class ConfirmView(View):
    """POST /api/auth/2fa/confirm/  (token)  {code}  ->  {enabled, backup_codes}"""

    def post(self, request):
        data, err = _body(request)
        if err:
            return err
        codes = services.confirm_setup(request.user, data.get("code", ""))
        if codes is None:
            return JsonResponse({"error": "Invalid code."}, status=400)
        return JsonResponse({"enabled": True, "backup_codes": codes})

@method_decorator(csrf_exempt, name="dispatch")
class DisableView(View):
    """POST /api/auth/2fa/disable/  (token)  {password, code}  ->  {enabled: false}

    Needs BOTH the account password and a current code (or backup code),
    so a stolen session alone can't switch 2FA off.
    """

    def post(self, request):
        data, err = _body(request)
        if err:
            return err
        password = data.get("password", "")
        code = data.get("code", "")
        if not password or not code:
            return JsonResponse({"error": "password and code are required."}, status=400)
        if not request.user.check_password(password):
            return JsonResponse({"error": "Wrong password."}, status=403)
        if not services.disable_2fa(request.user, code):
            return JsonResponse({"error": "Invalid code."}, status=403)
        return JsonResponse({"enabled": False})

@method_decorator(csrf_exempt, name="dispatch")
class VerifyView(View):
    """POST /api/auth/2fa/verify/  (PUBLIC)  {mfa_token, code}  ->  {access, refresh, user}"""

    def post(self, request):
        from users.views import issue_tokens_response  # your existing login success response

        data, err = _body(request)
        if err:
            return err
        if not data.get("mfa_token") or not data.get("code"):
            return JsonResponse({"error": "mfa_token and code are required."}, status=400)

        user, error = services.verify_challenge(data["mfa_token"], data["code"])
        if user is None:
            return JsonResponse({"error": error}, status=401)
        if not user.is_active:
            return JsonResponse({"error": "Account disabled."}, status=401)
        return issue_tokens_response(user)