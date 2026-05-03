#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import shlex
import shutil
import logging
import socket
import json
import pwd
import time
import re
from collections import OrderedDict


def cmd_run(cmd, cwd=None, capture=False):
    logging.info("Running command: {}".format(cmd))
    stdout = None
    if capture:
        stdout = subprocess.PIPE
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=stdout)
    if result.returncode != 0:
        assert 0, "Command {} failed with return code {}".format(cmd, result.returncode)
    if capture:
        result = result.stdout.decode("utf-8").strip()
    return result


def cmd_quote(cmd):
    assert isinstance(cmd, str), "cmd must be a string: {}".format(cmd)
    for label in ("'", '"'):
        if cmd.startswith(label) and cmd.endswith(label):
            return cmd
    return shlex.quote(cmd)


def cmd_join(cmd):
    if isinstance(cmd, list):
        cmd = " ".join(cmd_quote(_) for _ in cmd)
    elif not isinstance(cmd, str):
        assert 0, "cmd must be a string or a list of strings: {}".format(cmd)
    return cmd


def cmd_get_path(cmd, path=None):
    if path is not None:
        assert isinstance(path, str), "path must be a string: {}".format(path)
        pre_path = os.getenv("PATH")
        if pre_path:
            path = "{}:{}".format(path, pre_path)
    cmd_path = shutil.which(cmd, path=path)
    if not cmd_path:
        raise FileNotFoundError("Command {} not found".format(cmd))
    return cmd_path


def cmd_run_podman(command, cwd=None, capture=False):
    env_text = "PODMAN_IGNORE_CGROUPSV1_WARNING=1"
    cmd = "{} {}".format(env_text, command)
    return cmd_run(cmd, cwd=cwd, capture=capture)


def get_user_info():
    pwd_user = pwd.getpwuid(os.getuid())
    user_name = pwd_user.pw_name
    user_id = pwd_user.pw_uid
    user_home = pwd_user.pw_dir
    user_shell = pwd_user.pw_shell
    return user_name, user_id, user_shell, user_home


def remove_line_comments(lines, prefix="#"):
    assert isinstance(lines, str), lines
    pattern = re.escape(prefix) + r"[^\n]*\n"
    return re.sub(pattern, "\n", lines)


def load_json_file(filename):
    with open(filename, "rt") as f:
        lines = f.read()
        lines = remove_line_comments(lines, "//")
        return json.loads(lines)


def list_all_images():
    podman_path = cmd_get_path("podman")
    if podman_path is None:
        return []
    list_cmd = "podman image list --format '{{.ID}} {{.Repository}} {{.Tag}}'"
    images = cmd_run_podman(list_cmd, capture=True).splitlines()
    result = []
    for line in images:
        image_id, image_repo, image_tag = line.split(" ")
        result.append({"id": image_id, "repo": image_repo, "tag": image_tag})
    return result


def check_host_exists(hostname):
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.error:
        return False


def list_run_images(run_prefix):
    all_images = list_all_images()
    run_images = []
    for image in all_images:
        image_name = "{}:{}".format(image["repo"], image["tag"])
        if image_name.startswith(run_prefix):
            run_images.append(image)
    return run_images


def check_proxy_server(proxy_server):
    index = proxy_server.rfind(":")
    proxy_body = proxy_server
    proxy_tail = None
    if index >= 0:
        proxy_tail = proxy_server[index + 1 :]
        proxy_body = proxy_server[:index]
    if proxy_body:
        if proxy_tail and proxy_tail.isdigit():
            if check_host_exists(proxy_body):
                return {"type": "host", "host": proxy_body, "port": int(proxy_tail)}
        elif check_host_exists(proxy_body):
            return {"type": "host", "host": proxy_body, "port": 22}
    all_images = list_all_images()
    matched = []
    for image in all_images:
        image_repo = image["repo"]
        image_tag = image["tag"]
        if not image_repo.endswith(proxy_body):
            continue
        if proxy_tail:
            if not image_tag.startswith(proxy_tail):
                continue
        matched.append(image)
    if not matched:
        assert 0, "No image found for proxy server: '{}'".format(proxy_server)
    elif len(matched) > 1:
        cur_images = ["{}:{}".format(_["repo"], _["tag"]) for _ in matched]
        msg = "Multiple images found for proxy server: '{}', candidates:\n\t{}".format(
            proxy_server, "\n\t".join(cur_images)
        )
        assert 0, msg
    return {"type": "image", **matched[0]}


def exec_via_host(command):
    command = cmd_join(command)
    bash_path = cmd_get_path("bash")
    bash_args = [bash_path, "-c", command]
    logging.info("Exec: {}".format(cmd_join(bash_args)))
    os.execve(bash_path, bash_args, os.environ)
    return


