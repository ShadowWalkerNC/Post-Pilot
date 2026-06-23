# Render / Heroku Procfile
release: /app/.venv/bin/python -c "from app import init_db; init_db()"
web: /app/.venv/bin/gunicorn app:app --workers 2 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile -
