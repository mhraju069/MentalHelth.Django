import logging
import requests
from requests.exceptions import ConnectionError, Timeout, HTTPError
from rest_framework import generics, views, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .models import DailyReport, AIChatSession, AIChatMessage
from .serializes import DailyReportSerializer
from core.pagination import CustomLimitPagination

logger = logging.getLogger(__name__)

# ─── AI Chat Constants ───────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are Dr. Freud AI — a warm, empathetic mental health companion. "
    "Rules: "
    "1) Keep every reply to 2-3 short sentences max. "
    "2) Listen actively, validate feelings, then offer one practical tip. "
    "3) Be casual and friendly — like a caring friend, not a textbook. "
    "4) Never diagnose, prescribe, or write long paragraphs. "
    "5) Use emojis sparingly to add warmth."
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-001"
OPENROUTER_TIMEOUT = 30  # seconds
MAX_CONTEXT_MESSAGES = 30
MAX_MESSAGE_LENGTH = 2000


# ─── AI Chat Views ───────────────────────────────────────────────────────────

class AIChatSendMessageView(views.APIView):
    """
    POST /api/chat/send/
    Send a message and receive an AI response.

    Request body:   
    Response:      { "reply": "...", "session_id": "..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = (request.data.get("message") or "").strip()

        if not user_message:
            return Response(
                {"error": "Message cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(user_message) > MAX_MESSAGE_LENGTH:
            return Response(
                {"error": f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Get or create session ────────────────────────────────────────
        try:
            session, created = AIChatSession.objects.get_or_create(user=request.user)
        except Exception:
            logger.exception("Failed to get/create chat session")
            return Response(
                {"error": "Could not initialise chat session. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if created:
            AIChatMessage.objects.create(
                session=session, role="system", content=SYSTEM_PROMPT
            )

        # ── Save user message ────────────────────────────────────────────
        AIChatMessage.objects.create(
            session=session, role="user", content=user_message
        )

        # ── Build context window ─────────────────────────────────────────
        messages = self._build_context(session)

        # ── Call OpenRouter ──────────────────────────────────────────────
        ai_reply, error_response = self._call_openrouter(messages)

        if error_response is not None:
            return error_response

        # ── Save AI reply ────────────────────────────────────────────────
        obj = AIChatMessage.objects.create(
            session=session, role="assistant", content=ai_reply
        )

        return Response({
            "message": ai_reply,
            "time": timezone.now().isoformat(),
        })

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_context(session):
        """Return last N messages with system prompt always first."""
        msgs = list(
            AIChatMessage.objects.filter(session=session)
            .order_by("-created_at")[:MAX_CONTEXT_MESSAGES]
        )
        msgs.reverse()

        history = [{"role": m.role, "content": m.content} for m in msgs]

        # Ensure system prompt is present
        if not any(m["role"] == "system" for m in history):
            sys_msg = AIChatMessage.objects.filter(
                session=session, role="system"
            ).first()
            if sys_msg:
                history.insert(0, {"role": "system", "content": sys_msg.content})

        return history

    @staticmethod
    def _call_openrouter(messages):
        """
        Call the OpenRouter API.
        Returns (reply_text, None) on success or (None, Response) on failure.
        """
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            logger.error("OPENROUTER_API_KEY is not configured")
            return None, Response(
                {"error": "AI service is not configured. Please contact support."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dexter.app",
            "X-Title": "Dexter Therapist AI",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 500,
        }

        try:
            res = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=OPENROUTER_TIMEOUT,
            )
        except Timeout:
            logger.warning("OpenRouter request timed out")
            return None, Response(
                {"error": "The AI took too long to respond. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except ConnectionError:
            logger.warning("Could not connect to OpenRouter")
            return None, Response(
                {"error": "Could not reach the AI service. Check your connection and try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.exception("Unexpected error calling OpenRouter: %s", exc)
            return None, Response(
                {"error": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Handle HTTP-level errors ─────────────────────────────────────
        if res.status_code == 429:
            logger.warning("OpenRouter rate-limited: %s", res.text[:300])
            return None, Response(
                {"error": "AI service is busy right now. Please wait a moment and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if res.status_code == 401:
            logger.error("OpenRouter auth failed (401)")
            return None, Response(
                {"error": "AI service authentication error. Please contact support."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if res.status_code != 200:
            try:
                err_body = res.json().get("error", {})
                err_msg = err_body.get("message", "Unknown error")
            except Exception:
                err_msg = res.text[:200]
            logger.error("OpenRouter error %s: %s", res.status_code, err_msg)
            return None, Response(
                {"error": f"AI service error: {err_msg}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ── Parse successful response ────────────────────────────────────
        try:
            data = res.json()
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("Malformed OpenRouter response: %s – %s", exc, res.text[:300])
            return None, Response(
                {"error": "Received an invalid response from the AI. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return reply, None


class AIChatHistoryView(views.APIView):
    """
    GET /api/chat/history/?page=1&page_size=20
    Returns paginated chat history, recent messages first.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitPagination

    def get(self, request):
        session = AIChatSession.objects.filter(user=request.user).first()

        if not session:
            return Response({"session_id": None, "messages": [], "count": 0, "next": None, "previous": None})

        queryset = (
            AIChatMessage.objects.filter(session=session)
            .exclude(role="system")
            .order_by("-created_at")
        )

        paginator = CustomLimitPagination()
        page = paginator.paginate_queryset(queryset, request)

        messages = [
            {"role": m.role, "message": m.content, "time": m.created_at}
            for m in page
        ]

        return Response({
            "session_id": str(session.id),
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "messages": messages,
        })


class AIChatClearView(views.APIView):
    """
    DELETE /api/chat/clear/
    Clears ALL messages and resets the session with a fresh system prompt.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        session = AIChatSession.objects.filter(user=request.user).first()
        if not session:
            return Response({"detail": "No chat session found."}, status=status.HTTP_404_NOT_FOUND)

        AIChatMessage.objects.filter(session=session).delete()

        # Re-create system prompt
        AIChatMessage.objects.create(
            session=session, role="system", content=SYSTEM_PROMPT
        )

        return Response({"detail": "Chat history cleared."})



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


class FeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)