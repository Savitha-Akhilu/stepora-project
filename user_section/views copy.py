from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.views import PasswordResetView
from django.core.mail import send_mail
from .forms import SignUpForm, LoginForm, OTPForm
from adminpanel.models import CustomUser
import random, time
from django.db.models import Prefetch,Q
from django.contrib.auth.hashers import make_password
from category.models import Category,Brand,Size,Material,Color,Occasion
from django.contrib.auth.decorators import login_required
from products.models import Product,ProductVariant,ProductImage
from django.http import JsonResponse
from django.conf import settings


@login_required
def redirect_after_login(request):
    user = request.user
    if user.is_staff:  # or user.is_superuser, depending on your setup
        return redirect('/adminpanel/dashboard/')
    return redirect('/users/')
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
# def signup(request):
#     if request.method == 'POST':
#         form = SignUpForm(request.POST)
#         if form.is_valid():
#             user = form.save(commit=False)
#             user.is_active = False  # deactivate until OTP verified
#             user.save()

#             # Generate OTP
#             otp = random.randint(100000, 999999)
#             OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}

#             # Send OTP via email
#             subject = 'Your OTP for Signup'
#             message = f'Hello {user.username},\n\nYour OTP is: {otp}\nIt is valid for 5 minutes.'
#             from_email = None  # Uses DEFAULT_FROM_EMAIL
#             recipient_list = [user.email]
#             send_mail(subject, message, from_email, recipient_list)

#             request.session['user_email'] = user.email
#             messages.success(request, f"OTP sent to {user.email}")
#             return redirect('verify_otp')
#     else:
#         form = SignUpForm()
#     return render(request, 'user_section/sign_up.html', {'form': form})

def signup(request):

    if request.method == 'POST':
        form = SignUpForm(request.POST)

        if form.is_valid():

            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = random.randint(100000, 999999)
            OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}

            #  sending email
            try:
                subject = 'Your OTP for Signup'
                message = f'Hello {user.username},\n\nYour OTP is: {otp}\nIt is valid for 1 minute.'
                send_mail(subject, message, None, [user.email])
            except Exception as e:
                print(" Email sending failed:", e)

            request.session['user_email'] = user.email

            messages.success(request, f"OTP sent to {user.email}")
            return redirect('verify_otp')

        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()

    return render(request, 'user_section/sign_up.html', {'form': form})
# def signup(request):

#     if request.method == 'POST':
#         form = SignUpForm(request.POST)

#         if form.is_valid():
#             user = form.save(commit=False)
#             user.is_active = False
#             user.save()

#             # Generate OTP
#             otp = random.randint(100000, 999999)
#             OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}

#             # Send OTP via email
#             try:
#                 subject = 'Your OTP for Signup'
#                 message = f'Hello {user.username},\n\nYour OTP is: {otp}\nIt is valid for 1 minute.'
#                 from_email = None  # uses DEFAULT_FROM_EMAIL
#                 recipient_list = [user.email]
#                 send_mail(subject, message, from_email, recipient_list)
#             except Exception as e:
#                 print(" Email sending failed:", e)
#             request.session['user_email'] = user.email
#             messages.success(request, f"OTP sent to {user.email}")
#             return redirect('verify_otp')

#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = SignUpForm()

#     return render(request, 'user_section/sign_up.html', {'form': form})

# Verify OTP
# def verify_otp(request):
#     email = request.session.get('user_email')
#     if not email:
#         return redirect('signup')

#     if request.method == 'POST':
#         form = OTPForm(request.POST)
#         if form.is_valid():
#             otp_input = form.cleaned_data['otp']
#             otp_data = OTP_STORE.get(email)
#             if otp_data:
#                 # Check expiry (5 minutes)
#                 if time.time() - otp_data['time'] > 300:
#                     messages.error(request, "OTP expired. Please resend.")
#                     OTP_STORE.pop(email)
#                 elif otp_data['otp'] == int(otp_input):
#                     user = CustomUser.objects.get(email=email)
#                     user.is_active = True
#                     user.save()
#                     # login(request, user)
#                     login(request, user, backend='django.contrib.auth.backends.ModelBackend')

