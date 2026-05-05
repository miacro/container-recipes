#!/bin/bash
set -e

. /etc/profile

/usr/bin/env python3 /setup-ssh-user.py
exec /usr/bin/env python3 /start-ssh-server.py $*