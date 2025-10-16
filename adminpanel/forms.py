from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser

# -----------------------------
# Admin Registration Form
# -----------------------------
class AdminRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_admin = True
        user.is_staff = True
        user.is_customer = False
        if commit:
            user.save()
        return user

# -----------------------------
# Admin Login Form
# -----------------------------
class AdminLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150, 
        widget=forms.TextInput(attrs={'placeholder': 'Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'})
    )
