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


def run_container(
    image_name,
    container_name=None,
    volume_maps=None,
    port_maps=None,
    fresh_container=False,
    tty=False,
    interactive=False,
    extra_args=None,
    run_user=None,
    command=None,
):
    container_name = container_util.get_container_name(image_name, container_name)
    running = container_util.check_container_running(
        container_name, fresh_container=fresh_container
    )
    if running:
        return
    logging.info("Container {} not found, creating".format(container_name))
    if not run_user:
        if command:
            run_user = base_util.get_user_info()["name"]
    start_cmd = container_util.get_container_run_command(
        image_name,
        container_name,
        volume_maps=volume_maps,
        port_maps=port_maps,
        tty=tty,
        interactive=interactive,
        extra_args=extra_args,
        run_user=run_user,
        command=command,
    )
    container_util.start_container(
        container_name,
        start_cmd,
        interactive=interactive,
    )
    return


def exec_container(command: str):
    exec_util.exec_via_host(command)
    return


def check_image_name(image_name):
    index = image_name.rfind(":")
    image_body = image_name
    image_tail = None
    if index >= 0:
        image_tail = image_name[index + 1 :]
        image_body = image_name[:index]
    all_images = container_util.list_all_images()
    matched = []
    for image in all_images:
        image_repo = image["repo"]
        image_tag = image["tag"]
        if not image_repo.endswith(image_body):
            continue
        if image_tail:
            if not image_tag.startswith(image_tail):
                continue
        matched.append(image)
    if not matched:
        assert 0, "No image found for image name: '{}'".format(image_name)
    elif len(matched) > 1:
        cur_images = ["{}:{}".format(_["repo"], _["tag"]) for _ in matched]
        msg = "Multiple images found for image name: '{}', candidates:\n\t{}".format(
            image_name, "\n\t".join(cur_images)
        )
        assert 0, msg
    return matched[0]


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
        "-i",
        "--interactive",
        default=False,
        help="When set to true, make stdin available to the contained process.",
    )
    parser.add_argument(
        "-ca",
        "--container-args",
        help="Extra container args",
        default=None,
    )
    parser.add_argument(
        "-ru", "--run-user", help="The user to run the command", default=None
    )
    container_util.init_container_arg_parser(parser)
    args = container_util.parse_container_args(parser)
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    image_info = check_image_name(args.image_name)
    args.image_name = "{}:{}".format(image_info["repo"], image_info["tag"])
    if not args.container_name:
        args.container_name = container_util.get_container_name(image_info["repo"])

    volume_maps = OrderedDict()
    if args.volume_file:
        volume_maps.update(container_util.load_volume_file(args.volume_file))
    if args.volume_maps:
        volume_maps.update(container_util.load_volume_maps(args.volume_maps))
    if not args.image_name:
        assert 0, "Unspecified image_name"
    run_container(
        image_name=args.image_name,
        container_name=args.container_name,
        volume_maps=volume_maps,
        port_maps=args.port_maps,
        fresh_container=args.fresh_container,
        tty=args.tty,
        interactive=args.interactive,
        command=args.command,
        extra_args=args.container_args,
        run_user=args.run_user,
    )


if __name__ == "__main__":
    main()
