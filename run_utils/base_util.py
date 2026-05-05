import subprocess
import shlex
from typing import List, Optional, Union
import os
import logging
import shutil
import re
import json
import pwd
import socket


def cmd_run(
    cmd: str, cwd: Optional[str] = None, capture: bool = False
) -> Optional[str]:
    logging.info("Running command: {}".format(cmd))
    stdout = None
    if capture:
        stdout = subprocess.PIPE
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=stdout)
    if result.returncode != 0:
        assert 0, "Command {} failed with return code {}".format(cmd, result.returncode)
    if capture:
        result = result.stdout.decode("utf-8").strip()
    else:
        result = None
    return result


def cmd_quote(cmd: str) -> str:
    assert isinstance(cmd, str), "cmd must be a string: {}".format(cmd)
    for label in ("'", '"'):
        if cmd.startswith(label) and cmd.endswith(label):
            return cmd
    return shlex.quote(cmd)


def cmd_join(cmd: Union[str, List[str]]) -> str:
    if isinstance(cmd, list):
        cmd = " ".join(cmd_quote(_) for _ in cmd)
    elif not isinstance(cmd, str):
        assert 0, "cmd must be a string or a list of strings: {}".format(cmd)
    return cmd


def cmd_get_path(cmd: str, path: Optional[str] = None) -> str:
    if path is not None:
        assert isinstance(path, str), "path must be a string: {}".format(path)
        pre_path = os.getenv("PATH")
        if pre_path:
            path = "{}:{}".format(path, pre_path)
    cmd_path = shutil.which(cmd, path=path)
    if not cmd_path:
        raise FileNotFoundError("Command {} not found".format(cmd))
    return cmd_path


def get_user_info():
    pwd_user = pwd.getpwuid(os.getuid())
    user_name = pwd_user.pw_name
    user_id = pwd_user.pw_uid
    user_home = pwd_user.pw_dir
    user_shell = pwd_user.pw_shell
    user_gid = pwd_user.pw_gid
    return {
        "name": user_name,
        "uid": user_id,
        "gid": user_gid,
        "shell": user_shell,
        "home": user_home,
    }


def remove_line_comments(lines: str, prefix: str = "#") -> str:
    assert isinstance(lines, str), lines
    pattern = re.escape(prefix) + r"[^\n]*\n"
    return re.sub(pattern, "\n", lines)


def load_json_file(filename: str):
    with open(filename, "rt") as f:
        lines = f.read()
        lines = remove_line_comments(lines, "//")
        return json.loads(lines)


def check_host_exists(hostname: str):
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.error:
        return False


def check_port_alive(port, host="127.0.0.1"):
    if isinstance(port, str):
        port = int(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(1)
        return stream.connect_ex((host, port)) == 0
