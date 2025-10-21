from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.views import PasswordResetView
from django.core.mail import send_mail
from .forms import SignUpForm, LoginForm, OTPForm
from adminpanel.models import CustomUser
import random, time
from products.models import Product,ProductVariant



def redirect_after_login(request):
    """Redirect user based on role and app."""
    user = request.user
    print(user)

    if user.is_authenticated:
        # Admin/staff → adminpanel dashboard
        if user.is_superuser:
            return redirect('/adminpanel/dashboard/')
        # Normal user → user home
        else:
            return redirect('/users/')
    # fallback for non-authenticated
    return redirect('/')
def user_home(request):
    # Get product variants that have a primary image
    variants = (
        ProductVariant.objects.filter(images__is_primary=True, is_active=True, product__is_active=True)
        .select_related('product')
        .prefetch_related('images')
        .order_by('-created_at')[:8]
    )

    context = {'variants': variants}
    return render(request, 'user_section/user_home.html', context)
# In-memory OTP store with timestamp
OTP_STORE = {}

# Signup with OTP
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # deactivate until OTP verified
            user.save()

            # Generate OTP
            otp = random.randint(100000, 999999)
            OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}

            # Send OTP via email
            subject = 'Your OTP for Signup'
            message = f'Hello {user.username},\n\nYour OTP is: {otp}\nIt is valid for 5 minutes.'
            from_email = None  # Uses DEFAULT_FROM_EMAIL
            recipient_list = [user.email]
            send_mail(subject, message, from_email, recipient_list)

            request.session['user_email'] = user.email
            messages.success(request, f"OTP sent to {user.email}")
            return redirect('verify_otp')
    else:
        form = SignUpForm()
    return render(request, 'user_section/sign_up.html', {'form': form})

# Verify OTP
def verify_otp(request):
    email = request.session.get('user_email')
    if not email:
        return redirect('signup')

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            otp_input = form.cleaned_data['otp']
            otp_data = OTP_STORE.get(email)
            if otp_data:
                # Check expiry (5 minutes)
                if time.time() - otp_data['time'] > 300:
                    messages.error(request, "OTP expired. Please resend.")
                    OTP_STORE.pop(email)
                elif otp_data['otp'] == int(otp_input):
                    user = CustomerUser.objects.get(email=email)
                    user.is_active = True
                    user.save()
                    login(request, user)
                    OTP_STORE.pop(email)
                    messages.success(request, "Signup successful!")
                    return redirect('home')
                else:
                    messages.error(request, "Invalid OTP")
            else:
                messages.error(request, "No OTP found. Please signup again.")
                return redirect('signup')
    else:
        form = OTPForm()
    return render(request, 'users/verify_otp.html', {'form': form})

# Resend OTP
def resend_otp(request):
    email = request.session.get('user_email')
    if not email:
        messages.error(request, "No user found to resend OTP.")
        return redirect('signup')
    try:
        user = CustomerUser.objects.get(email=email)
        otp = random.randint(100000, 999999)
        OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}

        subject = 'Your OTP for Signup'
        message = f'Hello {user.username},\n\nYour new OTP is: {otp}\nIt is valid for 5 minutes.'
        from_email = None
        recipient_list = [user.email]
        send_mail(subject, message, from_email, recipient_list)

        messages.success(request, f"New OTP sent to {user.email}")
        return redirect('verify_otp')
    except CustomerUser.DoesNotExist:
        messages.error(request, "User does not exist.")
        return redirect('signup')

# Login using email
def user_login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            try:
                user_obj = CustomerUser.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
                if user:
                    login(request, user)
                    return redirect('home')
                else:
                    messages.error(request, "Invalid password")
            except CustomerUser.DoesNotExist:
                messages.error(request, "Email does not exist")
    else:
        form = LoginForm()
    return render(request, 'user_section/login.html', {'form': form})

# Logout
def user_logout(request):
    logout(request)
    return redirect('home')

# Forgot Password (Django built-in)
class CustomPasswordResetView(PasswordResetView):
    template_name = 'users/forgot_password.html'
    email_template_name = 'users/forgot_password_email.html'
    subject_template_name = 'users/forgot_password_subject.txt'
    success_url = '/users/login/'
