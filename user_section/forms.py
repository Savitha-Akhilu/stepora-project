from django import forms
from adminpanel.models import CustomUser

# Signup Form with password confirmation
class SignUpForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")
    
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'phone')

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 != p2:
            raise forms.ValidationError("Passwords do not match")
        return cleaned_data

# Login Form using email
class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

# OTP Form
class OTPForm(forms.Form):
    otp = forms.CharField(max_length=6)
