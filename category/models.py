from django.db import models
from adminpanel.models import Gender

class Color(models.Model):
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)  # Soft delete


    def __str__(self):
        return self.name

class Size(models.Model):
    name = models.CharField(max_length=50)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE,default=1)
    is_active = models.BooleanField(default=True)  # Soft delete


    def __str__(self):
        return self.name

class Material(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)  # Soft delete


    def __str__(self):
        return self.name

class Occasion(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)  # Soft delete


    def __str__(self):
        return self.name
