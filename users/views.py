import json
from django.http import JsonResponse
from django.views import View
from django.contrib.auth import authenticate
from .tokens import generate_access_token, generate_refresh_token, decode_token
from django.contrib.auth.models import User

# To disable the CRFS token checking. cuz we proviod our own token 
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(View):

    # POST /api/auth/login/
    # Body: {"username": "name ", "password": "pass"}

    # Returns access + refresh tokens if credentials are correct.

    def post(self, request):
        
        # paser the json data and extracr username and password

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        username = data.get('username', '')
        password = data.get('password', '')

        #    Check credentials against the database
        #    authenticate() is Django's built-in function.
        #    It hashes the password and compares it to the stored hash.
        #    Returns the User object if correct, None if wrong.
        user = authenticate(username=username, password=password)

        if user is None:
            return JsonResponse(
                {'error': 'Invalid username or password'},
                status=401
            )

        if not user.is_active:
            return JsonResponse(
                {'error': 'Account is disabled'},
                status=401
            )

        # here generate the access tokens and refresh tokens
        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)

        
        return JsonResponse({
            'access': access_token,
            'refresh': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        })

@method_decorator(csrf_exempt, name='dispatch')
class RefreshView(View):
    
    # POST /api/auth/refresh/
    # Body: {"refresh": "eyJhbGciOi..."}

    # Takes a valid refresh token and returns a NEW access token.
    # This is how the frontend stays logged in without re-entering
    # the password every 15 minutes.
    

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        refresh_token = data.get('refresh', '')

        if not refresh_token:
            return JsonResponse({'error': 'Refresh token required'}, status=400)

        # Verify the refresh token
        try:
            payload = decode_token(refresh_token)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=401)

        # Make sure it's actually a refresh token
        if payload.get('type') != 'refresh':
            return JsonResponse({'error': 'This is not a refresh token'}, status=401)

        # here we find the user
        try:
            user = User.objects.get(id=payload['user_id'])
            
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=401)

        if not user.is_active:
            return JsonResponse({'error': 'Account is disabled'}, status=401)

        # Issue a fresh access token
        new_access_token = generate_access_token(user)

        return JsonResponse({
            'access': new_access_token,
        })

class CurrentUserView(View):
    
    # GET /api/users/me/

    # Returns info about whoever is logged in.
    # The middleware already verified the token and set request.user,
    # so this view just reads it.
    

    def get(self, request):
        user = request.user  # set by the middleware

        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
        })
