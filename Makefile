MAKE=make --no-print-directory
SHELL=/bin/bash

SRC_DIR=$(realpath .)
DST_DIR=~/bin

reinstall:
	mkdir -p ${DST_DIR}
	ln -fs -n ${SRC_DIR}/run-via-proxy.py ${DST_DIR}/run-via-proxy.py
	ln -fs -n ${SRC_DIR}/run-container.py ${DST_DIR}/run-container.py

uninstall:
	[[ -L ${DST_DIR}/run-via-proxy.py ]] && rm ${DST_DIR}/run-via-proxy.py || true
	[[ -L ${DST_DIR}/run-container.py ]] && rm ${DST_DIR}/run-container.py || true

.PHONY: reinstall uninstall 
