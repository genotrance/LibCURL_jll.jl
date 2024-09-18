#! /bin/bash

git config --global --unset http.proxy
git config --global --unset https.proxy
git config --global --add safe.directory /workspaces/libcurl
git config --global pull.rebase false

julia -e 'using Pkg; Pkg.precompile();'
julia -e 'using Pkg; Pkg.add("BinaryBuilder")'
julia -e 'using Pkg; Pkg.add("BinaryBuilderBase")'