#                     OTP_STORE.pop(email)
#                     messages.success(request, "Signup successful!")
#                     messages.success(request, "OTP verified successfully! Please log in.")
#                     return redirect('login')
#                 else:
#                     messages.error(request, "Invalid OTP")
#             else:
#                 messages.error(request, "No OTP found. Please signup again.")
#                 return redirect('signup')
#     else:
#         form = OTPForm()
#     return render(request, 'user_section/verify_otp.html', {'form': form})


def verify_otp(request):
    email = request.session.get('user_email')
    if not email:
        messages.error(request, "Session expired. Please sign up again.")
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
                    return redirect('verify_otp')

                # Correct OTP
                elif otp_data['otp'] == int(otp_input):
                    user = CustomUser.objects.get(email=email)
                    user.is_active = True
                    user.save()

                    # Login user temporarily if needed
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')

                    OTP_STORE.pop(email)
                    messages.success(request, "OTP verified successfully! Please log in.")
                    return redirect('login')

                # Wrong OTP
                else:
                    messages.error(request, "Invalid OTP. Please try again.")
                    return redirect('verify_otp')
            else:
                messages.error(request, "No OTP found. Please sign up again.")
                return redirect('signup')
    else:
        form = OTPForm()

    return render(request, 'user_section/verify_otp.html', {'form': form})
# Login using email
def user_login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            try:
                user_obj = CustomUser.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
                if user:
                    login(request, user)
                    return redirect('user_home')
                else:
                    messages.error(request, "Invalid password")
            except CustomUser.DoesNotExist:
                messages.error(request, "Email does not exist")
    else:
        form = LoginForm()
    return render(request, 'user_section/login.html', {'form': form})

# Logout
def user_logout(request):
    logout(request)
    return redirect('user_home')

# Forgot Password (Django built-in)
class CustomPasswordResetView(PasswordResetView):
    template_name = 'users/forgot_password.html'
    email_template_name = 'users/forgot_password_email.html'
    subject_template_name = 'users/forgot_password_subject.txt'
    success_url = '/users/login/'
def check_email_exists(request):
    email = request.GET.get('email', '').strip().lower()
    exists = CustomUser.objects.filter(email=email).exists()
    return JsonResponse({'exists': exists})
def check_phone(request):
    phone = request.GET.get('phone', '')
    exists = CustomUser.objects.filter(phone=phone).exists()
    return JsonResponse({'exists': exists})

