# Database Reference

The database layer is intentionally small and is expected to grow as the service becomes more general-purpose.

## Current Tables

- `api_keys`: hashed API keys with permission level, rate limit, email, and timestamps.

## Extending the Schema

1. Add a new ORM model under `src/models/tables/`.
2. Import the table module from `src/models/tables/__init__.py` so it is registered during schema creation.
3. Add CRUD helpers under `src/models/crud/`.
4. Expose the data through a router under `src/api/` if it needs to be reachable from the frontend.

## Notes

- `src/models/database.py` creates tables directly from SQLAlchemy metadata at startup.
- The service currently keeps SQL echo enabled for visibility during development.