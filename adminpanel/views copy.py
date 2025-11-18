from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import AdminLoginForm, AdminRegistrationForm,OfferForm
from .models import CustomUser
from django.core.paginator import Paginator
from django.db.models import Q,F
from django.views.decorators.http import require_POST
import json
from django.http import JsonResponse,HttpResponse
from category.models import Category,Brand,Occasion,Size,Color,Material,Gender
from category.forms import CategoryForm
from django.views.decorators.cache import never_cache
from cart.models import Order,OrderItem,Offer,Coupon
from products.models import ProductVariant,Product,ProductImage
from user_section.models import Wallet,WalletTransaction,Refund,ReturnRequest
from .utils import get_filtered_orders, group_orders_by_period, get_sales_summary
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import io
from django.template.loader import render_to_string
import weasyprint
from django.db import transaction
from decimal import Decimal

# -----------------------------
# Admin Registration
# -----------------------------
def admin_register(request):

    if request.user.is_authenticated and getattr(request.user, 'is_admin', False):
        return redirect('admin_dashboard')

    if request.method == 'POST':

        form = AdminRegistrationForm(request.POST)

        if form.is_valid():
            admin_user = form.save()
            messages.success(request, "Admin registered successfully. Please login.")
            return redirect('admin_login')
        else:
            print(form.errors)  
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
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Check if user exists
            try:
                user_obj = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                user_obj = None

            if user_obj is not None:
                # Authenticate using the username 
                user = authenticate(request, username=user_obj.username, password=password)

                if user is not None and user.is_admin:
                    login(request, user)
                    messages.success(request, f"Welcome {user.first_name}!")
                    return redirect('admin_dashboard')
                else:
                    messages.error(request, "Invalid password or you are not an admin user.")
            else:
                messages.error(request, "No account found with this email.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = AdminLoginForm()

    return render(request, 'adminpanel/admin_login.html', {'form': form})

# -----------------------------
# Admin Logout
# -----------------------------
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_logout(request):
    logout(request)  # destroy session
    messages.success(request, "Logged out successfully.")
    return redirect('admin_login')

# -----------------------------
# Admin Dashboard
# -----------------------------
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_dashboard(request):
    storage = messages.get_messages(request)
    storage.used = True
    total_users = CustomUser.objects.filter(is_customer=True).count()
    total_admins = CustomUser.objects.filter(is_admin=True).count()

    context = {
        'total_users': total_users,
        'total_admins': total_admins,
    }
    return render(request, 'adminpanel/admin_dashboard.html', context)
# ===============================================================
#  USER MANAGEMENT SECTION
# ===============================================================

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_users(request):
    """
    Display all *customer* users with backend search, pagination, and descending order sorting.
    """
    q = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)
    per_page = 10  # records per page

    # Only customers (exclude admins/staff)
    users = CustomUser.objects.filter(is_customer=True).order_by('-date_joined')

    #  Search 
    if q:
        users = users.filter(
            Q(first_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )

    # Pagination
    paginator = Paginator(users, per_page)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'q': q,
    }
    return render(request, 'adminpanel/admin_users.html', context)
@require_POST
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_toggle_user_status(request, user_id):
    """
    Toggle user's active/inactive status via AJAX.
    """
    try:
        user = CustomUser.objects.get(pk=user_id, is_customer=True)

        # Parse JSON safely
        data = json.loads(request.body.decode('utf-8'))

        # Convert string 'true'/'false' 
        is_active = data.get('is_active', True)
        if isinstance(is_active, str):
            is_active = is_active.lower() == 'true'

        # Update and save
        user.is_active = is_active
        user.save()

        return JsonResponse({'success': True, 'is_active': user.is_active})
    except CustomUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print("error in admin_toggle_user_status:", str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    


    
    
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_categories(request):
    q = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)

    categories = Category.objects.all().order_by('-created_at')

    if q:
        categories = categories.filter(
            Q(category_name__icontains=q) |
            Q(description__icontains=q) |
            Q(gender__name__icontains=q)
        )

    paginator = Paginator(categories, 10)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'q': q,
    }
    return render(request, 'adminpanel/admin_categories.html', context)
