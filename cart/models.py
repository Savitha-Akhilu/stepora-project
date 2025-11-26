from django.db import models
from django.utils import timezone
from decimal import Decimal

from adminpanel.models import CustomUser
from django.core.validators import MinValueValidator
from products.models import ProductVariant
import random

MAX_CART_QUANTITY = 5  

class Cart(models.Model):
    """Represents the user's shopping cart."""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='carts')  
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    def total_price(self):
        return sum(item.subtotal() for item in self.items.all())

    def items_total(self):
        """Subtotal without offers (original prices)."""
        return sum(item.variant.price * item.quantity for item in self.items.all())

    def items_offer_total(self):
        """Subtotal considering active offers."""
        from adminpanel.utils import get_best_offer_price
        total = 0
        for item in self.items.select_related('variant', 'variant__product'):
            final_price, discount_percent, offer = get_best_offer_price(item.variant)
            # print(final_price,discount_percent,offer)
            total += final_price * item.quantity
            # print(total)
        return total

    def delivery_charge(self):
        """Delivery charge based on offer-adjusted subtotal."""
        # subtotal = self.items_total()
        subtotal = Decimal(self.items_offer_total())
        coupon_discount = Decimal('0.00')
        # If coupon stored in model
        if self.coupon:
            coupon_discount = self.coupon.calculate_discount(subtotal)
        total_after_discount = subtotal - coupon_discount

        # print(coupon_discount)
        # print(total_after_discount)
        if total_after_discount == 0:
            return 0
        elif total_after_discount < 1000:
            return 50
        elif total_after_discount < 3000:
            return 30
        else:
            return 0  # free delivery for orders ≥ ₹3000

    def grand_total(self):
        """Final total (subtotal with offers + delivery)."""
        subtotal = self.items_offer_total()
        return subtotal + self.delivery_charge()
    def get_items_with_offer(self):
        """
        Returns all cart items with attached offer details 
        (final_price, discount_percent, has_offer).
        """
        from adminpanel.utils import get_best_offer_price

        items = self.items.select_related('variant', 'variant__product')

        for item in items:
            final_price, discount_percent, offer = get_best_offer_price(item.variant)
            item.variant.final_price = final_price
            item.variant.discount_percent = discount_percent
            item.variant.has_offer = True if offer else False
            item.subtotal = final_price * item.quantity

        return items
    def apply_coupon(self, coupon):
        self.coupon = coupon
        self.save()
        self.calculate_totals()


    def calculate_totals(self):
        total = sum(item.subtotal() for item in self.items.all())
        self.total_amount = total

        if self.coupon:
            discount = self.coupon.calculate_discount(total)
            self.total_amount -= discount

        self.save()

    def get_final_amount(self):
       return self.total_amount


    def __str__(self):
        return f"Cart of {self.user.username}"
