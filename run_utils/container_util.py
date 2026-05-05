from typing import List, Dict, Optional, Any, Union
from . import base_util
import json
import os
import logging
from collections import OrderedDict
import time


def cmd_run_podman(
    command: str, cwd: Optional[str] = None, capture: bool = False
) -> Optional[str]:
    env_text = "PODMAN_IGNORE_CGROUPSV1_WARNING=1"
    cmd = "{} {}".format(env_text, command)
    return base_util.cmd_run(cmd, cwd=cwd, capture=capture)


def list_all_images() -> List[Dict[str, Any]]:
    base_util.cmd_get_path("podman")
    list_cmd = "podman image list --format '{{.ID}} {{.Repository}} {{.Tag}}'"
    images = cmd_run_podman(list_cmd, capture=True)
    assert isinstance(images, str), images
    images = images.splitlines()
    result: List[Dict[str, Any]] = []
    for line in images:
        image_id, image_repo, image_tag = line.split(" ")
        result.append({"id": image_id, "repo": image_repo, "tag": image_tag})
    return result


def get_container_name(image_name: str, container_name: Optional[str] = None) -> str:
    if container_name:
        return container_name
    assert isinstance(image_name, str), image_name
    local_prefix = "localhost/"
    if image_name.startswith(local_prefix):
        image_name = image_name[len(local_prefix) :]
    return image_name.replace("/", "-")


def get_container_info(container_name: str) -> Dict[str, Any]:
    command = "podman inspect {}".format(container_name)
    info = cmd_run_podman(command, capture=True)
    assert isinstance(info, str), info
    info = json.loads(info)
    assert info and isinstance(info, list), (container_name, info)
    info = info[0]
    assert isinstance(info, dict), info
    result: Dict[str, Any] = {
        k: info[k]
        for k in ["Id", "Path", "Args", "Image", "ImageName", "Name", "State"]
    }
    ports = info["NetworkSettings"]["Ports"]
    host_port = ports["22/tcp"][0]["HostPort"]
    result["HostPort"] = host_port
    return result


def init_policy_file():
    policy_file = os.path.join("~", ".config", "containers", "policy.json")
    policy_file = os.path.expanduser(policy_file)
    policy_data = {}
    if os.path.exists(policy_file):
        policy_data = base_util.load_json_file(policy_file)
        if not isinstance(policy_data, dict):
            policy_data = {}
    default_pre = policy_data.get("default", [])
    if not isinstance(default_pre, list):
        default_pre = []
    default_new = []
    matched = False
    changed = False
    for item in default_pre:
        if not isinstance(item, dict) or "type" not in item:
            changed = True
            continue
        default_new.append(item)
        if item["type"] == "insecureAcceptAnything":
            matched = True
    if not matched:
        default_new.append({"type": "insecureAcceptAnything"})
        changed = True
    if not changed:
        return
    policy_data["default"] = default_new
    if not os.path.exists(os.path.dirname(policy_file)):
        os.makedirs(os.path.dirname(policy_file))
    with open(policy_file, "wt") as f:
        json.dump(policy_data, f)
    return


def load_volume_maps(
    volume_maps: List[Any], not_found_ok: bool = True
) -> Dict[str, str]:
    assert isinstance(volume_maps, list), volume_maps
    result = OrderedDict()
    for item in volume_maps:
        cur_map = ()
        if isinstance(item, str):
            cur_map = item.split(":")
        elif isinstance(item, (list, tuple)):
            cur_map = item
        else:
            assert 0, "Invalid volume map: {}".format(item)
        if len(cur_map) == 1:
            src = cur_map[0]
            dst = cur_map[0]
            mode = "ro"
        elif len(cur_map) == 2:
            if cur_map[1].startswith(os.path.sep) or cur_map[1].startswith("~"):
                src, dst = cur_map
                mode = "ro"
            else:
                dst, mode = cur_map
                src = dst
        elif len(cur_map) == 3:
            src, dst, mode = cur_map
        else:
            assert 0, "Invalid volume map: {}".format(item)
            src, dst, mode = None, None, None
        assert isinstance(src, str), item
        assert isinstance(dst, str), item
        assert isinstance(mode, str), item
        src = os.path.expanduser(src)
        dst = os.path.expanduser(dst)
        if not os.path.isabs(src):
            assert 0, "Volume map src is not abspath: {}".format(item)
        if not os.path.isabs(dst):
            assert 0, "Volume map dst is not abspath: {}".format(item)
        if not os.path.exists(src):
            msg = "Volume map src not exists: {}".format(item)
            if not_found_ok:
                logging.warning(msg)
                continue
            assert 0, msg
        result[dst] = "{}:{}:{}".format(src, dst, mode)
    return result


