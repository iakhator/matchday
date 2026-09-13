#!/usr/bin/env sh
#
# Entrypoint for the production image.
#
#   migrate   apply database migrations, then exit
#   serve     run the API (the default)
#   <other>   executed as-is, so `docker run ... sh` still works
#
# Migrations are deliberately NOT run on `serve`. Two reasons:
#
#   1. With more than one replica, every container starting at once races
#      to migrate the same database. Alembic locks, so the result is a
#      slow rolling restart rather than corruption - but it makes "a
#      container restarted" and "the schema changed" the same event, which
#      is not a thing you want to discover during an incident.
#
#   2. A release phase that fails should stop the deploy. If migrations
#      run inside the app process, a failed migration looks like a
#      crash-looping container, and the platform will keep restarting it.
#
# So the deploy pipeline owns migrations and calls `migrate` before
# `serve`. Do not apply them by hand either: a database migrated ahead of
# the code that is deployed will fail the next release phase on a revision
# it cannot find, which is a genuinely unpleasant place to be mid-deploy.

set -eu

case "${1:-serve}" in
    migrate)
        echo "Applying database migrations..."
        exec alembic upgrade head
        ;;
    serve)
        # Workers default to 1. The rate limiter in app/core/rate_limit.py
        # counts in-process, so N workers allow N times the configured
        # rate - raise this only if you have read that note and accept it.
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT:-8010}" \
            --workers "${WEB_CONCURRENCY:-1}"
        ;;
    *)
        exec "$@"
        ;;
esac
