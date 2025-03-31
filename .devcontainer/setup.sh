#!/usr/bin/env bash

# Install dependencies
sudo apt-get update && sudo apt-get install -y sqlite3

# Install Python Dependencies
uv sync

# Install act
mkdir /tmp/act && cd /tmp/act
curl -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | bash
mv bin/act ~/.local/bin
cd ~ && rm -rf /tmp/act

# Disable hardlinking for uv
echo "export UV_LINK_MODE=copy" >> ~/.bashrc

# Create an alias for mkdocs
echo "alias mkdocs='uv run --package docs mkdocs'" >> ~/.bashrc
