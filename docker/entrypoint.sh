#!/bin/sh
# Production entrypoint. Migrations run in the deploy script (one-off container), not here,
# so several web replicas never race to migrate.
set -eu
exec "$@"
