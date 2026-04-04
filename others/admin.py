from django.contrib import admin
from .models import DailyReport, Feedback, FCMDevice, Notification

@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ('user', 'assesment', 'time', 'score')
    list_filter = ('assesment', 'time')
    search_fields = ('user__username', 'journal')

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'stars', 'created_at')
    list_filter = ('stars', 'created_at')
    search_fields = ('user__username', 'feedback')

@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'registration_id', 'active', 'updated_at')
    list_filter = ('active',)
    search_fields = ('user__username', 'registration_id')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'title', 'body')
