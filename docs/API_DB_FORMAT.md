# API / DB Expansion Format

Use this format when adding a new endpoint family or a new database feature.

## API Folder Shape

```text
src/api/system/<feature_name>/
  models.py
  routes/
    __init__.py
    router.py
    _get_routes.py
    _post_routes.py
    _delete_routes.py
```

## Database Folder Shape

```text
src/models/tables/<feature_table>.py
src/models/crud/<feature_table>_crud.py
```

## Rules

- Keep permission checks in `with_validation`.
- Keep request models close to the endpoints they serve.
- Keep table registration explicit in `src/models/tables/__init__.py`.
- Use the bootstrap script for any SUPER_ADMIN key creation.