#!/bin/bash
podman run -d \
  --name net-proxy-v2raya \
  --restart always \
  -p 2018:2017 \
  -p 20170:20170 \
  -p 20171:20171 \
  -p 20172:20172 \
  -v /etc/localtime:/etc/localtime:ro \
  -v ~/.config/v2raya:/etc/v2raya:Z \
  net-proxy/v2raya