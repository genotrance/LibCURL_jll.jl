#! /bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 username/repo"
    exit 1
fi

# Post to GitHUB
LIBCURL_PATH="build/L/LibCURL"
cd $LIBCURL_PATH/LibCURL\@8

julia build_tarballs.jl --deploy-bin=$1 --skip-build