def resend_otp(request):
    try:
        email = request.session.get('user_email')
        if not email:
            messages.error(request, "Session expired. Please sign up again.")
            return redirect('signup')

        # Generate new OTP
        new_otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Save OTP to user
        user = CustomUser.objects.get(email=email)
        user.otp = new_otp
        user.save()

        # Send OTP email
        send_mail(
            subject="Your Stepora Verification Code",
            message=f"Hello {user.first_name},\n\nYour new OTP is {new_otp}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        messages.success(request, "A new OTP has been sent to your email.")
        return redirect('verify_otp')

    except CustomUser.DoesNotExist:
        messages.error(request, "User not found. Please sign up again.")
        return redirect('signup')

RESET_OTP_STORE = {}  # Temporary OTP store for password reset

def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')

        try:
            user = CustomUser.objects.get(email=email)
            otp = random.randint(100000, 999999)
            RESET_OTP_STORE[email] = {'otp': otp, 'time': time.time()}

            # Send email
            send_mail(
                subject="Your Stepora Password Reset OTP",
                message=f"Hi {user.first_name or user.username},\n\nYour OTP for password reset is {otp}. It’s valid for 1 minute.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            request.session['reset_email'] = email
            messages.success(request, f"OTP sent to {email}")
            return redirect('verify_reset_otp')

        except CustomUser.DoesNotExist:
            messages.error(request, "No account found with that email.")
            return redirect('forgot_password')

    return render(request, 'user_section/forgot_password.html')


def verify_reset_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, "Session expired. Please start again.")
        return redirect('forgot_password')

    if request.method == 'POST':
        otp_input = request.POST.get('otp')
        otp_data = RESET_OTP_STORE.get(email)

        if not otp_data:
            messages.error(request, "No OTP found. Please resend.")
            return redirect('forgot_password')

        # OTP expiry (1 minute)
        if time.time() - otp_data['time'] > 60:
            messages.error(request, "OTP expired. Please resend.")
            RESET_OTP_STORE.pop(email)
            return redirect('forgot_password')

        # Check OTP
        if str(otp_data['otp']) == otp_input:
            RESET_OTP_STORE.pop(email)
            messages.success(request, "OTP verified! Set your new password.")
            return redirect('reset_password')
        else:
            messages.error(request, "Invalid OTP. Please try again.")
            return redirect('verify_reset_otp')

    return render(request, 'user_section/verify_reset_otp.html')


def reset_password(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, "Session expired. Please start again.")
        return redirect('forgot_password')

    if request.method == 'POST':
        password = request.POST.get('password')
        confirm = request.POST.get('confirm')

        if password != confirm:
            messages.error(request, "Passwords do not match.")
            return redirect('reset_password')

        user = CustomUser.objects.get(email=email)
        user.password = make_password(password)
        user.save()

        del request.session['reset_email']
        messages.success(request, "Password reset successful! Please log in.")
        return redirect('login')

    return render(request, 'user_section/reset_password.html')
# def reset_password(request):
#     #  Use the correct session key from verify_reset_otp
#     email = request.session.get('verified_reset_email')

#     if not email:
#         messages.error(request, "Session expired. Please start again.")
#         return redirect('forgot_password')

#     if request.method == 'POST':
#         password = request.POST.get('password')
#         confirm = request.POST.get('confirm')

#         if password != confirm:
#             messages.error(request, "Passwords do not match.")
#             return redirect('reset_password')

#         try:
#             user = CustomUser.objects.get(email=email)
#             user.password = make_password(password)
#             user.save()

#             #  Clear session after reset
#             del request.session['verified_reset_email']

#             messages.success(request, "Password reset successful! Please log in.")
#             return redirect('login')

#         except CustomUser.DoesNotExist:
#             messages.error(request, "User not found.")
#             return redirect('forgot_password')

#     return render(request, 'user_section/reset_password.html')



# ----- MEN COLLECTION -----
def men_collection(request):
    gender = 'Men'

    # Prefetch only active primary images for faster load
    variants = ProductVariant.objects.filter(
        product__product_type__name=gender,
        is_active=True,
        product__is_active=True
    ).prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True))
    ).select_related('product', 'color', 'size')

    # Sidebar filters
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True)
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': variants,
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
    }
    return render(request, 'user_section/men_collection.html', context)
def men_collections1(request):
    gender = 'Men'

    variants = ProductVariant.objects.filter(
        product__product_type__name=gender,
        is_active=True,
        product__is_active=True
    )

    # Sidebar filter data
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True)
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': variants,
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
    }
    return render(request, 'user_section/men_collection.html', context)


def men_collections2(request):
    gender = 'Men'
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '')

    #  Base queryset — only primary variants of Men's products
    variants = ProductVariant.objects.filter(
        product__product_type__name=gender,
        is_active=True,
        product__is_active=True,
        is_primary=True  #  show only the main (primary) variant per product
    ).select_related('product', 'color', 'size')

    #  Optional search (product or variant name)
    if q:
        variants = variants.filter(
            Q(product__name__icontains=q) |
            Q(variant_name__icontains=q)
        )

    #  Sorting logic
    if sort == 'price_low_high':
        variants = variants.order_by('price')
    elif sort == 'price_high_low':
        variants = variants.order_by('-price')
    elif sort == 'a_z':
        variants = variants.order_by('product__name')
    elif sort == 'z_a':
        variants = variants.order_by('-product__name')
    else:
        variants = variants.order_by('-id')  # default latest

    #  Prefetch only the primary image for each variant
    variants = variants.prefetch_related(
        Prefetch(
            'images',
            queryset=ProductImage.objects.filter(is_primary=True),
            to_attr='primary_image_list'
        )
    )

    #  Sidebar filter data (unchanged)
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True)
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': variants,
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
        'q': q,
        'sort': sort,
    }
    return render(request, 'user_section/men_collection.html', context)

