from django.contrib import admin, messages
from django.db.models import Count, F
from .models import *
from unfold.admin import ModelAdmin, TabularInline


def is_locked(question):
    return bool(question and question.questionnaire_id and question.questionnaire.is_locked)


class AssessmentOptionInline(TabularInline):
    model = AssessmentOption
    extra = 1
    fields = ('label', 'value', 'order', 'is_active')

    def has_add_permission(self, request, obj=None):
        return not is_locked(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not is_locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not is_locked(obj) and super().has_delete_permission(request, obj)


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(ModelAdmin):
    list_display = ('text', 'questionnaire', 'question_type', 'is_required', 'version', 'order', 'is_active', 'updated_at')
    list_editable = ('order', 'is_active')
    list_filter = ('questionnaire', 'is_active', 'question_type', 'is_required')
    list_select_related = ('questionnaire',)
    search_fields = ('text', 'key')
    fields = ('questionnaire', 'text', 'help_text', 'question_type', 'is_required', 'saves_as_tags', 'key', 'version', 'order', 'is_active')
    readonly_fields = ('version',)
    inlines = [AssessmentOptionInline]

    # Changes that alter what a question asks; once people have answered,
    # these bump the version so old answers keep their original meaning.
    MEANING_FIELDS = {'text', 'question_type'}

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.response_items.exists():
            # Analytics follow a question by its key and questionnaire.
            readonly += ['questionnaire', 'key']
        return readonly

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'questionnaire':
            kwargs['queryset'] = Questionnaire.objects.filter(is_locked=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return not is_locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Answered questions are deactivated instead, so history stays linked.
        if obj and (is_locked(obj) or obj.response_items.exists()):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        # The list page's inline editing bypasses has_change_permission(obj).
        if change and is_locked(AssessmentQuestion.objects.select_related('questionnaire').get(pk=obj.pk)):
            messages.error(request, f'"{obj}" belongs to a locked questionnaire and was not changed.')
            return
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        question = form.instance
        if question.question_type == AssessmentQuestion.SCALE and question.options.filter(
            is_active=True, value__isnull=True
        ).exists():
            messages.warning(request, f'"{question}" is a scored scale, but some answers have no value; they score nothing.')
        if not change:
            return
        meaning_changed = bool(self.MEANING_FIELDS & set(form.changed_data)) or any(
            self._options_changed(formset) for formset in formsets
        )
        if meaning_changed and question.response_items.exists():
            AssessmentQuestion.objects.filter(pk=question.pk).update(version=F('version') + 1)
            messages.info(
                request,
                f'"{question}" has saved answers, so this is now version {question.version + 1}. '
                'Earlier answers keep the wording they were given with.',
            )

    @staticmethod
    def _options_changed(formset):
        if formset.model is not AssessmentOption:
            return False
        return bool(
            formset.new_objects
            or formset.deleted_objects
            or any({'label', 'value'} & set(fields) for _, fields in formset.changed_objects)
        )


class QuestionnaireQuestionInline(TabularInline):
    """Read-only overview; questions are edited on their own page."""
    model = AssessmentQuestion
    fields = ('text', 'key', 'question_type', 'version', 'order', 'is_active')
    readonly_fields = fields
    extra = 0
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Questionnaire)
class QuestionnaireAdmin(ModelAdmin):
    list_display = ('name', 'key', 'is_daily', 'is_locked', 'scoring', 'frequency_days', 'question_count', 'is_active')
    list_filter = ('is_active', 'is_locked', 'is_daily')
    search_fields = ('name', 'key')
    fields = (
        'name', 'key', 'description', 'instructions', 'scoring', 'severity_bands',
        'frequency_days', 'copyright_notice', 'order', 'is_active', 'is_daily', 'is_locked',
    )
    inlines = [QuestionnaireQuestionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(num_questions=Count('questions'))

    @admin.display(description='Questions', ordering='num_questions')
    def question_count(self, obj):
        return obj.num_questions

    def get_readonly_fields(self, request, obj=None):
        # The daily check-in and locks are managed by `setup_assessments`.
        readonly = ['is_daily', 'is_locked']
        if obj and obj.is_locked:
            # Validated instruments: only scheduling and visibility change.
            editable = {'frequency_days', 'order', 'is_active'}
            readonly = [f for f in self.fields if f not in editable]
        elif obj and obj.responses.exists():
            readonly.append('key')
        return readonly

    def has_delete_permission(self, request, obj=None):
        # Deactivate instead, so users' results are never lost.
        if obj and (obj.is_daily or obj.is_locked or obj.responses.exists()):
            return False
        return super().has_delete_permission(request, obj)


class AssessmentResponseItemInline(TabularInline):
    model = AssessmentResponseItem
    fields = ('question_text', 'question_version', 'answer', 'value')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AssessmentResponse)
class AssessmentResponseAdmin(ModelAdmin):
    list_display = ('user', 'questionnaire', 'total_score', 'severity', 'created_at')
    list_filter = ('questionnaire', 'severity', 'created_at')
    list_select_related = ('user', 'questionnaire')
    search_fields = ('user__email',)
    fields = ('user', 'questionnaire', 'daily_report', 'total_score', 'severity', 'created_at')
    readonly_fields = fields
    inlines = [AssessmentResponseItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
