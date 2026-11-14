#!/usr/bin/env bash
# Opens, updates or closes the "<workflow> job failing" issue (see action.yml).
# A problem here is printed as a warning and never fails the job: on failure
# the job has already failed, and on success it must stay green.
set -uo pipefail

repo=$GITHUB_REPOSITORY
title="$GITHUB_WORKFLOW job failing"
attempt=${GITHUB_RUN_ATTEMPT:-1}
run_url="$GITHUB_SERVER_URL/$repo/actions/runs/$GITHUB_RUN_ID"
[ "$attempt" = 1 ] || run_url="$run_url/attempts/$attempt"
now=$(date -u '+%Y-%m-%d %H:%M UTC')

warn() { echo "::warning title=job-alert::$*"; exit 0; }

# The open issue for this workflow. A plain listing, not the search API, so it
# also sees an issue opened seconds ago.
open=$(gh api "repos/$repo/issues?state=open&labels=$LABEL&per_page=100") || warn "could not list issues"
number=$(jq -r --arg t "$title" '[.[] | select(.title == $t and (.pull_request | not))][0].number // empty' <<<"$open")

case "$OUTCOME" in
failure)
  # Steps of this run that failed so far (the job is still running, but its finished steps are listed).
  steps=$(gh api "repos/$repo/actions/runs/$GITHUB_RUN_ID/attempts/$attempt/jobs" \
    --jq '[.jobs[].steps[]? | select(.conclusion == "failure") | .name] | unique | join(", ")' 2>/dev/null)
  steps=${steps:-unknown (see the run)}
  if [ -n "$number" ]; then
    gh api "repos/$repo/issues/$number/comments" -f body="Failed again on $now: $run_url
Failed step: **$steps**" >/dev/null || warn "could not comment on #$number"
    echo "Commented on #$number."
  else
    gh api "repos/$repo/labels" -f name="$LABEL" -f color=B60205 \
      -f description="A scheduled job is failing; opened and closed by the job itself" >/dev/null 2>&1 || true
    body="The **$GITHUB_WORKFLOW** job failed on $now.

- Run: $run_url
- Failed step: **$steps**
- Started by: \`$GITHUB_EVENT_NAME\` on commit ${GITHUB_SHA:0:7}

Each further failure adds a comment here; the next successful run closes this issue. Opened by \`.github/actions/job-alert\`."
    url=$(gh api "repos/$repo/issues" -f title="$title" -f body="$body" -f "labels[]=$LABEL" --jq .html_url) \
      || warn "could not open an issue"
    # Assigned to the repository's owner: an assignment notifies even someone who doesn't watch every issue.
    gh api "repos/$repo/issues/${url##*/}/assignees" -f "assignees[]=$GITHUB_REPOSITORY_OWNER" >/dev/null 2>&1 || true
    echo "Opened $url"
  fi
  ;;
success)
  if [ -z "$number" ]; then
    echo "No open \"$title\" issue."
    exit 0
  fi
  gh api "repos/$repo/issues/$number/comments" -f body="Recovered on $now: $run_url succeeded." >/dev/null \
    || warn "could not comment on #$number"
  gh api -X PATCH "repos/$repo/issues/$number" -f state=closed -f state_reason=completed >/dev/null \
    || warn "could not close #$number"
  echo "Closed #$number."
  ;;
*)
  warn "outcome must be failure or success, got: $OUTCOME"
  ;;
esac
