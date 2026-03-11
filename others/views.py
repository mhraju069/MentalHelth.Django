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
        
        # Initialize dictionary with all possible assessments set to 0
        choices = ['excellent', 'good', 'neutral', 'sad', 'depressed']
        data_dict = {choice: {"assesment": choice, "count": 0, "percentage": 0.0} for choice in choices}

        if total_reports > 0:
            emotion_counts = reports.values('assesment').annotate(count=models.Count('id'))
            
            # Map the actual counts and percentages from DB results
            for item in emotion_counts:
                assesment = item['assesment']
                count = item['count']
                if assesment in data_dict:
                    data_dict[assesment]['count'] = count
                    data_dict[assesment]['percentage'] = round((count / total_reports) * 100, 2)
                    
        # Convert dictionary back to list and sort by highest count
        data = sorted(data_dict.values(), key=lambda x: x['count'], reverse=True)

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


class getInsightsView(GetReportView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reports = DailyReport.objects.filter(user=request.user, time__year=datetime.now().year, time__month=datetime.now().month)

        return Response({
            "entries": reports.count(),
            "average_mood": self.get_average_score(reports),
            "mood_trend": self.mood_trend(reports),
            "best_day": self.best_day(reports),
            "summary": self.get_top_emotions(reports),
        })
        
    def get_average_score(self, reports):
            total_reports = reports.count()
            if total_reports == 0:
                return "0/10"
            
            total_score = reports.aggregate(total_score=models.Sum('score'))['total_score']
            average_score = round(total_score / total_reports, 2)
            
            return f"{average_score}/10"

    def mood_trend(self, reports):
        from datetime import timedelta
        today = datetime.now()
        first_day_of_month = today.replace(day=1)
        last_month = first_day_of_month - timedelta(days=1)
        
        last_month_reports = DailyReport.objects.filter(
            user=self.request.user, 
            time__year=last_month.year, 
            time__month=last_month.month
        )
        
        current_total = reports.count()
        last_total = last_month_reports.count()
        
        current_avg = 0
        if current_total > 0:
            current_score = reports.aggregate(total_score=models.Sum('score'))['total_score'] or 0
            current_avg = current_score / current_total
            
        last_avg = 0
        if last_total > 0:
            last_score = last_month_reports.aggregate(total_score=models.Sum('score'))['total_score'] or 0
            last_avg = last_score / last_total
            
        if last_avg == 0 and current_avg > 0:
            trend = 100
        elif last_avg == 0 and current_avg == 0:
            trend = 0
        else:
            trend = ((current_avg - last_avg) / last_avg) * 100
            
        return f"+{round(trend)}%" if trend > 0 else f"{round(trend)}%"

    def get_top_emotions(self, reports):
        total_reports = reports.count()
        
        # Initialize dictionary with all possible assessments set to 0
        choices = ['excellent', 'good', 'neutral', 'sad', 'depressed']
        data_dict = {choice: {"assesment": choice, "count": 0, "percentage": 0.0} for choice in choices}

        if total_reports > 0:
            emotion_counts = reports.values('assesment').annotate(count=models.Count('id'))
            
            # Map the actual counts and percentages from DB results
            for item in emotion_counts:
                assesment = item['assesment']
                count = item['count']
                if assesment in data_dict:
                    data_dict[assesment]['count'] = count
                    data_dict[assesment]['percentage'] = round((count / total_reports) * 100, 2)
                    
        # Convert dictionary back to list and sort by highest count
        data = sorted(data_dict.values(), key=lambda x: x['count'], reverse=True)

        return data
        
    def best_day(self, reports):
        if not reports.exists():
            return {"day": None, "avg": 0}
            
        day_scores = {}
        for report in reports:
            day_name = report.time.strftime('%a')
            if day_name not in day_scores:
                day_scores[day_name] = []
            if report.score is not None:
                day_scores[day_name].append(report.score)
                
        best_d = None
        best_avg = -1
        
        for d, scores in day_scores.items():
            if scores:
                avg = sum(scores) / len(scores)
                if avg > best_avg:
                    best_avg = avg
                    best_d = d
                    
        return {"day": best_d, "avg": round(best_avg, 1)}