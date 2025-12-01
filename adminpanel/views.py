from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import AdminLoginForm, AdminRegistrationForm,OfferForm
from .models import CustomUser
from django.core.paginator import Paginator
# from django.db.models import Q,F,Sum,Case,When,Value,Count
from django.views.decorators.http import require_POST
import json
from django.http import JsonResponse,HttpResponse
from category.models import Category,Brand,Occasion,Size,Color,Material,Gender
from category.forms import CategoryForm
from django.views.decorators.cache import never_cache
from cart.models import Order,OrderItem,Offer,Coupon,Payment
from products.models import ProductVariant,Product,ProductImage
from user_section.models import Wallet,WalletTransaction,Refund,ReturnRequest,Address
from .utils import get_filtered_orders, group_orders_by_period, get_sales_summary,get_filtered_payments,group_payments_by_period
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import io
from django.template.loader import render_to_string
import weasyprint
from django.db import transaction
from decimal import Decimal
# from django.db.models.functions import TruncMonth, TruncYear
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear
from django.db.models import Sum, Count,Q, F, DecimalField, ExpressionWrapper,Case,When,Value
import random
from calendar import month_name
from datetime import datetime,timedelta
from django.core.mail import send_mail
from django.conf import settings

# -----------------------------
# Admin Registration
# -----------------------------
def admin_register(request):

    if request.user.is_authenticated and getattr(request.user, 'is_admin', False):
        return redirect('admin_dashboard')

    if request.method == 'POST':

        form = AdminRegistrationForm(request.POST)

        if form.is_valid():
            otp = random.randint(100000, 999999)
            expiry = timezone.now() + timedelta(minutes=2)
            expiry = timezone.now() + timedelta(minutes=2)
            request.session['admin_signup_otp_expiry'] = expiry.timestamp()   # Save as number

                        # Save to session
            request.session['admin_signup_data'] = form.cleaned_data
            request.session['admin_signup_otp'] = otp

            send_mail(
                "Stepora Admin – OTP Verification",
                f"Your OTP is {otp}. Valid for 2 minutes.",
                settings.EMAIL_HOST_USER,
                [form.cleaned_data["email"]],
                fail_silently=False,
            )
            messages.info(request, "OTP sent to your email.")
            return redirect('admin_signup_otp')
            # admin_user = form.save()
            # messages.success(request, "Admin registered successfully. Please login.")
            # return redirect('admin_login')
        else:
            print(form.errors)  
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminRegistrationForm()

    return render(request, 'adminpanel/admin_register.html', {'form': form})
def admin_signup_otp(request):
    expiry_ts = request.session.get("admin_signup_otp_expiry")
    expired = timezone.now().timestamp() > expiry_ts

    if request.method == "POST":
        if expired:
            return render(request, "adminpanel/admin_verify_otp.html",
                          {"expired": True})

        entered_otp = request.POST.get("otp")
        session_otp = str(request.session.get("admin_signup_otp"))

        if entered_otp == session_otp:
            data = request.session.get("admin_signup_data")
            form = AdminRegistrationForm(data)
            if form.is_valid():
                form.save()
                request.session.flush()
                return redirect("admin_login")
        else:
            return render(request, "adminpanel/admin_verify_otp.html",
                          {"error": "Invalid OTP"})

    return render(request, "adminpanel/admin_verify_otp.html",
                  {"expired": expired})


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
    total_products = Product.objects.count()

    sold_items = Order.objects.filter(
        status__in=["Delivered","Partially Returned","Partially Delivered"],
        payments__status="Success"
    )

    # Total completed orders 
    total_orders = sold_items.count()


    return render(request, "adminpanel/admin_dashboard.html", {
        "total_users": total_users,
        "total_admins": total_admins,
        "total_orders": total_orders,
        "total_products": total_products,
    })

# ===============================================================
#  USER MANAGEMENT SECTION
# ===============================================================
@login_required(login_url='/adminpanel/login/')
def top_selling_categories(request):
    filter_type = request.GET.get("filter", "yearly")

    try:
        year = int(request.GET.get("year", datetime.now().year))
    except:
        year = datetime.now().year

    try:
        month = int(request.GET.get("month")) if request.GET.get("month") else None
    except:
        month = None

    qs = OrderItem.objects.select_related(
        "product",
        "product__category",
        "product__category__gender"
    ).filter(
        status__in=["Delivered"],
        cancelled=False,
        returned=False,
        order__payments__status="Success"
    )

    if filter_type == "monthly" and month:
        qs = qs.filter(order__created_at__year=year,
                       order__created_at__month=month)
    else:
        qs = qs.filter(order__created_at__year=year)
    #    Group Results by Category + Gender
    data = qs.values(
            "product__category__category_name",
            "product__category__gender__name"
        ) \
        .annotate(total_sold=Sum("quantity")) \
        .order_by("-total_sold")[:10]
    #    Data for Chart
    labels = [f"{i['product__category__category_name']} - {i['product__category__gender__name']}" for i in data]
    units = [i["total_sold"] for i in data]

    return JsonResponse({
        "labels": labels,
        "units": units,
        "year": year,
        "month": month if filter_type == "monthly" else None
    })
