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
    score = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.time} - {self.assesment}"

    def save(self, *args, **kwargs):
        if self.assesment == 'excellent':
            self.score = 10
        elif self.assesment == 'good':
            self.score = 8
        elif self.assesment == 'neutral':
            self.score = 6
        elif self.assesment == 'sad':
            self.score = 4
        elif self.assesment == 'depressed':
            self.score = 2
        super().save(*args, **kwargs)

class AIChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AIChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AIChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=(('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')))
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)