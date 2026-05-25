#!/usr/bin/env sh
# Run python-semantic-release in CI.
#
# Determines whether a new version should be released, performs the release if
# so, and writes RELEASED=true|false (plus VERSION=...) to release.env for
# downstream CI jobs to consume via dotenv artifacts.
#
# On an actual release, also installs gitsign and configures git so that the
# release commit + tag produced by PSR are Sigstore-signed. Skipped on
# no-release runs to keep those pipelines fast.
#
# Expects these env vars from GitLab CI:
#   CI_COMMIT_BRANCH, CI_SERVER_PROTOCOL, CI_JOB_TOKEN, CI_SERVER_HOST,
#   CI_PROJECT_PATH
# Plus these when actually releasing (from .gitlab/ci/release.yml):
#   GITSIGN_VERSION (pinned, Renovate-tracked)
#   SIGSTORE_ID_TOKEN (auto-injected via the id_tokens: block)

set -eu

# ---------------------------------------------------------------------------
# Sign-the-release-commit setup. Self-contained so it runs only when we know
# we're going to release (see the `if` block below).
# ---------------------------------------------------------------------------
install_gitsign() {
    # gitsign GitHub release assets are named without the leading `v`
    # (tag `v0.10.2` → asset `gitsign_0.10.2_linux_amd64`).
    _ver="${GITSIGN_VERSION#v}"
    apt-get update -qq
    apt-get install -qq -y --no-install-recommends curl ca-certificates
    curl -fsSL -o /usr/local/bin/gitsign \
        "https://github.com/sigstore/gitsign/releases/download/${GITSIGN_VERSION}/gitsign_${_ver}_linux_amd64"
    chmod +x /usr/local/bin/gitsign
    gitsign --version
}

configure_git_signing() {
    # PSR shells out to `git commit` + `git tag`; with these settings, every
    # such invocation routes through gitsign, which picks up SIGSTORE_ID_TOKEN
    # automatically and runs unattended (no browser OIDC flow).
    git config --global user.name  "semantic-release"
    git config --global user.email "semantic-release@${CI_SERVER_HOST}"
    git config --global gpg.x509.program gitsign
    git config --global gpg.format       x509
    git config --global commit.gpgsign   true
    git config --global tag.gpgsign      true
}

# ---------------------------------------------------------------------------
# Decide release / no-release. PSR's --print-tag is cheap; the install +
# signing setup only runs once we know we're actually releasing.
# ---------------------------------------------------------------------------
# Re-attach HEAD so PSR can match branch rules against a real branch name.
git checkout "$CI_COMMIT_BRANCH"

# --print-tag always returns something; comparing it against
# --print-last-released-tag tells us whether a new release is pending.
VERSION=$(uv run semantic-release version --print-tag 2>/dev/null | tail -1) || true
CURRENT=$(uv run semantic-release version --print-last-released-tag 2>/dev/null | tail -1) || true

echo "VERSION=$VERSION" >> release.env

if [ "$VERSION" != "$CURRENT" ]; then
    echo "RELEASED=true" >> release.env
    install_gitsign
    configure_git_signing
    git remote set-url origin \
        "${CI_SERVER_PROTOCOL}://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git"
    uv run semantic-release -v version
else
    echo "RELEASED=false" >> release.env
    echo "No release needed"
fi
