from django import forms
from adminpanel.models import CustomUser


class SignUpForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your name'}),
        label="First Name"
    )
    phone = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter phone number'}),
        label="Phone"
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter Password'}),
        label="Password"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
        label="Confirm Password"
    )

    class Meta:
        model = CustomUser
        fields = ('first_name', 'email', 'phone')  

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if CustomUser.objects.filter(phone=phone).exists():
            raise forms.ValidationError("This phone number is already registered.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']  
        user.first_name = self.cleaned_data['first_name']
        user.phone = self.cleaned_data['phone']
        user.set_password(self.cleaned_data['password1'])
        user.is_customer = True  #  mark as customer

        if commit:
            user.save()
        return user


# Login Form using email
class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': 'Enter Email'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter Password'})
    )


# OTP Form
class OTPForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': 'Enter OTP'}),
        label="OTP Code"
    )

from .models import Address

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['full_name', 'house_name', 'city', 'state', 'pincode', 'country', 'is_default']

        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'house_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'House / Apartment name'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Pincode'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# from django import forms
# from adminpanel.models import CustomUser

# class SignUpForm(forms.ModelForm):
#     password1 = forms.CharField(
#         widget=forms.PasswordInput(attrs={'placeholder': 'Enter Password'}),
#         label="Password"
#     )
#     password2 = forms.CharField(
#         widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
#         label="Confirm Password"
#     )

#     class Meta:
#         model = CustomUser
#         fields = ('email', 'phone')

#     def clean_email(self):
#         email = self.cleaned_data.get('email').lower()
#         if CustomUser.objects.filter(email=email).exists():
#             raise forms.ValidationError("An account with this email already exists.")
#         return email

#     def clean(self):
#         cleaned_data = super().clean()
#         p1 = cleaned_data.get('password1')
#         p2 = cleaned_data.get('password2')
#         if p1 != p2:
#             raise forms.ValidationError("Passwords do not match.")
#         return cleaned_data

#     def save(self, commit=True):
#         user = super().save(commit=False)
#         user.username = self.cleaned_data['email']  #  use email as username
#         user.set_password(self.cleaned_data['password1'])
#         if commit:
#             user.save()
#         return user


# # Login Form using email
# class LoginForm(forms.Form):
#     email = forms.EmailField()
#     password = forms.CharField(widget=forms.PasswordInput)

# # OTP Form
# class OTPForm(forms.Form):
#     otp = forms.CharField(max_length=6)
