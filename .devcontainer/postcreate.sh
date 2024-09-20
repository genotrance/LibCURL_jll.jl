#! /bin/bash

git config --global --unset http.proxy
git config --global --unset https.proxy
git config --global --add safe.directory /workspaces/libcurl
git config --global pull.rebase false

julia -e 'using Pkg; Pkg.add(["BinaryBuilder", "BinaryBuilderBase", "CodecZlib", "JSON3", "URIs"]); Pkg.precompile()'
