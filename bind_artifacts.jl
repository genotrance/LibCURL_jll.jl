# Adapted from https://github.com/beacon-biosignals/Ray.jl

using Base: SHA1
using Base.BinaryPlatforms
using CodecZlib: GzipDecompressorStream
using Downloads
using JSON3
using LibGit2: LibGit2
using Pkg.Artifacts: bind_artifact!
using Pkg.Types: read_project
using SHA: sha256
using Tar
using URIs: URI, unescapeuri

const REQUIRED_BASE_TRIPLETS = ("aarch64-apple-darwin", "aarch64-linux-gnu", "aarch64-linux-musl", "x86_64-apple-darwin", "x86_64-linux-gnu", "x86_64-linux-musl", "x86_64-w64-mingw32", "aarch64-unknown-freebsd", "armv6l-linux-gnueabihf", "armv6l-linux-musleabihf", "armv7l-linux-gnueabihf", "armv7l-linux-musleabihf", "i686-linux-gnu", "i686-linux-musl", "i686-w64-mingw32", "powerpc64le-linux-gnu", "x86_64-unknown-freebsd")

const REQUIRED_PLATFORMS = parse.(Platform, REQUIRED_BASE_TRIPLETS)

function remote_url(repo_root::AbstractString, name::AbstractString="origin")
    return LibGit2.with(LibGit2.GitRepo(repo_root)) do repo
        LibGit2.with(LibGit2.lookup_remote(repo, name)) do remote
            return LibGit2.url(remote)
        end
    end
end

function convert_to_https_url(url)
    m = match(LibGit2.URL_REGEX, url)
    if m === nothing
        throw(ArgumentError("URL is not a valid SCP or HTTP(S) URL: $(url)"))
    end
    # Purposefully excluding username as we're assuming this is a public repo
    return LibGit2.git_url(; scheme="https", host=something(m[:host], ""),
                           port=something(m[:port], ""), path=something(m[:path], ""))
end

const REPO_PATH = pwd()
const REPO_HTTPS_URL = convert_to_https_url(remote_url(REPO_PATH))
const ARTIFACTS_TOML = joinpath(REPO_PATH, "Artifacts.toml")
const TARBALL_DIR = joinpath(REPO_PATH, "build", "L", "LibCURL", "LibCURL@8", "products")

const TAG, TAGFULL = let
    project_toml = joinpath(REPO_PATH, "Project.toml")
    project = read_project(project_toml)
    "v$(project.version.major).$(project.version.minor).$(project.version.patch)",
    "LibCURL-v$(project.version)"
end

function gen_artifact_url(; repo_url, tag, filename)
    return join([repo_url, "releases", "download", tag, filename], '/')
end

function gen_artifact_filename(; tag::AbstractString, platform::Platform)
    return "LibCURL.$tag.$(triplet(platform)).tar.gz"
end

# Compute the Artifact.toml `git-tree-sha1`.
function tree_hash_sha1(tarball_path)
    return open(GzipDecompressorStream, tarball_path, "r") do tar
        return SHA1(Tar.tree_hash(tar))
    end
end

# Compute the Artifact.toml `sha256` from the compressed archive.
function sha256sum(tarball_path)
    return open(tarball_path, "r") do tar
        return bytes2hex(sha256(tar))
    end
end

function bind_artifacts()
    # Start with a clean Artifacts.toml so that unsupported platforms are removed
    isfile(ARTIFACTS_TOML) && rm(ARTIFACTS_TOML)

    for platform in REQUIRED_PLATFORMS
        artifact_name = gen_artifact_filename(; tag=TAG, platform)
        artifact_url = gen_artifact_url(; repo_url=REPO_HTTPS_URL, tag=TAGFULL,
                                        filename=artifact_name)

        artifact_path = joinpath(TARBALL_DIR, artifact_name)
        isfile(artifact_path) || error("No such file $artifact_path")

        @info "Adding artifact for $(triplet(platform))"
        bind_artifact!(ARTIFACTS_TOML,
                       "LibCURL",
                       tree_hash_sha1(artifact_path);
                       platform=platform,
                       download_info=[(artifact_url, sha256sum(artifact_path))])
    end
end

if abspath(PROGRAM_FILE) == @__FILE__
    bind_artifacts()
end