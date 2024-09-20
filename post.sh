#! /bin/bash

# Prompt to update Project.toml version
echo "Update Project.toml version info"
echo
echo "Press any key to continue..."
read -n 1 -s -r

# Generate Artifacts.toml
echo "Generating Artifacts.toml"
julia bind_artifacts.jl

# Prompt user to check in version changes
echo "Please review Artifacts.toml and commit/push changes"
echo "The next step will create a tag and upload artifacts"
echo
echo "Press any key to continue..."
read -n 1 -s -r

# Get the GitHub repository URL
GITHUB_REPO_URL=$(git config --get remote.origin.url)
GITHUB_REPO_PATH=$(echo $GITHUB_REPO_URL | sed -E 's/^(https?:\/\/|git@)([^\/]+)\/(.+)$/\3/')
echo $GITHUB_REPO_PATH

# Post artifacts to GitHUB
LIBCURL_PATH="build/L/LibCURL"
cd $LIBCURL_PATH/LibCURL\@8

echo "Uploading artifacts"
julia build_tarballs.jl --deploy-bin=$GITHUB_REPO_PATH --skip-build
