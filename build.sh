#! /bin/bash
set -e

# ============================================================================
# Automated LibCURL Build Script
# ============================================================================
# Detects latest upstream version, checks if rebuild is needed, patches,
# builds sequentially with incremental support, and posts to GitHub.
# ============================================================================

# Platform list (pymcurl targets only)
PLATFORMS=(
  "x86_64-linux-gnu"
  "x86_64-linux-musl"
  "x86_64-w64-mingw32"        # x86_64-windows
  "i686-linux-gnu"
  "aarch64-linux-gnu"
  "aarch64-linux-musl"
  "aarch64-apple-darwin"      # arm64-mac
  "x86_64-apple-darwin"       # x86_64-macos
  # "aarch64-unknown-freebsd"
  # "armv6l-linux-gnueabihf"
  # "armv6l-linux-musleabihf"
  # "armv7l-linux-gnueabihf"
  # "armv7l-linux-musleabihf"
  # "i686-linux-musl"
  # "i686-w64-mingw32"
  # "powerpc64le-linux-gnu"
  # "x86_64-unknown-freebsd"
)

# Helper: Extract version from tag (e.g., "LibCURL-v8.18.0+0" -> "8.18.0+0")
extract_version() {
  echo "$1" | sed -E 's/^LibCURL-v(.+)$/\1/'
}

# Helper: Get latest release tag from a GitHub repo using gh CLI
get_latest_release_tag() {
  local repo="$1"
  gh release list --repo "$repo" --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || echo ""
}

# Helper: Parse version into base and suffix (e.g., "8.18.0+0" -> base=8.18.0, suffix=0)
parse_version() {
  local version="$1"
  local base=$(echo "$version" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+)\+.*$/\1/')
  local suffix=$(echo "$version" | sed -E 's/^[0-9]+\.[0-9]+\.[0-9]+\+([0-9]+)$/\1/')
  echo "$base $suffix"
}

# Helper: Update Project.toml version
update_project_version() {
  local new_version="$1"
  sed -i -E "s/^version = \"[^\"]+\"/version = \"$new_version\"/" Project.toml
  echo "Updated Project.toml to version $new_version"
}

# Helper: Apply idempotent patches to common.jl
apply_common_patches() {
  local common_file="$1"

  echo "Applying idempotent patches to $common_file"

  # Patch 1: Remove --with-libssh2 from configure flags
  if grep -q -- '--with-libssh2' "$common_file"; then
    echo "  - Removing --with-libssh2 from configure flags"
    sed -i -E 's/--with-libssh2=\$\{prefix\} //' "$common_file"
  else
    echo "  - LibSSH2 already removed (skipping)"
  fi

  # Patch 2: Enable Kerberos for Linux and FreeBSD
  if grep -q 'if false; then' "$common_file"; then
    echo "  - Enabling Kerberos for Linux and FreeBSD"
    sed -i -E 's/if false; then/if [[ "${target}" == *linux* ]] || [[ "${target}" == *-freebsd* ]]; then/' "$common_file"
  else
    echo "  - Kerberos condition already updated (skipping)"
  fi

  # Patch 3: Remove LibSSH2_jll dependency
  if grep -q 'Dependency("LibSSH2_jll")' "$common_file"; then
    echo "  - Removing LibSSH2_jll dependency"
    sed -i '/Dependency("LibSSH2_jll")/d' "$common_file"
  else
    echo "  - LibSSH2_jll dependency already removed (skipping)"
  fi

  # Patch 4: Add Kerberos_krb5_jll dependency
  if ! grep -q 'Kerberos_krb5_jll' "$common_file"; then
    echo "  - Adding Kerberos_krb5_jll dependency"
    sed -i '/Dependency("OpenSSL_jll"/a\        Dependency("Kerberos_krb5_jll"; platforms=filter(p->Sys.islinux(p) || Sys.isfreebsd(p), platforms)),' "$common_file"
  else
    echo "  - Kerberos_krb5_jll dependency already present (skipping)"
  fi

  # Patch 5: Fix openssl_platforms to include macOS when macos_use_openssl is true
  if grep -q 'openssl_platforms = if macos_use_openssl' "$common_file"; then
    if grep -q 'filter(p->Sys.islinux(p) || Sys.isfreebsd(p), platforms)' "$common_file"; then
      echo "  - Fixing openssl_platforms to include macOS"
      sed -i 's/filter(p->Sys\.islinux(p) || Sys\.isfreebsd(p), platforms)/filter(p->Sys.islinux(p) || Sys.isfreebsd(p) || Sys.isapple(p), platforms)/' "$common_file"
    else
      echo "  - openssl_platforms already includes macOS (skipping)"
    fi
  else
    echo "  - openssl_platforms filter not found (skipping)"
  fi

  echo "Patches applied successfully"
}

