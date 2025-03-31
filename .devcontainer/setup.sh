#!/usr/bin/env bash

# Install dependencies
sudo apt-get update && sudo apt-get install -y sqlite3

# Install Python Dependencies
uv sync --all-packages
