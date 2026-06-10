# Honeysuckle Trail API Backend

[![Django](https://img.shields.io/badge/Django-5.0+-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/DRF-API-ff1709?style=for-the-badge&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Celery](https://img.shields.io/badge/Celery-Workers-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)

Welcome to the backend API for **Honeysuckle Trail**, a supportive mental health, mood-tracking, and journaling application. This platform provides secure, personalized user authentication, daily check-ins with mood scoring, dynamic AI insights and companion chatting, push notification scheduling, and a premium administrative dashboard.


## 🛠️ Technology Stack

* **Web Framework:** Django & Django REST Framework (DRF)
* **Database:** PostgreSQL (with `psycopg2-binary`)
* **Task Queues:** Celery (Worker + Beat scheduler) & Redis (Broker & backend)
* **AI Service:** OpenAI API (`gpt-4o-mini` configuration)
* **Push Notifications & Auth:** Firebase Admin SDK (FCM and Firebase Token Verification)
* **Web Server & Reverse Proxy:** Nginx with SSL/TLS (Certbot / Let's Encrypt), Gzip compression, and optimized CSP headers
* **Deployment:** Docker & Docker Compose containerization
* **Admin Interface:** `django-unfold` (modern, Tailwind-based admin panel configured with brand-specific color palettes)

---

## 🚀 Completed Features Summary

### 1. User Account & Authentication Management
* **Credentials Sign-up/Sign-in:** Standard secure sign-up, sign-in, and refresh token endpoints using JWT (`rest_framework_simplejwt`).
* **Firebase Social Integration:** Verification of Firebase ID tokens for one-click OAuth login, automatic sync of Firebase profile photos, and fallback OTP generation.
* **Secure OTP System:** Four-digit OTP delivery via SMTP email (using a clean HTML template with embedded logo assets) with rate-limiting & cooldown locks to prevent brute-force attacks.
* **Profile Management:** Custom attributes such as bio, profile cover/images, daily check-in time preference, and notification opt-ins.

### 2. Daily Check-ins & Reflection Tracking
* **Mood Assessment:** Five-level assessment spectrum (`excellent`, `good`, `neutral`, `sad`, `depressed`) mapped to an internal scoring system (`10`, `8`, `6`, `4`, `2`) to measure emotional health over time.
* **Journaling:** Safe keeping of rich journal content accompanied by tag lists.
* **Dynamic Streak Calculator:** Keeps track of consecutive daily check-ins and detects gaps automatically.

### 3. AI Companion Chat (Honeysuckle Trail AI)
* **System Prompt Isolation:** Injected with warm, calm, empathetic, and non-judgmental instructions.
* **Context Preservation:** Keeps up to 30 past messages of history, with the system prompt constantly injected as the root context.
* **Medical Safeguards:** Configured to strictly avoid clinical diagnoses, medication instructions, and to direct users to crisis lines (e.g., 988 in the US) if self-harm or immediate danger is detected.

### 4. Aggregated Insights & Analytics
* **Emotion Summaries:** Dynamic percentage splits of registered emotions.
* **Weekly Aggregates:** Categorization of reports into weeks with top emotions and frequency percentage.
* **Best Day Index:** Detects which day of the week holds the highest average mood score.
* **Mood Trends:** Compares current month averages to the previous month, producing a clean percentage change trend.

### 5. Push Notification System (FCM)
* **FCM Token Registry:** Endpoint to associate user devices with Firebase registration tokens.
* **Automatic Token Cleanup:** Detects invalid/expired tokens during push dispatches and automatically deactivates them.
* **Streak Milestone Alerts:** Triggers celebratory notifications on 3rd and 7th day check-in milestones.
* **Scheduled Daily Reminders:** Celery Beat schedules a periodic task that runs every minute to dispatch a randomized check-in reminder to users whose preferred `checkin_time` matches the current system time.

---

## 🔌 Setup & Integrations

The system integrates several external services. Follow the instructions below to configure them:

### 1. Firebase Admin SDK Integration
1. Place your service account certificate file named `firebase-key.json` in the root directory.
2. The project will automatically load it on startup to initialize `firebase-admin` for FCM and authentication.

### 2. Email SMTP (OTP Services)
Configure the outgoing email credentials in your `.env` file to support mail dispatches. The backend employs `django.core.mail` with `smtplib` over TLS.

### 3. OpenAI Integration
Configure `OPENAI_API_KEY` to enable the journaling companion AI chat. The app connects to the `gpt-4o-mini` model with a 30-second timeout.

---

## 📝 Environment Variables (`.env`)

Create a `.env` file in the root directory and populate it with the following configuration:

```env
# General Settings
DEBUG=False
SECRET_KEY=your-django-secret-key
ALLOWED_HOSTS=api.thehoneysucklecompany.com,localhost

# CORS & CSRF
CORS_ALLOW_ORIGINS=https://api.thehoneysucklecompany.com,http://localhost:3000
CSRF_TRUSTED_ORIGINS=https://api.thehoneysucklecompany.com,http://localhost:3000

# Database Settings
DB_NAME=honeysuckle_db
DB_USER=honeysuckle_user
DB_PASSWORD=secure_password
DB_HOST=db
DB_PORT=5432

# SMTP Email Configuration
EMAIL_HOST_USER=notifications@yourdomain.com
EMAIL_HOST_PASSWORD=smtp_app_password
DEFAULT_FROM_EMAIL=Honey Suckle Trail <notifications@yourdomain.com>
CONTACT_EMAIL=support@yourdomain.com

# Stripe Integration (Optional)
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# OpenAI Integration
OPENAI_API_KEY=sk-proj-...

# Celery & Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

---

## 🐳 Docker Deployment

The application runs using a multi-container Docker Compose layout:

```bash
# 1. Build and compile the Docker images
docker compose build

# 2. Run the services in the background (detached mode)
docker compose up -d

# 3. Verify that all 6 containers are running
docker compose ps
```

### Services Defined:
* **`web`**: Gunicorn running Uvicorn ASGI workers on port `8000`. Runs migrations and collects static files on startup.
* **`nginx`**: Listens on ports `80` (HTTP redirect) and `443` (HTTPS with SSL). Proxies regular requests, WebSockets (`/ws/`), and serves static/media files.
* **`redis`**: Message broker for Celery and state database for Channels.
* **`celery_worker`**: Background consumer executing tasks like push alerts.
* **`celery_beat`**: Scheduler task executing periodic reminders every minute.
* **`db`**: PostgreSQL 15 database instance storing application data.

---

## 📡 API Reference

All API endpoints are prefixed with `/api/`. JWT Bearer tokens are required for all non-authentication requests.

### Authentication Endpoints (`/api/auth/`)

| Method | Endpoint | Description | Auth Required | Payload / Query |
| :--- | :--- | :--- | :---: | :--- |
| **POST** | `/signup/` | Register a new user credentials | No | `{ "email", "name", "password", "confirm_password" }` |
| **POST** | `/signin/` | Sign in with email and password | No | `{ "email", "password" }` |
| **POST** | `/token/refresh/` | Obtain a new JWT access token | No | `{ "refresh" }` |
| **POST** | `/get-otp/` | Request email OTP code | No | `{ "email", "task" }` |
| **POST** | `/verify-otp/` | Verify OTP code and return token | No | `{ "email", "otp_code" }` |
| **POST** | `/reset-password/` | Reset user password (authenticated) | **Yes** | `{ "email", "new_password" }` |
| **GET/PUT/PATCH** | `/profile/` | Manage current user profile settings | **Yes** | Profile details (Multipart/JSON) |
| **POST** | `/` (Base) | Log in or register via Firebase token | No | Query: `?token=<firebase_id_token>` |

### Features Endpoints (`/api/`)

| Method | Endpoint | Description | Auth Required | Payload / Query |
| :--- | :--- | :--- | :---: | :--- |
| **GET** | `/checkin/` | List all check-ins of the current user | **Yes** | — |
| **POST** | `/checkin/` | Submit a new daily mood report / check-in | **Yes** | `{ "assesment", "time", "journal", "tags" }` |
| **GET** | `/entries/` | Fetch paginated list of all entries | **Yes** | — |
| **GET** | `/report/` | Get monthly report stats (aggregates, streaks) | **Yes** | — |
| **GET** | `/insights/` | Get detailed month-to-month comparison trends | **Yes** | — |
| **POST** | `/feedback/` | Submit app feedback or star ratings | **Yes** | `{ "feedback", "stars" }` |
| **POST** | `/chat/send/` | Send message to OpenAI journaling companion | **Yes** | `{ "message" }` |
| **GET** | `/chat/history/` | Fetch recent AI chat messages (paginated) | **Yes** | — |
| **DELETE**| `/chat/clear/` | Clear history & reset AI session | **Yes** | — |
| **POST** | `/fcm/device/` | Register/update active FCM token | **Yes** | `{ "registration_id", "device_id" }` |
| **GET** | `/notifications/`| Get list of user push notification records | **Yes** | — |
| **PATCH**| `/notifications/<uuid:pk>/read/` | Mark specific notification as read | **Yes** | — |
| **POST** | `/test/fcm/` | Dispatches a manual push alert for testing | **Yes** | `{ "title", "body" }` |

---

## 🎨 Admin Dashboard Customization

The admin portal uses custom theme modifications built directly into Django settings to guarantee a warm, comforting vibe for the Honeysuckle company branding:
* **Accent Color**: Comforting Green (`#588157`)
* **Primary Color**: Warm Orange (`#FF7E46`)
* **Features Enabled**: Unfold history tracing and immediate redirect to administration landing pages.
