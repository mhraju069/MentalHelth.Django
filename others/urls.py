from django.urls import path
from .views import DailyReportView, GetReportView

urlpatterns = [
    path('checkin/', DailyReportView.as_view()),
    path('report/', GetReportView.as_view()),
]