# Install-tier test image: a clean Ubuntu with the airlab .deb installed.
# The .deb is built (from a staging tree of usr/ + etc/ + DEBIAN/) into the build
# context by the test fixture, then COPY'd in here.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

COPY airlab.deb /tmp/airlab.deb

# Install the package's Pre-Depends, then the package itself.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl lsb-release openssh-server rsync sshpass tmux tmuxp git ca-certificates \
 && dpkg -i /tmp/airlab.deb \
 && rm -f /tmp/airlab.deb \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
