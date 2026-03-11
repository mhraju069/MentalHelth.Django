from django.urls import path
from .views import DailyReportView, GetReportView, getInsightsView

urlpatterns = [
    path('checkin/', DailyReportView.as_view()),
    path('report/', GetReportView.as_view()),
    path('insights/', getInsightsView.as_view()),
]