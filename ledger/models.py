from django.db import models
from cart.models import Payment,Order

# Create your models here.
class Ledger(models.Model):
    TRANSACTION_TYPES = [
        ('CREDIT', 'Credit'),  
        ('DEBIT', 'Debit'),     
    ]

    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=6, choices=TRANSACTION_TYPES)
    description = models.TextField()
    balance_after_transaction = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - ₹{self.amount}"
