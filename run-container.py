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


def start_container(
    image_name,
    container_name=None,
    volume_maps=None,
    port_maps=None,
    fresh_container=False,
    tty=False,
    interactive=False,
    extra_args=None,
    command=None,
):
    container_name = container_util.get_container_name(image_name, container_name)
    running = container_util.check_container_running(
        container_name, fresh_container=fresh_container
    )
    if running:
        return
    logging.info("Container {} not found, creating".format(container_name))
    start_cmd = container_util.get_container_run_command(
        image_name,
        container_name,
        volume_maps=volume_maps,
        port_maps=port_maps,
        tty=tty,
        interactive=interactive,
        extra_args=extra_args,
        command=command,
    )
    container_util.start_container(container_name, start_cmd)
    return


def exec_container(command: str):
    exec_util.exec_via_host(command)
    return


def main():
    logging.getLogger().setLevel(logging.ERROR)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Run a command via ssh proxy server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    run_images = container_util.list_all_images()
    run_names = ["{}:{}".format(_["repo"], _["tag"]) for _ in run_images]

    parser.add_argument(
        "-in",
        "--image-name",
        help="The container image to run, available: {}".format(run_names),
        default=None,
    )
    parser.add_argument(
        "-cn",
        "--container-name",
        help="The name of container to run",
        default=None,
    )
    parser.add_argument(
        "-vm",
        "--volume-maps",
        help="The volume maps from host to container([src:]dst[:mode])",
        action="append",
        default=[],
    )
    parser.add_argument(
        "-vf",
        "--volume-file",
        help="The file contains multiple volume maps, in json list",
        action="append",
        default=[],
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
        "-i",
        "--interactive",
        default=False,
        help="When set to true, make stdin available to the contained process.",
    )
    parser.add_argument(
        "-pm",
        "--port-maps",
        action="append",
        help="The Container port maps",
        default=[],
    )
    parser.add_argument(
        "-ca",
        "--container-args",
        help="Extra container args",
        default=None,
    )
    parser.add_argument(
        "-fc",
        "--fresh-container",
        action="store_true",
        default=False,
        help="Remove the container if exists and start a new one, useful for image updating",
    )
    parser.add_argument(
        "-af",
        "--arg-file",
        help="The file contains args in json",
        default=None,
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
        action="extend",
    )
    args, _ = parser.parse_known_args()
    args_in_json = None
    if args.arg_file:
        args_in_json = base_util.load_json_file(args.arg_file)
    args = argparse.Namespace()
    if args_in_json and isinstance(args_in_json, dict):
        for key, val in args_in_json.items():
            setattr(args, key, val)
    args = parser.parse_args(namespace=args)

    log_level = getattr(logging, args.log_level)
    for idx, cur_level in enumerate(log_levels):
        arg_name = "v" * (idx + 1)
        arg_value = getattr(args, arg_name)
        if arg_value:
            cur_level = getattr(logging, cur_level)
            log_level = min(log_level, cur_level)
    logging.getLogger().setLevel(log_level)

    volume_maps = OrderedDict()
    if args.volume_file:
        volume_maps.update(container_util.load_volume_file(args.volume_file))
    if args.volume_maps:
        volume_maps.update(container_util.load_volume_maps(args.volume_maps))
    start_container(
        image_name=args.image_name,
        container_name=args.container_name,
        volume_maps=volume_maps,
        port_maps=args.port_maps,
        fresh_container=args.fresh_container,
        tty=args.tty,
        interactive=args.interactive,
        command=args.command,
        extra_args=args.container_args,
    )


if __name__ == "__main__":
    main()
