# Deployment Guide

## Option A: Render / Railway-style Python host
1. Create a new web service from this folder/repository.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Set environment variables:
   - `SECRET_KEY`
   - `MODULE_MIN_ACTIVE_SECONDS`
5. Attach persistent storage or migrate the DB to PostgreSQL.

## Option B: VPS
1. Install Python 3.12+, nginx, and a process manager.
2. Run Gunicorn behind nginx.
3. Enable HTTPS with a valid certificate.
4. Configure daily database backups.

## Database migration recommendation
SQLite is included so the package works immediately. Before multi-user production, migrate tables to PostgreSQL and update the database connector.

## Domain
Use a simple branded URL such as:
`learn.<your-domain>.com`

The public site should not state that a course is ACB-approved until approval has actually been issued.
