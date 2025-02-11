#!/usr/bin/env bash

# install dependencies
sudo apt-get update && sudo apt-get install -y sqlite3
pip3 install -r requirements.txt

# install mkdocs
python3 -m venv docs/.venv
source docs/.venv/bin/activate
pip3 install -r docs/requirements.txt
deactivate
echo "alias mkdocs='docs/.venv/bin/python3 -m mkdocs'" >> ~/.bashrc

# install act
mkdir /tmp/act && cd /tmp/act
curl -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | bash
mv bin/act ~/.local/bin
cd ~ && rm -rf /tmp/act
