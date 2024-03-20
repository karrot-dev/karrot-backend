#!/bin/sh

set -eu

case "${1:-}" in
"/"*)
  # Starts with / - we'll treat is as a proper command
  exec "$@"
;;
*)
  # Otherwise treat is as a karrot cli command

  # With MIGRATE env variable non-empty we'll run the migrations
  if [ ! -z "${MIGRATE:-}" ]; then
    python -m karrot.cli migrate
  fi

  # Then run a karrot CLI command
  exec python -m karrot.cli "$@"
;;
esac
