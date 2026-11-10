from rest_framework import serializers
from .assessments import build_items, daily_questions, record_daily_response
from .models import (
    AssessmentOption, AssessmentQuestion, AssessmentResponse, AssessmentResponseItem,
    DailyReport, Feedback, FCMDevice, Notification, Questionnaire,
)


class AssessmentOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentOption
        fields = ('id', 'label', 'value')


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentQuestion
        fields = ('id', 'key', 'version', 'text', 'help_text', 'question_type', 'is_required', 'saves_as_tags', 'options')

    def get_options(self, obj):
        # Options are prefetched as active-only by the view.
        return AssessmentOptionSerializer(obj.options.all(), many=True).data


class QuestionnaireSummarySerializer(serializers.ModelSerializer):
    """A questionnaire in the list, with when the user last did it."""
    last_completed_at = serializers.SerializerMethodField()
    next_due_at = serializers.SerializerMethodField()
    is_due = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = ('key', 'name', 'description', 'frequency_days', 'last_completed_at', 'next_due_at', 'is_due')

    def _last(self, obj):
        # Set by the view: {questionnaire_id: latest created_at}.
        return self.context.get('last_completed', {}).get(obj.id)

    def get_last_completed_at(self, obj):
        last = self._last(obj)
        return last.isoformat() if last else None

    def get_next_due_at(self, obj):
        from datetime import timedelta
        last = self._last(obj)
        if not last or not obj.frequency_days:
            return None
        return (last + timedelta(days=obj.frequency_days)).isoformat()

    def get_is_due(self, obj):
        from datetime import timedelta
        from django.utils import timezone
        last = self._last(obj)
        if not last:
            return True
        if not obj.frequency_days:
            return False
        return timezone.now() >= last + timedelta(days=obj.frequency_days)


class QuestionnaireDetailSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = ('key', 'name', 'description', 'instructions', 'copyright_notice', 'scoring', 'severity_bands', 'questions')

    def get_questions(self, obj):
        # Prefetched as active-only by the view.
        return AssessmentQuestionSerializer(obj.questions.all(), many=True).data


class AssessmentResponseItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentResponseItem
        fields = ('question_key', 'question_version', 'question_text', 'question_type', 'answer', 'value')


class AssessmentResponseSerializer(serializers.ModelSerializer):
    questionnaire = serializers.SlugRelatedField(slug_field='key', read_only=True)
    items = AssessmentResponseItemSerializer(many=True, read_only=True)
    # Incoming: [{"question_id": "<uuid>", "answer": "label" | ["label", ...] | "text"}]
    answers = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = AssessmentResponse
        fields = ('id', 'questionnaire', 'total_score', 'severity', 'needs_safety_followup', 'created_at', 'items', 'answers')
        read_only_fields = ('id', 'total_score', 'severity', 'needs_safety_followup', 'created_at')

    def validate_answers(self, value):
        questionnaire = self.context['questionnaire']
        return build_items(list(questionnaire.questions.all()), value)


class DailyReportSerializer(serializers.ModelSerializer):
    # Incoming: [{"question_id": "<uuid>", "answer": "text" | ["label", ...]}]
    # Stored:   a snapshot that also carries the question text and type.
    answers = serializers.ListField(child=serializers.DictField(), required=False)

    class Meta:
        model = DailyReport
        exclude = ('updated_at',)
        read_only_fields = ('user', 'created_at')

    def validate_answers(self, value):
        return build_items(list(daily_questions()), value)

    def create(self, validated_data):
        report = super().create(validated_data)
        # Also store the answers in the queryable responses table.
        record_daily_response(report)
        return report

    def _validate_ratings(self, attrs):
        if attrs.get('mood_rating') is None:
            # Older app versions send the mood label instead of a rating.
            if not attrs.get('assesment'):
                raise serializers.ValidationError({'mood_rating': 'Please rate your mood.'})
            return

        if attrs.get('anxiety_rating') is None:
            raise serializers.ValidationError({'anxiety_rating': 'Please rate your anxiety.'})

        sleep_hours = attrs.get('sleep_hours')
        if sleep_hours is not None and (sleep_hours * 2) % 1:
            raise serializers.ValidationError({'sleep_hours': 'Use half-hour steps, e.g. 7 or 7.5.'})

        if attrs.get('check_in_type', DailyReport.DETAILED) == DailyReport.DETAILED:
            if sleep_hours is None:
                raise serializers.ValidationError({'sleep_hours': 'Please enter how long you slept.'})
            if not attrs.get('sleep_quality'):
                raise serializers.ValidationError({'sleep_quality': 'Please choose how well you slept.'})

    def validate(self, attrs):
        self._validate_ratings(attrs)

        answers = attrs.get('answers')
        # Older app versions send `tags` directly; newer ones send answers
        # and the tags are derived from questions marked "saves as tags".
        if answers:
            tag_questions = set(
                str(pk) for pk in AssessmentQuestion.objects.filter(saves_as_tags=True).values_list('id', flat=True)
            )
            tags = []
            for item in answers:
                if item['question_id'] in tag_questions:
                    values = item['answer'] if isinstance(item['answer'], list) else [item['answer']]
                    tags.extend(v for v in values if v not in tags)
            attrs['tags'] = tags
        return attrs


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
        # The rating is what matters; the comment is optional.
        extra_kwargs = {'feedback': {'required': False, 'allow_blank': True}}

    def validate_stars(self, value):
        # Stored as text; only whole ratings from 1 to 5 are valid.
        if str(value).strip() not in {'1', '2', '3', '4', '5'}:
            raise serializers.ValidationError('Choose a rating from 1 to 5 stars.')
        return str(value).strip()
