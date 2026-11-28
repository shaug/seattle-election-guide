#!/usr/bin/env bash
# A closed, unmerged PR retires that exact pushed head. Older SHAs and forks
# do not own the current candidate. An open PR on our branch owns the slot.
set -euo pipefail
branch=$PRELIMINARY_RESULTS_BRANCH
repo=$GITHUB_REPOSITORY
gh api --paginate --method GET "repos/$repo/pulls" \
  -f state=all -f base=main -f "head=${repo%/*}:$branch" -F per_page=100 |
  jq -ers --arg repo "$repo" --arg branch "$branch" --arg sha "$1" '
    if length == 0 or any(.[]; type != "array") then error("Incomplete PR history") end |
    if any(.[][]; (.base.repo.full_name | type) != "string" or (.base.ref | type) != "string"
          or (.head.repo.full_name | type) != "string" or (.head.ref | type) != "string"
          or ((.head.sha // "") | test("^[0-9a-f]{40}$") | not)
          or (.state != "open" and .state != "closed") or (has("merged_at") | not))
    then error("Incomplete PR record") end |
    [ .[][] | select(.base.repo.full_name == $repo and .base.ref == "main"
                     and .head.repo.full_name == $repo and .head.ref == $branch) ] |
    if any(.[]; .state == "open") then "open"
    elif any(.[]; .state == "closed" and .merged_at == null and .head.sha == $sha) then "closed"
    else "available" end'