def exec_via_ssh(ssh_host, ssh_port, command, tty=False):
    command = cmd_join(command)
    ssh_user, _, _, ssh_home = get_user_info()
    command = "cd {} 2>/dev/null || cd {} 2>/dev/null || true && {}".format(
        os.getcwd(), ssh_home, command
    )
    ssh_path = cmd_get_path("ssh")
    log_level = logging.getLogger().getEffectiveLevel()
    if log_level <= logging.DEBUG:
        log_text = "DEBUG"
    elif log_level <= logging.INFO:
        log_text = "INFO"
    elif log_level <= logging.WARNING:
        log_text = "ERROR"
    else:
        log_text = "ERROR"
    ssh_args = ["-X"]
    if tty:
        ssh_args.append("-t")
    ssh_args += [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=6",
        "-o",
        "Compression=yes",
        "-o",
        "ServerAliveCountMax=6",
        "-o",
        "ServerAliveInterval=300",
        "-o",
        "LogLevel={}".format(log_text),
        "-p",
        "{}".format(ssh_port),
        "-i",
        "{}/.ssh/id_rsa".format(ssh_home),
        "{}@{}".format(ssh_user, ssh_host),
    ]
    ssh_args.insert(0, ssh_path)
    logging.info("Exec: {} {}".format(cmd_join(ssh_args), command))
    ssh_args.append(command)
    ssh_env = {**os.environ, "SSH_AUTH_SOCK": "0"}
    os.execve(ssh_path, ssh_args, ssh_env)
    return


def get_container_name(image):
    if isinstance(image, str):
        image_name = image
    elif isinstance(image, dict):
        image_name = image["repo"]
    local_prefix = "localhost/"
    if image_name.startswith(local_prefix):
        image_name = image_name[len(local_prefix) :]
    return image_name.replace("/", "-")


