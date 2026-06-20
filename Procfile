# Render / Heroku Procfile
# DB is initialised before the web process starts via the release command.
release: python -c "from app import init_db; init_db()"
web: gunicorn app:app --workers 2 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile -
