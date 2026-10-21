# Custom builds of LibCURL for pymcurl using binarybuilder.org

This project builds custom binaries of the [LibCURL_jll.jl](https://github.com/JuliaBinaryWrappers/LibCURL_jll.jl/)
project for [pymcurl](https://github.com/genotrance/mcurl). The build has been modified to include `Kerberos_krb5`
on Linux/FreeBSD and remove `LibSSH2` on all platforms.

## Automated Build System

The build system is **fully automated** with **incremental build support**. Simply run `./build.sh` and it will:

1. **Detect** the latest upstream version from `JuliaBinaryWrappers/LibCURL_jll.jl`
2. **Check** if a rebuild is needed (compares with our latest release)
3. **Skip** if already up-to-date, or proceed with build if new version available
4. **Setup** Yggdrasil repository and apply patches
5. **Build** only platforms that haven't been built yet (incremental builds)
6. **Post** artifacts to GitHub (when using `--post` flag)

### Prerequisites

- **Docker**: For containerized builds
- **GitHub CLI (`gh`)**: Must be installed and authenticated (`gh auth login`)

### Usage

#### Check and Build (if needed)

```bash
./build.sh
```

This will automatically:
- Detect the latest upstream LibCURL version
- Exit immediately if already up-to-date
- **Skip platforms that are already built** (incremental builds)
- Build only missing platforms sequentially
- Display progress as each platform builds

The build artifacts are created in `build/L/LibCURL/LibCURL@8/products`.

**Incremental Builds**: The script automatically detects which platforms have already been built by checking for existing artifacts in the products directory. Only missing platforms will be built, saving time on partial rebuilds.

#### Force Rebuild

To rebuild all platforms from scratch (deleting existing artifacts):

```bash
./build.sh --force
```

This will:
- Delete all existing artifacts for the current version
- Rebuild all 8 platforms sequentially

#### Post to GitHub

After a successful build, post the artifacts:

```bash
./build.sh --post
```

This will automatically:
- Update `Project.toml` with the new version
- Generate `Artifacts.toml`
- Commit and push changes
- Create a GitHub release and upload all artifacts

**No manual steps required!**

## Weekly GitHub Release Automation

`.github/workflows/build.yml` checks upstream every Monday at **06:00 UTC**. This
precedes mcurl's Monday 18:00 UTC check so the downstream package can consume a
completed LibCURL release.

- The setup job computes the target from the latest upstream release, then checks
  for the corresponding `LibCURL-v<version>` release in this repository.
- If the release and all eight `Artifacts.toml` URLs are already present, the
  scheduled run succeeds after setup; build, test, and release jobs are skipped.
- For a new upstream release, the workflow builds all eight platforms, runs the
  existing platform tests, commits `Project.toml` and `Artifacts.toml`, then
  publishes the GitHub release.
- Pushes and manual dispatches still build and test as before. `devel` never
  releases. On `main`, the release job also checks the GitHub release immediately
  before publishing, so it cannot create a duplicate.

The metadata commit is pushed before publication. If that push succeeds but
publication fails, the next Monday rebuilds and publishes the missing release.
If publication exists but the metadata is absent (for example, an interrupted
run at the opposite boundary), the next run rebuilds only to reconcile and commit
the metadata, while the final release check skips duplicate publication. A normal
completed release therefore makes future scheduled runs no-ops.

The workflow uses `GITHUB_TOKEN` with `contents: write` for the metadata push and
release. In repository **Settings -> Actions -> General**, set *Workflow
permissions* to **Read and write permissions** and allow GitHub Actions to create
and approve pull requests only if local policy requires it. If `main` branch
protection is enabled, allow `github-actions[bot]` (or this workflow) to push the
release metadata, or exempt this workflow from the required PR rule. Pushes made
with `GITHUB_TOKEN` do not trigger another `push` workflow run, so the release
commit cannot create a workflow loop.

## Version Scheme

- **Upstream**: `LibCURL-v8.18.0+0`
- **Our build**: `8.18.0+1` (always increments the `+N` suffix by 1)

## Customizations

The build applies these patches to upstream LibCURL:

1. **Remove LibSSH2**: Removes `--with-libssh2` from configure flags and `LibSSH2_jll` dependency
2. **Enable Kerberos**: Enables Kerberos support on Linux and FreeBSD platforms
3. **Add dependency**: Adds `Kerberos_krb5_jll` to the dependency list
4. **Enable NTLM**: Re-enables NTLM authentication (`--enable-ntlm`), which was disabled by default since curl 8.21 as the protocol is deprecated upstream. This flag may need to be removed once curl drops NTLM support entirely.
5. **Fix macOS OpenSSL**: Fixes `openssl_platforms` filter to include macOS when using OpenSSL

All patches are applied idempotently using content-based matching (not line numbers), making them resilient to upstream changes.

## Supported Platforms

The build targets 8 platforms required for pymcurl:
- `x86_64-linux-gnu`
- `x86_64-linux-musl`
- `x86_64-w64-mingw32` (x86_64-windows)
- `i686-linux-gnu`
- `aarch64-linux-gnu`
- `aarch64-linux-musl`
- `aarch64-apple-darwin` (arm64-mac)
- `x86_64-apple-darwin` (x86_64-macos)
