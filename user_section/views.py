from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.views import PasswordResetView
from django.core.mail import send_mail
from .forms import SignUpForm, LoginForm, OTPForm
from adminpanel.models import CustomUser
import random, time
import uuid
from datetime import date, timedelta
from django.views.decorators.http import require_POST
from django.db.models import Prefetch
from django.db.models import Prefetch,Q
from django.contrib.auth.hashers import make_password
from category.models import Category,Brand,Size,Material,Color,Occasion
from django.contrib.auth.decorators import login_required
from products.models import Product,ProductVariant,ProductImage
from django.http import JsonResponse
from django.conf import settings
from decimal import Decimal
import json
from django.db.models import OuterRef, Subquery, Prefetch, Min
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.hashers import check_password
from .models import Address,Referral,Wallet,WalletTransaction
from .forms import AddressForm
from category.models import Gender
from cart.models import Order,Wishlist,Cart,Offer,Coupon,CartItem
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
from adminpanel.utils import get_best_offer_price
from django.db import transaction
from cart.views import merge_session_cart_to_db
from .utils import send_otp_email
@login_required
def redirect_after_login(request):
    user = request.user
    if user.is_staff:  
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


def signup(request):
    referral_error = None  # for displaying message below referral field

    if request.method == 'POST':
        form = SignUpForm(request.POST)

        if form.is_valid():
            referral_code = request.POST.get('referral', '').strip()
            referrer_ref = None

            #  Check referral before creating user
            if referral_code:
                try:
                    referrer_ref = Referral.objects.get(referral_code=referral_code)
                    if referrer_ref.referred_count >= 3:
                        referral_error = f"{referrer_ref.user.username} has already reached the maximum referral limit (3)."
                    # no else yet — continue if valid
                except Referral.DoesNotExist:
                    referral_error = "Invalid referral code entered."

            # If referral error found → show it below field without creating user
            if referral_error:
                return render(request, 'user_section/sign_up.html', {
                    'form': form,
                    'referral_error': referral_error
                })

            #  Create user and wallet atomically
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False
                    user.save()
                    Referral.objects.create(user=user)
                    Wallet.objects.create(user=user)

                    #  Add wallet reward if referrer exists and valid
                    if referrer_ref:
                        referrer_ref.referred_count += 1
                        referrer_ref.save()

                        referral_bonus = Decimal('50.00')
                        wallet = referrer_ref.user.wallet
                        wallet.balance += referral_bonus
                        wallet.save()

                        WalletTransaction.objects.create(
                            wallet=wallet,
                            transaction_type='CREDIT',
                            amount=referral_bonus,
                            description=f"Referral reward for referring {user.email}"
                        )

                    #  OTP logic
                    otp = random.randint(100000, 999999)
                    OTP_STORE[user.email] = {'otp': otp, 'time': time.time()}
                    send_otp_email(user.email, user.username, otp, validity_minutes=1)

                    # subject = 'Your OTP for Signup'
                    # message = f'Hello {user.username},\n\nYour OTP is: {otp}\nIt is valid for 1 minute.'
                    # send_mail(subject, message, None, [user.email])

                    request.session['user_email'] = user.email
                    messages.success(request, f"OTP sent to {user.email}")
                    return redirect('verify_otp')

            except Exception as e:
                messages.error(request, f"Signup failed: {str(e)}")
                print("Signup transaction failed:", e)

        else:
            messages.error(request, "Please correct the errors below.")

    else:
        form = SignUpForm()

    return render(request, 'user_section/sign_up.html', {'form': form})


