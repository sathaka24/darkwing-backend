import jwt
import datetime
from django.conf import settings

def generate_access_token(user):

    """
    Create a short-lived token (15 minutes).
    This is what the frontend sends on every request.
    """
    payload = {
        'user_id': user.id,                # who this token belongs to
        'exp': datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(minutes=15),   # when it expires
        'iat': datetime.datetime.now(datetime.timezone.utc),  # when it was issued
        'type': 'access',                  # so we can tell access from refresh
    }

    # Sign the payload with our secret key
    # HMAC-SHA256 means: hash the payload + secret together.
    # Anyone can READ the payload (it's just base64), but only
    # someone with the secret can PRODUCE a valid signature.

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

    return token


def generate_refresh_token(user):
    """
    Create a long-lived token (7 days).
    Used only to get a new access token when the old one expires.
    Longer lifetime so the user doesn't have to log in every 15 minutes.
    """
    payload = {
        'user_id': user.id,
        'exp': datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(days=7),
        'iat': datetime.datetime.now(datetime.timezone.utc),
        'type': 'refresh',
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token

def decode_token(toke):

    try:
        payload = jwt.decode(toke, settings.SECRET_KEY, algorithms='HS256')
        return payload
    except jwt.ExpiredSignatureError:

        raise ValueError("Token has expired")

    except jwt.InvalidTokenError:

        raise ValueError("Invalid token")

    