"""Admin home page: OpenAI credits and usage (UNFOLD["DASHBOARD_CALLBACK"])."""
import json
import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from . import openai_billing

logger = logging.getLogger(__name__)


def dashboard_callback(request, context):
    if not request.user.is_superuser:
        return context
    try:
        data = openai_billing.dashboard_data()
    except Exception:
        # Never break the admin home page over the dashboard.
        logger.exception("Could not build the OpenAI dashboard")
        return context
    data["cost_chart"] = json.dumps(data["cost_chart"])
    data["token_chart"] = json.dumps(data["token_chart"])
    context["openai"] = data
    return context


@staff_member_required
@require_POST
def sync_openai_now(request):
    if not request.user.is_superuser:
        return redirect("admin:index")
    if not openai_billing._admin_key():
        messages.error(request, "Set OPENAI_ADMIN_KEY on the server first.")
        return redirect("admin:index")
    try:
        days = openai_billing.sync_usage()
    except openai_billing.OpenAIBillingError as exc:
        messages.error(request, f"OpenAI sync failed: {exc}")
        return redirect("admin:index")

    from django.utils import timezone
    billing = openai_billing.OpenAIBillingSettings.load()
    billing.last_synced_at = timezone.now()
    billing.last_sync_error = ""
    billing.save(update_fields=["last_synced_at", "last_sync_error"])
    messages.success(request, f"Updated {days} day{'s' if days != 1 else ''} of OpenAI usage.")
    return redirect("admin:index")