def top_selling_brands(request):
    filter_type = request.GET.get("filter", "yearly")

    try:
        year = int(request.GET.get("year", datetime.now().year))
    except:
        year = datetime.now().year

    try:
        month = int(request.GET.get("month")) if request.GET.get("month") else None
    except:
        month = None

    qs = OrderItem.objects.select_related(
        "product",
        "product__brand"
    ).filter(
        status__in=["Delivered"],
        cancelled=False,
        returned=False,
        order__payments__status="Success"
    )

    if filter_type == "monthly" and month:
        qs = qs.filter(order__created_at__year=year,
                       order__created_at__month=month)
    else:
        qs = qs.filter(order__created_at__year=year)

    data = qs.values("product__brand__name") \
             .annotate(total_sold=Sum("quantity")) \
             .order_by("-total_sold")[:5]

    labels = [i["product__brand__name"] for i in data]
    units = [i["total_sold"] for i in data]

    return JsonResponse({
        "labels": labels,
        "units": units,
        "year": year,
        "month": month if filter_type == "monthly" else None
    })

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
def sales_chart_data(request):
    filter_type = request.GET.get("filter", "monthly")
    year = request.GET.get("year")

    sold_items = OrderItem.objects.filter(
        status="Delivered",
        cancelled=False,
        returned=False,
        order__payments__status="Success"
    )

    # ======================= MONTHLY ==========================
    if filter_type == "monthly":

        if year:
            year = int(year)
        else:
            year = datetime.now().year

        sold_items = sold_items.filter(order__created_at__year=year)

        grouped = (
            sold_items
            .annotate(period=TruncMonth("order__created_at"))
            .values("period")
            .annotate(total_sales=Sum(F("final_price") * F("quantity")))
            .order_by("period")
        )

        month_map = {g["period"].month: float(g["total_sales"]) for g in grouped}

        labels = [month_name[m][:3] for m in range(1, 13)]
        values = [month_map.get(m, 0) for m in range(1, 13)]

        return JsonResponse({
            "labels": labels,
            "values": values,
            "year": year
        })

    # ======================= YEARLY ==========================
    elif filter_type == "yearly":

        # All delivered & paid items already filtered above
        grouped = (
            sold_items
            .annotate(period=TruncYear("order__created_at"))
            .values("period")
            .annotate(total_sales=Sum(F("final_price") * F("quantity")))
            .order_by("period")
        )

        # Prepare year → sales mapping
        year_map = {
            g["period"].year: float(g["total_sales"])
            for g in grouped
        }

        # Generate last 10 years
        current_year = datetime.now().year
        year_list = list(range(current_year - 9, current_year + 1))

        # Labels: 10 years consistently
        labels = [str(y) for y in year_list]

        # Values: fill with 0 where no data
        values = [year_map.get(y, 0) for y in year_list]

        return JsonResponse({
            "labels": labels,
            "values": values,
            "year": f"{year_list[0]} - {year_list[-1]}"
        })
    # ============== VERY IMPORTANT: DEFAULT RETURN ==============
    return JsonResponse({"labels": [], "values": [], "year": "N/A"})

def order_stackchart_data(request):
    filter_type = request.GET.get("filter", "monthly")
    year = request.GET.get("year")

    # --------------------------- MONTHLY ----------------------------
    if filter_type == "monthly":
        year = int(year) if year else datetime.now().year

        delivered_qs = Order.objects.filter(
            status__in=["Delivered", "Partially Delivered", "Partially Returned"],
            payments__status="Success",
            created_at__year=year
        )

        returned_qs = Order.objects.filter(
            status="Returned",
            created_at__year=year
        )

        cancelled_qs = Order.objects.filter(
            status="Cancelled",
            created_at__year=year
        )

        def group(qs):
            data = qs.annotate(period=TruncMonth("created_at")) \
                     .values("period") \
                     .annotate(c=Count("id")) \
                     .order_by("period")
            return {x["period"].month: x["c"] for x in data}

        delivered_map = group(delivered_qs)
        returned_map = group(returned_qs)
        cancelled_map = group(cancelled_qs)

        labels = [month_name[m][:3] for m in range(1, 13)]

        delivered_vals = [delivered_map.get(m, 0) for m in range(1, 13)]
        returned_vals = [returned_map.get(m, 0) for m in range(1, 13)]
        cancelled_vals = [cancelled_map.get(m, 0) for m in range(1, 13)]

        return JsonResponse({
            "labels": labels,
            "delivered": delivered_vals,
            "returned": returned_vals,
            "cancelled": cancelled_vals,
            "year": year
        })

    # --------------------------- YEARLY ----------------------------
    elif filter_type == "yearly":

    # last 10 years
        current_year = datetime.now().year
        years = list(range(current_year - 9, current_year + 1))

        delivered_qs = Order.objects.filter(
            status__in=["Delivered", "Partially Delivered", "Partially Returned"],
            payments__status="Success",
            created_at__year__in=years
        )

        returned_qs = Order.objects.filter(
            status="Returned",
            created_at__year__in=years
        )

        cancelled_qs = Order.objects.filter(
            status="Cancelled",
            created_at__year__in=years
        )

        def group_year(qs):
            data = qs.annotate(period=TruncYear("created_at")) \
                    .values("period") \
                    .annotate(c=Count("id")) \
                    .order_by("period")
            return {x["period"].year: x["c"] for x in data}

        delivered_map = group_year(delivered_qs)
        returned_map = group_year(returned_qs)
        cancelled_map = group_year(cancelled_qs)

        delivered_vals = [delivered_map.get(y, 0) for y in years]
        returned_vals = [returned_map.get(y, 0) for y in years]
        cancelled_vals = [cancelled_map.get(y, 0) for y in years]

        return JsonResponse({
            "labels": years,
            "delivered": delivered_vals,
            "returned": returned_vals,
            "cancelled": cancelled_vals,
            "period": "Yearly"
        })

    # --------------------------- DEFAULT ----------------------------
    return JsonResponse({
        "labels": [],
        "delivered": [],
        "returned": [],
        "cancelled": []
    })
