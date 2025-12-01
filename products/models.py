from django.db import models
from adminpanel.models import CustomUser
from PIL import Image
from category.models import Color,Size,Material,Occasion,Brand,Category,Gender
from django.utils import timezone
from cloudinary.models import CloudinaryField

# ------------------ PRODUCT MODEL ------------------
class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)  # assuming a Brand model
    product_type = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)  # Gender model
    manufacture_details= models.TextField(blank=True)
    material = models.ForeignKey(Material, on_delete=models.SET_NULL, null=True, blank=True)
    occasion = models.ForeignKey(Occasion, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)  # Soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


# ------------------ VARIANT MODEL ------------------
class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    variant_name = models.CharField(max_length=100)  # Example: "Red - XL"
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100)
    stock = models.IntegerField(default=0)
    low_stock_qty = models.IntegerField(default=0)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    short_description = models.CharField(max_length=250, blank=True)
    long_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)  # Soft delete
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def best_offer(self):
        """Get the best active offer (product or category level) for this variant."""
        from cart.models import Offer

        now = timezone.now()
        base_price = float(self.price)
        product = self.product
        best_offer = None

        # Product-level offer
        product_offer = Offer.objects.filter(
            target_type='product',
            target_id=product.id,
            is_active=True,
            start_at__lte=now,
            end_at__gte=now
        ).order_by('-discount_value').first()

        # Category-level offer
        category_offer = Offer.objects.filter(
            target_type='category',
            target_id=product.category.id,
            is_active=True,
            start_at__lte=now,
            end_at__gte=now
        ).order_by('-discount_value').first()

        # Choose the best offer
        if product_offer and category_offer:
            best_offer = (
                product_offer
                if product_offer.discount_value >= category_offer.discount_value
                else category_offer
            )
        else:
            best_offer = product_offer or category_offer

        # Apply the best offer
        if best_offer:
            if best_offer.discount_type == 'percent':
                final_price = base_price - (base_price * float(best_offer.discount_value) / 100)
            else:
                final_price = base_price - float(best_offer.discount_value)
            # print(best_offer.discount_type.upper())    

            return {
                'has_offer': True,
                'final_price': round(final_price, 2),
                'discount_percent': float(best_offer.discount_value),
                'offer_type': best_offer.discount_type.upper(),  # 'PERCENT' or 'FLAT'
            }

        # No offer
        return {
            'has_offer': False,
            'final_price': round(base_price, 2),
            'discount_percent': 0.0,
            'offer_type': None,
        }

# ------------------ IMAGE MODEL ------------------
class ProductImage(models.Model):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='images')
    image = CloudinaryField('image',folder="products/")
    is_primary = models.BooleanField(default=True)  # Soft delete

    # def save(self, *args, **kwargs):
    #     """Crop and resize image before saving."""
    #     super().save(*args, **kwargs)
    #     img = Image.open(self.image.path)
    #     img = img.convert('RGB')

    #     # Resize and crop (make square thumbnail 600x600)
    #     img.thumbnail((600, 600))
    #     width, height = img.size
    #     min_side = min(width, height)
    #     left = (width - min_side) / 2
    #     top = (height - min_side) / 2
    #     right = (width + min_side) / 2
    #     bottom = (height + min_side) / 2
    #     img = img.crop((left, top, right, bottom))
    #     img.save(self.image.path)




    def __str__(self):
        return f"Image for {self.variant.variant_name}"
