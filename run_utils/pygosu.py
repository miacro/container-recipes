#!/usr/bin/env python3
import os
import sys
import pwd
import shlex
import shutil
import argparse
import subprocess
import logging


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


def build_user_environ(username, uid, home, user_shell):
    """
    Constructs a comprehensive, production-grade environment dictionary.
    Inherits global custom variables while strictly isolating user-specific contexts.
    """
    new_env = os.environ.copy()

    env_overrides = {
        # --- Identity and Shell Overrides ---
        "HOME": home,
        "USER": username,
        "LOGNAME": username,
        "SHELL": user_shell,
        # --- Standard System Paths ---
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        # --- Temporary Directories ---
        "TMPDIR": "/tmp",
        "TEMP": "/tmp",
        "TMP": "/tmp",
        # --- Mail System ---
        "MAIL": "/var/mail/{}".format(username),
        # --- XDG Base Directory Specification ---
        "XDG_RUNTIME_DIR": "/run/user/{}".format(uid),
        "XDG_CONFIG_HOME": "{}/.config".format(home),
        "XDG_CACHE_HOME": "{}/.cache".format(home),
        "XDG_DATA_HOME": "{}/.local/share".format(home),
        "XDG_STATE_HOME": "{}/.local/state".format(home),
        # --- Language Runtime Caching Variables (Redirected to home) ---
        "GOCACHE": "{}/.cache/go-build".format(home),
        "CARGO_HOME": "{}/.cargo".format(home),
        "RUSTUP_HOME": "{}/.rustup".format(home),
        "NPM_CONFIG_CACHE": "{}/.npm".format(home),
        "GEM_HOME": "{}/.gems".format(home),
        "PIP_CACHE_DIR": "{}/.cache/pip".format(home),
    }

    new_env.update(env_overrides)

    if "TERM" not in new_env:
        new_env["TERM"] = "xterm-256color"
    if "LANG" not in new_env:
        new_env["LANG"] = "C.UTF-8"
    if "LC_ALL" not in new_env:
        new_env["LC_ALL"] = new_env["LANG"]

    return new_env


def capture_login_environ(username, user_shell):
    """
    Spawns a temporary login shell as the target user to capture environment variables.
    Strictly relies on the POSIX-standard 'env' command. Fails fast if unavailable.
    """
    if sys.platform == "darwin":
        cmd = ["su", "-l", username, "-c", "env"]
    else:
        cmd = ["su", "-l", username, "-s", user_shell, "-c", "env"]

    try:
        # Capture the raw stream safely
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=True,
        )
    except subprocess.TimeoutExpired as e:
        msg = "Timeout while capturing login environment for user '{}': {}".format(
            username, e
        )
        logging.error(msg)
        raise e
    except subprocess.CalledProcessError as e:
        msg = "Failed to capture login environment for user '{}'".format(username)
        logging.error(msg)
        raise e
    captured_env = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            captured_env[key] = val
    return captured_env


def exec_via_user(username, command_args, login=False):
    """
    Executes a command as a specific user.
    :param username: The target system user to switch to.
    :param command_args: The command to execute, provided as a list of arguments.
    :param login: Whether to execute the command within a full login shell context.
    """
    if not (command_args and isinstance(command_args, list)):
        assert 0, "command_args must be a non-empty list of strings."
    if not (username and isinstance(username, str)):
        assert 0, "username must be a non-empty string."

    # Fetch the target user's system records
    try:
        pw_record = pwd.getpwnam(username)
    except KeyError:
        assert 0, "User '{}' does not exist.".format(username)

    uid = pw_record.pw_uid
    gid = pw_record.pw_gid
    home = pw_record.pw_dir
    user_shell = pw_record.pw_shell if pw_record.pw_shell else "/bin/sh"

    # Invoke the Extracted Environment Builder
    user_env = build_user_environ(username, uid, home, user_shell)

    if login:
        login_env = capture_login_environ(username, user_shell)
        user_env.update(login_env)

    raw_binary = command_args[0]
    if raw_binary.startswith((".", "/")):
        res_binary = os.path.abspath(raw_binary)
    else:
        res_binary = shutil.which(raw_binary, path=user_env.get("PATH", os.defpath))
    if not res_binary:
        res_binary = user_shell
        command_text = cmd_join(command_args)
        command_args = [res_binary, "-c", command_text]

    # Initialize supplementary groups
    try:
        os.initgroups(username, gid)
    except PermissionError as e:
        assert 0, "Must be run as root to switch users: {}".format(e)

    # Switch GID and UID (Drop privileges irrevocably)
    try:
        os.setgid(gid)
        os.setuid(uid)
    except PermissionError:
        assert 0, "Failed to set UID/GID. Check permissions."

    # Change directory ONLY if explicit Login Shell is requested
    # Non-login mode will bypass this entirely to preserve the caller's working directory.
    if login:
        try:
            os.chdir(home)
        except Exception as e:
            try:
                os.chdir("/")
            except Exception:
                pass

    os.execvpe(res_binary, command_args, user_env)


def main():
    logging.getLogger().setLevel(logging.ERROR)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="A Python-based gosu alternative",
    )
    parser.add_argument(
        "-l",
        "--login",
        action="store_true",
        help="Force executing inside a full login shell context (changes directory to home and loads profiles).",
    )
    parser.add_argument("username", help="The system user name to drop privileges to.")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command and arguments to execute.",
    )

    args = parser.parse_args()
    assert args.command, "Error: You must provide a command to execute."
    exec_via_user(args.username, args.command, login=args.login)


if __name__ == "__main__":
    main()
