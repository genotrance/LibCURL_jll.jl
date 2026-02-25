# Use the base image
FROM mcr.microsoft.com/devcontainers/base:bullseye

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Julia
RUN curl -fsSL https://julialang-s3.julialang.org/bin/linux/x64/1.7/julia-1.7.3-linux-x86_64.tar.gz | tar -xz -C /usr/local --strip-components=1

# Pre-install Julia packages for faster container startup
RUN julia -e 'using Pkg; Pkg.add(["BinaryBuilder", "BinaryBuilderBase", "CodecZlib", "JSON3", "URIs"]); Pkg.precompile()'

# Set environment variables
ENV BINARYBUILDER_RUNNER=privileged
ENV BINARYBUILDER_AUTOMATIC_APPLE=true
ENV BINARYBUILDER_USE_CCACHE=true

# Configure Git
RUN git config --global pull.rebase false && \
      git config --global --add safe.directory /libcurl && \
      git config --global --add safe.directory /libcurl/build

WORKDIR /libcurl
