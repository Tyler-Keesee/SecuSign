# SecuSign — File Signing API Prototype

**Status: educational Flask security experiment; not production-ready. Do not expose on the public internet or use with sensitive documents.**

## Implemented API surface

- `POST /register`, `POST /login`: local SQLite user storage and Werkzeug password hashing
- `POST /generate-keys`: RSA key generation after JWT authentication
- `POST /batch-sign`: experimental uploaded-file signing
- `GET /admin/dashboard`: a valid token **plus** a server-side database role of `admin`
- SQLite audit records and basic request throttling

This repository does not ship a user interface or a deployable Docker image; the committed Dockerfile is empty.

## Local development

```bash
git clone https://github.com/Tyler-Keesee/SecuSign.git
cd SecuSign
python -m venv .venv
# Activate the environment on your operating system
python -m pip install -r requirements.txt
python SecuSign.py
```

The app listens on **http://127.0.0.1:5000**, not HTTPS and not your LAN interface. Use API clients to exercise endpoints. Never use a real password or protected file in this experiment.

## Security limitations

- **Generated private keys are stored unencrypted** in `uploads/`. They are ignored by Git, but need real key custody and permissions before production use.
- `SECRET_KEY` defaults to a random process-local value, so existing tokens will fail after restart. Supply a strong environment value in controlled local development.
- Default CORS allows only `http://127.0.0.1:5000`; set `CORS_ORIGINS` to a comma-separated allowlist if needed.
- Requests are limited to 10 MiB, but file content and key lifecycle defenses are incomplete.
- Admin access is determined from the server-side database role, not whether a JWT username happens to say "admin". Self-registration of the reserved name is rejected.
- Audit/logging, email sending, rate limiting, and signature verification are **not independently security-tested**. The roadmap is aspirational, not a list of verified capabilities.
- This code has no certified compliance or production-readiness guarantee. Previously committed secrets may remain in Git history and must be rotated if ever used.

## Regression checks

```bash
python -m unittest discover -s tests -v
```

GitHub Actions checks dependency installation, Python syntax, and basic admin authorization. These are smoke tests, not a security assessment.
