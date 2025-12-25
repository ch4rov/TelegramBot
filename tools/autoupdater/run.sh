#!/bin/sh
set -eu

REPO_DIR="${REPO_DIR:-/repo}"
BRANCH="${GIT_BRANCH:-main}"
POLL_SEC="${POLL_SEC:-60}"
SERVICES="${COMPOSE_SERVICES:-telegrambot miniapp-backend}"
HARD_RESET="${HARD_RESET:-false}"

cd "$REPO_DIR"

git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true

echo "[autoupdater] repo=$REPO_DIR branch=$BRANCH poll=${POLL_SEC}s services=$SERVICES"

while true; do
  git fetch origin "$BRANCH" --prune >/dev/null 2>&1 || true

  LOCAL_SHA="$(git rev-parse HEAD 2>/dev/null || echo '')"
  REMOTE_SHA="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo '')"

  if [ -n "$REMOTE_SHA" ] && [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    echo "[autoupdater] update detected: $LOCAL_SHA -> $REMOTE_SHA"

    if ! git pull --ff-only origin "$BRANCH"; then
      if [ "$HARD_RESET" = "true" ] || [ "$HARD_RESET" = "1" ] || [ "$HARD_RESET" = "yes" ]; then
        echo "[autoupdater] pull failed; hard reset to origin/$BRANCH"
        git reset --hard "origin/$BRANCH"
      else
        echo "[autoupdater] pull failed; skipping (set HARD_RESET=true to force)"
        sleep "$POLL_SEC"
        continue
      fi
    fi

    echo "[autoupdater] rebuild/restart: $SERVICES"
    docker compose up -d --build $SERVICES
  fi

  sleep "$POLL_SEC"
done