# def order_stackchart_data(request):
#     filter_type = request.GET.get("filter", "monthly")
#     year = request.GET.get("year")

#     if filter_type == "monthly":
#         year = int(year) if year else datetime.now().year

#         # ------------------------- QUERYSETS --------------------------

#         # 1. Delivered + Partial (Blue)
#         delivered_qs = Order.objects.filter(
#             status__in=[
#                 "Delivered",
#                 "Partially Delivered",
#                 "Partially Returned"
#             ],
#             payments__status="Success",
#             created_at__year=year
#         )

#         # 2. Returned Orders (Orange)
#         returned_qs = Order.objects.filter(
#             status="Returned",
#             created_at__year=year
#         )

#         # 3. Cancelled Orders (Red)
#         cancelled_qs = Order.objects.filter(
#             status="Cancelled",
#             created_at__year=year
#         )

#         # ------------------------- GROUPING ---------------------------

#         def group(qs):
#             data = qs.annotate(period=TruncMonth("created_at")) \
#                 .values("period") \
#                 .annotate(c=Count("id")) \
#                 .order_by("period")
#             return {x["period"].month: x["c"] for x in data}

#         delivered_map = group(delivered_qs)
#         returned_map = group(returned_qs)
#         cancelled_map = group(cancelled_qs)

#         labels = [month_name[m][:3] for m in range(1, 13)]

#         delivered_vals = [delivered_map.get(m, 0) for m in range(1, 13)]
#         returned_vals = [returned_map.get(m, 0) for m in range(1, 13)]
#         cancelled_vals = [cancelled_map.get(m, 0) for m in range(1, 13)]

#         return JsonResponse({
#             "labels": labels,
#             "delivered": delivered_vals,
#             "returned": returned_vals,
#             "cancelled": cancelled_vals,
#             "year": year
#         })

#     return JsonResponse({
#         "labels": [],
#         "delivered": [],
#         "returned": [],
#         "cancelled": []
#     })
def order_chart_data(request):
    filter_type = request.GET.get("filter", "monthly")
    year = request.GET.get("year")

    # ====================== MONTHLY ======================
    if filter_type == "monthly":
        year = int(year) if year else datetime.now().year

        # SUCCESSFUL ITEMS – group by delivered_at
        success = OrderItem.objects.filter(
            status="Delivered",
            cancelled=False,
            returned=False,
            delivered_at__year=year,
            order__payments__status="Success"
        )

        # CANCELLED ITEMS – group by order.created_at
        cancelled = OrderItem.objects.filter(
            status="Cancelled",
            cancelled=True,
            order__created_at__year=year
        )

        # RETURNED ITEMS – group by returned_at
        returned = OrderItem.objects.filter(
            status="Returned",
            returned=True,
            returned_at__year=year
        )

        def group_success(qs):
            g = qs.annotate(period=TruncMonth("delivered_at")) \
                .values("period") \
                .annotate(c=Sum("quantity")) \
                .order_by("period")
            return {x["period"].month: x["c"] for x in g}

        def group_items(qs):
            g = qs.annotate(period=TruncMonth("order__created_at")) \
                .values("period") \
                .annotate(c=Count("id")) \
                .order_by("period")
            return {x["period"].month: x["c"] for x in g}

        success_map = group_success(success)
        cancelled_map = group_items(cancelled)
        returned_map = group_items(returned)

        labels = [month_name[m][:3] for m in range(1, 13)]
        success_values = [success_map.get(m, 0) for m in range(1, 13)]
        cancelled_values = [cancelled_map.get(m, 0) for m in range(1, 13)]
        returned_values = [returned_map.get(m, 0) for m in range(1, 13)]

        return JsonResponse({
            "labels": labels,
            "success": success_values,
            "cancelled": cancelled_values,
            "returned": returned_values,
            "year": year,
            "title": "Product Order Overview"
        })

    # ====================== YEARLY ======================
    elif filter_type == "yearly":

        # SUCCESSFUL ITEMS – delivered items
        success = OrderItem.objects.filter(
            status="Delivered",
            cancelled=False,
            returned=False,
            delivered_at__isnull=False
        )

        # CANCELLED ITEMS
        cancelled = OrderItem.objects.filter(
            status="Cancelled",
            cancelled=True
        )

        # RETURNED ITEMS
        returned = OrderItem.objects.filter(
            status="Returned",
            returned=True,
            returned_at__isnull=False
        )

        def group_year_by_delivery(qs):
            g = qs.annotate(period=TruncYear("delivered_at")) \
                .values("period") \
                .annotate(c=Sum("quantity")) \
                .order_by("period")
            return {x["period"].year: x["c"] for x in g}

        def group_year(qs):
            g = qs.annotate(period=TruncYear("order__created_at")) \
                .values("period") \
                .annotate(c=Count("id")) \
                .order_by("period")
            return {x["period"].year: x["c"] for x in g}

        success_map = group_year_by_delivery(success)
        cancelled_map = group_year(cancelled)
        returned_map = group_year(returned)

        current_year = datetime.now().year
        year_list = list(range(current_year - 9, current_year + 1))

        labels = [str(y) for y in year_list]
        success_values = [success_map.get(y, 0) for y in year_list]
        cancelled_values = [cancelled_map.get(y, 0) for y in year_list]
        returned_values = [returned_map.get(y, 0) for y in year_list]

        return JsonResponse({
            "labels": labels,
            "success": success_values,
            "cancelled": cancelled_values,
            "returned": returned_values,
            "year": f"{year_list[0]} - {year_list[-1]}",
            "title": "Product Order Overview"
        })

    # fallback
    return JsonResponse({
        "labels": [],
        "success": [],
        "cancelled": [],
        "returned": [],
        "title": "Product Order Overview"
    })



