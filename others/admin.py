from django.contrib import admin
from .models import *
from unfold.admin import ModelAdmin

@admin.register(DailyReport)
class DailyReportAdmin(ModelAdmin):
    list_display = ('user', 'assesment', 'time', 'score')
    list_filter = ('assesment', 'time')
    search_fields = ('user__email', 'journal')

@admin.register(Feedback)
class FeedbackAdmin(ModelAdmin):
    list_display = ('user', 'stars', 'created_at')
    list_filter = ('stars', 'created_at')
    search_fields = ('user__email', 'feedback')

@admin.register(FCMDevice)
class FCMDeviceAdmin(ModelAdmin):
    list_display = ('user', 'registration_id', 'active', 'updated_at')
    list_filter = ('active',)
    search_fields = ('user__email', 'registration_id')

@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__email', 'title', 'body')
