# TwinCity Portal — Python prototype

A runnable demonstration starter for the TwinCity Portal SRS. Backend: FastAPI + SQLite; frontend: HTML/CSS/JavaScript; 3D demo view: Three.js loaded from a CDN.

## Requirements
- Python 3.10+
- Internet access in the browser for the Three.js CDN (the rest of the app runs locally)

## Run on Windows
Open a terminal in this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app:app --reload
```

If PowerShell blocks activation, run `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and then `\.venv\Scripts\python.exe -m uvicorn app:app --reload`.

Open http://127.0.0.1:8000. API documentation is at http://127.0.0.1:8000/docs.

## Demo login
- Email: `admin@twincity.local`
- Password: `ChangeMe123!`

Change the demo password and set `TWINCITY_SECRET_KEY` to a strong secret before any shared deployment. The seeded database is `twincity.db` and can be deleted to reset demo data.

## Implemented in this prototype
- Registration (new accounts receive `citizen` role; request cannot choose a role)
- Login with signed, expiring bearer token; basic failed-login lockout
- Dashboard counts
- Sample assets with sensitive assets hidden from citizens
- Layer listing and role-protected toggle
- Alert listing and operator/admin acknowledgement with audit entries
- Scenario creation with a clearly labelled deterministic demo result
- Admin user list and audit log
- Interactive illustrative 3D city scene plus accessible asset list

## Important scope and production gaps
This is a starter/demo, **not a claim of full SRS compliance**. It does not yet implement production-grade refresh/revocable sessions, MFA/SSO, field-level AES-GCM encryption and blind indexes, rate limiting by IP, full admin role management, complete CRUD for every entity, historical time-series feeds, real IoT and simulation adapters, real geospatial/3D city data, full AI features and golden-set evaluation, exports/reporting, object storage, retention jobs, CI/CD, accessibility audit, load tests, or the SRS's full API error/correlation-ID contract. Do not deploy with real sensitive data. Build and test those requirements before production.