def brand_pie_chart_data(request):

    # Only count REAL sold items
    sold_items = OrderItem.objects.filter(
        status="Delivered",
        cancelled=False,
        returned=False,
        order__payments__status="Success"
    )

    data = (
        sold_items
        .values("product__brand__name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")
    )

    labels = [item["product__brand__name"] for item in data]
    values = [int(item["total"]) for item in data]

    return JsonResponse({"labels": labels, "values": values})


def top_selling_products_chart(request):
    filter_type = request.GET.get("filter", "yearly")

    # Safe year conversion
    year_param = request.GET.get("year")
    try:
        year = int(year_param) if year_param else datetime.now().year
    except ValueError:
        year = datetime.now().year

    # Safe month conversion
    month_param = request.GET.get("month")
    try:
        month = int(month_param) if month_param else None
    except ValueError:
        month = None

    qs = OrderItem.objects.select_related("product")

    # Monthly filter
    if filter_type == "monthly" and month:
        qs = qs.filter(order__created_at__year=year,
                       order__created_at__month=month)
    else:  # Yearly
        qs = qs.filter(order__created_at__year=year)

    data = (
        qs.values("product__name")
          .annotate(units=Sum("quantity"))
          .order_by("-units")[:10]
    )

    labels = [item["product__name"] for item in data]
    units = [item["units"] for item in data]


    return JsonResponse({"labels": labels, "units": units,"year": year,"month": month if filter_type == "monthly" else None})

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
            return redirect('admin_color_add')

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
            return redirect('admin_size_add')

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
            return redirect('admin_size_edit')

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
            return redirect('admin_material_add')

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
    address = None
    if order.address_id:
        try:
            address = Address.objects.get(id=order.address_id)
        except Address.DoesNotExist:
            address = None
    

    context = {
        'order': order,
        'order_items': order_items,  
                'address': address,   
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

    paginator = Paginator(offers, 10)  # 10 offers per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/offer_list.html', {
        'page_obj': page_obj
    })
# def offer_list(request):
#     offers = Offer.objects.all().order_by('-created_at')
#     return render(request, 'adminpanel/offer_list.html', {'offers': offers})
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
    paginator = Paginator(coupons, 10)   
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/coupons.html', {
        'page_obj': page_obj
    })
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
def check_coupon(request):
    code = request.GET.get("code", "")
    exclude_id = request.GET.get("exclude_id")

    qs = Coupon.objects.filter(code__iexact=code)

    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    return JsonResponse({"exists": qs.exists()})


@login_required(login_url='/adminpanel/login/')
def edit_coupon(request, id):
    coupon = get_object_or_404(Coupon, id=id)

    if request.method == 'POST':
        coupon.code = request.POST.get('code')
        new_code = request.POST.get('code')
        if Coupon.objects.filter(code=new_code).exclude(id=id).exists():
            messages.error(request, "A coupon with this code already exists!")
            return redirect('admin_edit_coupon', id=id)
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
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    period = request.GET.get("period", "day")

    if start_date in (None, "", "None"):
        start_date = None
    if end_date in (None, "", "None"):
        end_date = None


    period_map = {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
        "year": TruncYear,
    }
    trunc = period_map.get(period, TruncDay)

    # 1) GET VALID ORDERS
    valid_orders = Order.objects.filter(
        status__in=["Delivered", "Partially Returned", "Partially Delivered"],
        payments__status="Success",
    )

    if start_date:
        valid_orders = valid_orders.filter(created_at__date__gte=start_date)
    if end_date:
        valid_orders = valid_orders.filter(created_at__date__lte=end_date)

    # 2) GET VALID ITEMS
    valid_items = OrderItem.objects.filter(
        order_id__in=valid_orders.values("id"),
        status="Delivered",
        cancelled=False,
        returned=False,
    )

    # 3) GROUPED ORDERS
    grouped_orders = (
        valid_orders
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(
            total_orders=Count("id"),
            delivery_charge=Sum("delivery_charge"),
            coupon_deduction=Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
        )
        .order_by("period")
    )

    total_coupon_summary = Decimal("0.00")

    # 4) COUPON CALCULATION (FIXED FOR ALL PERIODS)
    for row in grouped_orders:
        period_date = row["period"]

        # DAILY
        if period == "day":
            orders_in_period = valid_orders.filter(
                created_at__date=period_date.date()
            )

        # WEEKLY (7-day range)
        elif period == "week":
            start = period_date.date()
            end = (period_date + timedelta(days=7)).date()

            orders_in_period = valid_orders.filter(
                created_at__date__gte=start,
                created_at__date__lt=end
            )

        # MONTHLY
        elif period == "month":
            start = period_date.date()

            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)

            orders_in_period = valid_orders.filter(
                created_at__date__gte=start,
                created_at__date__lt=end
            )

        # YEARLY
        elif period == "year":
            start = period_date.date()
            end = start.replace(year=start.year + 1)

            orders_in_period = valid_orders.filter(
                created_at__date__gte=start,
                created_at__date__lt=end
            )

        period_coupon = Decimal("0.00")

        # CALCULATE COUPON FOR THIS PERIOD
        for order in orders_in_period:
            items = order.items.all()

            order_total = sum(i.final_price * i.quantity for i in items)
            delivered_total = sum(
                i.final_price * i.quantity
                for i in items
                if i.status == "Delivered" and not i.cancelled and not i.returned
            )

            order_coupon = Decimal(order.coupon_discount or 0)

            if order_total > 0:
                delivered_coupon = (delivered_total / order_total) * order_coupon
            else:
                delivered_coupon = Decimal("0.00")

            period_coupon += delivered_coupon
            total_coupon_summary += delivered_coupon

        row["coupon_deduction"] = round(period_coupon, 2)

    # 5) SALES & DISCOUNT SUMMARY
    sales_map = (
        valid_items
        .annotate(period=trunc("order__created_at"))
        .values("period")
        .annotate(
            total_sales=Sum(F("final_price") * F("quantity")),
            total_discount=Sum("discount_value")
        )
    )

    sales_dict = {s["period"]: s for s in sales_map}

    for row in grouped_orders:
        p = row["period"]
        row["total_sales"] = sales_dict.get(p, {}).get("total_sales", 0)
        row["total_discount"] = sales_dict.get(p, {}).get("total_discount", 0)

    # 6) SUMMARY TOTALS
    summary = {
        "total_orders": valid_orders.count(),
        "total_sales": valid_items.aggregate(s=Sum(F("final_price") * F("quantity")))["s"] or 0,
        "total_discount": valid_items.aggregate(s=Sum("discount_value"))["s"] or 0,
        "total_delivery": valid_orders.aggregate(s=Sum("delivery_charge"))["s"] or 0,
        "total_coupon": round(total_coupon_summary, 2),
    }
    summary["total_revenue"] = (
        summary["total_sales"] - summary["total_coupon"] + summary["total_delivery"]
    )
    # PAGINATION
    page_number = request.GET.get("page")
    paginator = Paginator(grouped_orders, 10)
    page_obj = paginator.get_page(page_number)

    return render(request, "adminpanel/sales_report.html", {
        "grouped_data": page_obj,
        "page_obj": page_obj,
        "summary": summary,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
    })