def validate_referral(request):
    code = request.GET.get('code', '').strip()

    if not code:
        return JsonResponse({'valid': False, 'message': 'Please enter a referral code.'})

    try:
        ref = Referral.objects.get(referral_code=code)
        if ref.referred_count >= 3:
            return JsonResponse({
                'valid': False,
                'message': f"{ref.user.username} has already reached the maximum referral limit (3)."
            })
        return JsonResponse({'valid': True, 'message': f"Referral code applied successfully! Referred by {ref.user.username}."})
    except Referral.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid referral code.'})


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
            # print(otp_data)

            if otp_data:
                # Check expiry (5 minutes)
                if time.time() - otp_data['time'] > 60:
                    messages.error(request, "OTP expired. Please resend.")
                    OTP_STORE.pop(email)
                    return redirect('verify_otp')

                # Correct OTP
                elif otp_data['otp'] == int(otp_input):
                    user = CustomUser.objects.get(email=email)
                    user.is_active = True
                    user.save()

                    # # Login user temporarily if needed
                    # login(request, user, backend='django.contrib.auth.backends.ModelBackend')

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

    # return render(request, 'user_section/verify_otp.html', {'form': form})
    return render(request, 'user_section/verify_otp.html', {
    'form': form,
    'user_email': email
})

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
                    merge_session_cart_to_db(request)
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
        # user = CustomUser.objects.get(email=email)
        # user.otp = new_otp
        # user.save()
        # Save OTP in OTP_STORE instead of DB
        OTP_STORE[email] = {'otp': int(new_otp), 'time': time.time()}


        # Send OTP email
        user = CustomUser.objects.get(email=email)
        send_otp_email(user.email, user.username, new_otp, validity_minutes=1)

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
            # send_mail(
            #     subject="Your Stepora Password Reset OTP",
            #     message=f"Hi {user.first_name or user.username},\n\nYour OTP for password reset is {otp}. It’s valid for 1 minute.",
            #     from_email=settings.DEFAULT_FROM_EMAIL,
            #     recipient_list=[email],
            #     fail_silently=False,
            # )
            send_otp_email(user.email, user.username, otp, validity_minutes=1)

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

    #   to get the first active variant per product 
    first_variant_subquery = ProductVariant.objects.filter(
        product=OuterRef('pk'),
        is_active=True
    ).order_by('id').values('id')[:1]

    #  Filter all active men’s products and annotate with first_variant_id
    products = Product.objects.filter(
        product_type__name=gender,
        is_active=True
    ).annotate(
        first_variant_id=Subquery(first_variant_subquery)
    )

    #  Step 3: Get those specific variants
    variants = ProductVariant.objects.filter(
        id__in=products.values('first_variant_id'),
        product__is_active=True
    ).select_related('product', 'color', 'size').prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True))
    )
    # Apply offers
    for v in variants:
        final_price, discount_percent, offer = get_best_offer_price(v)
        v.final_price = final_price
        v.discount_percent = discount_percent
        v.has_offer = True if offer else False

    #  Step 4: Sidebar filters
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True)
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)
    # print(variants)
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


def men_collection_is_primary(request):
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

