# Portfolio MVP

Private local personal finance portfolio application.

## Backend

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python -m pytest backend/tests/test_api.py -q
.venv/bin/python -m ruff check backend
```

Run the API locally:

```bash
.venv/bin/python -m uvicorn portfolio_app.asgi:app --reload
```
