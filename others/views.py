from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import DailyReport
from .serializes import DailyReportSerializer
from rest_framework import views
from rest_framework.response import Response
from django.db import models
from datetime import datetime
from django.utils import timezone
# Create your views here.

class DailyReportView(generics.ListCreateAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DailyReport.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        return serializer.save(user=self.request.user)


class GetReportView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = datetime.now().month
        year = datetime.now().year

        reports = DailyReport.objects.filter(
            user=request.user,
            time__year=year,
            time__month=month
        )
        
        return Response({
            "level": self.get_level(reports),
            "top_emotions": self.get_top_emotions(reports),
            "streak": self.get_streak(reports),
            "average_mood": self.get_average_score(reports),
            "entries": DailyReport.objects.filter(user=request.user).count(),
        })

    def get_level(self, reports):

        # Bucket the assessments into 4 weeks
        weeks = {1: [], 2: [], 3: [], 4: []}
        for report in reports:
            day = report.time.day
            # Distribute days into up to 4 weeks (Days 1-7, 8-14, 15-21, 22+)
            week_num = min((day - 1) // 7 + 1, 4)
            weeks[week_num].append(report.assesment)

        data = []
        for week_num, assessments in weeks.items():
            total_for_week = len(assessments)
            if total_for_week == 0:
                data.append({
                    "week": f"Week {week_num}",
                    "top_assesment": None,
                    "percentage": 0
                })
            else:
                # Count frequency of each assessment
                counts = {}
                for a in assessments:
                    counts[a] = counts.get(a, 0) + 1
                
                # Get the top assessment
                top_assesment = max(counts, key=counts.get)
                top_count = counts[top_assesment]
                
                # Calculate percentage
                percentage = round((top_count / total_for_week) * 100, 2)
                
                data.append({
                    "week": f"Week {week_num}",
                    "top_assesment": top_assesment,
                    "percentage": percentage
                })

        return data
    def get_top_emotions(self, reports):
        total_reports = reports.count()
        if total_reports == 0:
            return []
            
        emotion_counts = reports.values('assesment').annotate(count=models.Count('id')).order_by('-count')
        
        data = []
        for item in emotion_counts:
            data.append({
                "assesment": item['assesment'],
                "count": item['count'],
                "percentage": round((item['count'] / total_reports) * 100, 2)
            })

        return data
    def get_streak(self, reports):

        report_dates = reports.dates('time', 'day', order='DESC')
        
        streak = 0
        today = timezone.now().date()
        
        previous_date = None
        for report_date in report_dates:
            if previous_date is None:
                # The streak must start either today or yesterday to be active
                if (today - report_date).days <= 1:
                    streak += 1
                    previous_date = report_date
                else:
                    # Streak is broken
                    if (today - report_date).days > 1:
                        break
            else:
                # Check for consecutive days backwards
                if (previous_date - report_date).days == 1:
                    streak += 1
                    previous_date = report_date
                else:
                    # Gap found, streak ends
                    break
                    
        return streak
    def get_average_score(self, reports):
        total_reports = reports.count()
        if total_reports == 0:
            return "0/10"
        
        total_score = reports.aggregate(total_score=models.Sum('score'))['total_score']
        average_score = round(total_score / total_reports, 2)
        
        return f"{average_score}/10"