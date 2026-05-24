#!/bin/bash
set -e
. /etc/profile

ARGS=${@:1}
exec bash -c "${ARGS}"