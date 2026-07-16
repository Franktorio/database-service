# Database Service

Async FastAPI + PostgreSQL service for API-key-secured data operations. The current implementation ships with API-key administration endpoints, permission levels, per-key rate limiting, backups, DB health checks, time-based ratelimit cache cleanup, and operations scripts.

## What This Service Does

- Exposes API-key administration endpoints under /api/db/keys.
- Stores API keys (hashed with pepper) and supports CRUD management for them.
- Validates API keys and enforces permission levels.
- Enforces per-key in-memory rate limiting.
- Evicts inactive ratelimit cache entries on a time basis via background service.
- Runs backup and DB healthcheck background services.
- Uses Python logging with daily log rotation.

## Technology Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy async + asyncpg
- PostgreSQL

## Architecture Overview

Startup flow:

1. Logging initializes.
2. Main starts service entrypoints through the service layer.
3. Backup, DB healthcheck, and ratelimit cache services are started.
4. FastAPI starts and initializes schema with SQLAlchemy metadata.

Main components:

- main.py: process bootstrap
- config/loader.py: env loading and secret safety checks
- config/service_config.json: runtime service controls and timeout settings
- src/api: API app, auth validation, ratelimit logic, admin routes
- src/models: ORM base, DB engine/session, table models, CRUD
- src/services: logging, backup, healthcheck, ratelimit cache, service layer abstraction
- scripts: setup_postgres, generate_api_key, migrate_db

## Configuration

### Environment Variables

Create config/.env and set:

- OPERATING_MODE
- POSTGRESQL_DATABASE_NAME
- POSTGRESQL_USERNAME
- POSTGRESQL_PASSWORD
- POSTGRESQL_HOST
- POSTGRESQL_PORT
- API_ENABLED
- API_PORT
- API_KEY_PEPPER

Important:

- In non-development mode, default/unsafe POSTGRESQL_PASSWORD and API_KEY_PEPPER values will raise at startup.

### Service Runtime Config

Edit config/service_config.json:

- backup
	- enabled
	- interval
	- retention
	- backup_dir
	- subprocess_timeout_seconds
- dbhealthchecker
	- enabled
	- auto_rollover
	- shutdown_on_failure
	- leniency
	- interval
	- backup_dir
	- healthcheck_subprocess_timeout_seconds
	- restore_subprocess_timeout_seconds
- setup_postgres
	- command_subprocess_timeout_seconds
	- probe_subprocess_timeout_seconds
- ratelimit_cache
	- enabled
	- sweep_interval
	- max_inactive_seconds

## Local Development Run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start service:

```bash
python main.py
```

The process starts managed services first, then the API server.

## API Surface

- GET /
- POST /auth-test
- GET /api/db/keys
- POST /api/db/keys/list
- POST /api/db/keys/create
- POST /api/db/keys/update
- DELETE /api/db/keys/delete

API-protected endpoints require api_key in request body.

## Utility Scripts

PostgreSQL setup (Debian/Ubuntu oriented):

```bash
python3 -m scripts.setup_postgres
```

Generate API key:

```bash
python3 -m scripts.generate_api_key <permission_level> <rate_limit>
```

Database migration (schema-first compatibility copy/swap):

```bash
python3 -m scripts.migrate_db
```

## Logging

- Uses Python logging module.
- Active log file: logs/db_service_logs.log
- Daily rotation at midnight.
- Keeps 7 rotated files.
- Log levels are derived from prefix conventions such as [DEBUG], [INFO], [WARNING], [ERROR].

## Detailed Deployment Guide (Linux VM)

This section describes a practical deployment flow for Ubuntu 22.04+.

### 1) Provision Host

- Create VM.
- Open ports: 22 (SSH), 80 (HTTP), 443 (HTTPS).
- Keep API port (for example 8000) private if using reverse proxy.

