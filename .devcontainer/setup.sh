#!/usr/bin/env bash

sudo apt-get update && sudo apt-get install -y sqlite3
pip3 install --user -r requirements.txt

python3 -m venv docs/.venv
source docs/.venv/bin/activate
pip3 install -r docs/requirements.txt
deactivate

# add an alias for mkdocs in the .bashrc file
echo "alias mkdocs='docs/.venv/bin/python3 -m mkdocs'" >> ~/.bashrc