# Add new category
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_category_add(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Category added successfully!")
            return redirect('admin_categories')
    else:
        form = CategoryForm()
    return render(request, 'adminpanel/admin_category_form.html', {'form': form, 'is_create': True})


# Edit category
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated successfully!")
            return redirect('admin_categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'adminpanel/admin_category_form.html', {'form': form, 'is_create': False})

# Soft delete category
@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.soft_delete()
    messages.warning(request, f"Category '{category.category_name}' deleted.")
    return redirect('admin_categories')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_colors(request):
    q = request.GET.get('q', '').strip()
    colors = Color.objects.all().order_by('-id')

    if q:
        colors = colors.filter(Q(name__icontains=q))

    paginator = Paginator(colors, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'adminpanel/admin_colors.html', {'page_obj': page_obj, 'q': q})

@login_required(login_url='admin_login')
@never_cache
def admin_color_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()

        # Validation: Empty field
        if not name:
            messages.error(request, "Color name cannot be empty.")
            return redirect('admin_color_add')

        # Validation: Duplicate check (case-insensitive)
        if Color.objects.filter(name__iexact=name).exists():
            messages.warning(request, f"Color '{name}' already exists.")
            return redirect('admin_colors')

        #  Save if not duplicate
        Color.objects.create(name=name)
        messages.success(request, f"Color '{name}' added successfully.")
        return redirect('admin_colors')

    return render(request, 'adminpanel/admin_color_add.html')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_color_edit(request, pk):
    color = get_object_or_404(Color, pk=pk)
    if request.method == 'POST':
        color.name = request.POST.get('name')
        color.save()
        messages.success(request, f"Color '{color.name}' updated successfully.")
        return redirect('admin_colors')
    return render(request, 'adminpanel/admin_color_edit.html', {'color': color})

@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_color_delete(request, pk):
    color = get_object_or_404(Color, pk=pk)
    color.is_active = False
    color.save()
    messages.warning(request, f"Color '{color.name}' deleted.")
    return redirect('admin_colors')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_sizes(request):
    q = request.GET.get('q', '').strip()
    sizes = Size.objects.select_related('gender').all().order_by('-id')

    if q:
        sizes = sizes.filter(
            Q(name__icontains=q) |
            Q(gender__name__icontains=q)
        )

    paginator = Paginator(sizes, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'adminpanel/admin_sizes.html', {
        'page_obj': page_obj,
        'q': q,
    })
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_size_add(request):
    genders = Gender.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        gender_id = request.POST.get('gender')

        # Empty name check
        if not name:
            messages.error(request, "Size name cannot be empty.")
            return redirect('admin_size_add')

        # Gender validation
        if not gender_id:
            messages.error(request, "Please select a gender.")
            return redirect('admin_size_add')

        gender = get_object_or_404(Gender, id=gender_id)

        # Duplicate check — same name + same gender
        if Size.objects.filter(name__iexact=name, gender=gender).exists():
            messages.warning(request, f"Size '{name}' already exists for {gender.name}.")
            return redirect('admin_sizes')

        # Create size
        Size.objects.create(name=name, gender=gender)
        messages.success(request, f"Size '{name}' added successfully for {gender.name}.")
        return redirect('admin_sizes')

    return render(request, 'adminpanel/admin_size_add.html', {'genders': genders})

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_size_edit(request, pk):
    size = get_object_or_404(Size, pk=pk)
    genders = Gender.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        gender_id = request.POST.get('gender')

        if not name:
            messages.error(request, "Size name cannot be empty.")
            return redirect('admin_size_edit', pk=pk)

        if not gender_id:
            messages.error(request, "Please select a gender.")
            return redirect('admin_size_edit', pk=pk)

        gender = get_object_or_404(Gender, id=gender_id)

        # Duplicate check 
        if Size.objects.filter(name__iexact=name, gender=gender).exclude(pk=pk).exists():
            messages.warning(request, f"Size '{name}' already exists for {gender.name}.")
            return redirect('admin_sizes')

        size.name = name
        size.gender = gender
        size.save()
        messages.success(request, f"Size '{size.name}' updated successfully.")
        return redirect('admin_sizes')

    return render(request, 'adminpanel/admin_size_edit.html', {
        'size': size,
        'genders': genders
    })

@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_size_delete(request, pk):
    size = get_object_or_404(Size, pk=pk)
    size.is_active = False
    size.save()
    messages.warning(request, f"Size '{size.name}' deleted.")
    return redirect('admin_sizes')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_materials(request):
    q = request.GET.get('q', '').strip()
    materials = Material.objects.all().order_by('-id')

    if q:
        materials = materials.filter(Q(name__icontains=q))

    paginator = Paginator(materials, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'adminpanel/admin_materials.html', {
        'page_obj': page_obj,
        'q': q,
    })

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_material_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()

        #  Empty name check
        if not name:
            messages.error(request, "Material name cannot be empty.")
            return redirect('admin_material_add')

        # Duplicate check (case-insensitive)
        if Material.objects.filter(name__iexact=name).exists():
            messages.warning(request, f"Material '{name}' already exists.")
            return redirect('admin_materials')

        # Create new record
        Material.objects.create(name=name)
        messages.success(request, f"Material '{name}' added successfully.")
        return redirect('admin_materials')

    return render(request, 'adminpanel/admin_material_add.html')
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()

        # Empty name check
        if not name:
            messages.error(request, "Material name cannot be empty.")
            return redirect('admin_material_edit', pk=pk)

        #  Duplicate check excluding current material
        if Material.objects.filter(name__iexact=name).exclude(pk=pk).exists():
            messages.warning(request, f"Material '{name}' already exists.")
            return redirect('admin_materials')

        #  Save update
        material.name = name
        material.save()
        messages.success(request, f"Material '{material.name}' updated successfully.")
        return redirect('admin_materials')

    return render(request, 'adminpanel/admin_material_edit.html', {'material': material})

@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_material_delete(request, pk):
    material = get_object_or_404(Material, pk=pk)
    material.is_active = False
    material.save()
    messages.warning(request, f"Material '{material.name}' deleted.")
    return redirect('admin_materials')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_occasions(request):
    q = request.GET.get('q', '').strip()
    occasions = Occasion.objects.all().order_by('-id')

    if q:
        occasions = occasions.filter(Q(name__icontains=q))

    paginator = Paginator(occasions, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'adminpanel/admin_occasions.html', {
        'page_obj': page_obj,
        'q': q,
    })

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_occasion_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        Occasion.objects.create(name=name)
        messages.success(request, f"Occasion '{name}' added successfully.")
        return redirect('admin_occasions')
    return render(request, 'adminpanel/admin_occasion_add.html')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_occasion_edit(request, pk):
    occasion = get_object_or_404(Occasion, pk=pk)
    if request.method == 'POST':
        occasion.name = request.POST.get('name')
        occasion.save()
        messages.success(request, f"Occasion '{occasion.name}' updated successfully.")
        return redirect('admin_occasions')
    return render(request, 'adminpanel/admin_occasion_edit.html', {'occasion': occasion})

@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_occasion_delete(request, pk):
    occasion = get_object_or_404(Occasion, pk=pk)
    occasion.is_active = False
    occasion.save()
    messages.warning(request, f"Occasion '{occasion.name}' deleted.")
    return redirect('admin_occasions')

# ---------- BRAND LIST ----------
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_brands(request):
    q = request.GET.get('q', '').strip()
    brands = Brand.objects.all().order_by('-id')

    if q:
        brands = brands.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q)
        )

    paginator = Paginator(brands, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'adminpanel/admin_brands.html', {
        'page_obj': page_obj,
        'q': q,
    })


