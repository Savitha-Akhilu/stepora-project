# from django.utils import timezone
# from decimal import Decimal
# from cart.models import Offer  # adjust path if Offer is in another app

# def get_best_offer_price(product_variant):
#     """
#     Calculate the best offer for a product variant.
#     Returns tuple: (final_price, discount_percent, offer_obj)
#     """
#     now = timezone.now()
#     product = product_variant.product
#     base_price = Decimal(product_variant.price)

#     # --- Get active Product Offer ---
#     product_offer = Offer.objects.filter(
#         target_type='product',
#         target_id=product.id,
#         is_active=True,
#         start_at__lte=now,
#         end_at__gte=now
#     ).order_by('-discount_value').first()

#     # --- Get active Category Offer ---
#     category_offer = Offer.objects.filter(
#         target_type='category',
#         target_id=product.category.id,
#         is_active=True,
#         start_at__lte=now,
#         end_at__gte=now
#     ).order_by('-discount_value').first()

#     # --- Pick the better offer ---
#     best_offer = None
#     if product_offer and category_offer:
#         best_offer = product_offer if product_offer.discount_value > category_offer.discount_value else category_offer
#     else:
#         best_offer = product_offer or category_offer

#     # --- Apply Offer ---
#     if best_offer:
#         discount_value = Decimal(best_offer.discount_value)
#         final_price = base_price

#         if best_offer.discount_type.lower() == 'percent':
#             discount_amount = (base_price * discount_value) / Decimal(100)
#             final_price -= discount_amount
#         elif best_offer.discount_type.lower() == 'flat':
#             final_price -= discount_value

#         if final_price < 0:
#             final_price = Decimal('0.00')

#         return round(final_price, 2), discount_value, best_offer

#     return base_price, 0, None

#above mistake-------- sometime percentage and flat value not coming correctly-nov7--

from django.utils import timezone
from decimal import Decimal
from cart.models import Offer  ,Order,Payment
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear

def get_best_offer_price(product_variant):
    """
    Calculate the best offer for a product variant.
    Returns:
        (final_price, discount_amount, offer_obj)
    - final_price: discounted price (Decimal)
    - discount_amount: rupee value of discount (Decimal)
    - offer_obj: Offer instance applied
    """
    now = timezone.now()
    product = product_variant.product
    base_price = Decimal(product_variant.price)

    # --- Get active Product Offer ---
    product_offer = Offer.objects.filter(
        target_type='product',
        target_id=product.id,
        is_active=True,
        start_at__lte=now,
        end_at__gte=now
    ).order_by('-discount_value').first()

    # Get active Category Offer 
    category_offer = Offer.objects.filter(
        target_type='category',
        target_id=product.category.id,
        is_active=True,
        start_at__lte=now,
        end_at__gte=now
    ).order_by('-discount_value').first()

    # Pick the gooood offer 
    best_offer = None
    if product_offer and category_offer:
        best_offer = (
            product_offer
            if product_offer.discount_value > category_offer.discount_value
            else category_offer
        )
    else:
        best_offer = product_offer or category_offer

    if best_offer:
        discount_value = Decimal(best_offer.discount_value)
        final_price = base_price
        discount_amount = Decimal('0.00')

        if best_offer.discount_type.lower() == 'percent':
            discount_amount = (base_price * discount_value) / Decimal('100')
            final_price -= discount_amount
        elif best_offer.discount_type.lower() == 'flat':
            discount_amount = discount_value
            final_price -= discount_value

        if final_price < 0:
            final_price = Decimal('0.00')

        return round(final_price, 2), round(discount_amount, 2), best_offer

    # --- No active offer ---
    return base_price, Decimal('0.00'), None

# reports/utils.py
def group_payments_by_period(qs, period):
    """Group payments by day, month, or year for reporting."""

    amount_field = "order__total"   # Payment does NOT have amount field

    if period == "day":
        grouped = (
            qs.annotate(date=TruncDay("created_at"))
              .values("date")
              .annotate(total=Sum(amount_field))
              .order_by("date")
        )
        return [{"label": g["date"].strftime("%Y-%m-%d"), "total": g["total"]} for g in grouped]

    if period == "month":
        grouped = (
            qs.annotate(date=TruncMonth("created_at"))
              .values("date")
              .annotate(total=Sum(amount_field))
              .order_by("date")
        )
        return [{"label": g["date"].strftime("%b %Y"), "total": g["total"]} for g in grouped]

    if period == "year":
        grouped = (
            qs.annotate(date=TruncYear("created_at"))
              .values("date")
              .annotate(total=Sum(amount_field))
              .order_by("date")
        )
        return [{"label": g["date"].year, "total": g["total"]} for g in grouped]

    return []
def get_filtered_orders(start_date=None, end_date=None):
    """Fetch orders within selected date range that are completed or delivered."""
    qs = Order.objects.filter(status__in=['Delivered', 'Returned'])
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    return qs
def get_filtered_payments(start_date=None, end_date=None):
    """Fetch REAL sales = successful payments only."""
    qs = Payment.objects.filter(status="Success")

    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    return qs


def group_orders_by_period(qs, period='day'):
    """Group orders by day/week/month."""
    if period == 'day':
        trunc = TruncDay('created_at')
    elif period == 'week':
        trunc = TruncWeek('created_at')
    elif period == 'month':
        trunc = TruncMonth('created_at')
    elif period == 'year':
        trunc = TruncYear('created_at')
    else:
        trunc = TruncDay('created_at')

    data = qs.annotate(period=trunc).values('period').annotate(
        total_orders=Count('id', distinct=True),
        total_sales=Sum('total', output_field=DecimalField(max_digits=12, decimal_places=2)),
        total_discount=Sum('discount', output_field=DecimalField(max_digits=12, decimal_places=2)),
        coupon_deduction=Sum('coupon_discount', output_field=DecimalField(max_digits=12, decimal_places=2)),
        delivery_charge=Sum('delivery_charge', output_field=DecimalField(max_digits=12, decimal_places=2)),
    ).order_by('period')
    return data

# def get_sales_summary(qs):
#     """Return overall summary totals."""
#     result = qs.aggregate(
#         total_orders=Count('id', distinct=True),
#         total_sales=Sum('total', output_field=DecimalField(max_digits=12, decimal_places=2)),
#         total_discount=Sum('discount', output_field=DecimalField(max_digits=12, decimal_places=2)),
#         total_coupon=Sum('coupon_discount', output_field=DecimalField(max_digits=12, decimal_places=2)),
#         total_delivery=Sum('delivery_charge', output_field=DecimalField(max_digits=12, decimal_places=2)),
#     )
#     return result
def get_sales_summary(qs):
    """Summary of total revenue and number of orders."""
    return {
        "total_sales": qs.aggregate(total_sales=Sum("total"))["total_sales"] or 0,
        "total_orders": qs.count()
    }
