#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import shlex
import shutil
import getpass
import logging


def cmd_run(cmd, cwd=None, capture=False):
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
    parser = argparse.ArgumentParser(description="Run a command via ssh proxy server")
    parser.add_argument(
        "--image-prefix",
        default="run-frame/",
        help="The prefix of the ssh proxy server image name, default: run-frame/",
    )
    parser.add_argument(
        "-s",
        "--proxy-server",
        required=True,
        help="The host or image of the ssh proxy server, <host>[:port] or <image>",
    )


if __name__ == "__main__":
    main()