def sales_report_org(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    period = request.GET.get("period", "day")
    if start_date in (None, "", "None"):
        start_date = None
    if end_date in (None, "", "None"):
        end_date = None

    period_map = {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
        "year": TruncYear,
    }
    trunc = period_map.get(period, TruncDay)

    # ------------------------------
    # 1) GET VALID ORDERS
    # ------------------------------
    valid_orders = Order.objects.filter(
        status__in=["Delivered", "Partially Returned","Partially Delivered"],
        payments__status="Success",
    )

    if start_date:
        valid_orders = valid_orders.filter(created_at__date__gte=start_date)
    if end_date:
        valid_orders = valid_orders.filter(created_at__date__lte=end_date)

    # ------------------------------
    # 2) GET VALID ORDER ITEMS
    # ------------------------------
    valid_items = OrderItem.objects.filter(
        order_id__in=valid_orders.values("id"),
        status="Delivered",
        cancelled=False,
        returned=False,
    )

    # ------------------------------
    # 3) GROUPED DATA (USING ORDERS)
    # ------------------------------
    grouped_orders = (
        valid_orders
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(
            total_orders=Count("id"),
            delivery_charge=Sum("delivery_charge"),
            # coupon_deduction=Sum("coupon_discount"),
            coupon_deduction = Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))

        )
        .order_by("period")
    )
    

    total_coupon_summary = Decimal("0.00")

    for row in grouped_orders:
        period_date = row["period"]
        
        orders_in_period = valid_orders.filter(created_at__date=period_date.date())

        period_coupon = Decimal("0.00")

        for order in orders_in_period:
            items = order.items.all()

            order_total = sum(i.final_price * i.quantity for i in items)
            delivered_total = sum(
                i.final_price * i.quantity
                for i in items
                if i.status == "Delivered" and not i.cancelled and not i.returned
            )

            order_coupon = Decimal(order.coupon_discount or 0)

            if order_total > 0:
                delivered_coupon = (delivered_total / order_total) * order_coupon
            else:
                delivered_coupon = Decimal("0.00")

            period_coupon += delivered_coupon
            total_coupon_summary += delivered_coupon

        row["coupon_deduction"] = round(period_coupon, 2)


    # ------------------------------
    # 4) ADD SALES & DISCOUNT PER PERIOD FROM ITEMS
    # ------------------------------
    sales_map = (
        valid_items
        .annotate(period=trunc("order__created_at"))
        .values("period")
        .annotate(
            total_sales=Sum(F("final_price") * F("quantity")),
            total_discount=Sum("discount_value")
        )
    )

    # Convert item sales to dict for easy merge
    sales_dict = {s["period"]: s for s in sales_map}

    # Merge item-sales into grouped orders
    for row in grouped_orders:
        p = row["period"]
        row["total_sales"] = sales_dict.get(p, {}).get("total_sales", 0)
        row["total_discount"] = sales_dict.get(p, {}).get("total_discount", 0)

    # ------------------------------
    # SUMMARY
    # ------------------------------
    summary = {
        "total_orders": valid_orders.count(),
        "total_sales": valid_items.aggregate(s=Sum(F("final_price") * F("quantity")))["s"] or 0,
        "total_discount": valid_items.aggregate(s=Sum("discount_value"))["s"] or 0,
        # "total_coupon": valid_orders.aggregate(s=Sum("coupon_discount"))["s"] or 0,
        "total_delivery": valid_orders.aggregate(s=Sum("delivery_charge"))["s"] or 0,
        # "total_coupon": total_coupon_summary,
        "total_coupon": round(total_coupon_summary, 2),


    }
    # PAGINATION
    page_number = request.GET.get("page")
    paginator = Paginator(grouped_orders, 10)  # 10 rows per page
    page_obj = paginator.get_page(page_number)

    return render(request, "adminpanel/sales_report.html", {
        # "grouped_data": grouped_orders,
        "grouped_data": page_obj,
        "page_obj": page_obj,
        "summary": summary,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
    })


