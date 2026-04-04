from rest_framework import serializers
from .models import DailyReport

class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)