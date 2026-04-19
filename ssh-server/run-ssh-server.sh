#!/bin/bash

if [ ! -f ~/.ssh/id_rsa ]; then
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
fi

if ! grep -q "$(cat ~/.ssh/id_rsa.pub)" ~/.ssh/authorized_keys 2>/dev/null; then
    cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
fi

podman run -d --name ssh-server \
    -p 2222:22 \
    -v /home:/home:rw \
    --userns=keep-id \
    --group-add=keep-groups \
    --user=root \
    -e SSH_SERVING_USER=$(id -un) \
    -e SSH_SERVING_SHELL=${SHELL} \
    --replace \
    ssh-server
#    -v /etc/passwd:/etc/passwd:ro \
#    -v /etc/group:/etc/group:ro \
#    -v /etc/shadow:/etc/shadow:ro \
#    -v /etc/sudoers:/etc/sudoers:ro \
#    -v /etc/gshadow:/etc/gshadow:ro \
#    -v /etc/pam.d:/etc/pam.d:ro \