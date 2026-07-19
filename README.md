# AIROS Opportunity OS v1.0

A Telegram-based personal AI agent that automatically discovers, evaluates, and applies to professional opportunities on your behalf.

**Supports:** Remote jobs · Scholarships · Fellowships · Grants · Competitions · Bootcamps · Conferences · Research programs

---

## Architecture

```
Telegram → Planner → Search → Rank → Eligibility → Documents → Apply → Email → Report
```

Single repo · Single deployment · Free-tier compatible · ~21 files.

---

## Prerequisites

| Service | Purpose | Free Tier |
|---|---|---|
| [Telegram Bot](https://t.me/BotFather) | User interface | ✅ Free |
| [OpenRouter](https://openrouter.ai) | LLM (Gemini, DeepSeek, Qwen) | ✅ Free models |
| [Supabase](https://supabase.com) | Database + memory | ✅ Free tier |
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

Create a new Supabase project and run this SQL:

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
2. Send `/newbot` and follow prompts
3. Copy the bot token

### 4. Enable Gmail App Password

1. Go to Google Account → Security → 2-Step Verification → App Passwords
2. Generate an app password for "Mail"
3. Use this as `EMAIL_APP_PASSWORD`

### 5. Deploy to Render

1. Push to GitHub
2. Connect repo to Render → New Web Service
3. Set environment variables:

```
TELEGRAM_BOT_TOKEN=your_token
OPENROUTER_API_KEY=your_key
LLM_MODEL=google/gemini-flash-1.5
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_anon_key
BROWSERLESS_API_KEY=your_key
EMAIL_ADDRESS=your.career.email@gmail.com
EMAIL_APP_PASSWORD=your_app_password
AUTO_APPLY=false
SMART_APPLY=true
TIMEZONE=Africa/Lagos
```

4. Deploy

---

## Usage

Open your Telegram bot and start:

| Command | Action |
|---|---|
| `/mission` | Full session: search + apply + email check |
| `/search` | Search for opportunities only |
| `/apply` | Submit queued applications |
| `/email` | Check career email |
| `/profile` | View your profile |
| `/status` | Recent applications |
| `/report` | Last mission summary |
| `/settings` | Current configuration |
| `/help` | Command list |

**Natural language also works:**
- _"Find AI research grants in Germany"_
- _"Search fully funded scholarships"_
- _"Check if I have any interview emails"_

**To import your CV:** Send a PDF or DOCX file with caption `cv` or `resume`.

---

## Application Modes

| Mode | Behavior | Config |
|---|---|---|
| **Manual** | Nothing submitted without approval | `AUTO_APPLY=false`, `SMART_APPLY=false` |
| **Smart** (recommended) | Auto-submits standard applications, pauses for complex ones | `SMART_APPLY=true` |
| **Automatic** | Submits everything possible | `AUTO_APPLY=true` |

---

## File Structure

```
airos-opportunity-os/
├── app.py              # Entry point
├── telegram_bot.py     # Telegram interface
├── config.py           # Configuration
├── planner.py          # Brain / orchestrator
├── llm.py              # OpenRouter LLM engine
├── browser.py          # Browserless automation
├── search.py           # Opportunity discovery
├── profile.py          # Profile manager
├── opportunity.py      # Opportunity parser + eligibility
├── ranking.py          # Scoring + deduplication
├── documents.py        # Resume, cover letter, SOP generation
├── application.py      # Form filling + submission
├── account.py          # Account lifecycle
├── email_agent.py      # Gmail monitoring
├── notification.py     # Telegram alerts
├── report.py           # Message formatting
├── storage.py          # Supabase gateway
├── prompts.py          # All LLM prompts
├── utils.py            # Shared utilities
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
- **Free-tier first.** No mandatory paid dependencies.
- **Fail gracefully.** One failed step does not abort the mission.

---

## Roadmap

**v2**
- Automatic scheduling (APScheduler)
- Web dashboard
- Multi-user support
- Advanced analytics

**v3**
- Interview simulation
- Salary negotiation assistant
- Skill gap analysis
- Company relationship tracking