def men_collections_org(request):
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
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '')
    sort_labels = {
    'price_low_high': 'Price: Low → High',
    'price_high_low': 'Price: High → Low',
    'a_z': 'A → Z',
    'z_a': 'Z → A',
    'popularity': 'Popularity',
    'avg_rating': 'Average Rating',
    'new_arrivals': 'New Arrivals',
    'featured': 'Featured',
               }
    sort_label = sort_labels.get(sort, '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    brand_name = request.GET.get('brand', '').strip()
    size_name = request.GET.get('size', '').strip()
    occasion_name = request.GET.get('occasion', '')  
    color_name = request.GET.get('color', '')         
    material_name = request.GET.get('material', '')   
    category_id = request.GET.get('category')

    page = request.GET.get('page', 1)  # 🆕 current page

    variants = (
        ProductVariant.objects.filter(
            product__product_type__name=gender,
            product__is_active=True,
            is_active=True,
            images__is_primary=True
        )
        .select_related('product', 'color', 'size')
        .prefetch_related(
            Prefetch(
                'images',
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr='primary_image_list'
            )
        )
        .distinct()
    )
    # # Apply offers
    # for v in variants:
    #     final_price, discount_percent, offer = get_best_offer_price(v)
    #     v.final_price = final_price
    #     v.discount_percent = discount_percent
    #     v.has_offer = True if offer else False
    
    # Filters
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
    if min_price and max_price:
            variants = variants.filter(price__gte=min_price, price__lte=max_price)
    elif min_price:
            variants = variants.filter(price__gte=min_price)
    elif max_price:
            variants = variants.filter(price__lte=max_price)

    # Search
    if q:
        variants = variants.filter(
            Q(product__name__icontains=q) |
            Q(variant_name__icontains=q)
        )
    if category_id:
        variants = variants.filter(product__category_id=category_id)

    # Sorting
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

    #  Pagination
    paginator = Paginator(variants, 12)  # 12 per page
    page_obj = paginator.get_page(page)

    # Sidebar filters
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True).order_by('name')
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)

    context = {
        'variants': page_obj,  # use page_obj
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
        'q': q,
        'sort': sort,
        'sort_label': sort_label,  
        'brand_name': brand_name,
        'size_name': size_name,
        'occasion_name': occasion_name,
        'color_name': color_name,
        'material_name': material_name,
        'page_obj': page_obj,
        'min_price': min_price,
        'max_price': max_price,
        'user_authenticated': request.user.is_authenticated,

    }
    return render(request, 'user_section/women_collection.html', context)


    # q = request.GET.get('q', '').strip()
    # sort = request.GET.get('sort', '')
    # sort_labels = {
    # 'price_low_high': 'Price: Low → High',
    # 'price_high_low': 'Price: High → Low',
    # 'a_z': 'A → Z',
    # 'z_a': 'Z → A',
    # 'popularity': 'Popularity',
    # 'avg_rating': 'Average Rating',
    # 'new_arrivals': 'New Arrivals',
    # 'featured': 'Featured',
    #            }
    # sort_label = sort_labels.get(sort, '')
    # min_price = request.GET.get('min_price')
    # max_price = request.GET.get('max_price')

    # brand_name = request.GET.get('brand', '').strip()
    # size_name = request.GET.get('size', '').strip()
    # occasion_name = request.GET.get('occasion', '')  
    # color_name = request.GET.get('color', '')         
    # material_name = request.GET.get('material', '')   

    # page = request.GET.get('page', 1)  # current page

    # variants = (
    #     ProductVariant.objects.filter(
    #         product__product_type__name=gender,
    #         product__is_active=True,
    #         is_active=True,
    #         images__is_primary=True
    #     )
    #     .select_related('product', 'color', 'size')
    #     .prefetch_related(
    #         Prefetch(
    #             'images',
    #             queryset=ProductImage.objects.filter(is_primary=True),
    #             to_attr='primary_image_list'
    #         )
    #     )
    #     .distinct()
    # )

    # # Filters
    # if brand_name:
    #     variants = variants.filter(product__brand__name=brand_name)
    # if size_name:
    #     variants = variants.filter(size__name=size_name)
    # if occasion_name:
    #     variants = variants.filter(product__occasion__name=occasion_name)
    # if color_name:
    #     variants = variants.filter(color__name=color_name)
    # if material_name:
    #     variants = variants.filter(product__material__name=material_name)
    # if min_price and max_price:
    #         variants = variants.filter(price__gte=min_price, price__lte=max_price)
    # elif min_price:
    #         variants = variants.filter(price__gte=min_price)
    # elif max_price:
    #         variants = variants.filter(price__lte=max_price)

    # # Search
    # if q:
    #     variants = variants.filter(
    #         Q(product__name__icontains=q) |
    #         Q(variant_name__icontains=q)
    #     )

    # # Sorting
    # if sort == 'price_low_high':
    #     variants = variants.order_by('price')
    # elif sort == 'price_high_low':
    #     variants = variants.order_by('-price')
    # elif sort == 'a_z':
    #     variants = variants.order_by('product__name')
    # elif sort == 'z_a':
    #     variants = variants.order_by('-product__name')
    # else:
    #     variants = variants.order_by('-id')

    # #  Pagination
    # paginator = Paginator(variants, 12)  # 12 per page
    # page_obj = paginator.get_page(page)

    # # Sidebar filters
    # brands = Brand.objects.all()
    # sizes = Size.objects.filter(gender__name=gender, is_active=True).order_by('name')
    # occasions = Occasion.objects.filter(is_active=True)
    # colors = Color.objects.filter(is_active=True)
    # materials = Material.objects.filter(is_active=True)
    # categories = Category.objects.filter(gender__name=gender, is_active=True)

    # context = {
    #     'variants': page_obj,  # use page_obj
    #     'brands': brands,
    #     'sizes': sizes,
    #     'occasions': occasions,
    #     'colors': colors,
    #     'materials': materials,
    #     'categories': categories,
    #     'gender': gender,
    #     'q': q,
    #     'sort': sort,
    #     'sort_label': sort_label,  
    #     'brand_name': brand_name,
    #     'size_name': size_name,
    #     'occasion_name': occasion_name,
    #     'color_name': color_name,
    #     'material_name': material_name,
    #     'page_obj': page_obj,
    #     'min_price': min_price,
    #     'max_price': max_price,

    # }
    # return render(request, 'user_section/women_collection.html', context)

