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

## Version Scheme

- **Upstream**: `LibCURL-v8.18.0+0`
- **Our build**: `8.18.0+1` (always increments the `+N` suffix by 1)

## Customizations

The build applies these patches to upstream LibCURL:

1. **Remove LibSSH2**: Removes `--with-libssh2` from configure flags and `LibSSH2_jll` dependency
2. **Enable Kerberos**: Enables Kerberos support on Linux and FreeBSD platforms
3. **Add dependency**: Adds `Kerberos_krb5_jll` to the dependency list
4. **Fix macOS OpenSSL**: Fixes `openssl_platforms` filter to include macOS when using OpenSSL

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