@login_required(login_url='/adminpanel/login/')
def export_sales_excel_withoutrevenue(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    period = request.GET.get("period", "day")

    # Convert None values
    if start_date in (None, "", "None"):
        start_date = None
    if end_date in (None, "", "None"):
        end_date = None

    # SAME FILTER AS DASHBOARD
    sold_items = OrderItem.objects.filter(
        status="Delivered",
        cancelled=False,
        returned=False,
        order__payments__status="Success"
    )

    if start_date:
        sold_items = sold_items.filter(order__created_at__date__gte=start_date)
    if end_date:
        sold_items = sold_items.filter(order__created_at__date__lte=end_date)

    # PERIOD GROUPING
    period_map = {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
        "year": TruncYear,
    }
    trunc = period_map.get(period, TruncDay)

    grouped = (
        sold_items
        .annotate(period=trunc("order__created_at"))
        .values("period")
        .annotate(
            total_orders=Count("order_id", distinct=True),
            total_sales=Sum(F("final_price") * F("quantity")),
            total_discount=Sum("discount_value"),
            coupon_deduction=Sum("order__coupon_discount", distinct=True),
            delivery_charge=Sum("order__delivery_charge", distinct=True),
        )
        .order_by("period")
    )

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Sales Report'

    # Header row
    headers = ['Date', 'Total Orders', 'Total Sales (₹)', 'Discount (₹)', 'Coupon (₹)', 'Delivery (₹)']
    ws.append(headers)

    # Data rows
    for row in grouped:
        ws.append([
            row["period"].strftime("%d-%m-%Y") if row["period"] else "",
            row["total_orders"] or 0,
            float(row["total_sales"] or 0),
            float(row["total_discount"] or 0),
            float(row["coupon_deduction"] or 0),
            float(row["delivery_charge"] or 0),
        ])

    # Auto-adjust column width
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value) if cell.value is not None else ""
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max_len + 2

    # Save to memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    # Return response
    filename = f"sales_report_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response



def export_sales_excel(request):
    from decimal import Decimal

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    period = request.GET.get("period", "day")

    # Convert None values
    if start_date in (None, "", "None"):
        start_date = None
    if end_date in (None, "", "None"):
        end_date = None

    # SAME FILTER AS PDF
    valid_orders = Order.objects.filter(
        status__in=["Delivered", "Partially Returned", "Partially Delivered"],
        payments__status="Success",
    )

    if start_date:
        valid_orders = valid_orders.filter(created_at__date__gte=start_date)
    if end_date:
        valid_orders = valid_orders.filter(created_at__date__lte=end_date)

    valid_items = OrderItem.objects.filter(
        order_id__in=valid_orders.values("id"),
        status="Delivered",
        cancelled=False,
        returned=False,
    )

    # PERIOD GROUPING
    period_map = {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
        "year": TruncYear,
    }
    trunc = period_map.get(period, TruncDay)

    grouped_orders = (
        valid_orders.annotate(period=trunc("created_at"))
        .values("period")
        .annotate(
            total_orders=Count("id"),
            delivery_charge=Sum("delivery_charge"),
            coupon_deduction=Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
        )
        .order_by("period")
    )

    # ---- COUPON PROPORTION LOGIC (SAME AS PDF) ----
    for row in grouped_orders:
        period_date = row["period"]
        orders_in_period = valid_orders.filter(created_at__date=period_date.date())

        period_coupon = Decimal("0.00")

        for order in orders_in_period:
            items = order.items.all()
            order_total = sum(i.final_price * i.quantity for i in items)

            delivered_total = sum(
                i.final_price * i.quantity
                for i in items
                if i.status == "Delivered" and not i.cancelled and not i.returned
            )

            order_coupon = Decimal(order.coupon_discount or 0)

            if order_total > 0:
                delivered_coupon = (delivered_total / order_total) * order_coupon
            else:
                delivered_coupon = Decimal("0.00")

            period_coupon += delivered_coupon

        row["coupon_deduction"] = float(round(period_coupon, 2))

    # ---- SALES & DISCOUNT CALC (same as PDF) ----
    sales_map = (
        valid_items.annotate(period=trunc("order__created_at"))
        .values("period")
        .annotate(
            total_sales=Sum(F("final_price") * F("quantity")),
            total_discount=Sum("discount_value"),
        )
    )
    sales_dict = {s["period"]: s for s in sales_map}

    for row in grouped_orders:
        p = row["period"]
        row["total_sales"] = float(sales_dict.get(p, {}).get("total_sales", 0))
        row["total_discount"] = float(sales_dict.get(p, {}).get("total_discount", 0))

        # ---- TOTAL REVENUE ----
        row["total_revenue"] = (
            row["total_sales"]
            - float(row["coupon_deduction"])
            + float(row["delivery_charge"] or 0)
        )

    # -------- CREATE EXCEL --------
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Report"

    headers = [
        "Date", "Total Orders", "Total Sales (₹)", "Discount (₹)",
        "Coupon (₹)", "Delivery (₹)", "Total Revenue (₹)"
    ]
    ws.append(headers)

    for row in grouped_orders:
        ws.append([
            row["period"].strftime("%d-%m-%Y"),
            row["total_orders"],
            row["total_sales"],
            row["total_discount"],
            row["coupon_deduction"],
            float(row["delivery_charge"] or 0),
            round(row["total_revenue"], 2),
        ])
    # ---------- ADD TOTAL ROW ----------
    total_orders = sum(r["total_orders"] for r in grouped_orders)
    total_sales = sum(r["total_sales"] for r in grouped_orders)
    total_discount = sum(r["total_discount"] for r in grouped_orders)
    total_coupon = sum(float(r["coupon_deduction"]) for r in grouped_orders)
    total_delivery = sum(float(r["delivery_charge"] or 0) for r in grouped_orders)
    total_revenue = sum(r["total_revenue"] for r in grouped_orders)

    ws.append([])  # Empty row for spacing

    ws.append([
        "TOTAL",          # Date column blank replaced with label
        total_orders,
        round(total_sales, 2),
        round(total_discount, 2),
        round(total_coupon, 2),
        round(total_delivery, 2),
        round(total_revenue, 2),
    ])

    # Auto column width
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value) if cell.value else ""
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max_len + 2

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"sales_report_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

