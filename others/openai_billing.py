"""
OpenAI credits and usage for the admin dashboard, plus low-credit warnings.

OpenAI does not offer an API for the remaining prepaid credit balance. What
it does offer (with an Admin API key, not the normal key the chat uses) is:

- the Costs API: dollars spent per day, and
- the Usage API: tokens and requests per day.

So the balance shown here is an estimate: credits entered by an admin
(OpenAICredit) minus the costs OpenAI reports since the first entry. When
OpenAI actually runs out, the chat gets a 429 "insufficient_quota" error;
report_out_of_credit() sends a warning right away in that case.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Min, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from .models import OpenAIBillingSettings, OpenAICredit, OpenAIDailyUsage

logger = logging.getLogger(__name__)

API_BASE = "https://api.openai.com/v1/organization"
TIMEOUT = 30
BILLING_URL = "https://platform.openai.com/settings/organization/billing/overview"

# Warn when the credit would run out within this many days at the recent
# spending rate, even if it is still above the dollar threshold.
LOW_DAYS_LEFT = 7
# While the balance stays low, repeat the warning at most this often.
LOW_ALERT_REPEAT = timedelta(hours=24)
OUT_OF_CREDIT_REPEAT = timedelta(hours=6)
# Days synced on every run (OpenAI fills in recent days late).
RECENT_DAYS = 7
CHART_DAYS = 30
MAX_BACKFILL_DAYS = 365


class OpenAIBillingError(Exception):
    pass


# ─── Fetching from OpenAI ────────────────────────────────────────────────────

def _admin_key():
    return getattr(settings, "OPENAI_ADMIN_KEY", "") or ""


def _get_buckets(endpoint, params):
    """All daily buckets from a Costs/Usage endpoint, following pagination."""
    headers = {"Authorization": f"Bearer {_admin_key()}"}
    buckets, page = [], None
    for _ in range(50):  # safety stop
        query = dict(params, **({"page": page} if page else {}))
        try:
            res = requests.get(f"{API_BASE}/{endpoint}", headers=headers, params=query, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise OpenAIBillingError(f"Could not reach OpenAI: {exc}") from exc
        if res.status_code != 200:
            try:
                message = res.json().get("error", {}).get("message") or res.text[:200]
            except ValueError:
                message = res.text[:200]
            raise OpenAIBillingError(f"OpenAI {endpoint} returned {res.status_code}: {message}")
        body = res.json()
        buckets.extend(body.get("data", []))
        page = body.get("next_page")
        if not body.get("has_more") or not page:
            break
    return buckets


def _bucket_date(bucket):
    return datetime.fromtimestamp(bucket["start_time"], tz=dt_timezone.utc).date()


def _sync_start(today):
    """First day to fetch: recent days, plus any history the dashboard still lacks."""
    wanted = today - timedelta(days=CHART_DAYS)
    first_credit = OpenAICredit.objects.aggregate(d=Min("added_on"))["d"]
    if first_credit:
        wanted = min(wanted, first_credit)
    wanted = max(wanted, today - timedelta(days=MAX_BACKFILL_DAYS))

    oldest_stored = OpenAIDailyUsage.objects.aggregate(d=Min("date"))["d"]
    start = today - timedelta(days=RECENT_DAYS)
    if oldest_stored is None or oldest_stored > wanted:
        start = min(start, wanted)
    return start


def sync_usage(today=None):
    """Fetch daily costs and token usage from OpenAI and store them."""
    today = today or timezone.now().astimezone(dt_timezone.utc).date()
    start = _sync_start(today)
    start_ts = int(datetime.combine(start, time.min, tzinfo=dt_timezone.utc).timestamp())
    days = (today - start).days + 1

    costs = _get_buckets("costs", {"start_time": start_ts, "bucket_width": "1d", "limit": min(days, 180)})
    usage = _get_buckets("usage/completions", {"start_time": start_ts, "bucket_width": "1d", "limit": min(days, 31)})

    rows = {}
    for bucket in costs:
        total = sum(
            Decimal(str((r.get("amount") or {}).get("value") or 0)) for r in bucket.get("results", [])
        )
        rows.setdefault(_bucket_date(bucket), {})["cost_usd"] = total
    for bucket in usage:
        results = bucket.get("results", [])
        rows.setdefault(_bucket_date(bucket), {}).update(
            input_tokens=sum(r.get("input_tokens") or 0 for r in results),
            output_tokens=sum(r.get("output_tokens") or 0 for r in results),
            requests=sum(r.get("num_model_requests") or 0 for r in results),
        )

    for day, values in rows.items():
        OpenAIDailyUsage.objects.update_or_create(date=day, defaults=values)
    return len(rows)


# ─── Balance ─────────────────────────────────────────────────────────────────

def balance_summary(today=None):
    """Estimated balance and spending figures, or None if no credit was entered."""
    today = today or timezone.now().astimezone(dt_timezone.utc).date()
    credits = OpenAICredit.objects.aggregate(total=Sum("amount"), first=Min("added_on"))
    if credits["total"] is None:
        return None

    spent = (
        OpenAIDailyUsage.objects.filter(date__gt=credits["first"])
        .aggregate(s=Sum("cost_usd"))["s"] or Decimal(0)
    )
    balance = credits["total"] - spent

    # Recent spending rate: the last 7 full days (today is still filling in).
    week = OpenAIDailyUsage.objects.filter(
        date__gte=today - timedelta(days=7), date__lt=today
    ).aggregate(s=Sum("cost_usd"))["s"] or Decimal(0)
    per_day = week / 7
    days_left = int(balance / per_day) if per_day > 0 and balance > 0 else None

    return {
        "credits": credits["total"],
        "since": credits["first"],
        "spent": spent,
        "balance": balance,
        "per_day": per_day,
        "days_left": days_left,
    }


def is_low(summary, threshold):
    if summary is None:
        return False
    if summary["balance"] <= threshold:
        return True
    return summary["days_left"] is not None and summary["days_left"] <= LOW_DAYS_LEFT


# ─── Alerts ──────────────────────────────────────────────────────────────────

def alert_recipients(billing=None):
    billing = billing or OpenAIBillingSettings.load()
    raw = [getattr(settings, "CONTACT_EMAIL", "") or ""]
    raw += (getattr(settings, "OPENAI_ALERT_EMAILS", "") or "").split(",")
    raw += billing.alert_emails.splitlines()
    seen, out = set(), []
    for email in (e.strip() for e in raw):
        if email and email.lower() not in seen:
            seen.add(email.lower())
            out.append(email)
    return out


def _send_alert(subject, heading, intro, lines, billing):
    recipients = alert_recipients(billing)
    if not recipients:
        logger.error("OpenAI credit alert not sent: no recipients configured")
        return False

    from accounts.email_branding import email_logo_url

    admin_url = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/") + "/admin/"
    html = render_to_string("openai_alert_email.html", {
        "heading": heading,
        "intro": intro,
        "lines": lines,
        "billing_url": BILLING_URL,
        "admin_url": admin_url,
        "logo_src": email_logo_url(),
    })
    text = "\n".join([heading, "", intro, ""] + [f"{k}: {v}" for k, v in lines] + [
        "", f"Add credit: {BILLING_URL}", f"Dashboard: {admin_url}",
    ])
    sender = getattr(settings, "EMAIL_HOST_USER", None) or settings.DEFAULT_FROM_EMAIL
    msg = EmailMultiAlternatives(subject, text, sender, recipients)
    msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except Exception:
        logger.exception("Could not send the OpenAI credit alert")
        return False
    return True


def _money(value):
    return f"${Decimal(value):,.2f}"


def check_balance_and_alert(now=None):
    """Email a warning when the estimated balance is low (at most once a day while low)."""
    now = now or timezone.now()
    billing = OpenAIBillingSettings.load()
    summary = balance_summary(now.astimezone(dt_timezone.utc).date())

    if not is_low(summary, billing.low_balance_threshold):
        if billing.low_alert_sent_at:
            # Back above the line (credit was added): warn again next time it drops.
            billing.low_alert_sent_at = None
            billing.save(update_fields=["low_alert_sent_at"])
        return False

    if billing.low_alert_sent_at and now - billing.low_alert_sent_at < LOW_ALERT_REPEAT:
        return False

    lines = [
        ("Estimated balance", _money(summary["balance"])),
        ("Warning threshold", _money(billing.low_balance_threshold)),
        ("Average spend (last 7 days)", f"{_money(summary['per_day'])} a day"),
    ]
    if summary["days_left"] is not None:
        lines.append(("Runs out in about", f"{summary['days_left']} day{'s' if summary['days_left'] != 1 else ''}"))

    sent = _send_alert(
        "Honeysuckle Trail: OpenAI credit is running low",
        "OpenAI credit is running low",
        "The AI chat in Honeysuckle Trail stops working when the OpenAI credit runs out. "
        "Please add credit soon.",
        lines,
        billing,
    )
    if sent:
        billing.low_alert_sent_at = now
        billing.save(update_fields=["low_alert_sent_at"])
    return sent


def report_out_of_credit(now=None):
    """Called when OpenAI refuses a chat for lack of credit. Rate-limited."""
    now = now or timezone.now()
    billing = OpenAIBillingSettings.load()
    if billing.out_of_credit_alert_sent_at and now - billing.out_of_credit_alert_sent_at < OUT_OF_CREDIT_REPEAT:
        return False

    sent = _send_alert(
        "Honeysuckle Trail: OpenAI credit has run out, AI chat is down",
        "OpenAI credit has run out",
        "OpenAI is refusing AI chat requests because the account has no credit left "
        "(insufficient_quota). The AI chat is not working for anyone until credit is added.",
        [("Detected at", now.strftime("%Y-%m-%d %H:%M UTC"))],
        billing,
    )
    if sent:
        billing.out_of_credit_alert_sent_at = now
        billing.save(update_fields=["out_of_credit_alert_sent_at"])
    return sent


# ─── Scheduled job ───────────────────────────────────────────────────────────

def sync_and_check():
    """Hourly: refresh usage from OpenAI, then send a warning if credit is low."""
    billing = OpenAIBillingSettings.load()
    if not _admin_key():
        billing.last_sync_error = "OPENAI_ADMIN_KEY is not set."
        billing.save(update_fields=["last_sync_error"])
        # Credits may still be entered by hand; the estimate just won't move.
        return check_balance_and_alert()

    try:
        sync_usage()
    except OpenAIBillingError as exc:
        logger.warning("OpenAI usage sync failed: %s", exc)
        billing.last_sync_error = str(exc)[:1000]
        billing.save(update_fields=["last_sync_error"])
        # Don't warn from stale numbers.
        return False

    billing.last_synced_at = timezone.now()
    billing.last_sync_error = ""
    billing.save(update_fields=["last_synced_at", "last_sync_error"])
    return check_balance_and_alert()


# ─── Dashboard ───────────────────────────────────────────────────────────────

def dashboard_data(today=None):
    today = today or timezone.now().astimezone(dt_timezone.utc).date()
    billing = OpenAIBillingSettings.load()
    summary = balance_summary(today)

    start = today - timedelta(days=CHART_DAYS - 1)
    by_day = {u.date: u for u in OpenAIDailyUsage.objects.filter(date__gte=start)}
    days = [start + timedelta(days=i) for i in range(CHART_DAYS)]
    labels = [d.strftime("%b %d") for d in days]

    def value(day, field):
        row = by_day.get(day)
        return getattr(row, field) if row else 0

    cost_chart = {
        "labels": labels,
        "datasets": [{
            "label": "Spend (USD)",
            "data": [round(float(value(d, "cost_usd")), 4) for d in days],
            "backgroundColor": "var(--color-primary-600)",
        }],
    }
    token_chart = {
        "labels": labels,
        "datasets": [
            {
                "label": "Input tokens",
                "data": [value(d, "input_tokens") for d in days],
                "borderColor": "var(--color-primary-600)",
                "backgroundColor": "var(--color-primary-600)",
            },
            {
                "label": "Output tokens",
                "data": [value(d, "output_tokens") for d in days],
                "borderColor": "var(--color-base-400)",
                "backgroundColor": "var(--color-base-400)",
            },
        ],
    }

    month_start = today.replace(day=1)
    month = OpenAIDailyUsage.objects.filter(date__gte=month_start).aggregate(
        cost=Sum("cost_usd"), requests=Sum("requests"),
        input=Sum("input_tokens"), output=Sum("output_tokens"),
    )

    status = "unknown"
    if summary is not None:
        if summary["balance"] <= 0:
            status = "empty"
        elif is_low(summary, billing.low_balance_threshold):
            status = "low"
        else:
            status = "ok"

    percent_left = None
    if summary and summary["credits"] > 0:
        percent_left = max(0, min(100, int(summary["balance"] / summary["credits"] * 100)))

    return {
        "has_admin_key": bool(_admin_key()),
        "summary": summary,
        "status": status,
        "percent_left": percent_left,
        "threshold": billing.low_balance_threshold,
        "month_cost": month["cost"] or Decimal(0),
        "month_requests": month["requests"] or 0,
        "month_tokens_display": f"{(month['input'] or 0) + (month['output'] or 0):,}",
        "has_usage": bool(by_day),
        "cost_chart": cost_chart,
        "token_chart": token_chart,
        "last_synced_at": billing.last_synced_at,
        "last_sync_error": billing.last_sync_error,
        "recipients": alert_recipients(billing),
        "billing_url": BILLING_URL,
    }
