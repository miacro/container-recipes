MAKE=make --no-print-directory
SHELL=/bin/bash

SRC=$(realpath .)/run-via-proxy.py
DST=~/bin/run-via-proxy.py

reinstall:
	mkdir -p $(shell dirname ${DST})
	ln -fs -n ${SRC} ${DST}

uninstall:
	[[ -L ${DST} ]] && rm ${DST} || exit 0

.PHONY: reinstall uninstall 