def get_container_info(image):
    container_name = get_container_name(image)
    command = "podman inspect {}".format(container_name)
    info = cmd_run_podman(command, capture=True)
    info = json.loads(info)
    assert info, (image, container_name, info)
    info = info[0]
    result = {
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
        policy_data = load_json_file(policy_file)
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


def load_volume_maps(volume_maps, not_found_ok=True):
    assert isinstance(volume_maps, list), volume_maps
    result = OrderedDict()
    for item in volume_maps:
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
            src, dst = cur_map
            mode = "ro"
        elif len(cur_map) == 3:
            src, dst, mode = cur_map
        else:
            assert 0, "Invalid volume map: {}".format(item)
        assert isinstance(src, str), item
        assert isinstance(dst, str), item
        assert isinstance(mode, str), item
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
        result["{}:{}:{}".format(src, dst, mode)] = True
    return list(result.keys())


def load_volume_file(volume_file, not_found_ok=True):
    if isinstance(volume_file, list):
        result = OrderedDict()
        for cur_file in volume_file:
            for item in load_volume_file(cur_file, not_found_ok=not_found_ok):
                result[item] = True
        return list(result.keys())
    volume_maps = load_json_file(volume_file)
    return load_volume_maps(volume_maps, not_found_ok=not_found_ok)


def check_port_alive(port, host="127.0.0.1"):
    if isinstance(port, str):
        port = int(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(1)
        return stream.connect_ex((host, port)) == 0


def start_container(image, volume_maps=None, fresh_container=False):
    container_name = get_container_name(image)
    check_cmd = 'podman ps --no-trunc -q -f name="^{}$"'.format(container_name)
    container_id = cmd_run_podman(check_cmd, capture=True)
    if container_id and not fresh_container:
        logging.info("Container {} already running".format(container_name))
        return
    if container_id:
        cmd_run_podman("podman stop --time=30 {}".format(container_id))
    check_cmd = 'podman ps -a --no-trunc -q -f name="^{}$"'.format(container_name)
    container_id = cmd_run_podman(check_cmd, capture=True)
    if container_id and not fresh_container:
        logging.info("Container {} already exists, starting".format(container_name))
        start_cmd = "podman start {}".format(container_id)
        cmd_run_podman(start_cmd)
        return
    if container_id:
        cmd_run_podman("podman rm -f --time=32 {}".format(container_id))
    logging.info("Container {} not found, creating".format(container_name))
    image_id = image["id"]
    user_name, user_id, user_shell, user_home = get_user_info()

    start_cmd = """
podman run -d \
--name %s \
-p 22 \
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
    extra_args = ["--ipc=host"]
    volume_args = ["-v {}/.ssh:{}/.ssh:rw".format(user_home, user_home)]
    if volume_maps:
        for v_map in volume_maps:
            assert isinstance(v_map, str), v_map
            volume_args.append("-v {}".format(v_map))
    start_cmd = start_cmd % (
        container_name,
        user_id,
        user_name,
        user_shell,
        " ".join(extra_args),
        " ".join(volume_args),
        image_id,
    )
    start_cmd = start_cmd.strip()
    init_policy_file()
    cmd_run_podman(start_cmd)
    time.sleep(3)
    max_seconds = 30
    for i in range(max_seconds):
        info = get_container_info(image)
        state = info.get("State", {})
        running = state.get("Running", False)
        if running:
            break
        if i == max_seconds - 1:
            assert 0, "Failed to start {}, State: {}".format(container_name, state)
        time.sleep(1)
    info = get_container_info(image)
    ssh_port = info["HostPort"]
    for i in range(max_seconds):
        if check_port_alive(ssh_port):
            break
        if i == max_seconds - 1:
            assert 0, "SSH Port {} not available".format(ssh_port)
        time.sleep(1)
    return


def main():
    logging.getLogger().setLevel(logging.ERROR)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Run a command via ssh proxy server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    run_images = list_run_images("localhost/run-frame/")
    run_names = ["{}:{}".format(_["repo"], _["tag"]) for _ in run_images]

    parser.add_argument(
        "-s",
        "--proxy-server",
        help="The host or image of the ssh proxy server(<host>[:port] or <image>), "
        "available images: [{}]".format(", ".join(run_names)),
        default=None,
    )
    parser.add_argument(
        "-vm",
        "--volume-maps",
        help="The volume maps from host to container([src:]dst[:mode])",
        action="append",
    )
    parser.add_argument(
        "-vf",
        "--volume-file",
        help="The file contains multiple volume maps, in json list",
        action="append",
    )
    log_levels = ["ERROR", "WARNING", "INFO", "DEBUG"]
    parser.add_argument(
        "-l",
        "--log-level",
        default="ERROR",
        choices=log_levels,
        help="Set the log level",
    )
    parser.add_argument(
        "-t",
        "--tty",
        action="store_true",
        default=False,
        help="Force ssh pseudo-terminal allocation. This can be used to execute arbitrary "
        "screen-based programs(eg. base, tmux, ...), which can be very useful.",
    )
    parser.add_argument(
        "-fc",
        "--fresh-container",
        action="store_true",
        default=False,
        help="Remove the container if exists and start a new one, useful for image updating",
    )
    for idx, log_level in enumerate(log_levels):
        arg_name = "v" * (idx + 1)
        parser.add_argument(
            "-" + arg_name,
            help="Set log level to {}".format(log_level),
            action="store_true",
            default=False,
        )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run via proxy server",
    )
    args = parser.parse_args()
    if not args.command:
        assert 0, "No command to run via proxy server"

    log_level = getattr(logging, args.log_level)
    for idx, cur_level in enumerate(log_levels):
        arg_name = "v" * (idx + 1)
        arg_value = getattr(args, arg_name)
        if arg_value:
            cur_level = getattr(logging, cur_level)
            log_level = min(log_level, cur_level)
    logging.getLogger().setLevel(log_level)

    if not args.proxy_server:
        logging.info("Exec locally")
        exec_via_host(args.command)
        return
    proxy_info = check_proxy_server(args.proxy_server)
    ssh_host = None
    ssh_port = None
    if proxy_info["type"] == "host":
        host = "{}:{}".format(proxy_info["host"], proxy_info["port"])
        logging.info("Exec via host {}".format(host))
        ssh_host = proxy_info["host"]
        ssh_port = proxy_info["port"]
    elif proxy_info["type"] == "image":
        image = "{}:{}".format(proxy_info["repo"], proxy_info["tag"])
        logging.info("Exec via image: {}".format(image))
        volume_maps = OrderedDict()
        for v_map in load_volume_file(args.volume_file):
            volume_maps[v_map] = True
        for v_map in load_volume_maps(args.volume_maps):
            volume_maps[v_map] = True
        volume_maps = list(volume_maps.keys())
        start_container(
            image=proxy_info,
            volume_maps=volume_maps,
            fresh_container=args.fresh_container,
        )
        container_info = get_container_info(proxy_info)
        ssh_host = "127.0.0.1"
        ssh_port = container_info["HostPort"]
    else:
        assert 0, proxy_info
    exec_via_ssh(ssh_host, ssh_port, args.command, tty=args.tty)


if __name__ == "__main__":
    main()
