# Use the base image
FROM mcr.microsoft.com/devcontainers/base:bullseye

# Install Julia
RUN curl -fsSL https://julialang-s3.julialang.org/bin/linux/x64/1.7/julia-1.7.3-linux-x86_64.tar.gz | tar -xz -C /usr/local --strip-components=1

# Set environment variables
ENV BINARYBUILDER_RUNNER=privileged
ENV BINARYBUILDER_AUTOMATIC_APPLE=true
ENV BINARYBUILDER_USE_CCACHE=true

# Configure Git
RUN git config --global pull.rebase false && \
      git config --global --add safe.directory /libcurl && \
      git config --global --add safe.directory /libcurl/build

WORKDIR /libcurl
