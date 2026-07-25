#!/bin/bash
export SUDO_ASKPASS=/home/raspberry/.livi-askpass
sudo() { command sudo -A "$@"; }
export -f sudo
bash /home/raspberry/setup-pi.sh
