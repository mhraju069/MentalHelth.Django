from django.urls import path
from .views import (
    DailyReportView,
    GetReportView,
    getInsightsView,
    AIChatSendMessageView,
    AIChatHistoryView,
    AIChatClearView,
)

urlpatterns = [
    path('checkin/', DailyReportView.as_view()),
    path('report/', GetReportView.as_view()),
    path('insights/', getInsightsView.as_view()),

    # AI Chat (HTTP — replaces WebSocket)
    path('chat/send/', AIChatSendMessageView.as_view()),
    path('chat/history/', AIChatHistoryView.as_view()),
    path('chat/clear/', AIChatClearView.as_view()),
]