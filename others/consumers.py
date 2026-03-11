import json
import sys
import requests
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import AIChatSession, AIChatMessage
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

def log(msg):
    print(msg, flush=True)

SYSTEM_PROMPT = (
    "You are Dr. Freud AI, a warm and empathetic mental health companion. "
    "Your job is to listen actively, uplift the user's mood, and offer practical suggestions "
    "to help them feel better. Be conversational, concise, and never give medical diagnoses. "
    "Always respond with care and encouragement."
)

OPENROUTER_API_KEY = "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"


class TherapistChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        log("[WS] connect() called")
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token_list = params.get('token', [])
        token = token_list[0] if token_list else None

        log(f"[WS] token found: {bool(token)}")

        if not token:
            log("[WS] No token, closing")
            await self.close(code=4001)
            return

        try:
            access_token = AccessToken(token)
            user_id = access_token.payload['user_id']
            self.user = await sync_to_async(User.objects.get)(id=user_id)
            log(f"[WS] Authenticated user: {self.user.id}")
        except Exception as e:
            log(f"[WS] Auth failed: {e}")
            await self.close(code=4002)
            return

        # Get or create a single session per user
        self.session, created = await sync_to_async(
            AIChatSession.objects.get_or_create
        )(user=self.user)
        self.session_id = str(self.session.id)
        log(f"[WS] Session: {self.session_id} (created={created})")

        if created:
            await sync_to_async(AIChatMessage.objects.create)(
                session=self.session, role='system', content=SYSTEM_PROMPT
            )

        self.room_group_name = f'chat_user_{self.user.id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        log("[WS] Connection accepted")

        # Send chat history on connect
        history = await self.get_full_history()
        await self.send(json.dumps({
            'type': 'chat_history',
            'session_id': self.session_id,
            'messages': history
        }))

    async def disconnect(self, close_code):
        log(f"[WS] disconnect() code={close_code}")
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        log(f"[WS] receive() raw: {text_data[:200]}")
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError as e:
            log(f"[WS] JSON error: {e}")
            await self.send(json.dumps({'type': 'error', 'message': 'Invalid JSON.'}))
            return

        user_message = data.get('message', '').strip()
        log(f"[WS] user_message: {user_message}")

        if not user_message:
            return

        # Save user message
        await sync_to_async(AIChatMessage.objects.create)(
            session=self.session, role='user', content=user_message
        )

        # Get context window
        messages = await self.get_message_history()
        log(f"[WS] Sending {len(messages)} messages to OpenRouter")

        # Call AI
        ai_response = await self.call_openrouter_api(messages)
        log(f"[WS] AI response: {str(ai_response)[:200]}")

        # Save and send AI reply
        if ai_response:
            await sync_to_async(AIChatMessage.objects.create)(
                session=self.session, role='assistant', content=ai_response
            )
            await self.send(json.dumps({
                'type': 'chat_message',
                'message': ai_response
            }))

    @sync_to_async
    def get_full_history(self):
        msgs = AIChatMessage.objects.filter(
            session=self.session
        ).exclude(role='system').order_by('created_at')
        return [{'role': m.role, 'content': m.content} for m in msgs]

    @sync_to_async
    def get_message_history(self):
        # Last 30 messages reversed (newest first, then flipped)
        msgs = list(
            AIChatMessage.objects.filter(session=self.session).order_by('-created_at')[:30]
        )
        msgs.reverse()

        history = [{'role': m.role, 'content': m.content} for m in msgs]

        # Ensure system prompt is always first
        has_system = any(m['role'] == 'system' for m in history)
        if not has_system:
            sys_msg = AIChatMessage.objects.filter(session=self.session, role='system').first()
            if sys_msg:
                history.insert(0, {'role': 'system', 'content': sys_msg.content})

        return history

    @sync_to_async
    def call_openrouter_api(self, messages):
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dexter.app",
            "X-Title": "Dexter Therapist AI"
        }
        payload = {
            "model": "google/gemini-2.0-flash-lite-001",
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 500
        }
        try:
            log(f"[OpenRouter] Calling API with {len(messages)} messages...")
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            log(f"[OpenRouter] Status: {res.status_code}")
            log(f"[OpenRouter] Body: {res.text[:600]}")

            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content']
            else:
                error = res.json().get('error', {})
                msg = error.get('message', 'Unknown OpenRouter error')
                return f"(I'm having a moment — {msg})"
        except Exception as e:
            log(f"[OpenRouter] Exception: {e}")
            return "Sorry, I couldn't reach my thoughts right now. Please try again."
