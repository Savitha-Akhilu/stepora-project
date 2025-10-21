from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

class AdminSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        This method is called after successful authentication from the provider,
        but before the login is actually processed.
        """
        user = sociallogin.user

        # If user already exists, check if admin
        if user.email:
            from .models import CustomUser
            try:
                existing_user = CustomUser.objects.get(email=user.email)
                sociallogin.state['process'] = 'login'
                if existing_user.is_admin:
                    # force login
                    sociallogin.connect(request, existing_user)
            except CustomUser.DoesNotExist:
                # If user doesn't exist, you can create one or block
                messages.error(request, "This Google account is not registered as admin.")
                raise ImmediateHttpResponse(redirect('admin_login'))
