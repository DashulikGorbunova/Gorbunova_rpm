#!/usr/bin/env bash
set -euo pipefail
# Dedicated local development database, no host ports and no production credentials.
name="${PG_CONTAINER:-rpm-lab-postgres}"
if ! docker --host=unix:///var/run/docker.sock container inspect "$name" >/dev/null 2>&1; then
  docker --host=unix:///var/run/docker.sock run -d --name "$name" -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5
else
  docker --host=unix:///var/run/docker.sock start "$name" >/dev/null
fi
for i in {1..30}; do
  if docker --host=unix:///var/run/docker.sock exec "$name" pg_isready -U postgres >/dev/null; then exit 0; fi
  sleep 1
done
exit 1