def product_detail_old(request, product_id):
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

from django.core.paginator import Paginator

def men_collections(request):
    gender = 'Men'
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '')
    sort_labels = {
    'price_low_high': 'Price: Low → High',
    'price_high_low': 'Price: High → Low',
    'a_z': 'A → Z',
    'z_a': 'Z → A',
    'popularity': 'Popularity',
    'avg_rating': 'Average Rating',
    'new_arrivals': 'New Arrivals',
    'featured': 'Featured',
               }
    sort_label = sort_labels.get(sort, '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    brand_name = request.GET.get('brand', '').strip()
    size_name = request.GET.get('size', '').strip()
    occasion_name = request.GET.get('occasion', '')  
    color_name = request.GET.get('color', '')         
    material_name = request.GET.get('material', '')   
    category_id = request.GET.get('category')

    page = request.GET.get('page', 1)  # 🆕 current page

    variants = (
        ProductVariant.objects.filter(
            product__product_type__name=gender,
            product__is_active=True,
            is_active=True,
            images__is_primary=True
        )
        .select_related('product', 'color', 'size')
        .prefetch_related(
            Prefetch(
                'images',
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr='primary_image_list'
            )
        )
        .distinct()
    )
    # # Apply offers
    # for v in variants:
    #     final_price, discount_percent, offer = get_best_offer_price(v)
    #     v.final_price = final_price
    #     v.discount_percent = discount_percent
    #     v.has_offer = True if offer else False
    
    # Filters
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
    if min_price and max_price:
            variants = variants.filter(price__gte=min_price, price__lte=max_price)
    elif min_price:
            variants = variants.filter(price__gte=min_price)
    elif max_price:
            variants = variants.filter(price__lte=max_price)

    # Search
    if q:
        variants = variants.filter(
            Q(product__name__icontains=q) |
            Q(variant_name__icontains=q)
        )
    if category_id:
        variants = variants.filter(product__category_id=category_id)

    # Sorting
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

    #  Pagination
    paginator = Paginator(variants, 12)  # 12 per page
    page_obj = paginator.get_page(page)

    from cart.utils import get_variant_image
    for v in page_obj:
        v.image_url = get_variant_image(v)


    # Sidebar filters
    brands = Brand.objects.all()
    sizes = Size.objects.filter(gender__name=gender, is_active=True).order_by('name')
    occasions = Occasion.objects.filter(is_active=True)
    colors = Color.objects.filter(is_active=True)
    materials = Material.objects.filter(is_active=True)
    categories = Category.objects.filter(gender__name=gender, is_active=True)
    wishlist_ids = []

    if request.user.is_authenticated:
        wishlist_ids = (
            Wishlist.objects.filter(user=request.user)
            .values_list('variant_id', flat=True)
        )
    context = {
        'variants': page_obj,  # use page_obj
        'brands': brands,
        'sizes': sizes,
        'occasions': occasions,
        'colors': colors,
        'materials': materials,
        'categories': categories,
        'gender': gender,
        'q': q,
        'sort': sort,
        'sort_label': sort_label,  
        'brand_name': brand_name,
        'size_name': size_name,
        'occasion_name': occasion_name,
        'color_name': color_name,
        'material_name': material_name,
        'page_obj': page_obj,
        'min_price': min_price,
        'max_price': max_price,
        'user_authenticated': request.user.is_authenticated,
        'wishlist_ids': list(wishlist_ids),


    }
    return render(request, 'user_section/men_collection.html', context)
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)

    # Fetch all variants with related color, size, and images
    variants = ProductVariant.objects.filter(
        product=product, is_active=True
    ).select_related('color', 'size').prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.all(), to_attr='all_images'),
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_image_list')
    )

    primary_image = (
        ProductImage.objects.filter(variant__product=product, is_primary=True).first()
        or ProductImage.objects.filter(variant__product=product).first()
    )
    
    if request.user.is_authenticated:
        user_wishlist_variants = Wishlist.objects.filter(user=request.user, variant__in=variants).values_list("variant_id", flat=True)
    else:
        user_wishlist_variants = []
    # Group sizes by color
    color_size_map = {}
    for v in variants:
        if not v.color:
            continue
        color_name = v.color.name
        size_name = v.size.name if v.size else ""
        if color_name not in color_size_map:
            color_size_map[color_name] = set()
        color_size_map[color_name].add(size_name)

    # Pick default color (first available)
    default_color = next(iter(color_size_map), None)
    default_sizes = list(color_size_map.get(default_color, []))

    # Unique color variants for display
    unique_color_variants = {}
    for v in variants:
        if v.color and v.color.name not in unique_color_variants:
            unique_color_variants[v.color.name] = v
    color_variants = list(unique_color_variants.values())

    # Prepare variant data for JS
    variant_data = []
    for v in variants:
        # print(v.long_description)
        images = [img.image.url for img in v.all_images]
        offer_info = v.best_offer 
        final_price = offer_info['final_price']
        discount_percent = offer_info['discount_percent']
        has_offer = offer_info['has_offer']
        discount_type=offer_info['offer_type']
        # print(discount_type)

        variant_data.append({
            "id": v.id,
            "color": v.color.name if v.color else "",
            "size": v.size.name if v.size else "",
            "price": float(v.price),
            "images": images,
            "stock": v.stock, 
            "des":v.long_description,
            "final_price": float(final_price),
            "discount_percent": discount_percent,
            "has_offer": has_offer,
            "offer_type": discount_type,
            "variant_name": v.variant_name,
            
        })

    context = {
        "product": product,
        "variants": variants,
        "color_variants": color_variants,
        "variant_data": json.dumps(variant_data),
        "primary_image": primary_image,
        "color_size_map": color_size_map,
        "default_color": default_color,
        "default_sizes": default_sizes,
        'user_authenticated': request.user.is_authenticated,
        "user_wishlist_variants": list(user_wishlist_variants),
    }

    return render(request, "user_section/product_detail.html", context)


