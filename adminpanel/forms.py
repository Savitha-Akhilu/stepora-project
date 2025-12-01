from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .models import CustomUser
from datetime import timedelta, datetime, timezone as dt_timezone
from cart.models import Offer
import re
from django.utils import timezone

class AdminRegistrationForm(UserCreationForm):
    fullname = forms.CharField(
        required=True,
        label="Full Name",
        min_length=3,
        max_length=150,
        validators=[
            RegexValidator(
                regex=r'^[A-Za-z\s]+$',
                message="Full name can only contain letters and spaces."
            )
        ],
        widget=forms.TextInput(attrs={'placeholder': 'Full Name'})
    )

    email = forms.EmailField(
        required=True,
        label="Email Address",
        widget=forms.EmailInput(attrs={'placeholder': 'Email'})
    )

    phone = forms.CharField(
        required=True,
        label="Mobile Number",
        validators=[
            RegexValidator(
                regex=r'^[6-9]\d{9}$',
                message="Enter a valid 10-digit mobile number (starting with 6–9)."
            )
        ],
        widget=forms.TextInput(attrs={'placeholder': 'Mobile Number'})
    )

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'}),
        help_text=(
            "Password must contain at least 8 characters, "
            "one uppercase letter, one lowercase letter, one number, and one special character."
        )
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
        strip=False,
    )

    class Meta:
        model = CustomUser
        fields = ('fullname', 'email', 'phone', 'password1', 'password2')


    def clean_email(self):
        """Ensure email is unique."""
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email address is already registered.")
        return email

    def clean_mobile(self):
        """Ensure mobile is unique and valid."""
        phone = self.cleaned_data.get('phone')
        if CustomUser.objects.filter(phone=phone).exists():
            raise ValidationError("This mobile number is already registered.")
        return phone

    def clean_fullname(self):
        """Ensure name is valid."""
        fullname = self.cleaned_data.get('fullname', '').strip()
        if len(fullname) < 3:
            raise ValidationError("Full name must be at least 3 characters long.")
        return fullname

    def clean_password1(self):
        """Validate password strength."""
        password = self.cleaned_data.get('password1')

        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'\d', password):
            raise ValidationError("Password must contain at least one number.")
        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
            raise ValidationError("Password must contain at least one special character.")
        return password

    def clean(self):
        """Confirm both passwords match."""
        cleaned_data = super().clean()
        pwd1 = cleaned_data.get("password1")
        pwd2 = cleaned_data.get("password2")
        if pwd1 and pwd2 and pwd1 != pwd2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        """Save admin user, using email as username."""
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['fullname']
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.username = self.cleaned_data['email']  # use email as username
        user.is_admin = True
        user.is_staff = True
        user.is_customer = False
        if commit:
            user.save()
        return user


# -----------------------------
# Admin Login Form (email-based)
# -----------------------------
class AdminLoginForm(forms.Form):
    email = forms.EmailField(
        max_length=150,
        widget=forms.EmailInput(attrs={'placeholder': 'Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'})
    )
class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            'name', 'target_type', 'target_id',
            'discount_type', 'discount_value',
            'start_at', 'end_at', 'is_active'
        ]
        widgets = {
            'start_at': forms.DateInput(attrs={
                'type': 'datetime-local', 
                'class': 'form-control',
                'id':'id_start_at',
                'required': 'required'
            },
            format='%Y-%m-%dT%H:%M'),
            
            'end_at': forms.DateInput(attrs={
                'type': 'datetime-local',  
                'class': 'form-control',
                'id':'id_end_at',
                'required': 'required'
            },format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_id'].label = "Target (Product / Category /Brand )"

    def clean(self):
        cleaned_data = super().clean()
        start_at = cleaned_data.get('start_at')
        end_at = cleaned_data.get('end_at')

        now = datetime.now(dt_timezone.utc)  # current UTC time
        tomorrow = now + timedelta(days=1)

        # Validate end date
        if start_at and end_at:
            # print(start_at)
            # print(end_at)
            if start_at >= end_at:
                self.add_error('end_at', " End date must be after start date.")
            elif (end_at - start_at).days < 3:
                self.add_error('end_at', "Offer must be valid for at least 3 days.")

        return cleaned_data
    def clean_name(self):
        name = self.cleaned_data.get('name')

        # If we are editing, exclude current instance
        offer_id = self.instance.id

        if Offer.objects.filter(name__iexact=name).exclude(id=offer_id).exists():
            raise forms.ValidationError("An offer with this name already exists.")

        return name


