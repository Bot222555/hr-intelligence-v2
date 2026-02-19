# HR Intelligence v2.0

> Creativefuel Custom HR Platform — Phase 1: Core HR + Attendance + Leave

**Domain:** hr.cfai.in | **Server:** AWS EC2 (3.110.62.153)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI + Uvicorn |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Frontend | React 18 + Vite + TypeScript |
| UI | Tailwind CSS + shadcn/ui |
| Auth | Google OAuth 2.0 + JWT (@creativefuel.io domain lock) |
| ORM | SQLAlchemy 2.0 + Alembic |
| Deploy | Docker + Docker Compose + Nginx |

## Quick Start

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your credentials

# Start services (PostgreSQL + Redis + API)
docker compose up -d

# Run migrations
docker compose exec api alembic upgrade head

# API available at http://localhost:8000
# Health check: http://localhost:8000/api/v1/health
```

## Project Structure

```
hr-intelligence-v2/
├── backend/           # FastAPI application
│   ├── auth/          # Google OAuth + JWT + RBAC
│   ├── core_hr/       # Employee management
│   ├── attendance/    # Attendance & time tracking
│   ├── leave/         # Leave management
│   ├── dashboard/     # Analytics & dashboard
│   ├── notifications/ # In-app notifications
│   └── common/        # Shared utilities
├── frontend/          # React SPA
├── alembic/           # Database migrations
├── migration/         # Keka → PostgreSQL data migration
├── tests/             # pytest test suite
├── scripts/           # Deployment & utility scripts
└── nginx/             # Nginx configuration
```

## Blueprint

Full specification: [memory/hr-intelligence-fresh-build.md](../memory/hr-intelligence-fresh-build.md) (3,175 lines)

- 22 tasks decomposed for fleet agents
- Complete database schema (PostgreSQL)
- Full API contracts (REST, JSON, JWT auth)
- Frontend component specs
- Test plan with 90+ test cases
- Deployment & CI/CD pipeline

## Team

- **Alfred** — Coordinator & memory
- **Donna** — Builder (all coding tasks)
- **Vision** — Code reviewer
- **Jarvis** — Test orchestrator

---

*Built for Creativefuel | 283 active employees | 21 departments | 2 locations*
