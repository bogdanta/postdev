import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Post(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    title = models.CharField(max_length=64)
    description = models.CharField(max_length=1024)
    code = models.CharField(max_length=16)
    created_at = models.DateTimeField()
    is_private = models.BooleanField(default=False)
    views = models.IntegerField()
    expires_at = models.DateTimeField()