def men_collections(request):
    gender = 'Men'
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '')
    brand_name = request.GET.get('brand', '')  
    size_name = request.GET.get('size', '') 
    occasion_name = request.GET.get('occasion', '')  
    color_name = request.GET.get('color', '')         
    material_name = request.GET.get('material', '')   
    # Fetch only variants linked to primary images
    variants = (
        ProductVariant.objects.filter(
            product__product_type__name=gender,
            product__is_active=True,
            is_active=True,
            images__is_primary=True  
        )
        .select_related('product', 'color', 'size')  # JOIN product/color/size
        .prefetch_related(
            Prefetch(
                'images',
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr='primary_image_list'
            )
        )
        .distinct()
    )
    if brand_name:
        variants = variants.filter(product__brand__name=brand_name)
    if size_name:
        variants = variants.filter(size__name=size_name)
    if occasion_name:
        variants = variants.filter(product__occasion__name=occasion_name)
    if color_name:
        variants = variants.filter(color__name=color_name)

    if material_name:
        variants = variants.filter(product__material__name=material_name)


    if q:
        variants = variants.filter(
            Q(product__name__icontains=q) |
            Q(variant_name__icontains=q)
        )

    #  Sorting
    if sort == 'price_low_high':
        variants = variants.order_by('price')
    elif sort == 'price_high_low':
        variants = variants.order_by('-price')
    elif sort == 'a_z':
        variants = variants.order_by('product__name')
    elif sort == 'z_a':
        variants = variants.order_by('-product__name')
    else:
        variants = variants.order_by('-id')

    # Sidebar filters
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True).order_by('name')
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': variants,
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
        'q': q,
        'sort': sort,
    }
    return render(request, 'user_section/men_collection.html', context)


# ----- WOMEN COLLECTION -----
def women_collection(request):
    gender = 'Women'

    variants = ProductVariant.objects.filter(
        product__product_type__name=gender,
        is_active=True,
        product__is_active=True
    )

    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True)
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': variants,
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
    }
    return render(request, 'user_section/women_collection.html', context)
# def product_detail(request, product_id):
#     product = get_object_or_404(Product, id=product_id, is_active=True)
#     variants = ProductVariant.objects.filter(product=product, is_active=True).select_related('color', 'size').prefetch_related(
#         Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_image_list')
#     )
#     images = ProductImage.objects.filter(variant__product=product).order_by('-is_primary', 'id')
#     primary_image = images.filter(is_primary=True).first()

#     context = {
#         'product': product,
#         'variants': variants,
#         'images': images,
#         'primary_image': primary_image,
#     }
#     return render(request, 'user_section/product_detail.html', context)
def product_detailold(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)

    variants = ProductVariant.objects.filter(
        product=product, is_active=True
    ).select_related('color', 'size').prefetch_related(
        Prefetch(
            'images',
            queryset=ProductImage.objects.filter(is_primary=True),
            to_attr='primary_image_list'
        )
    )

    images = ProductImage.objects.filter(variant__product=product).order_by('-is_primary', 'id')
    primary_image = images.filter(is_primary=True).first()

    unique_color_variants = {}
    for v in variants:
        if v.color and v.color.name not in unique_color_variants:
            unique_color_variants[v.color.name] = v
    color_variants = list(unique_color_variants.values())

    context = {
        'product': product,
        'variants': variants,             
        'color_variants': color_variants,
        'images': images,
        'primary_image': primary_image,
    }
    return render(request, 'user_section/product_detail.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)

    # Prefetch all images + also mark primary ones
    variants = ProductVariant.objects.filter(
        product=product, is_active=True
    ).select_related('color', 'size').prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.all(), to_attr='all_images'),
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_image_list')
    )

    # Main product image (primary if exists)
    primary_image = (
        ProductImage.objects.filter(variant__product=product, is_primary=True).first()
        or ProductImage.objects.filter(variant__product=product).first()
    )

    # Unique color list (one variant per color)
    unique_color_variants = {}
    for v in variants:
        if v.color and v.color.name not in unique_color_variants:
            unique_color_variants[v.color.name] = v
    color_variants = list(unique_color_variants.values())

    # Variant data for JS (so we can load images dynamically)
    variant_data = []
    for v in variants:
        images = [img.image.url for img in v.all_images]
        variant_data.append({
            "id": v.id,
            "color": v.color.name if v.color else "",
            "size": v.size.name if v.size else "",
            "price": v.price,
            "images": images,  
        })

    context = {
        "product": product,
        "variants": variants,
        "color_variants": color_variants,
        "variant_data": variant_data,
        "primary_image": primary_image,
    }
    return render(request, "user_section/product_detail.html", context)