from django.http import JsonResponse
from django.contrib.auth.models import User
from .tokens import decode_token

class JWTAuthenticationMiddleware:

    """
    Intercepts every request. If the URL needs authentication,
    it checks for a valid JWT in the Authorization header.
    """

    # here we define urls that don't need token. means anyone can access them

    PUBLIC_URLS = [
        '/api/auth/login/',
        '/api/auth/refresh/',
        '/api/auth/2fa/verify/',
        '/admin/'
    ]

    def __init__(self, get_response):

        # django calls this onces when the server starts
        # get response is the next thing in the chain
        # either the next middlewear of view 

        self.get_response = get_response

    def __call__(self, request):

        # calls on every request. this is the gatekeeper

        if self._is_public(request.path):
            return self.get_response(request)

        # here we check wheather the comes requests has Authorization  header

        auth_header : str = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return JsonResponse(
                {'error': 'No token provided. Send Authorization: Bearer <token>'},
                status=401  # 401 = "you're not logged in"
            )

        token = auth_header.split(' ')[1]

        try:
            payload = decode_token(token)
        except ValueError as e:
            return JsonResponse(
                {'error': str(e)},  # "Token has expired" or "Invalid token"
                status=401
            )

        # 4. Make sure it's an ACCESS token, not a refresh token

        if payload.get('type') != 'access':
            return JsonResponse(
                {'error': 'This is not an access token'},
                status=401
            )

        # here we find the corrosponding user

        try:
            user = User.objects.get(id=payload['user_id'])
        except User.DoesNotExist:
            return JsonResponse(
                {'error': 'User not found'},
                status=401
            )

        # Check the user hasn't been deactivated
        if not user.is_active:
            return JsonResponse(
                {'error': 'Account is disabled'},
                status=401
            )

        #    Attach the user to the request so views can use it
        #    Now any view can do request.user to get the logged-in user
        request.user = user

        # Everything checks out — let the request continue to the view
        return self.get_response(request)

    def _is_public(self, path: str):

        return any(path.startswith(p) for p in self.PUBLIC_URLS)
        