### 2) Install System Packages

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git nginx
```

### 3) Create App User and Directory

```bash
sudo useradd -m -s /bin/bash dbservice
sudo mkdir -p /opt/database-service
sudo chown -R dbservice:dbservice /opt/database-service
```

### 4) Deploy Code

```bash
sudo -u dbservice git clone <your-repo-url> /opt/database-service
cd /opt/database-service
```

### 5) Create Virtual Environment and Install Dependencies

```bash
sudo -u dbservice python3 -m venv /opt/database-service/.venv
sudo -u dbservice /opt/database-service/.venv/bin/pip install --upgrade pip
sudo -u dbservice /opt/database-service/.venv/bin/pip install -r /opt/database-service/requirements.txt
```

### 6) Configure App Environment

Create /opt/database-service/config/.env with production-safe values:

```env
OPERATING_MODE=production
POSTGRESQL_DATABASE_NAME=your_db
POSTGRESQL_USERNAME=your_user
POSTGRESQL_PASSWORD=your_strong_password
POSTGRESQL_HOST=127.0.0.1
POSTGRESQL_PORT=5432
API_ENABLED=True
API_PORT=8000
API_KEY_PEPPER=your_long_random_pepper
```

Review /opt/database-service/config/service_config.json for intervals/timeouts before first start.

### 7) Set Up PostgreSQL

If you are using the included setup script on Ubuntu:

```bash
cd /opt/database-service
sudo -u dbservice /opt/database-service/.venv/bin/python -m scripts.setup_postgres
```

If your Postgres is managed externally, skip this and point .env values to that DB.

### 8) Bootstrap SUPER_ADMIN API Key

```bash
cd /opt/database-service
sudo -u dbservice /opt/database-service/.venv/bin/python -m scripts.generate_api_key 4 1000
```

Store the emitted token securely; it is shown only once.

### 9) Create Systemd Service

Create /etc/systemd/system/database-service.service:

```ini
[Unit]
Description=Database Service API
After=network.target

[Service]
Type=simple
User=dbservice
Group=dbservice
WorkingDirectory=/opt/database-service
ExecStart=/opt/database-service/.venv/bin/python /opt/database-service/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable database-service
sudo systemctl start database-service
sudo systemctl status database-service
```

### 10) Configure Nginx Reverse Proxy

Create /etc/nginx/sites-available/database-service:

```nginx
server {
		listen 80;
		server_name your-domain.com;

		location / {
				proxy_pass http://127.0.0.1:8000;
				proxy_http_version 1.1;
				proxy_set_header Host $host;
				proxy_set_header X-Real-IP $remote_addr;
				proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
				proxy_set_header X-Forwarded-Proto $scheme;
		}
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/database-service /etc/nginx/sites-enabled/database-service
sudo nginx -t
sudo systemctl reload nginx
```

### 11) Enable TLS (Recommended)

Using Certbot:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 12) Verify Deployment

```bash
curl http://127.0.0.1:8000/
curl https://your-domain.com/
sudo systemctl status database-service
sudo journalctl -u database-service -f
```

### 13) Operational Checks

- Confirm logs are rotating in logs/.
- Confirm backups are generated in configured backup_dir.
- Confirm DB healthcheck behavior matches your leniency and shutdown settings.
- Confirm ratelimit cache cleanup is running at intended sweep interval.

## Upgrade Procedure

1. Pull new code.
2. Install any new dependencies.
3. Review config changes in .env and service_config.json.
4. Restart service:

```bash
sudo systemctl restart database-service
```

If schema changes are included, run migration process before restart strategy finalization.

## Troubleshooting

- Service fails immediately:
	- Check .env secrets and OPERATING_MODE in config/loader.py rules.
- API unreachable:
	- Check systemd status and nginx config.
- Backup or healthcheck errors:
	- Verify pg_dump, pg_isready, psql availability and timeout settings.
- Permission denied on logs/backups:
	- Verify filesystem ownership for service user.

## Documentation

- API reference: docs/API.md
- Database reference: docs/DB.md
- Expansion format: docs/API_DB_FORMAT.md
