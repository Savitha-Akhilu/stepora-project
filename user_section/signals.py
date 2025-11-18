from django.db.models.signals import post_save
from django.dispatch import receiver
from adminpanel.models import CustomUser
from .models import Address
from cart.models import Cart

@receiver(post_save, sender=CustomUser)
# def create_profile(sender, instance, created, **kwargs):
#     if created:
#         Address.objects.create(user=instance)
@receiver(post_save, sender=CustomUser)
def create_user_cart(sender, instance, created, **kwargs):
    if created:
        Cart.objects.create(user=instance)

