#!/usr/bin/env python3
import argparse
import os
import logging
import time
from collections import OrderedDict
import sys

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, CUR_DIR)

from run_utils import base_util, container_util, exec_util


def list_run_images(run_prefix: str):
    all_images = container_util.list_all_images()
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
            if base_util.check_host_exists(proxy_body):
                return {"type": "host", "host": proxy_body, "port": int(proxy_tail)}
        elif base_util.check_host_exists(proxy_body):
            return {"type": "host", "host": proxy_body, "port": 22}
    all_images = container_util.list_all_images()
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


def get_container_name(image):
    image_name = None
    if isinstance(image, str):
        image_name = image
    elif isinstance(image, dict):
        image_name = image["repo"]
    else:
        assert 0, image
    assert isinstance(image_name, str), image
    return container_util.get_container_name(image_name)


def get_container_info(image):
    container_name = get_container_name(image)
    return container_util.get_container_info(container_name)


def start_container(image, volume_maps=None, port_maps=None, fresh_container=False):
    container_name = get_container_name(image)
    running = container_util.check_container_running(
        container_name, fresh_container=fresh_container
    )
    if running:
        return
    logging.info("Container {} not found, creating".format(container_name))
    user_home = base_util.get_user_info()["home"]
    ssh_dir = "{}/.ssh".format(user_home)
    if not volume_maps:
        volume_maps = OrderedDict()
    volume_maps[ssh_dir] = "{}:{}:rw".format(ssh_dir, ssh_dir)
    start_cmd = container_util.get_container_run_command(
        image["id"],
        container_name,
        volume_maps=volume_maps,
        port_maps=port_maps,
        extra_args=[],
        ipc_host=True,
    )
    container_util.start_container(container_name, start_cmd)
    info = get_container_info(image)
    ssh_port = info["HostPort"]
    max_seconds = 30
    for i in range(max_seconds):
        if base_util.check_port_alive(ssh_port):
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
        "-pm",
        "--port-maps",
        action="append",
        help="The Container port maps",
    )
    parser.add_argument(
        "-fc",
        "--fresh-container",
        action="store_true",
        default=False,
        help="Remove the container if exists and start a new one, useful for image updating",
    )
    parser.add_argument(
        "-txf",
        "--trusted-x11-forwarding",
        action="store_true",
        default=False,
        help="Enable trusted X11 forwarding",
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
        exec_util.exec_via_host(args.command)
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
        if args.volume_file:
            volume_maps.update(container_util.load_volume_file(args.volume_file))
        if args.volume_maps:
            volume_maps.update(container_util.load_volume_maps(args.volume_maps))
        start_container(
            image=proxy_info,
            volume_maps=volume_maps,
            port_maps=args.port_maps,
            fresh_container=args.fresh_container,
        )
        container_info = get_container_info(proxy_info)
        ssh_host = "127.0.0.1"
        ssh_port = container_info["HostPort"]
    else:
        assert 0, proxy_info
    exec_util.exec_via_ssh(
        ssh_host,
        ssh_port,
        args.command,
        tty=args.tty,
        trusted_x11_forwarding=args.trusted_x11_forwarding,
    )


if __name__ == "__main__":
    main()