def convert(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return date_str
@login_required(login_url='/adminpanel/login/')
def export_sales_pdf(request):
    from decimal import Decimal
    from datetime import datetime

    # -------- 1) CLEAN DATE INPUT -------
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    period = request.GET.get("period", "day")

    start_date = start_date.strip() if start_date not in (None, "", "None") else None
    end_date = end_date.strip() if end_date not in (None, "", "None") else None

    # Convert yyyy-mm-dd → dd/mm/yyyy for PDF heading
    def convert(date_str):
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return date_str

    start_date_fmt = convert(start_date)
    end_date_fmt = convert(end_date)

    # -------- 2) SAME PERIOD MAP --------
    period_map = {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
        "year": TruncYear,
    }
    trunc = period_map.get(period, TruncDay)

    # -------- 3) SAME VALID ORDERS --------
    valid_orders = Order.objects.filter(
        status__in=["Delivered", "Partially Returned", "Partially Delivered"],
        payments__status="Success",
    )

    if start_date:
        valid_orders = valid_orders.filter(created_at__date__gte=start_date)
    if end_date:
        valid_orders = valid_orders.filter(created_at__date__lte=end_date)

    # -------- 4) SAME VALID ITEMS --------
    valid_items = OrderItem.objects.filter(
        order_id__in=valid_orders.values("id"),
        status="Delivered",
        cancelled=False,
        returned=False,
    )

    # -------- 5) SAME GROUPING BASED ON ORDERS --------
    grouped_orders = (
        valid_orders
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(
            total_orders=Count("id"),
            delivery_charge=Sum("delivery_charge"),
            coupon_deduction=Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
        )
        .order_by("period")
    )

    # -------- 6) SAME COUPON PROPORTIONAL LOGIC --------
    total_coupon_summary = Decimal("0.00")

    for row in grouped_orders:
        period_date = row["period"]
        orders_in_period = valid_orders.filter(created_at__date=period_date.date())

        period_coupon = Decimal("0.00")

        for order in orders_in_period:
            items = order.items.all()
            order_total = sum(i.final_price * i.quantity for i in items)

            delivered_total = sum(
                i.final_price * i.quantity
                for i in items
                if i.status == "Delivered" and not i.cancelled and not i.returned
            )

            order_coupon = Decimal(order.coupon_discount or 0)

            if order_total > 0:
                delivered_coupon = (delivered_total / order_total) * order_coupon
            else:
                delivered_coupon = Decimal("0.00")

            period_coupon += delivered_coupon
            total_coupon_summary += delivered_coupon

        row["coupon_deduction"] = round(period_coupon, 2)

    # -------- 7) SAME SALES & DISCOUNT FROM ITEMS --------
    sales_map = (
        valid_items
        .annotate(period=trunc("order__created_at"))
        .values("period")
        .annotate(
            total_sales=Sum(F("final_price") * F("quantity")),
            total_discount=Sum("discount_value")
        )
    )

    sales_dict = {s["period"]: s for s in sales_map}

    for row in grouped_orders:
        p = row["period"]
        row["total_sales"] = sales_dict.get(p, {}).get("total_sales", 0)
        row["total_discount"] = sales_dict.get(p, {}).get("total_discount", 0)

    # -------- 8) SAME SUMMARY --------
    summary = {
        "total_orders": valid_orders.count(),
        "total_sales": valid_items.aggregate(s=Sum(F("final_price") * F("quantity")))["s"] or 0,
        "total_discount": valid_items.aggregate(s=Sum("discount_value"))["s"] or 0,
        "total_delivery": valid_orders.aggregate(s=Sum("delivery_charge"))["s"] or 0,
        "total_coupon": round(total_coupon_summary, 2),
        
    }
    summary["total_revenue"] = (
    summary["total_sales"]
    
    - summary["total_coupon"]
    + summary["total_delivery"]
)
    # -------- 9) RENDER PDF --------
    html = render_to_string("adminpanel/sales_report_pdf.html", {
        "grouped_data": grouped_orders,
        "summary": summary,
        "period": period,
        "start_date": start_date_fmt,
        "end_date": end_date_fmt,
        "now": timezone.now(),
    })

    pdf = weasyprint.HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="sales_report.pdf"'
    return response


@login_required(login_url='/adminpanel/login/')
def return_requests(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    date = request.GET.get('date', '')

    rr = ReturnRequest.objects.all().order_by('-created_at')

    if q:
        rr = rr.filter(
            Q(order__iorderid__icontains=q) |
            Q(requested_by__first_name__icontains=q)        )

    if status:
        rr = rr.filter(status=status)

    if date:
        rr = rr.filter(created_at__date=date)

    paginator = Paginator(rr, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/return_requests.html', {
        'page_obj': page_obj,
        'q': q,
        'status': status,
        'date': date,
    })


# def return_requests(request):
#     """Admin view to list all return requests"""
#     requests = ReturnRequest.objects.all().order_by('-created_at')
#     return render(request, 'adminpanel/return_requests.html', {'requests': requests})

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
        if rr.status == 'VERIFIED':
            messages.warning(request, "This return request is already processed.")
            return redirect('return_requests')

        rr.status = 'VERIFIED'
        rr.verified_by = request.user
        rr.verified_at = timezone.now()
        rr.save()

        user = rr.requested_by
        order = rr.order
        order_item = rr.item
        active_items = order.items.filter(cancelled=False, returned=False)
        active_count = active_items.count()

        order_total_price = sum(
            Decimal(i.final_price) * i.quantity for i in active_items
        )
        order_total_price_all = sum(
            Decimal(i.final_price) * i.quantity for i in order.items.all()
        )


        # Step 2: Total of the item being cancelled
        item_total = Decimal(order_item.final_price) * order_item.quantity

        # Step 3: Coupon discount applied on whole order
        coupon_discount = Decimal(order.coupon_discount or 0)

        # Step 4: Proportional coupon share
        if order_total_price_all > 0:
            coupon_share = (item_total / order_total_price_all) * coupon_discount
        else:
            coupon_share = Decimal('0.00')

        # Step 5: Final refund = item price - coupon share + delivery refund (if any)
        # refund_amount = item_total - coupon_share + delivery_refund


        if active_count == 1:
            delivery_refund = Decimal(order.delivery_charge or 0)
        else:
            delivery_refund = Decimal('0.00')
        print("item_total--",item_total,"coupon_share--",coupon_share,"delivery_refund--",delivery_refund)

        refund_amount = item_total - coupon_share + delivery_refund 
        refund_amount = refund_amount.quantize(Decimal("0.01"))

                #  Restore stock
        variant = order_item.variant
        variant.stock = (variant.stock or 0) + order_item.quantity
        variant.save()
   
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
        rr.status = 'REFUNDED'
        rr.refund_amount = refund_amount
        rr.save()


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
        rr.verified_by = request.user
        rr.save()
        order = rr.order
        order_item = rr.item
        order_item.return_status = 'Rejected'
        order_item.save()


        messages.warning(request, "Return request rejected.")

    else:
        messages.error(request, "Invalid action.")

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
        item.delivered_at = timezone.now()
        item.save()

        # Update parent order status automatically
        order = item.order
        order.status = order.get_overall_status()
        order.save()
        if new_status == "Delivered":
            payment = order.payments.filter().first()
            if payment:
                # Only update if payment is not already success
                if payment.status != "Success":
                    payment.status = "Success"
                    payment.save()
        

        messages.success(request, f"{item.product.name} status updated to {new_status}.")
    return redirect('admin_order_detail', order_id=item.order.id)
@login_required(login_url='/adminpanel/login/')
def admin_change_password(request):
    if request.method == "POST":
        old_pwd = request.POST.get("old_password")
        pwd1 = request.POST.get("password1")
        pwd2 = request.POST.get("password2")

        user = request.user

        # 1. Check old password
        if not user.check_password(old_pwd):
            messages.error(request, "Old password is incorrect!")
            return redirect("admin_change_password")

        # 2. Check if new passwords match
        if pwd1 != pwd2:
            messages.error(request, "New passwords do not match!")
            return redirect("admin_change_password")

        # 3. Update password
        user.set_password(pwd1)
        user.save()
        update_session_auth_hash(request, user)

        messages.success(request, "Password changed successfully.")
        return redirect("admin_dashboard")

    return render(request, "adminpanel/change_password.html")


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = CustomUser.objects.get(email=email)
        except:
            messages.error(request, "Email not found!")
            return redirect("forgot_password")

        otp = random.randint(100000, 999999)
        request.session["reset_email"] = email
        request.session["otp"] = otp
        request.session["otp_time"] = timezone.now().isoformat()

        send_mail(
            "Stepora Admin Password Reset",
            f"Your OTP is {otp}",
            "stepora@example.com",
            [email],
        )

        messages.success(request, "OTP has been sent to your email.")
        return redirect("admin_verify_otp")

    return render(request, "adminpanel/forgot_password.html")


def admin_verify_otp(request):
    otp_time = request.session.get("otp_time")

    if otp_time:
        otp_time = timezone.datetime.fromisoformat(otp_time)

        if timezone.now() > otp_time + timedelta(seconds=60):
            messages.error(request, "OTP expired! Please request a new one.")
            return redirect("admin_forgot_password")

    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        saved_otp = str(request.session.get("otp"))

        if entered_otp == saved_otp:
            return redirect("admin_reset_password")
        else:
            messages.error(request, "Invalid OTP! Please try again.")
            return redirect("admin_verify_otp")

    return render(request, "adminpanel/verify_otp.html")




def admin_reset_password(request):
    if request.method == "POST":
        pwd1 = request.POST.get("password1")
        pwd2 = request.POST.get("password2")

        if pwd1 != pwd2:
            messages.error(request, "Passwords do not match!")
            return redirect("admin_reset_password")

        email = request.session.get("reset_email")
        user = CustomUser.objects.get(email=email)
        user.set_password(pwd1)
        user.save()

        messages.success(request, "Password reset successful! Login again.")
        return redirect("admin_login")

    return render(request, "adminpanel/reset_password.html")

