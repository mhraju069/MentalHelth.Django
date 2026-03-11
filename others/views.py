from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import DailyReport
from .serializes import DailyReportSerializer
# Create your views here.

class DailyReportView(generics.ListCreateAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DailyReport.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        return serializer.save(user=self.request.user)