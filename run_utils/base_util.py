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


def cmd_quote(cmd: str, safely=True) -> str:
    assert isinstance(cmd, str), "cmd must be a string: {}".format(cmd)
    # for label in ("'", '"'):
    #     if cmd.startswith(label) and cmd.endswith(label):
    #         return cmd
    if not safely:
        blanks = (" ", "\t", "\n")
        if all(_ not in cmd for _ in blanks):
            return cmd
    return shlex.quote(cmd)


def cmd_join(cmd, quote="auto", safely=False) -> str:
    assert quote in ("auto", "always"), quote
    safely = bool(safely)
    quote_always = quote == "always"
    if isinstance(cmd, str):
        if quote_always:
            cmd = [cmd]
    elif isinstance(cmd, (list, tuple)):
        assert all(isinstance(_, str) for _ in cmd), cmd
        cmd = list(cmd)
        if len(cmd) == 1 and not quote_always:
            cmd = cmd[0]
    else:
        assert 0, cmd

    if isinstance(cmd, (list, tuple)):
        cmd = " ".join(cmd_quote(_, safely=safely) for _ in cmd)
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


def cmd_check_compound(command_args, env_path=None):
    """
    Analyzes the command arguments to determine if they require a shell interpreter.

    :param command_args: list, the raw command split into arguments.
    :param env_path: str, the PATH string to use for binary lookup.
    :return: tuple (bool, str or None), (True, None) if a shell wrapper is required,
             (False, resolved_absolute_path) if direct binary execution is safe.
    """
    raw_binary = command_args[0]

    # 1. Base Shell Operators (Pipes, redirections, compounds, background execution)
    forbidden_operators = ("&&", "||", ";", "|", ">>", ">", "<", "&", "!")
    if any(op in command_args for op in forbidden_operators):
        return True, None

    # 2. Advanced Shell Features (Wildcards, command substitution, variables, escapes)
    shell_features = ("*", "?", "[", "]", "$", "`", "\\", "\n")
    if any(any(feat in arg for feat in shell_features) for arg in command_args):
        return True, None

    # 3. Common Shell Builtin Commands and Keywords
    shell_builtins = (
        ".",
        "source",
        "if",
        "for",
        "while",
        "until",
        "case",
        "exec",
        "eval",
        "export",
        "alias",
        "read",
        "set",
        "unset",
        "echo",
    )
    if raw_binary in shell_builtins:
        return True, None

    # 4. Binary Path Resolution
    if raw_binary.startswith((".", "/")):
        resolved_binary = os.path.abspath(raw_binary)
    else:
        if not env_path:
            env_path = os.getenv("PATH", os.defpath)
        resolved_binary = shutil.which(raw_binary, path=env_path)

    # If the binary cannot be found on disk, let the shell handle it
    # (it could be an unlisted shell-bound alias or function unknown to Python).
    if resolved_binary is None:
        return True, None

    return False, resolved_binary
