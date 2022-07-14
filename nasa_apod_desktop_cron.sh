#!/bin/bash
#
# Script that can be run as a cron job. The main purpose is to set the DBUG
# environment variables so that the gsettings command works.
#

# Taken from
# https://askubuntu.com/questions/742870/background-not-changing-using-gsettings-from-cron
PID=$(pgrep gnome-session | head -n1)
export DBUS_SESSION_BUS_ADDRESS=$(grep -z DBUS_SESSION_BUS_ADDRESS /proc/$PID/environ|cut -d= -f2-)

echo PID=$PID
echo DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS
echo WHOAMI=$(whoami)

CRON_SCRIPT=$(readlink -f "$0")
CRON_SCRIPT_DIR=$(dirname "$CRON_SCRIPT")
echo $CRON_SCRIPT_DIR

# Assume the pythong script to do the actual work is located in the same
# directory as this cron bash script.
$CRON_SCRIPT_DIR/nasa_apod_desktop.py
