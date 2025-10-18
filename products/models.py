from django.db import models
from adminpanel.models import Category,CustomUser,Brand,Gender
from PIL import Image
from category.models import Color,Size,Material,Occasion

# ------------------ PRODUCT MODEL ------------------
class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)  # assuming a Brand model
    product_type = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)  # Gender model
    manufacture_details= models.TextField(blank=True)
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
    material = models.ForeignKey(Material, on_delete=models.SET_NULL, null=True, blank=True)
    occasion = models.ForeignKey(Occasion, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100)
    stock = models.IntegerField(default=0)
    low_stock_qty = models.IntegerField(default=0)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    short_description = models.CharField(max_length=250, blank=True)
    long_description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)  # Soft delete
    created_at = models.DateTimeField(auto_now_add=True)


# ------------------ IMAGE MODEL ------------------
class ProductImage(models.Model):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    is_primary = models.BooleanField(default=True)  # Soft delete

    def save(self, *args, **kwargs):
        """Crop and resize image before saving."""
        super().save(*args, **kwargs)
        img = Image.open(self.image.path)
        img = img.convert('RGB')

        # Resize and crop (make square thumbnail 600x600)
        img.thumbnail((600, 600))
        width, height = img.size
        min_side = min(width, height)
        left = (width - min_side) / 2
        top = (height - min_side) / 2
        right = (width + min_side) / 2
        bottom = (height + min_side) / 2
        img = img.crop((left, top, right, bottom))
        img.save(self.image.path)

    def __str__(self):
        return f"Image for {self.variant.variant_name}"