def product_detail_old(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)

    variants = ProductVariant.objects.filter(
        product=product, is_active=True
    ).select_related('color', 'size').prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.all(), to_attr='all_images'),
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_image_list')
    )

    primary_image = (
        ProductImage.objects.filter(variant__product=product, is_primary=True).first()
        or ProductImage.objects.filter(variant__product=product).first()
    )

    # Unique color variants
    unique_color_variants = {}
    for v in variants:
        if v.color and v.color.name not in unique_color_variants:
            unique_color_variants[v.color.name] = v
    color_variants = list(unique_color_variants.values())

    # Prepare variant data and convert Decimal to float
    variant_data = []
    for v in variants:
        images = [img.image.url for img in v.all_images]
        variant_data.append({
            "id": v.id,
            "color": v.color.name if v.color else "",
            "size": v.size.name if v.size else "",
            "price": float(v.price),  # 👈 convert Decimal to float
            "images": images,
        })

    context = {
        "product": product,
        "variants": variants,
        "color_variants": color_variants,
        "variant_data": json.dumps(variant_data),
        "primary_image": primary_image,
    }
    return render(request, "user_section/product_detail.html", context)

@login_required
def user_profile(request):
    genders = Gender.objects.all()
    return render(request, 'user_section/profile.html', {'genders': genders})
@login_required
def manage_address(request):
    addresses = Address.objects.filter(user=request.user)
    return render(request, 'user_section/manage_address.html', {'addresses': addresses})
# @login_required
# def add_address(request):
#     if request.method == 'POST':
#         form = AddressForm(request.POST)
#         if form.is_valid():
#             address = form.save(commit=False)
#             address.user = request.user
#             address.save()
#             messages.success(request, 'Address added successfully!')
#             return redirect('user_address')
#     else:
#         form = AddressForm()
#     return render(request, 'user_section/add_address.html', {'form': form})

