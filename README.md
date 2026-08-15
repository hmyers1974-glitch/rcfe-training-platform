# California RCFE Leadership Academy — Deployable Training Portal

This package upgrades the prototype into a deployable Flask application with:

- Student authentication
- Admin authentication
- Read-only reviewer account
- 20 interactive self-paced modules
- Server-side progress records
- Server-side active-time accumulation
- Idle-time exclusion in the browser
- Required Regulation Hunt responses
- Required scenario responses
- Feedback reveal only after learner input
- Quiz attempts + remediation
- Exit-ticket records
- Module completion gates
- Admin student creation/enrollment
- Admin/reviewer audit dashboard
- CSV completion-record export
- Completion certificate PDF generation
- Course/module version fields
- Activity-event audit trail

## Demo credentials
Change these immediately before real deployment.

- Admin: `admin@rcfeacademy.local` / `Admin123!`
- Reviewer: `reviewer@rcfeacademy.local` / `Review123!`
- Student: `student@rcfeacademy.local` / `Student123!`

## Local run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export SECRET_KEY='replace-this'
export MODULE_MIN_ACTIVE_SECONDS=60
python app.py
```

Open `http://localhost:8000`.

## IMPORTANT: active-time configuration

For development, `.env.example` uses a short threshold so the workflow can be tested.

Before offering approved course credit, set `MODULE_MIN_ACTIVE_SECONDS` to the **approved requirement** and ensure the learner experience actually contains enough instructional content and interaction to support that duration.

Do **not** simply set a 3600-second timer on a short lesson. The course content and interaction must support the approved instructional time.

## Production hardening still recommended

This codebase is deployable, but a public production system should also use:

- PostgreSQL/MySQL instead of SQLite for multi-user hosting
- HTTPS
- Managed backups
- Rotated secret keys
- Password-reset workflow
- Email verification
- Rate limiting / login lockout
- CSRF protection
- Privacy notice / terms
- Accessibility testing
- Secure audit-log retention
- Server-side session store
- Record-retention and backup policy matching the approved vendor procedure

## Reviewer access

The reviewer role can:
- browse every module
- view student completion evidence
- review active time, quiz attempts and audit events
- export records

It cannot create students or alter learner records.

## Hosting options

The included `Procfile` works with common Python hosts that support Gunicorn. The project can also be containerized or deployed to a VPS.

## ACB submission workflow

Use this portal as the interactive-course delivery environment once it is hosted and finalized. Provide the reviewer URL and reviewer credentials in the course-approval package. Keep the course version (`2026.08`) synchronized with the version submitted for review.

## Certificate note

The generated PDF currently identifies itself as a prototype and does not invent vendor/course numbers. Add the actual approved vendor and course numbers only after they are issued.
