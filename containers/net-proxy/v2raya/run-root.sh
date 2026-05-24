#!/bin/bash
sudo podman run -d \
  --name net-proxy-v2raya \
  --restart always \
  --network host \
  -v /etc/localtime:/etc/localtime:ro \
  -v /lib/modules:/lib/modules:ro \
  -v /etc/v2raya:/etc/v2raya \
  net-proxy/v2raya