from django.db import models
from adminpanel.models import CustomUser
from django.core.validators import MinValueValidator
from products.models import ProductVariant
import uuid
from decimal import Decimal
from django.db import transaction
from cart.models import Order,Refund,OrderItem
from decimal import Decimal
ADDRESS_TYPE_CHOICES = (
    ('Home', 'Home'),
    ('Office', 'Office'),
)
class Address(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='addresses')
    full_name = models.CharField(max_length=100)
    house_name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=15, default='')
    city = models.CharField(max_length=100)
    street_address = models.CharField(max_length=200,default="")
    locality = models.CharField(max_length=150, default="")
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE_CHOICES, default='Home')
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.full_name} - {self.city}"
class Referral(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    referral_code = models.CharField(max_length=10, unique=True)
    referred_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = str(self.user.first_name[:4]).upper() + str(uuid.uuid4())[:4].upper()
        super().save(*args, **kwargs)
class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - ₹{self.balance}"
    @transaction.atomic
    def credit(self, amount, description=""):
        amount = Decimal(amount)
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='CREDIT',
            amount=amount,
            description=description
        )

    @transaction.atomic
    def debit(self, amount, description=""):
        amount = Decimal(amount)
        if amount > self.balance:
            raise ValueError("Insufficient wallet balance")
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='DEBIT',
            amount=amount,
            description=description
        )
class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('CREDIT', 'Credit'),
        ('DEBIT', 'Debit'),
    )
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    refund = models.ForeignKey(Refund, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet.user.username} - {self.transaction_type} ₹{self.amount}"

from decimal import Decimal

class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
        ('REFUNDED', 'Refunded'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='return_requests'
    )
    item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='return_requests'
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='return_requests'
    )
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True, null=True)
    verified_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_returns'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ReturnRequest #{self.id} for {self.order.iorderid or self.order.id}"

    class Meta:
        ordering = ['-created_at']
