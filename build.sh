#! /bin/bash

if [ ! -f /.dockerenv ]; then
  # Build container and run
  docker build . -t libcurl_devcontainer
  docker run -it --rm -v $(pwd):/libcurl --privileged libcurl_devcontainer /libcurl/build.sh $@
elif [[ "$1" = "--post" ]]; then
  # Post payload to Github

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
else
  # Build binaries

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
  patch -u $LIBCURL_PATH/common.jl -i common.jl.patch

  cd $LIBCURL_PATH/LibCURL\@8

  # Change version if specified
  if [ -n "$1" ]; then
    echo "Changing version to $1"
    sed -i -E s/v\"[0-9]+\.[0-9]+\.[0-9]+\"/v\"$1\"/ build_tarballs.jl
  fi

  # Build for specified platforms
  julia --color=yes build_tarballs.jl --verbose aarch64-apple-darwin,aarch64-linux-gnu,aarch64-linux-musl,x86_64-apple-darwin,x86_64-linux-gnu,x86_64-linux-musl,x86_64-w64-mingw32,aarch64-unknown-freebsd,armv6l-linux-gnueabihf,armv6l-linux-musleabihf,armv7l-linux-gnueabihf,armv7l-linux-musleabihf,i686-linux-gnu,i686-linux-musl,i686-w64-mingw32,powerpc64le-linux-gnu,x86_64-unknown-freebsd
fi
