from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)  # mark admin users
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)

    # You can add more fields here if needed
    def __str__(self):
        return self.username
