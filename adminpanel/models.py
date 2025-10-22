from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)  # mark admin users
    phone = models.CharField(max_length=15, blank=True, null=True)  # Add phone number field
    def __str__(self):
        return self.username
