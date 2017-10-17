from datetime import timedelta
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import update_last_login

from rest_framework import parsers, renderers, status
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import get_authorization_header

from django_rest_multitokenauth.models import MultiToken
from django_rest_multitokenauth.serializers import EmailSerializer
from django_rest_multitokenauth.signals import pre_auth, post_auth


def user_is_authenticated_helper(user):
    if callable(user.is_authenticated):
        return user.is_authenticated()
    else:
        # Starting with Django 2.0 is_authenticated is no longer a function, but a property
        return user.is_authenticated


class LogoutAndDeleteAuthToken(APIView):
    """ Custom API View for logging out"""

    def post(self, request, *args, **kwargs):
        # ToDo: Remove Support For Django 1.8 and 1.9 and use request.user.is_authenticated
        if user_is_authenticated_helper(request.user):
            # delete this users auth token
            auth_header = get_authorization_header(request)

            token = auth_header.split()[1].decode()
            tokens = MultiToken.objects.filter(key=token, user=request.user)
            if len(tokens) == 1:
                tokens.delete()
                return Response({'status': 'logged out'})
            else:
                return Response({'error': 'invalid token'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'error': 'not logged in'}, status=status.HTTP_401_UNAUTHORIZED)


class LoginAndObtainAuthToken(APIView):
    """ Custom View for logging in and getting the auth token """
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        # fire pre_auth signal
        pre_auth.send(
            sender=self.__class__,
            username=serializer.data['username'],
            password=serializer.data['password']
        )

        user = serializer.validated_data['user']

        # ToDo: Remove Support For Django 1.8 and 1.9 and use user.is_authenticated
        if user_is_authenticated_helper(user):
            update_last_login(None, user)
            token = MultiToken.objects.create(
                user=user,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                last_known_ip=request.META.get('REMOTE_ADDR', '')
            )

            # fire post_auth signal
            post_auth.send(sender=self.__class__, user=user)

            return Response({'token': token.key})
        # else:
        return Response({'error': 'not logged in'}, status=status.HTTP_401_UNAUTHORIZED)


login_and_obtain_auth_token = LoginAndObtainAuthToken.as_view()
logout_and_delete_auth_token = LogoutAndDeleteAuthToken.as_view()