# ---------- ADD BRAND ----------
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_brand_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')

        Brand.objects.create(name=name, description=description)
        messages.success(request, f"Brand '{name}' added successfully.")
        return redirect('admin_brands')

    return render(request, 'adminpanel/admin_brand_add.html')


# ---------- EDIT BRAND ----------
@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_brand_edit(request, pk):
    brand = get_object_or_404(Brand, pk=pk)

    if request.method == 'POST':
        brand.name = request.POST.get('name')
        brand.description = request.POST.get('description')
        brand.save()
        messages.success(request, f"Brand '{brand.name}' updated successfully.")
        return redirect('admin_brands')

    return render(request, 'adminpanel/admin_brand_edit.html', {'brand': brand})


# ---------- DELETE BRAND (soft delete) ----------
@login_required(login_url='/adminpanel/login/')
@require_POST
@never_cache
def admin_brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    brand.delete() 
    # occasion.is_active = False
    # occasion.save()

    messages.warning(request, f"Brand '{brand.name}' deleted.")
    return redirect('admin_brands')

@login_required(login_url='/adminpanel/login/')
@never_cache
def admin_orders(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    orders = Order.objects.all().order_by('-created_at')

    if search:
        orders = orders.filter(
            Q(iorderid__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search)
        )

    if status:
        orders = orders.filter(status=status)

    paginator = Paginator(orders, 10)
    page = request.GET.get('page')
    orders = paginator.get_page(page)

    status_choices = ['Pending', 'Processing', 'Shipped', 'Out for Delivery', 'Delivered', 'Cancelled','Returned']

    return render(request, 'adminpanel/admin_orders.html', {
        'orders': orders,
        'search': search,
        'status': status,
        'status_choices': status_choices,
    })

# def update_order_status(request, order_id):
#     order = get_object_or_404(Order, id=order_id)
#     new_status = request.POST.get('status')

#     if new_status and new_status != order.status:
#         order.status = new_status
#         order.save()

#         if new_status == 'Cancelled':
#             for item in order.items.all():
#                 variant = item.variant
#                 variant.stock += item.quantity
#                 variant.save()

#         messages.success(request, f"Order {order.iorderid} updated to {new_status}.")
#     return redirect('admin_orders')

def update_order_status(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        
        if new_status and new_status != order.status:
            order.status = new_status
            order.save()
            messages.success(request, f" Order {order.iorderid} status updated to {new_status}.")
        else:
            messages.info(request, " No changes made to the order status.")

    return redirect('admin_orders')
@login_required(login_url='/adminpanel/login/')
def admin_inventory(request):
    query = request.GET.get('q') or ''          
    status = request.GET.get('status') or ''    

    variants = ProductVariant.objects.select_related('product', 'color', 'size').order_by('product__name')

    #  Apply filters
    if query:
        variants = variants.filter(
            Q(product__name__icontains=query) |
            Q(variant_name__icontains=query) |
            Q(color__name__icontains=query)|
            Q(stock__icontains=query)
        )

    if status == 'low':
        variants = variants.filter(stock__lte=F('low_stock_qty'))
    elif status == 'available':
        variants = variants.filter(stock__gt=F('low_stock_qty'))

    # Pagination
    paginator = Paginator(variants, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'variants': page_obj,
        'query': query,
        'status': status,
    }
    return render(request, 'adminpanel/admin_inventory.html', context)


# def admin_inventory(request):
#     variants = ProductVariant.objects.select_related('product', 'color', 'size').order_by('product__name')
#     return render(request, 'adminpanel/admin_inventory.html', {'variants': variants})
# def admin_inventory(request):
#     query = request.GET.get('q')  # for search
#     status = request.GET.get('status')  # for stock filter

#     variants = ProductVariant.objects.select_related('product', 'color', 'size').order_by('product__name')

#     # 🔍 Filter by search or status
#     if query:
#         variants = variants.filter(
#             Q(product__name__icontains=query) |
#             Q(variant_name__icontains=query) |
#             Q(color__name__icontains=query)
#         )

#     if status == 'low':
#         variants = variants.filter(stock__lte=models.F('low_stock_qty'))
#     elif status == 'available':
#         variants = variants.filter(stock__gt=models.F('low_stock_qty'))

#     # Pagination (10 items per page)
#     paginator = Paginator(variants, 10)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     context = {
#         'variants': page_obj,  # use page_obj in template
#         'query': query,
#         'status': status
#     }
#     return render(request, 'adminpanel/admin_inventory.html', context)

@login_required(login_url='/adminpanel/login/')
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # Fetch related order items efficiently
    order_items = (
        order.items
        .select_related('variant', 'product')
    )

    # Attach calculated fields dynamically
    for item in order_items:
        #  Correct discounted price logic
        item.final_price = float(item.price) - float(item.discount_value or 0)
        item.subtotal_after_discount = item.final_price * item.quantity

    context = {
        'order': order,
        'order_items': order_items,  # keep queryset
    }
    return render(request, 'adminpanel/admin_order_detail.html', context)


# def admin_order_detail(request, order_id):
#     # Get order for the given ID
#     order = get_object_or_404(Order, id=order_id)

#     # Fetch related order items, variants, and products
#     order_items = (
#         order.items
#         .select_related('variant', 'product')
#         .prefetch_related('variant__images')
#     )

#     # Prepare items with their primary image
#     order_item_data = []
#     for item in order_items:
#         primary_image = ProductImage.objects.filter(
#             variant=item.variant, is_primary=True
#         ).first()
#         order_item_data.append({
#             'product_name': item.product.name,
#             'variant_name': item.variant.variant_name,
#             'price': item.price,
#             'quantity': item.quantity,
#             'subtotal': item.price * item.quantity,
#             'image': primary_image.image.url if primary_image else None
#         })

#     context = {
#         'order': order,
#         'order_items': order_item_data,
#     }
#     return render(request, 'adminpanel/admin_order_detail.html', context)


@login_required(login_url='/adminpanel/login/')
def offer_list(request):
    offers = Offer.objects.all().order_by('-created_at')
    return render(request, 'adminpanel/offer_list.html', {'offers': offers})
@login_required(login_url='/adminpanel/login/')
def add_offer(request):
    if request.method == 'POST':
        form = OfferForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Offer added successfully!")
            return redirect('offer_list')
    else:
        form = OfferForm()
    context = {
        'form': form,
        'products': Product.objects.all(),
        'categories': Category.objects.select_related('gender').all(),
        'brands': Brand.objects.all(),
    }
    return render(request, 'adminpanel/offer_form.html', context)

def edit_offer(request, pk):
    offer = get_object_or_404(Offer, pk=pk)
    if request.method == 'POST':
        form = OfferForm(request.POST, instance=offer)
        if form.is_valid():
            form.save()
            messages.success(request, "Offer updated successfully!")
            return redirect('offer_list')
    else:
        form = OfferForm(instance=offer)
    context = {
        'form': form,
        'offer': offer,
        'products': Product.objects.all(),
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
    }
    return render(request, 'adminpanel/offer_form.html', context)
@login_required(login_url='/adminpanel/login/')
def delete_offer(request, pk):
    offer = get_object_or_404(Offer, pk=pk)
    
    offer.is_active = False
    offer.save(update_fields=['is_active'])
    
    messages.warning(request, f"Offer '{offer.name}' has been deactivated successfully!")
    return redirect('offer_list')
@login_required(login_url='/adminpanel/login/')
def coupons_list(request):
    coupons = Coupon.objects.all().order_by('id')
    # for c in coupons:
    #     c.status = c.status()
    return render(request, 'adminpanel/coupons.html', {'coupons': coupons})
@login_required(login_url='/adminpanel/login/')
def add_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        description = request.POST.get('description')
        coupon_type = request.POST.get('coupon_type')
        discount_value = request.POST.get('discount_value')
        min_purchase = request.POST.get('min_purchase_amount')
        valid_from = request.POST.get('valid_from')
        valid_to = request.POST.get('valid_to')
        active = request.POST.get('active') == 'on'

        # Validation 
        if not code or not discount_value or not valid_from or not valid_to:
            messages.error(request, "Please fill all required fields.")
            return redirect('admin_add_coupon')

        if Coupon.objects.filter(code=code).exists():
            messages.error(request, "Coupon code already exists!")
            return redirect('admin_add_coupon')

        Coupon.objects.create(
            code=code,
            description=description,
            coupon_type=coupon_type,
            discount_value=discount_value,
            min_purchase_amount=min_purchase or 0,
            valid_from=valid_from,
            valid_to=valid_to,
            active=active,
        )
        messages.success(request, "Coupon added successfully!")
        return redirect('admin_coupons')

    return render(request, 'adminpanel/add_coupon.html')

@login_required(login_url='/adminpanel/login/')
def edit_coupon(request, id):
    coupon = get_object_or_404(Coupon, id=id)

    if request.method == 'POST':
        coupon.code = request.POST.get('code')
        coupon.description = request.POST.get('description')
        coupon.coupon_type = request.POST.get('coupon_type')
        coupon.discount_value = request.POST.get('discount_value')
        coupon.min_purchase_amount = request.POST.get('min_purchase_amount')
        coupon.valid_from = request.POST.get('valid_from')
        coupon.valid_to = request.POST.get('valid_to')
        coupon.active = request.POST.get('active') == 'on'
        coupon.save()

        messages.success(request, "Coupon updated successfully!")
        return redirect('admin_coupons')

    return render(request, 'adminpanel/edit_coupon.html', {'coupon': coupon})

# @login_required(login_url='/adminpanel/login/')
# def delete_coupon(request, id):
#     coupon = get_object_or_404(Coupon, id=id)
#     coupon.delete()
#     messages.success(request, f"Coupon '{coupon.code}' deleted successfully!")
#     return redirect('admin_coupons')

@login_required(login_url='/adminpanel/login/')
def delete_coupon(request, id):
    coupon = get_object_or_404(Coupon, id=id)
    coupon.active = False  
    coupon.save(update_fields=['active'])  
    messages.success(request, f"Coupon '{coupon.code}' has been deactivated successfully!")
    return redirect('admin_coupons')

@login_required(login_url='/adminpanel/login/')
def sales_report(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    period = request.GET.get('period', 'day')

    qs = get_filtered_orders(start_date, end_date)
    grouped_data = group_orders_by_period(qs, period)
    summary = get_sales_summary(qs)

    return render(request, 'adminpanel/sales_report.html', {
        'grouped_data': grouped_data,
        'summary': summary,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
    })

@login_required(login_url='/adminpanel/login/')
def export_sales_excel(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    period = request.GET.get('period', 'day')

    qs = get_filtered_orders(start_date, end_date)
    data = group_orders_by_period(qs, period)

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Sales Report'

    # Header row
    headers = ['Date', 'Total Orders', 'Total Sales (₹)', 'Discount (₹)', 'Coupon (₹)', 'Delivery (₹)']
    ws.append(headers)

    # Data rows
    for row in data:
        ws.append([
            row['period'].strftime('%d-%m-%Y') if row['period'] else '',
            row['total_orders'] or 0,
            row['total_sales'] or 0,
            row['total_discount'] or 0,
            row['coupon_deduction'] or 0,
            row['delivery_charge'] or 0,
        ])

    # Auto-adjust column width
    for col in ws.columns:
        max_length = 0
        column = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[column].width = max_length + 2

    # Save to memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    # HTTP Response
    filename = f"sales_report_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# def export_sales_pdf(request):
#     start_date = request.GET.get('start_date')
#     end_date = request.GET.get('end_date')
#     period = request.GET.get('period', 'day')

#     qs = get_filtered_orders(start_date, end_date)
#     grouped_data = group_orders_by_period(qs, period)
#     summary = get_sales_summary(qs)

#     html = render(request, 'adminpanel/sales_report_pdf.html', {
#         'grouped_data': grouped_data,
#         'summary': summary,
#         'start_date': start_date,
#         'end_date': end_date,
#     })
#     pdf = weasyprint.HTML(string=html.content).write_pdf()
#     response = HttpResponse(pdf, content_type='application/pdf')
#     response['Content-Disposition'] = f'attachment; filename="sales_report.pdf"'
#     return response
@login_required(login_url='/adminpanel/login/')
def export_sales_pdf(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    period = request.GET.get('period', 'day')

    qs = get_filtered_orders(start_date, end_date)
    grouped_data = group_orders_by_period(qs, period)
    summary = get_sales_summary(qs)

    # Fallback: if no date selected, show today's date
    if not start_date:
        start_date = timezone.now().date().strftime('%d/%m/%Y')
    else:
        start_date = timezone.datetime.strptime(start_date, "%Y-%m-%d").strftime('%d/%m/%Y')

    if not end_date:
        end_date = timezone.now().date().strftime('%d/%m/%Y')
    else:
        end_date = timezone.datetime.strptime(end_date, "%Y-%m-%d").strftime('%d/%m/%Y')

    html_content = render_to_string('adminpanel/sales_report_pdf.html', {
        'grouped_data': grouped_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'period': period,
        'now': timezone.now(),
    })

    pdf = weasyprint.HTML(string=html_content).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="sales_report.pdf"'
    return response

@login_required(login_url='/adminpanel/login/')
def return_requests(request):
    """Admin view to list all return requests"""
    requests = ReturnRequest.objects.all().order_by('-created_at')
    return render(request, 'adminpanel/return_requests.html', {'requests': requests})

@login_required(login_url='/adminpanel/login/')
@transaction.atomic
def verify_return_and_refund(order_item: OrderItem, admin_user, reason=None):
    """Admin verifies a return and refunds to wallet."""
    order = order_item.order
    refund_amount = order_item.final_price * order_item.quantity

    # Ceate wallet or get existing
    wallet, _ = Wallet.objects.get_or_create(user=order.user)

    # credit refund
    wallet.balance += refund_amount
    wallet.save(update_fields=['balance'])

    #  Log transaction
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=refund_amount,
        txn_type='CREDIT',
        note=f"Refund for returned item"
    )

    #  Update order & order_item
    order_item.returned = True
    order_item.returned_at = timezone.now()
    order_item.refunded_amount = refund_amount
    order_item.save()

    order.status = 'Returned'
    order.refunded_amount += refund_amount
    order.save()

    #  Log refund in Refund model
    Refund.objects.create(
        payment=order.payments.first(),
        order=order,
        item=order_item,
        amount=refund_amount,
        reason=reason or 'Admin verified return and refunded to wallet',
        status='Completed',
        initiated_by=admin_user,
    )

    return {
        'success': True,
        'message': f"Refund ₹{refund_amount} added to {order.user.username}'s wallet."
    }
@login_required(login_url='/adminpanel/login/')
def approve_return(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    result = verify_return_and_refund(item, request.user)
    messages.success(request, result['message'])
    return redirect('admin_orders')

# adminpanel/views.py
# def verify_return_request(request, request_id):
#     rr = get_object_or_404(ReturnRequest, id=request_id)

#     action = request.GET.get('action')  

#     if rr.status != 'PENDING':
#         messages.warning(request, 'This return request was already processed.')
#         return redirect('return_requests')

#     if action == 'approve':
#         rr.status = 'Approved'
#         rr.verified_at = timezone.now()
#         rr.save()

#         # refund to wallet
#         wallet, created = Wallet.objects.get_or_create(user=rr.user)
#         refund_amount = rr.order.total_amount 
#         wallet.credit(refund_amount)

#         order_item = rr.order_item
#         order_item.status = 'Returned'
#         order_item.return_status = 'Approved'   
#         order_item.save()

#         messages.success(request, f'Return approved. ₹{refund_amount} credited to {rr.user.username} wallet.')

#     elif action == 'reject':
#         print("reject")
#         rr.status = 'Delivered'
#         rr.verified_at = timezone.now()
#         rr.save()
#         order_item = rr.order_item
#         order_item.return_status = 'Rejected'   
#         order_item.save()
#         messages.info(request, 'Return request rejected.')

#     return redirect('return_requests')



@transaction.atomic
def verify_return_request(request, rr_id):
    """Admin verifies and processes individual return requests."""
    rr = get_object_or_404(ReturnRequest, id=rr_id)
    action = request.GET.get('action')

    if action == 'approve':
        if rr.status == 'Approved':
            messages.warning(request, "This return request is already processed.")
            return redirect('return_requests')

        rr.status = 'REFUNDED'
        rr.verified_by_id = request.user.id
        rr.verified_at = timezone.now()
        rr.save()

        user = rr.requested_by
        order = rr.order
        order_item = rr.item

        total_items = order.items.count() or 1
        item_total = Decimal(order_item.final_price) * order_item.quantity
        active_items = order.items.filter(cancelled=False, returned=False)
        product_total = Decimal(order_item.final_price) * order_item.quantity

        coupon_discount = Decimal(order.coupon_discount or 0)
        coupon_share = coupon_discount / total_items

        delivery_charge_total = order.delivery_charge or Decimal('0.00')

        delivery_share = delivery_charge_total / total_items
        # --- Final refund amount ---
        refund_amount = (product_total - coupon_share) + delivery_share
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.balance += refund_amount
        wallet.save()

        # --- Log Wallet Transaction ---
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='CREDIT',
            amount=refund_amount,
            description=f"Refund for returned item "
        )

        # --- Update Order Item ---
        order_item.status = 'Returned'
        order_item.return_status = 'Approved'
        order_item.refunded_amount = refund_amount
        order_item.returned = True
        order_item.save()

        # --- Update Overall Order Status ---
        items = order.items.all()
        if all(i.status == 'Returned' for i in items):
            order.status = 'Returned'
        elif any(i.status == 'Returned' for i in items):
            order.status = 'Partially Returned'
        order.save()

        messages.success(
            request,
            f"Return approved — ₹{refund_amount:.2f} credited to {user.username}'s wallet."
        )

    elif action == 'reject':
        rr.status = 'Rejected'
        rr.verified_by_id = request.user.id
        rr.save()
        order = rr.order
        order_item = rr.item
        order_item.return_status = 'Rejected'


        messages.warning(request, "Return request rejected.")

    else:
        messages.error(request, "Invalid action.")

    return redirect('return_requests')


def verify_return_requestold(request, request_id):
    rr = get_object_or_404(ReturnRequest, id=request_id)
    action = request.GET.get('action')


    # APPROVE RETURN
    if action == 'approve':
        rr.status = 'REFUNDED'
        rr.verified_at = timezone.now()
        rr.save()

        # Refund amount to wallet
        wallet = rr.requested_by.wallet  # You already create wallet at user signup
        wallet.credit(rr.refund_amount, description=f"Refund for Order #{rr.order.iorderid}")

        # Update the order item
        order_item = rr.item
        order_item.status = 'Returned'
        order_item.return_status = 'Approved'
        order_item.save()

        messages.success(request, f"Return approved — ₹{rr.refund_amount} credited to {rr.requested_by.username}'s wallet.")

    # REJECT RETURN
    elif action == 'reject':
        rr.status = 'REJECTED'
        rr.verified_at = timezone.now()
        rr.save()

        order_item = rr.item
        order_item.return_status = 'Rejected'
        order_item.status = 'Delivered'  
        order_item.save()

        messages.info(request, f"Return request rejected for item {order_item.product.name}.")

    return redirect('return_requests')
@transaction.atomic
def admin_update_item_status(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')

        if new_status not in dict(OrderItem.STATUS_CHOICES):
            messages.error(request, "Invalid status selection.")
            return redirect('admin_order_detail', order_id=item.order.id)

        item.status = new_status
        item.save()

        # Update parent order status automatically
        order = item.order
        order.status = order.get_overall_status()
        order.save()

        messages.success(request, f"{item.product.name} status updated to {new_status}.")
    return redirect('admin_order_detail', order_id=item.order.id)

