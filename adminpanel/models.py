from django.db import models
from django.contrib.auth.models import AbstractUser
from category.models import Gender

class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)  # mark admin users
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)  # phone number field (unique)
    email = models.EmailField(unique=True)
    is_customer = models.BooleanField(default=False)  
    profile_image = models.ImageField(upload_to='profile_pics/', blank=True, null=True, default='profile_pics/default.png')
    gender = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)
    dob = models.DateField(blank=True, null=True)
    USERNAME_FIELD = 'email'         # use existing email field as login
    REQUIRED_FIELDS = ['username']   #  keep username required for superuser
    def __str__(self):
        return self.username