@login_required
def edit_address(request, id):
    address = get_object_or_404(Address, id=id, user=request.user)

    if request.method == "GET":
        return render(request, "user_section/edit_address.html", {"address": address})

    elif request.method == "POST":
        try:
            address.full_name = request.POST.get("full_name")
            address.mobile = request.POST.get("mobile")
            address.pincode = request.POST.get("pincode")
            address.state = request.POST.get("state")
            address.city = request.POST.get("city")
            address.locality = request.POST.get("locality")
            address.house_name = request.POST.get("house_name")
            address.address_type = request.POST.get("address_type")
            address.is_default = request.POST.get("is_default") == "on"

            # If this is default, unset others
            if address.is_default:
                Address.objects.filter(user=request.user, is_default=True).exclude(id=address.id).update(is_default=False)

            address.save()
            return JsonResponse({"status": "success"})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
# def delete_address(request, id):
#     address = get_object_or_404(Address, id=id, user=request.user)
    
#     if request.method == 'POST':  # safer: delete only via POST
#         address.delete()
#         messages.success(request, 'Address deleted successfully!')
#         return redirect('user_address')

#     # optional confirmation template
#     return render(request, 'user_section/confirm_delete.html', {'address': address})
@login_required
def delete_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    messages.success(request, "Address deleted successfully.")
    return redirect('user_address')  # redirect to your address list page
@login_required
def update_profile_image(request):
    if request.method == "POST" and request.FILES.get('profile_image'):
        user = request.user
        user.profile_image = request.FILES['profile_image']
        user.save()
        return JsonResponse({
            "status": "success",
            "image_url": user.profile_image.url
        })
    return JsonResponse({"status": "error"}, status=400)
def update_profile_info(request):
    if request.method == "POST":
        user = request.user
        user.first_name = request.POST.get('full_name')
        user.phone = request.POST.get('phone')
        user.dob = request.POST.get('dob') or None
        user.location = request.POST.get('location')
        user.alternate_phone = request.POST.get('alternate_phone')
        user.hint_name = request.POST.get('hint_name')

        gender_id = request.POST.get('gender')
        if gender_id:
            try:
                user.gender = Gender.objects.get(id=gender_id)
            except Gender.DoesNotExist:
                pass

        user.save()
        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=400)
@login_required
def add_address(request):
    if request.method == "GET":
        return render(request, "user_section/add_address.html")

    elif request.method == "POST":
        try:
            user = request.user
            full_name = request.POST.get("full_name")
            mobile = request.POST.get("mobile")
            pincode = request.POST.get("pincode")
            state = request.POST.get("state")
            city = request.POST.get("city")
            house_name = request.POST.get("house_name")
            locality = request.POST.get("locality")
            address_type = request.POST.get("address_type")
            is_default = request.POST.get("is_default") == "on"

            # If it's the first address, auto-mark as default
            if not Address.objects.filter(user=user).exists():
                is_default = True

            # If marked as default, unset previous ones
            if is_default:
                Address.objects.filter(user=user, is_default=True).update(is_default=False)

            Address.objects.create(
                user=user,
                full_name=full_name,
                mobile=mobile,
                pincode=pincode,
                state=state,
                city=city,
                house_name=house_name,
                locality=locality,
                address_type=address_type,
                is_default=is_default
            )
            next_url = request.GET.get("next")
            # print(next_url)
            if next_url:
                return JsonResponse({"status": "success", "redirect_url": next_url})
            return JsonResponse({"status": "success"})

        except Exception as e:
            print("Error:", e)
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    #  If someone opens this URL directly
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

otp_store_profile = {}

@login_required
def send_email_otp(request):
    if request.method == "POST":
        data = json.loads(request.body)
        email = data.get("email")

        # Basic email validation
        if not email or "@" not in email:
            return JsonResponse({"status": "error", "message": "Invalid email."})

        otp = str(random.randint(100000, 999999))
        otp_store_profile[request.user.id] = {"otp": otp, "email": email}

        send_mail(
            subject="Your Stepora Email Verification OTP",
            message=f"Hello {request.user.first_name},\n\nYour verification OTP is: {otp}\n\nDo not share this code.",
            from_email="noreply@stepora.com",
            recipient_list=[email],
            fail_silently=False,
        )

        return JsonResponse({"status": "sent", "message": "OTP sent successfully."})

    return JsonResponse({"status": "error", "message": "Invalid request."})