def load_volume_file(
    volume_file: Union[List[Any], str], not_found_ok: bool = True
) -> Dict[str, str]:
    if isinstance(volume_file, list):
        result = OrderedDict()
        for cur_file in volume_file:
            result.update(load_volume_file(cur_file, not_found_ok=not_found_ok))
        return result
    volume_maps = base_util.load_json_file(volume_file)
    assert isinstance(volume_maps, list), (volume_file, volume_maps)
    return load_volume_maps(volume_maps, not_found_ok=not_found_ok)


def check_container_running(container_name, fresh_container=False) -> bool:
    check_cmd = 'podman ps --no-trunc -q -f name="^{}$"'.format(container_name)
    container_id = cmd_run_podman(check_cmd, capture=True)
    if container_id and not fresh_container:
        logging.info("Container {} already running".format(container_name))
        return True
    if container_id:
        cmd_run_podman("podman stop --time=30 {}".format(container_id))
    check_cmd = 'podman ps -a --no-trunc -q -f name="^{}$"'.format(container_name)
    container_id = cmd_run_podman(check_cmd, capture=True)
    if container_id and not fresh_container:
        logging.info("Container {} already exists, starting".format(container_name))
        start_cmd = "podman start {}".format(container_id)
        cmd_run_podman(start_cmd)
        return True
    if container_id:
        cmd_run_podman("podman rm -f --time=30 {}".format(container_id))
    return False


def get_container_run_command(
    image_name: str,
    container_name=None,
    volume_maps=None,
    port_maps=None,
    tty=False,
    interactive=False,
    extra_args=None,
    command=None,
    ipc_host=False,
) -> str:
    container_name = get_container_name(image_name, container_name)
    user_info = base_util.get_user_info()
    start_cmd = """
podman run %s \
--name %s \
-p 22 \
%s \
--userns=keep-id \
--group-add=keep-groups \
--network=slirp4netns \
--replace \
--user=root \
--env SSH_SERVING_UID=%s \
--env SSH_SERVING_USER=%s \
--env SSH_SERVING_SHELL=%s \
%s \
%s \
%s
"""
    # ipc=host required by vscode
    # pid=host required by htop/ps maybe,
    #     but can sometimes prevent podman from properly cleaning up
    #     background processes after the container exits
    if not extra_args:
        extra_args = []
    else:
        extra_args = [*extra_args]
    if ipc_host:
        extra_args += ["--ipc=host"]

    ia_args = []
    if not interactive:
        ia_args.append("-d")
    else:
        if tty:
            ia_args.append("-it")
        else:
            ia_args.append("-i")

    volume_args = []
    if volume_maps:
        assert isinstance(volume_maps, dict), volume_maps
    else:
        volume_maps = OrderedDict()
    port_args = []
    if port_maps:
        port_args = ["-p {}".format(_) for _ in port_maps]
    for _, val in volume_maps.items():
        assert isinstance(val, str), val
        volume_args.append("-v {}".format(val))
    start_cmd = start_cmd % (
        " ".join(ia_args),
        container_name,
        " ".join(port_args),
        user_info["uid"],
        user_info["name"],
        user_info["shell"],
        " ".join(extra_args),
        " ".join(volume_args),
        image_name,
    )
    start_cmd = start_cmd.strip()
    if command:
        command = base_util.cmd_join(command)
        start_cmd = "{} {}".format(start_cmd, command)
    return start_cmd


def start_container(container_name, command):
    init_policy_file()
    cmd_run_podman(command)
    time.sleep(3)
    max_seconds = 30
    for i in range(max_seconds):
        info = get_container_info(container_name)
        state = info.get("State", {})
        running = state.get("Running", False)
        if running:
            break
        if i == max_seconds - 1:
            assert 0, "Failed to start {}, State: {}".format(container_name, state)
        time.sleep(1)
    pass
