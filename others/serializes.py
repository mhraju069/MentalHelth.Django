from rest_framework import serializers
from .models import DailyReport, Feedback, FCMDevice, Notification

class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)


class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = ['registration_id', 'device_id']
        read_only_fields = ('user',)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('user',)


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)