@login_required
def verify_email_otp(request):
    if request.method == "POST":
        data = json.loads(request.body)
        otp = data.get("otp")
        email = data.get("email")

        user_data = otp_store_profile.get(request.user.id)
        if not user_data:
            return JsonResponse({"status": "error", "message": "OTP expired or not requested."})

        if otp == user_data["otp"] and email == user_data["email"]:
            user = request.user
            user.email = email
            user.save()
            del otp_store_profile[request.user.id]
            return JsonResponse({"status": "verified"})
        else:
            return JsonResponse({"status": "error", "message": "Invalid OTP."})

    return JsonResponse({"status": "error", "message": "Invalid request."})


@login_required
def change_password(request):
    if request.method == "GET":
        return render(request, "user_section/change_password.html")

    elif request.method == "POST":
        user = request.user
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        # Check if current password is correct
        if not check_password(current_password, user.password):
            return JsonResponse({"status": "error", "message": "Current password is incorrect."}, status=400)

        # Validate new password match
        if new_password != confirm_password:
            return JsonResponse({"status": "error", "message": "New passwords do not match."}, status=400)

        # Optional: minimum password strength
        if len(new_password) < 6:
            return JsonResponse({"status": "error", "message": "Password must be at least 6 characters long."}, status=400)

        # Update password
        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)  # keeps user logged in

        return JsonResponse({"status": "success", "message": "Password changed successfully!"})

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)
@login_required
def my_orders(request):

    orders = (
        Order.objects.filter(user=request.user)
        .exclude(status__in=['Failed'])
        .prefetch_related('items__variant__images')
        .order_by('-created_at')
    )

    paginator = Paginator(orders, 3)
    page = request.GET.get('page')
    orders_page = paginator.get_page(page)

    for order in orders_page:
        coupon_discount = Decimal(order.coupon_discount or 0)

        # total before coupon
        order_total_price = sum(
            Decimal(i.final_price) * i.quantity for i in order.items.all()
        ) or Decimal("1.00")

        for item in order.items.all():
            # primary image
            primary_image = item.variant.images.filter(is_primary=True).first()
            item.primary_image = primary_image.image.url if primary_image else None

            # item total
            item_total = Decimal(item.final_price) * item.quantity

            # proportional coupon split
            if coupon_discount > 0:
                item_coupon = (item_total / order_total_price) * coupon_discount
            else:
                item_coupon = Decimal("0.00")

            # round
            item.coupon_share = item_coupon.quantize(Decimal("0.01"))

            # final price after coupon
            item.final_after_coupon = (item_total - item.coupon_share).quantize(Decimal("0.01"))

    return render(request, 'user_section/my_orders.html', {
        'orders': orders_page
    })

# def my_orders(request):
#     # orders = (
#     #     Order.objects.filter(user=request.user)
#     #     .prefetch_related('items__variant__images')
#     #     .order_by('-created_at')
#     # )
#     orders = (
#         Order.objects.filter(user=request.user)
#         .exclude(status__in=['Failed'])
#         .prefetch_related('items__variant__images')
#           .order_by('-created_at')
#     )
    
#     paginator = Paginator(orders, 1)
#     page = request.GET.get('page')
#     orders_page = paginator.get_page(page)

#     for order in orders_page:
#         for item in order.items.all():
#             primary_image = item.variant.images.filter(is_primary=True).first()
#             item.primary_image = primary_image.image.url if primary_image else None

#     return render(request, 'user_section/my_orders.html', {
#         'orders': orders_page
#     })
@login_required
def wishlist(request):
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('variant__product').prefetch_related(
        Prefetch('variant__images', queryset=ProductImage.objects.filter(is_primary=True))
    )    
    return render(request, 'user_section/wishlist.html', {'wishlist_items': wishlist_items})
@login_required
@require_POST
def add_to_wishlist(request, variant_id):
    variant = ProductVariant.objects.filter(id=variant_id).first()
    if not variant:
        return JsonResponse({'error': 'Variant not found'}, status=404)

    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user,
        variant=variant
    )

    if not created:
        # If already exists → remove from wishlist
        wishlist_item.delete()
        return JsonResponse({'removed': True})
    
    return JsonResponse({'success': True})
