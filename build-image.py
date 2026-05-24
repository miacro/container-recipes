#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os

IMAGE_BASE_DIR = os.path.dirname(os.path.realpath(__file__))
IMAGE_BASE_DIR = os.path.join(IMAGE_BASE_DIR, "images")


def run_cmd(cmd, cwd=None, capture=False):
    print("Running command: {}".format(cmd))
    stdout = None
    if capture:
        stdout = subprocess.PIPE
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=stdout)
    if result.returncode != 0:
        assert 0, "Command {} failed with return code {}".format(cmd, result.returncode)
    if capture:
        result = result.stdout.decode("utf-8").strip()
    return result


def check_image(image_name, base_dir=IMAGE_BASE_DIR):
    if os.path.isabs(image_name):
        image_dir = os.path.realpath(image_name)
        if not image_dir.startswith(base_dir):
            assert 0, "Image {} not in base dir {}".format(image_dir, base_dir)
    else:
        image_dir = os.path.join(base_dir, image_name)
        if not os.path.exists(image_dir):
            base_name = os.path.basename(base_dir)
            image_head = image_name.split(os.path.sep)[0]
            if image_head == base_name:
                image_name = image_name[len(image_head):]
                image_name = image_name.lstrip(os.path.sep)
                image_dir = os.path.join(base_dir, image_name)
    image_file = None
    for file in ["Containerfile", "Dockerfile"]:
        image_file = image_dir
        if not image_file.endswith(file):
            image_file = os.path.join(image_dir, file)
        if os.path.isfile(image_file):
            break
    else:
        assert 0, "No Containerfile or Dockerfile found in {}".format(image_dir)
    image_dir = os.path.dirname(image_file)
    image_name = os.path.relpath(image_dir, base_dir)
    if image_name.startswith(os.path.sep):
        image_name = image_name[1:]
    return image_name


def build_image(image_name, base_dir=IMAGE_BASE_DIR, extra_args=None):
    image_name = check_image(image_name, base_dir=base_dir)
    image_dir = os.path.join(base_dir, image_name)
    env_text = "PODMAN_IGNORE_CGROUPSV1_WARNING=1"
    extra_text = ""
    if extra_args:
        if isinstance(extra_args, list):
            extra_text = " ".join(extra_args)
        elif isinstance(extra_args, str):
            extra_text = extra_args
        else:
            assert 0, "extra_args must be a list or a string"
    build_cmd = "{} podman build -t {} --network=slirp4netns {} ."
    build_cmd = build_cmd.format(env_text, image_name, extra_text)
    run_cmd(build_cmd, cwd=image_dir)
    return


def main():
    parser = argparse.ArgumentParser(
        description="Build a container image",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--image-base-dir",
        help="The base directory containing the Dockerfile and context",
        default=IMAGE_BASE_DIR,
    )
    parser.add_argument(
        "-b",
        "--build-chain",
        nargs="+",
        required=True,
        help="Images to build",
    )
    parser.add_argument(
        "-a",
        "--build-extra-args",
        nargs="*",
        help="Extra arguments for the podman build command",
    )
    args = parser.parse_args()
    image_base_dir = os.path.realpath(args.image_base_dir)
    image_names = []
    for image_name in args.build_chain:
        image_name = check_image(image_name, base_dir=image_base_dir)
        image_names.append(image_name)
    for image_name in image_names:
        build_image(image_name, image_base_dir, extra_args=args.build_extra_args)


if __name__ == "__main__":
    main()
