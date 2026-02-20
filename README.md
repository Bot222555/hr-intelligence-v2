# HR Intelligence v2.0

**Creativefuel Custom HR Platform** — Phase 1: Core HR + Attendance + Leave

> Replacing Keka for 283 active employees across 21 departments, 2 locations.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12 + FastAPI + Uvicorn |
| **Database** | PostgreSQL 16 |
| **Cache** | Redis 7 |
| **Frontend** | React 18 + Vite + TypeScript |
| **UI** | Tailwind CSS + shadcn/ui |
| **Auth** | Google OAuth 2.0 + JWT |
| **ORM** | SQLAlchemy 2.0 + Alembic |
| **Deploy** | Docker + Docker Compose + Nginx |

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/Bot222555/hr-intelligence-v2.git
cd hr-intelligence-v2
cp .env.example .env  # Edit with real values

# 2. Start infrastructure
docker compose up -d db redis

# 3. Install Python deps
pip install -r requirements.txt

# 4. Run migrations
alembic upgrade head

# 5. Start API server
uvicorn backend.main:app --reload --port 8000

# 6. Start frontend (once built)
cd frontend && npm install && npm run dev
```

## API Docs

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- Health: http://localhost:8000/api/v1/health

## Project Structure

```
hr-intelligence-v2/
├── backend/           # FastAPI application
│   ├── auth/          # Google OAuth + JWT + RBAC
│   ├── core_hr/       # Employee management
│   ├── attendance/    # Clock in/out, regularization
│   ├── leave/         # Leave management
│   ├── dashboard/     # Analytics & overview
│   ├── notifications/ # In-app notifications
│   └── common/        # Shared utilities
├── frontend/          # React SPA
├── alembic/           # Database migrations
├── migration/         # Keka → PostgreSQL data migration
├── tests/             # pytest test suite
├── scripts/           # Setup, deploy, backup
└── nginx/             # Nginx configuration
```

## Commands

```bash
make help          # Show all commands
make dev           # Start dev infrastructure
make test          # Run tests
make lint          # Run linter
make migrate       # Run database migrations
make deploy        # Deploy to production
make backup        # Backup database
```

## Architecture

- **Modular monolith** — Single FastAPI app with separated modules
- **API-first** — Pure JSON API, frontend is separate SPA
- **RBAC** — Four roles: employee, manager, hr_admin, system_admin
- **Audit trail** — Every mutation logged
- **Mobile-first** — Responsive design for phone usage

## Domain

- **Production:** https://hr.cfai.in
- **Server:** AWS EC2 (3.110.62.153)

---

*Built by the Alfred Fleet 🎩 — Donna builds, Vision reviews, Jarvis tests, Alfred orchestrates.*
