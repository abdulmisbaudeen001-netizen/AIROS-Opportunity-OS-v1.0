# AIROS Opportunity OS v1.0

A personal AI operating system that automatically discovers, evaluates, and applies to professional opportunities — controlled via Telegram and a professional web dashboard.

**Supports:** Remote jobs · Scholarships · Fellowships · Grants · Competitions · Bootcamps · Conferences · Research programs

---

## Architecture

```
Telegram / Web UI
        │
        ▼
   FastAPI + Planner
        │
   ┌────┼────────────────────┐
   ▼    ▼                    ▼
Search  Profile          Browser
   ▼    ▼                    ▼
Rank  Documents         Application
   ▼    ▼                    ▼
Email  Storage (Supabase)  Report
        │
        ▼
  Telegram + Web UI
```

Single repo · Single Render deployment · Free-tier compatible · 30 files.

---

## Prerequisites

| Service | Purpose | Free Tier |
|---|---|---|
| [Telegram Bot](https://t.me/BotFather) | Mobile interface | ✅ Free |
| [OpenRouter](https://openrouter.ai) | LLM — Gemini, DeepSeek, Qwen | ✅ Free models |
| [Supabase](https://supabase.com) | Database + persistent memory | ✅ Free tier |
| [Browserless](https://browserless.io) | Browser automation | ✅ Free tier |
| [Render](https://render.com) | Hosting | ✅ Free tier |
| Gmail account | Career email monitoring | ✅ Free |

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/yourusername/airos-opportunity-os
cd airos-opportunity-os
```

### 2. Set up Supabase

Create a new Supabase project. Go to the SQL Editor and run:

```sql
create table profile (
  id uuid default gen_random_uuid() primary key,
  name text, email text, phone text, location text, bio text,
  linkedin text, github text, portfolio text,
  remote_preference boolean default true,
  relocation_willing boolean default false,
  visa_required boolean default false,
  salary_expectation text,
  preferred_countries text[],
  preferred_categories text[],
  telegram_chat_id text,
  updated_at timestamptz default now()
);

create table experience (
  id uuid default gen_random_uuid() primary key,
  title text, company text, location text,
  start_date text, end_date text, current boolean default false, description text
);

create table education (
  id uuid default gen_random_uuid() primary key,
  degree text, institution text, field text,
  start_date text, end_date text, grade text
);

create table skills (
  id uuid default gen_random_uuid() primary key,
  name text unique, level text default 'intermediate'
);

create table opportunities (
  id uuid default gen_random_uuid() primary key,
  hash text unique, title text, organization text, country text,
  category text, deadline text, salary text, funding text,
  visa_sponsored boolean, remote boolean,
  requirements jsonb, application_url text, source text, description text,
  score integer default 0, eligible text, eligibility_reason text,
  days_until_deadline integer, session_id text, created_at timestamptz default now()
);

create table applications (
  id uuid default gen_random_uuid() primary key,
  opportunity_title text, organization text, category text,
  application_url text, status text,
  opportunity_data jsonb, account_platform text,
  submitted_at timestamptz, created_at timestamptz default now(),
  updated_at timestamptz
);

create table documents (
  id uuid default gen_random_uuid() primary key,
  type text, content jsonb, opportunity_title text,
  opportunity_id uuid, pdf_b64 text, created_at timestamptz default now()
);

create table accounts (
  id uuid default gen_random_uuid() primary key,
  platform text, email text, password text, status text, notes text,
  created_at timestamptz default now(),
  unique(platform, email)
);

create table missions (
  id text primary key, command text, status text,
  started_at timestamptz, ended_at timestamptz,
  tasks_completed integer default 0, tasks_failed integer default 0,
  retry_count integer default 0, errors jsonb, summary jsonb
);

create table mission_logs (
  id uuid default gen_random_uuid() primary key,
  mission_id text, module text, error text, created_at timestamptz default now()
);

create table emails (
  id uuid default gen_random_uuid() primary key,
  message_id text unique, subject text, sender text,
  body_preview text, received_at text, category text,
  priority text, requires_action boolean, action_type text,
  summary text, sender_organization text, deadline text
);

create table knowledge_base (
  id uuid default gen_random_uuid() primary key,
  category text, content text, metadata jsonb,
  created_at timestamptz default now()
);

create table task_queue (
  id uuid default gen_random_uuid() primary key,
  mission_id text, status text, result jsonb,
  created_at timestamptz default now(), completed_at timestamptz
);
```

### 3. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 4. Enable Gmail App Password

1. Google Account → Security → 2-Step Verification → App Passwords
2. Generate a password for "Mail"
3. Use it as `EMAIL_APP_PASSWORD`

### 5. Deploy to Render

1. Push repo to GitHub
2. Render → New Web Service → connect your repo
3. Set all environment variables (see below)
4. Deploy

---

## Environment Variables

Set these in Render → Environment before deploying.

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `OPENROUTER_API_KEY` | From openrouter.ai |
| `SUPABASE_URL` | From Supabase project settings |
| `SUPABASE_KEY` | Supabase anon/public key |
| `BROWSERLESS_API_KEY` | From browserless.io |
| `WEB_PASSWORD` | Password for the web dashboard login |
| `SECRET_KEY` | Any long random string — protects session tokens |

### Optional (recommended)

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `google/gemini-flash-1.5` | Primary OpenRouter model |
| `EMAIL_ADDRESS` | — | Gmail address to monitor |
| `EMAIL_APP_PASSWORD` | — | Gmail app password |
| `AUTO_APPLY` | `false` | Enable fully automatic submissions |
| `SMART_APPLY` | `true` | Enable smart auto-submission |
| `TIMEZONE` | `Africa/Lagos` | Your local timezone |
| `PORT` | `8000` | Web server port (Render sets this automatically) |
| `BROWSERLESS_URL` | `https://chrome.browserless.io` | Browserless endpoint |
| `BRAVE_API_KEY` | — | Brave Search API (better search quality) |
| `TAVILY_API_KEY` | — | Tavily Search API (alternative) |

---

## Interfaces

### Web Dashboard

Access at `https://your-app.onrender.com` after deployment.

| Section | What it does |
|---|---|
| **Dashboard** | Live stats, last mission summary, quick actions |
| **Mission Control** | Run any command, watch real-time execution log |
| **Profile** | View/edit all profile fields, upload CV, completeness score |
| **Opportunities** | Ranked table with filters, score bars, apply links |
| **Applications** | Full history, status tracking, approve pending submissions |
| **Documents** | Download all generated CVs, cover letters, SOPs |
| **Email** | Categorized career inbox, high-priority flagged |
| **Settings** | View current configuration, sign out |

### Telegram Bot

| Command | Action |
|---|---|
| `/mission` | Full session: search + apply + email check |
| `/search` | Search for opportunities only |
| `/apply` | Submit queued applications |
| `/email` | Check career email inbox |
| `/profile` | View your profile and completeness |
| `/status` | Recent application history |
| `/report` | Last mission summary |
| `/settings` | Current configuration |
| `/help` | Command list |

**Natural language works too:**
- _"Find AI research grants in Germany"_
- _"Search fully funded scholarships in Canada"_
- _"Check if I have any interview emails"_
- _"Add Python to my skills"_

**To import your CV via Telegram:** Send a PDF or DOCX file captioned `cv` or `resume`.

---

## Application Modes

| Mode | Behavior | Config |
|---|---|---|
| **Manual** | Every application requires your approval | `AUTO_APPLY=false`, `SMART_APPLY=false` |
| **Smart** ✅ Recommended | Auto-submits standard applications, pauses for complex ones | `SMART_APPLY=true` |
| **Automatic** | Submits everything eligible with no confirmation | `AUTO_APPLY=true` |

Smart mode pauses for: long essays, research proposals, payment requests, missing profile fields, unrecognized platforms, or CAPTCHA/MFA requirements.

---

## File Structure

```
airos-opportunity-os/
│
├── app.py              # Entry point — runs FastAPI + Telegram concurrently
├── api.py              # FastAPI REST API — all web UI endpoints
├── telegram_bot.py     # Telegram polling interface
├── config.py           # All environment variable loading
├── planner.py          # Brain — sole workflow orchestrator
│
├── llm.py              # OpenRouter LLM engine with failover
├── browser.py          # Browserless automation
├── search.py           # Multi-provider opportunity search
├── profile.py          # Profile manager + CV import
├── opportunity.py      # Opportunity parser + eligibility checker
│
├── ranking.py          # Scoring + deduplication pipeline
├── documents.py        # Resume, cover letter, SOP, PDF generation
├── application.py      # Form filling + submission engine
├── account.py          # Account lifecycle + credential management
├── email_agent.py      # Gmail IMAP monitoring + classification
│
├── notification.py     # Telegram alerts (immediate + mission summary)
├── report.py           # Message formatting for Telegram
├── storage.py          # Supabase gateway — only DB access point
├── prompts.py          # All LLM prompts centralized
├── utils.py            # Shared helpers, Result envelope
│
├── web/
│   ├── index.html      # Login page
│   ├── app.html        # Main application shell
│   ├── css/
│   │   └── style.css   # Full professional dark stylesheet
│   └── js/
│       ├── api.js      # All fetch calls to Render backend
│       ├── app.js      # Navigation, session, toast system
│       ├── mission.js  # Mission Control + real-time log stream
│       └── pages.js    # All section renderers
│
├── requirements.txt
├── render.yaml
└── README.md
```

---

## Design Principles

- **Planner is the only orchestrator.** No module coordinates other modules directly.
- **Provider abstraction everywhere.** Replacing Browserless or OpenRouter requires editing one file.
- **Only `storage.py` touches Supabase.** All other modules request data through it.
- **Only `llm.py` touches OpenRouter.** Automatic failover across free models.
- **Only `api.py` exposes HTTP endpoints.** Web UI never calls Supabase directly.
- **Free-tier first.** No mandatory paid dependencies.
- **Fail gracefully.** One failed step never aborts the mission.
- **Single deployment.** Telegram bot and web UI run from the same Render service.

---

## How It Works

1. You send `/mission` (Telegram or web)
2. Planner loads your profile from Supabase
3. Search engine generates smart queries from your profile and runs them across multiple sources
4. Raw results are parsed into standardized opportunity objects
5. Eligibility is checked for each opportunity against your profile
6. Opportunities are ranked 0–100 and deduplicated
7. For each top opportunity: required documents are generated (resume, cover letter, SOP)
8. Applications are submitted according to your configured mode
9. Human checkpoints (CAPTCHA, MFA, complex essays) are paused and you are notified
10. Career Gmail is checked for interviews, offers, and verifications
11. All activity is saved to Supabase
12. A complete mission summary is sent to Telegram and available on the web dashboard

---

## Roadmap

**v2**
- Automatic scheduling (APScheduler — run at 6 AM / 6 PM daily)
- Multi-user support
- Advanced analytics and charts
- Calendar integration for interview scheduling

**v3**
- Interview simulation and preparation
- Salary negotiation assistant
- Skill gap analysis and learning roadmap
- Company relationship tracking
