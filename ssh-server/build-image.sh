#!/bin/bash
podman build -t ssh-server --network slirp4netns . 