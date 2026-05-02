#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import shlex
import shutil
import getpass
import logging
import socket


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


def list_all_images():
    podman_path = cmd_get_path("podman")
    if podman_path is None:
        return []
    list_cmd = "%s image list --format '{{.ID}} {{.Repository}} {{.Tag}}'"
    list_cmd = list_cmd % podman_path
    images = cmd_run(list_cmd, capture=True).splitlines()
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
    command = "cd {} && {}".format(os.getcwd(), command)
    ssh_path = cmd_get_path("ssh")
    ssh_user = getpass.getuser()
    ssh_home = os.path.expanduser("~")
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
    if proxy_info["type"] == "host":
        host = "{}:{}".format(proxy_info["host"], proxy_info["port"])
        logging.info("Exec via host {}".format(host))
        exec_via_ssh(proxy_info["host"], proxy_info["port"], args.command, tty=True)
    elif proxy_info["type"] == "image":
        image = "{}:{}".format(proxy_info["repo"], proxy_info["tag"])
        logging.info("Exec via image: {}".format(image))
    else:
        assert 0, proxy_info


if __name__ == "__main__":
    main()
