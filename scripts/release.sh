#!/usr/bin/env sh
# Run python-semantic-release in CI.
#
# Determines whether a new version should be released, performs the release if
# so, and writes RELEASED=true|false (plus VERSION=...) to release.env for
# downstream CI jobs to consume via dotenv artifacts.
#
# Expects these env vars from GitLab CI:
#   CI_COMMIT_BRANCH, CI_SERVER_PROTOCOL, CI_JOB_TOKEN, CI_SERVER_HOST,
#   CI_PROJECT_PATH

set -eu

# Re-attach HEAD so PSR can match branch rules against a real branch name.
git checkout "$CI_COMMIT_BRANCH"

# Determine the version PSR would emit (current or next).
# --print-tag always returns something; comparing it against
# --print-last-released-tag tells us whether a new release is pending.
VERSION=$(uv run semantic-release version --print-tag 2>/dev/null | tail -1) || true
CURRENT=$(uv run semantic-release version --print-last-released-tag 2>/dev/null | tail -1) || true

echo "VERSION=$VERSION" >> release.env

if [ "$VERSION" != "$CURRENT" ]; then
    echo "RELEASED=true" >> release.env
    git remote set-url origin \
        "${CI_SERVER_PROTOCOL}://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git"
    uv run semantic-release -v version
else
    echo "RELEASED=false" >> release.env
    echo "No release needed"
fi
