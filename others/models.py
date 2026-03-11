from django.db import models
from django.conf import settings
import uuid

# Create your models here.

class DailyReport(models.Model):
    LIST= (('excellent', 'Excellent'),('good', 'Good'),('neutral', 'Neutral'),('sad', 'Sad'),('depressed', 'Depressed'),)
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    assesment = models.CharField(max_length=100, choices=LIST)
    time = models.DateTimeField()
    journal = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.time} - {self.assesment}"