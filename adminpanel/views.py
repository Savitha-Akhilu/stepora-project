from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import AdminLoginForm, AdminRegistrationForm
from .models import CustomUser

# -----------------------------
# Admin Registration
# -----------------------------
def admin_register(request):
    if request.user.is_authenticated and request.user.is_admin:
        return redirect('admin_dashboard')

    if request.method == 'POST':
        form = AdminRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Admin registered successfully. Please login.")
            return redirect('admin_login')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminRegistrationForm()

    return render(request, 'adminpanel/admin_register.html', {'form': form})

# -----------------------------
# Admin Login
# -----------------------------
def admin_login(request):
    if request.user.is_authenticated and request.user.is_admin:
        return redirect('admin_dashboard')

    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None and user.is_admin:
                login(request, user)  # start session
                messages.success(request, f"Welcome {user.username}!")
                return redirect('admin_dashboard')
            else:
                messages.error(request, "Invalid credentials or not an admin.")
    else:
        form = AdminLoginForm()

    return render(request, 'adminpanel/admin_login.html', {'form': form})

# -----------------------------
# Admin Logout
# -----------------------------
@login_required(login_url='admin_login')
def admin_logout(request):
    logout(request)  # destroy session
    messages.success(request, "Logged out successfully.")
    return redirect('admin_login')

# -----------------------------
# Admin Dashboard
# -----------------------------
@login_required(login_url='admin_login')
def admin_dashboard(request):
    # Optional: show some stats for admin dashboard
    total_users = CustomUser.objects.filter(is_customer=True).count()
    total_admins = CustomUser.objects.filter(is_admin=True).count()

    context = {
        'total_users': total_users,
        'total_admins': total_admins,
    }
    return render(request, 'adminpanel/adminpaneladmin_dashboard.html', context)
