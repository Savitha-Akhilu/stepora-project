from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField


class Gender(models.Model):
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name    


class Category(models.Model):
    category_name = models.CharField(max_length=100)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, related_name='categories')
    description = models.TextField()
    # image = models.ImageField(upload_to='media/categories/', null=True, blank=True) 
    image = CloudinaryField(
        'image',
        null=True,
        blank=True,
        folder='categories'
    ) 
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True) 
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['-created_at']  #   showing latest first

    def __str__(self):
        return self.category_name
    def soft_delete(self):
        """Soft delete """
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_active', 'deleted_at'])

    def restore(self):
        """Restore a soft-deleted category"""
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=['is_active', 'deleted_at'])

class Color(models.Model):
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=50)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Material(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Occasion(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
