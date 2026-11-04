from django.contrib import admin
from .models import *
from unfold.admin import ModelAdmin, TabularInline


class AssessmentOptionInline(TabularInline):
    model = AssessmentOption
    extra = 1
    fields = ('label', 'order', 'is_active')


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(ModelAdmin):
    list_display = ('text', 'question_type', 'is_required', 'saves_as_tags', 'order', 'is_active', 'updated_at')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active', 'question_type', 'is_required')
    search_fields = ('text',)
    fields = ('text', 'help_text', 'question_type', 'is_required', 'saves_as_tags', 'order', 'is_active')
    inlines = [AssessmentOptionInline]

@admin.register(DailyReport)
class DailyReportAdmin(ModelAdmin):
    list_display = ('user', 'check_in_type', 'assesment', 'mood_rating', 'anxiety_rating', 'sleep_hours', 'time')
    list_filter = ('check_in_type', 'assesment', 'sleep_quality', 'time')
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
