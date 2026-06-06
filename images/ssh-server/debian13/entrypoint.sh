#!/bin/bash
set -e
. /etc/profile

/usr/bin/env python3 /ssh-user-setup.py
ssh-keygen -A
exec /usr/bin/env python3 /ssh-server-start.py $*