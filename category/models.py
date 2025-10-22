from django.db import models

class Gender(models.Model):
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name    


class Category(models.Model):
    category_name = models.CharField(max_length=100)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, related_name='categories')
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.category_name


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
