# Quadlet Configuration
```shell
mkdir -p ~/.config/containers/systemd # for root is /etc/containers/systemd/my-example.yaml
podman kube generate <container> >> ~/.config/containers/systemd/my-example.yaml
cp ./my-example.kube ~/.config/containers/systemd/my-example.yaml
podman stop my-example
podman rm my-example
systemctl --user daemon-reload
systemctl --user start my-example-kube.service
```
