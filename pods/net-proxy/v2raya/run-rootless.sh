#!/bin/bash
podman run -d \
  --name net-proxy-v2raya \
  --restart always \
  -p 2017:2017 \
  -p 20170:20170 \
  -p 20171:20171 \
  -p 20172:20172 \
  -p 20173:20173 \
  --tmpfs /var/log/v2raya:rw,size=100m \
  -v /etc/localtime:/etc/localtime:ro \
  -v ~/.config/v2raya:/etc/v2raya:Z \
  net-proxy/v2raya
