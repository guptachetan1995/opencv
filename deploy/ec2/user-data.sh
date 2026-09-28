#!/bin/bash
# EC2 user data for Second Look. Paste this whole file into the launch wizard's
# Advanced details > User data field (docs/deploy.md, "EC2 console deploy").
#
# Runs once, as root, on the instance's first boot: installs Docker and git, clones the
# PUBLIC repository, builds deploy/ec2/Dockerfile, and runs app/server.py behind port 80.
# The reviewer token is generated here, on the instance, so it never appears in this
# script, in the console form, or in the repository. It is written to a root-only file
# and printed once to the instance's system log, where the owner reads it.
set -euo pipefail

dnf install -y docker git
systemctl enable --now docker

git clone --depth 1 https://github.com/guptachetan1995/opencv /opt/secondlook
docker build -f /opt/secondlook/deploy/ec2/Dockerfile -t secondlook:ec2 /opt/secondlook

umask 077
python3 -c 'import secrets; print(secrets.token_hex(16))' > /root/reviewer-token
docker run -d --name secondlook --restart unless-stopped -p 80:8080 \
  -e REVIEWER_TOKEN="$(cat /root/reviewer-token)" secondlook:ec2

echo "second-look reviewer token: $(cat /root/reviewer-token)" > /dev/console
echo "second-look: serving on port 80" > /dev/console
