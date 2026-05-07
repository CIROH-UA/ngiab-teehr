#!/bin/bash
set -e
# When running as --user $(id -u):$(id -g), the UID may not exist in /etc/passwd.
# Java's UnixLoginModule does a native getpwuid() lookup and crashes with
# "invalid null input: name" if no entry is found.
# This adds a minimal passwd entry for the current UID at runtime.
if ! getent passwd "$(id -u)" > /dev/null 2>&1; then
    echo "app:x:$(id -u):$(id -g):App User:/tmp:/bin/bash" >> /etc/passwd
fi
exec "$@"