class CartItem(models.Model):
    """Represents each product variant added to the cart."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'variant')  # Prevent duplicates

    def subtotal(self):
        """Price × quantity"""
        return self.variant.price * self.quantity
    def offer_subtotal(self):
        """Returns offer-based subtotal for the item."""
        from adminpanel.utils import get_best_offer_price
        final_price, _, _ = get_best_offer_price(self.variant)
        return Decimal(final_price) * self.quantity


    def is_in_stock(self):
        """Check stock availability"""
        return self.variant.stock >= self.quantity

    def __str__(self):
        return f"{self.variant.product.name} ({self.variant}) × {self.quantity}"
  
class Wishlist(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='wishlist')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'variant')

    def __str__(self):
        return f"{self.variant.product.name} ({self.variant}) in {self.user.username}'s wishlist"

class Coupon(models.Model):
    COUPON_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FLAT', 'Flat Discount'),
    ]

    code = models.CharField(max_length=20, unique=True)
    description = models.CharField(max_length=255, blank=True)
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPE_CHOICES, default='PERCENTAGE')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField()
    active = models.BooleanField(default=True)
    def calculate_discount(self, total):
        if self.coupon_type == 'PERCENTAGE':
            return (total * self.discount_value) / 100
        elif self.coupon_type == 'FLAT':
            return self.discount_value
        return 0

    def is_valid(self):
        today = timezone.now().date()
        return self.active and self.valid_from <= today <= self.valid_to
    def is_valid_for(self, amount):
        today = timezone.now().date()
        return (
            self.active
            and self.valid_from <= today <= self.valid_to
            and amount >= self.min_purchase_amount
        )

    def apply_discount(self, amount):
        """Return discount amount."""
        if not self.is_valid_for(amount):
            return Decimal('0.00')
        if self.coupon_type == 'PERCENTAGE':
            discount = (amount * self.discount_value / 100)
        else:
            discount = self.discount_value
        return min(discount, amount)
    def __str__(self):
        return f"{self.code} - {self.discount_value}{'%' if self.coupon_type == 'PERCENTAGE' else '₹'}"
    
    def status(self):
        """Return readable coupon status"""
        today = timezone.now().date()
        if not self.active:
            return "Inactive"
        elif self.valid_from > today:
            return "Upcoming"
        elif self.valid_to < today:
            return "Expired"
        else:
            return "Active"        
    @staticmethod
    def get_best_coupon(amount):
        """
        Find and return the best valid coupon based on the given amount.
        Returns a tuple: (best_coupon, best_discount)
        """
        from django.utils import timezone
        today = timezone.now().date()

        best_coupon = None
        best_discount = Decimal('0.00')

        for c in Coupon.objects.filter(active=True, valid_to__gte=today):
            if c.is_valid_for(amount):
                discount = Decimal(c.apply_discount(amount))
                if discount > best_discount:
                    best_discount = discount
                    best_coupon = c

        return best_coupon, best_discount
    
DISCOUNT_TYPE_CHOICES = (
    ('percent', 'Percent'),
    ('flat', 'Flat Amount'),
)

TARGET_TYPE_CHOICES = (
    ('product', 'Product'),
    ('category', 'Category'),
    ('brand', 'Brand'),
)


class Offer(models.Model):
    """Single Offer table for Product, Category, Brand, or Global level."""
    name = models.CharField(max_length=200)
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    # Store the ID of the target object (like product_id, category_id)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    start_at = models.DateTimeField(default=timezone.now)
    end_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.target_type}) - {self.discount_value}{'%' if self.discount_type == 'percent' else ''}"

    def is_valid(self):
        now = timezone.now()
        return (
            self.is_active and
            (not self.start_at or self.start_at <= now) and
            (not self.end_at or self.end_at >= now)
        )
    def get_status(self):
        now = timezone.now()

        if not self.is_active:
            return "Inactive"
        elif self.start_at and self.start_at > now:
            return "Upcoming"
        elif self.end_at and self.end_at < now:
            return "Expired"
        else:
            return "Active"

    def save(self, *args, **kwargs):
        now = timezone.now()
        # deactivate if offer has ended
        if self.end_at and self.end_at <= now:
            self.is_active = False
        super().save(*args, **kwargs)


class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending','Pending'),
        ('Processing','Processing'),
        ('Delivered','Delivered'),
        ('Cancelled','Cancelled'),
        ('Returned','Returned'),
        ('Failed','Failed'),
    ]
    PAYMENT_METHOD_CHOICES = [
    ('COD', 'Cash on Delivery'),
    ('RAZORPAY', 'Razorpay'),
    ('WALLET', 'Wallet'),
]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    address = models.ForeignKey('user_section.Address', on_delete=models.CASCADE)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey('cart.Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    coupon_code = models.CharField(max_length=50, blank=True, null=True)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    iorderid = models.CharField(max_length=20, unique=True, blank=True, null=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"
    
    def save(self, *args, **kwargs):
        if not self.iorderid:
            random_number = random.randint(100000000000, 999999999999)
            self.iorderid = f"#{random_number}"
        super().save(*args, **kwargs)
    def get_overall_status(self):
        items = self.items.all()
        # print(items)
        if not items.exists():
            return 'Pending'

        statuses = set(item.status for item in items)
        # print(statuses)

        if all(s == 'Delivered' for s in statuses):
            return 'Delivered'
        elif all(s == 'Cancelled' for s in statuses):
            return 'Cancelled'
        elif all(s == 'Returned' for s in statuses):
            return 'Returned'
        elif 'Returned' in statuses and len(statuses) > 1:
            return 'Partially Returned'
        elif 'Cancelled' in statuses and len(statuses) > 1:
            return 'Partially Cancelled'
        elif 'Delivered' in statuses and len(statuses) > 1:
            return 'Partially Delivered'
        elif 'Processing' in statuses:
            return 'Processing'
        else:
            return 'Pending'
    def original_subtotal(self):
      """Total MRP before discounts."""
      return sum(item.price * item.quantity for item in self.items.all())


class OrderItem(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
        ('Returned', 'Returned'),
    ]
    RETURN_STATUS = [
        ('None', 'Not Requested'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.PROTECT)
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cancelled = models.BooleanField(default=False)
    returned = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')  
    return_status = models.CharField(max_length=20, choices=RETURN_STATUS, default='None')  # 🟢 new
    class Meta:
             indexes = [
        models.Index(fields=['delivered_at']),
        models.Index(fields=['returned_at']),
        models.Index(fields=['cancelled']),
        models.Index(fields=['returned']),
    ]
    def save(self, *args, **kwargs):
        # store per-unit final price after discount
        self.final_price = (self.price - self.discount_value)
        super().save(*args, **kwargs)
    def subtotal(self):
        return self.price * self.quantity
    def subtotal_after_discount(self):
        return (self.price - self.discount_value) * self.quantity
# Log cancellation or return actions with reason
class OrderActionLog(models.Model):
    ACTION_CHOICES = [
        ('CancelOrder','Cancel Order'),
        ('CancelItem','Cancel Item'),
        ('ReturnOrder','Return Order'),
        ('ReturnItem','Return Item'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    item = models.ForeignKey(OrderItem, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Payment(models.Model):
    METHOD_CHOICES = [
        ('Razorpay', 'Razorpay'),
        ('COD', 'Cash on Delivery'),
        ('Wallet', 'Wallet'),
    ]

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
        ('Refunded', 'Refunded'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    provider_order_id = models.CharField(max_length=255, blank=True, null=True)   # Razorpay Order ID
    provider_payment_id = models.CharField(max_length=255, blank=True, null=True) # Razorpay Payment ID
    provider_signature = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    raw_response = models.JSONField(blank=True, null=True)  # store full Razorpay response
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.method} - {self.status} - ₹{self.amount} for Order {self.order.iorderid or self.order.id}"
class Refund(models.Model):
    STATUS_CHOICES = [
        ('Initiated', 'Initiated'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField(blank=True, null=True)
    refund_id = models.CharField(max_length=255, blank=True, null=True)  # Razorpay refund ID
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Initiated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_response = models.JSONField(blank=True, null=True)  # store Razorpay API response
    initiated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='initiated_refunds')
    class Meta:
                constraints = [
        models.UniqueConstraint(fields=['order', 'item'], name='unique_refund_per_item')
    ]

    def __str__(self):
        return f"Refund ₹{self.amount} - {self.status} for {self.order.iorderid or self.order.id}"
    def save(self, *args, **kwargs):
         super().save(*args, **kwargs)
         if self.status == 'Completed':
        # Update payment total
                self.payment.refunded_amount = (
                self.payment.refunds.filter(status='Completed').aggregate(total=Sum('amount'))['total'] or 0
        )
                self.payment.save(update_fields=['refunded_amount'])