# ============================================================================
# Main Logic
# ============================================================================

if [ ! -f /.dockerenv ]; then
  # ========================================================================
  # OUTSIDE DOCKER: Version detection and build orchestration
  # ========================================================================

  # Parse arguments
  POST_ARG=""
  FORCE_ARG=""
  for arg in "$@"; do
    if [[ "$arg" == "--post" ]]; then
      POST_ARG="--post"
    elif [[ "$arg" == "--force" ]]; then
      FORCE_ARG="--force"
    fi
  done

  # If --post, handle posting inside Docker container
  if [ -n "$POST_ARG" ]; then
    echo "=== Posting Artifacts to GitHub ==="
    echo

    # Check for gh CLI and credentials
    if ! command -v gh &> /dev/null; then
      echo "ERROR: gh CLI not found. Please install it: https://cli.github.com/"
      exit 1
    fi

    if ! gh auth status &> /dev/null; then
      echo "ERROR: gh CLI not authenticated. Run: gh auth login"
      exit 1
    fi

    # Get gh config directory
    GH_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gh"
    if [ ! -d "$GH_CONFIG_DIR" ]; then
      echo "ERROR: gh config directory not found at $GH_CONFIG_DIR"
      exit 1
    fi

    # Run post inside Docker container with gh credentials mounted
    echo "Running post inside Docker container..."
    docker run --rm --network host \
      -v $(pwd):/workspace:rw \
      -v $(pwd)/build:/libcurl/build:rw \
      -v $GH_CONFIG_DIR:/root/.config/gh:ro \
      -v $HOME/.julia:/root/.julia \
      --privileged \
      libcurl_devcontainer /workspace/build.sh --post-internal

    exit 0
  fi

  echo "=== LibCURL Automated Build System ==="
  echo

  # Check dependencies
  if ! command -v gh &> /dev/null; then
    echo "ERROR: gh CLI not found. Please install it: https://cli.github.com/"
    exit 1
  fi

  if ! gh auth status &> /dev/null; then
    echo "ERROR: gh CLI not authenticated. Run: gh auth login"
    exit 1
  fi

  echo "Detecting latest upstream version..."
  UPSTREAM_TAG=$(get_latest_release_tag "JuliaBinaryWrappers/LibCURL_jll.jl")

  if [ -z "$UPSTREAM_TAG" ]; then
    echo "ERROR: Could not detect upstream version from JuliaBinaryWrappers/LibCURL_jll.jl"
    exit 1
  fi

  UPSTREAM_VERSION=$(extract_version "$UPSTREAM_TAG")
  echo "  Upstream: $UPSTREAM_TAG (version: $UPSTREAM_VERSION)"

  # Parse upstream version
  read UPSTREAM_BASE UPSTREAM_SUFFIX <<< $(parse_version "$UPSTREAM_VERSION")

  # Our version is upstream base + (suffix + 1)
  OUR_SUFFIX=$((UPSTREAM_SUFFIX + 1))
  OUR_VERSION="${UPSTREAM_BASE}+${OUR_SUFFIX}"
  OUR_TAG="LibCURL-v${OUR_VERSION}"

  echo "  Our target: $OUR_TAG (version: $OUR_VERSION)"
  echo

  # Check if we already have this version released
  echo "Checking if rebuild is needed..."
  OUR_LATEST_TAG=$(get_latest_release_tag "genotrance/LibCURL_jll.jl")

  if [ -n "$OUR_LATEST_TAG" ]; then
    OUR_LATEST_VERSION=$(extract_version "$OUR_LATEST_TAG")
    echo "  Our latest: $OUR_LATEST_TAG (version: $OUR_LATEST_VERSION)"

    if [ "$OUR_VERSION" = "$OUR_LATEST_VERSION" ]; then
      echo
      echo "✓ Already up to date! No rebuild needed."
      exit 0
    fi
  else
    echo "  Our latest: (none found)"
  fi

  echo
  echo "→ Rebuild needed: $UPSTREAM_BASE → $OUR_VERSION"
  echo

  # Build Docker image
  echo "Building Docker container..."
  docker build . --network host -t libcurl_devcontainer

  # Setup Yggdrasil on host
  echo
  echo "Setting up Yggdrasil repository on host..."
  if [ -d "build/.git" ]; then
    echo "  Updating existing repository..."
    git -C build reset --hard HEAD
    git -C build pull
  else
    echo "  Cloning repository..."
    rm -rf build
    git clone --depth 1 https://github.com/JuliaPackaging/Yggdrasil build
  fi

  LIBCURL_PATH="build/L/LibCURL"

  # Apply patches on host
  echo
  apply_common_patches "$LIBCURL_PATH/common.jl"

  # Update version in build_tarballs.jl
  echo
  echo "Setting version to $UPSTREAM_BASE in build_tarballs.jl"
  sed -i -E "s/v\"[0-9]+\.[0-9]+\.[0-9]+\"/v\"$UPSTREAM_BASE\"/" "$LIBCURL_PATH/LibCURL@8/build_tarballs.jl"

  # Update Project.toml
  update_project_version "$OUR_VERSION"

  # Create products directory
  mkdir -p "$LIBCURL_PATH/LibCURL@8/products"

  # Handle --force flag
  if [ -n "$FORCE_ARG" ]; then
    echo
    echo "🔥 --force flag detected: Deleting existing artifacts..."
    rm -f "$LIBCURL_PATH/LibCURL@8/products/LibCURL.v${UPSTREAM_BASE}."*.tar.gz
    rm -f "$LIBCURL_PATH/LibCURL@8/products/LibCURL-logs.v${UPSTREAM_BASE}."*.tar.gz
    echo "   Deleted all artifacts for version $UPSTREAM_BASE"
  fi

  # Filter platforms - skip already built ones unless --force
  PLATFORMS_TO_BUILD=()
  PLATFORMS_SKIPPED=()

  echo
  echo "Checking for existing artifacts..."
  for platform in "${PLATFORMS[@]}"; do
    ARTIFACT_FILE="$LIBCURL_PATH/LibCURL@8/products/LibCURL.v${UPSTREAM_BASE}.${platform}.tar.gz"
    if [ -f "$ARTIFACT_FILE" ] && [ -z "$FORCE_ARG" ]; then
      PLATFORMS_SKIPPED+=("$platform")
      echo "  ✓ $platform (already built)"
    else
      PLATFORMS_TO_BUILD+=("$platform")
      echo "  → $platform (needs build)"
    fi
  done

  # Check if there's anything to build
  if [ ${#PLATFORMS_TO_BUILD[@]} -eq 0 ]; then
    echo
    echo "✓ All platforms already built! Nothing to do."
    echo
    echo "To rebuild everything, use: ./build.sh --force"
    exit 0
  fi

  echo
  echo "Summary:"
  echo "  To build: ${#PLATFORMS_TO_BUILD[@]} platforms"
  echo "  Skipped:  ${#PLATFORMS_SKIPPED[@]} platforms"

  # Build platforms sequentially
  echo
  echo "Starting sequential builds..."
  echo

  COMPLETED=0
  FAILED=0
  TOTAL_PLATFORMS=${#PLATFORMS_TO_BUILD[@]}

  for PLATFORM in "${PLATFORMS_TO_BUILD[@]}"; do
    COMPLETED_PLUS_FAILED=$((COMPLETED + FAILED))
    echo "[$((COMPLETED_PLUS_FAILED + 1))/$TOTAL_PLATFORMS] Building $PLATFORM..."

    # Launch Docker container for this platform
    if docker run --rm --network host \
      -v $(pwd):/workspace:ro \
      -v $(pwd)/build:/libcurl/build:rw \
      -v $HOME/.julia:/root/.julia \
      --privileged \
      -e BUILD_PLATFORM="$PLATFORM" \
      -e LIBCURL_VERSION="$UPSTREAM_BASE" \
      libcurl_devcontainer /workspace/build.sh --build-single; then
      echo "  ✓ Build complete for $PLATFORM"
      COMPLETED=$((COMPLETED + 1))
    else
      echo "  ✗ Build FAILED for $PLATFORM"
      FAILED=$((FAILED + 1))
    fi

    echo
  done

  echo "="
  echo "Build Summary:"
  echo "  Completed: $COMPLETED platforms"
  echo "  Failed:    $FAILED platforms"
  echo "  Skipped:   ${#PLATFORMS_SKIPPED[@]} platforms"
  echo
  echo "Build artifacts are in: build/L/LibCURL/LibCURL@8/products/"
  echo
  if [ $FAILED -gt 0 ]; then
    echo "⚠ Some builds failed. Review the output above for details."
    echo
  fi
  echo "To post artifacts to GitHub:"
  echo "  ./build.sh --post"

elif [[ "$1" = "--post-internal" ]]; then
  # ========================================================================
  # INSIDE DOCKER: Post artifacts to GitHub
  # ========================================================================

  echo "=== Posting Artifacts to GitHub (inside container) ==="
  echo

  cd /workspace

  # Configure git to trust the workspace directory
  git config --global --add safe.directory /workspace

  # Configure git to use gh CLI for authentication
  gh auth setup-git

  # Extract GitHub token for Julia/BinaryBuilder
  echo "Extracting GitHub token..."
  export GITHUB_TOKEN=$(gh auth token)
  if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: Could not extract GitHub token from gh CLI"
    exit 1
  fi
  echo "GitHub token configured for Julia"

  # Get version from Project.toml
  OUR_VERSION=$(grep '^version = ' Project.toml | sed -E 's/version = "(.+)"/\1/')

  if [ -z "$OUR_VERSION" ]; then
    echo "ERROR: Could not read version from Project.toml"
    exit 1
  fi

  echo "Version: $OUR_VERSION"
  echo

  # Generate Artifacts.toml
  echo "Generating Artifacts.toml..."
  julia bind_artifacts.jl

  # Commit and push changes
  echo
  echo "Committing changes..."

  # Get git user info from gh CLI
  GH_USER=$(gh api user --jq '.login' 2>/dev/null || echo "")
  GH_EMAIL=$(gh api user --jq '.email' 2>/dev/null || echo "")

  # Fall back to defaults if gh API fails
  if [ -z "$GH_USER" ]; then
    GH_USER="Automated Build"
  fi
  if [ -z "$GH_EMAIL" ] || [ "$GH_EMAIL" = "null" ]; then
    GH_EMAIL="${GH_USER}@users.noreply.github.com"
  fi

  git config --global user.name "$GH_USER"
  git config --global user.email "$GH_EMAIL"
  echo "Git user: $GH_USER <$GH_EMAIL>"

  # Add all changed files (build/ is already in .gitignore)
  git add -A

  git commit -m "Release $OUR_VERSION" || echo "No changes to commit"

  echo "Pushing to GitHub..."
  # Detect the default branch
  DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
  if [ -z "$DEFAULT_BRANCH" ]; then
    DEFAULT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
  fi
  git push origin "$DEFAULT_BRANCH"

  # Get the GitHub repository path
  GITHUB_REPO_URL=$(git config --get remote.origin.url)
  GITHUB_REPO_PATH=$(echo $GITHUB_REPO_URL | sed -E 's/^(https?:\/\/|git@)([^:\/]+)[:\/](.+?)(\.git)?$/\3/')
  echo "Repository: $GITHUB_REPO_PATH"

  # Post artifacts to GitHub
  cd /libcurl/build/L/LibCURL/LibCURL@8

  echo
  echo "Uploading artifacts to GitHub release..."
  julia build_tarballs.jl --deploy-bin=$GITHUB_REPO_PATH --skip-build

  echo
  echo "✓ Release complete: $OUR_VERSION"

elif [[ "$1" = "--build-single" ]]; then
  # ========================================================================
  # INSIDE DOCKER: Build single platform
  # ========================================================================

  if [ -z "$BUILD_PLATFORM" ]; then
    echo "ERROR: BUILD_PLATFORM not set"
    exit 1
  fi

  if [ -z "$LIBCURL_VERSION" ]; then
    echo "ERROR: LIBCURL_VERSION not set"
    exit 1
  fi

  echo "=== Building LibCURL for $BUILD_PLATFORM ==="
  echo "Version: $LIBCURL_VERSION"
  echo

  # Navigate to build directory
  cd /libcurl/build/L/LibCURL/LibCURL@8

  # Build single platform
  echo "Starting build..."
  julia --color=yes build_tarballs.jl --verbose "$BUILD_PLATFORM"

  echo
  echo "✓ Build complete for $BUILD_PLATFORM"

fi
