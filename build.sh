#! /bin/bash

# Checkout yggdrasil
if [ -d "build/.git" ]; then
    echo "Updating repository."
    git -C build reset --hard HEAD
    git -C build pull
else
    echo "Cloning repository from scratch."
    rm -rf build
    git clone --depth 1 https://github.com/JuliaPackaging/Yggdrasil build
fi

LIBCURL_PATH="build/L/LibCURL"

# Apply patch to build/L/LibCurl/common.jl
patch $LIBCURL_PATH/common.jl < common.jl.patch

cd $LIBCURL_PATH/LibCURL\@8

# Change version if specified
if [ -n "$1" ]; then
    echo "Changing version to $1"
    sed -i -E s/v\"[0-9]+\.[0-9]+\.[0-9]+\"/v\"$1\"/ build_tarballs.jl
fi

# Build for specified platforms
julia --color=yes build_tarballs.jl aarch64-apple-darwin,aarch64-linux-gnu,aarch64-linux-musl,x86_64-apple-darwin,x86_64-linux-gnu,x86_64-linux-musl,x86_64-w64-mingw32 --verbose

# Skipped platforms
# aarch64-unknown-freebsd, armv6l-linux-gnueabihf, armv6l-linux-musleabihf, armv7l-linux-gnueabihf, armv7l-linux-musleabihf, i686-linux-gnu, i686-linux-musl, i686-w64-mingw32, powerpc64le-linux-gnu, x86_64-unknown-freebsd,