# def add_to_wishlist(request, product_id):
#     product = get_object_or_404(Product, id=product_id)
#     wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
#     if created:
#         return JsonResponse({'success': True, 'message': 'Added to wishlist!'})
#     else:
#         return JsonResponse({'success': False, 'error': 'Already in wishlist!'})

@login_required
@require_POST
def remove_from_wishlist(request, item_id):
    wishlist_item = get_object_or_404(Wishlist, id=item_id, user=request.user)
    wishlist_item.delete()
    return JsonResponse({'success': True, 'message': 'Removed from wishlist!'})

# @login_required
# @require_POST
# def move_all_to_cart(request):
#     wishlist_items = Wishlist.objects.filter(user=request.user)
#     for item in wishlist_items:
#         Cart.objects.get_or_create(user=request.user, product=item.product)
#     wishlist_items.delete()
#     return JsonResponse({'success': True, 'message': 'All items moved to cart!'})
@login_required
@require_POST
def move_all_to_cart(request):
    #  Get or create a cart for the current user
    cart, _ = Cart.objects.get_or_create(user=request.user)
    wishlist_items = Wishlist.objects.filter(user=request.user)

    moved_count = 0

    for item in wishlist_items:
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=item.variant,
            defaults={'quantity': 1}
        )
        # If already exists → increment quantity
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        moved_count += 1

    #  Clear wishlist after moving
    wishlist_items.delete()

    return JsonResponse({
        'success': True,
        'message': f'{moved_count} items moved to cart successfully!'
    })

@login_required
@require_POST
def clear_wishlist(request):
    Wishlist.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True, 'message': 'Wishlist cleared successfully!'})

def search_products(request):
    query = request.GET.get('q', '').strip()
    results = []

    if query:
        # 🔍 Search in product name OR brand name (case-insensitive)
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(brand__name__icontains=query)
        ).distinct()[:5]

        for product in products:
            # Get the first variant for this product
            variant = ProductVariant.objects.filter(product=product).first()

            # Get the primary image for that variant
            primary_image = None
            if variant:
                primary_image = ProductImage.objects.filter(
                    variant=variant,
                    is_primary=True
                ).first()

            # Fallback image if no primary one
            image_url = ''
            if primary_image and primary_image.image:
                image_url = primary_image.image.url
            elif variant:
                fallback = ProductImage.objects.filter(variant=variant).first()
                if fallback and fallback.image:
                    image_url = fallback.image.url

            # Include brand name in the result
            brand_name = product.brand.name if product.brand else ''

            results.append({
                'id': product.id,
                'name': product.name,
                'brand': brand_name,
                'image': image_url,
                'url': f"/product/{product.id}/",
            })

    return JsonResponse({'results': results})
@login_required(login_url='/login/')
def my_wallet(request):
    wallet = Wallet.objects.get(user=request.user)
    transactions = wallet.transactions.all().order_by('-created_at')

    page = request.GET.get('page', 1)   # current page
    paginator = Paginator(transactions, 10)  # 10 transactions per page
    paginated_transactions = paginator.get_page(page)

    context = {
        'wallet': wallet,
        'transactions': paginated_transactions  
    }    
    return render(request, 'user_section/my_wallet.html', context)
@login_required(login_url='/login/')
def refer_and_earn(request):
    referral = Referral.objects.get(user=request.user)
    return render(request, "user_section/refer_and_earn.html", {"referral": referral})

def get_address(request, id):
    addr = get_object_or_404(Address, id=id, user=request.user)
    return JsonResponse({
        "full_name": addr.full_name,
        "mobile": addr.mobile,
        "pincode": addr.pincode,
        "state": addr.state,
        "city": addr.city,
        "house_name": addr.house_name,
        "locality": addr.locality,
    })
@login_required(login_url='/login/')
def about_page(request):
    return render(request, 'user_section/about.html')
@login_required(login_url='/login/')
def customer_care(request):
    return render(request, 'user_section/customer_care.html')
@login_required(login_url='/login/')
def contact_page(request):
    return render(request, 'user_section/contact.html')
@login_required(login_url='/login/')
def privacy_policy(request):
    return render(request, 'user_section/privacy.html')
@login_required(login_url='/login/')
def shipping_returns(request):
    return render(request, 'user_section/shipping_returns.html')

