from django.urls import path
from .views import DailyReportView

urlpatterns = [
    path('checkin/', DailyReportView.as_view()),
]