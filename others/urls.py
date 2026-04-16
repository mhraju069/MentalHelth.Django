from django.urls import path
from .views import (
    DailyReportView,
    GetReportView,
    getInsightsView,
    AIChatSendMessageView,
    AIChatHistoryView,
    AIChatClearView,
    FeedbackView,
    FCMDeviceView,
    NotificationListView,
    MarkNotificationReadView,
    TestFCMNotificationView,
)

urlpatterns = [
    path('checkin/', DailyReportView.as_view()),
    path('report/', GetReportView.as_view()),
    path('insights/', getInsightsView.as_view()),
    path('feedback/', FeedbackView.as_view()),
    path('chat/send/', AIChatSendMessageView.as_view()),
    path('chat/history/', AIChatHistoryView.as_view()),
    path('chat/clear/', AIChatClearView.as_view()),
    path('fcm/device/', FCMDeviceView.as_view()),
    path('notifications/', NotificationListView.as_view()),
    path('notifications/<uuid:pk>/read/', MarkNotificationReadView.as_view()),
    path('test/fcm/', TestFCMNotificationView.as_view()),
]