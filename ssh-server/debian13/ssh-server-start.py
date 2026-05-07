import os
import shutil
import sys
import shlex
import argparse
import pwd
import logging


def cmd_quote(cmd: str, safely=True) -> str:
    assert isinstance(cmd, str), "cmd must be a string: {}".format(cmd)
    # for label in ("'", '"'):
    #     if cmd.startswith(label) and cmd.endswith(label):
    # return cmd
    if not safely:
        for blank in (" ", "\t", "\n"):
            if blank in cmd:
                break
        else:
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


def cmd_get_path(cmd, path=None):
    if path is not None:
        assert isinstance(path, str), "path must be a string"
        pre_path = os.getenv("PATH")
        if pre_path:
            path = "{}:{}".format(path, pre_path)
    cmd_path = shutil.which(cmd, path=path)
    if not cmd_path:
        raise FileNotFoundError("Command {} not found".format(cmd))
    return cmd_path


def exec_into_sshd():
    sshd_path = cmd_get_path("sshd", path="/usr/sbin:/sbin")
    logging.info("Exec {} -D".format(sshd_path))
    os.execve(sshd_path, [sshd_path, "-D"], os.environ)


def exec_command(command):
    command = cmd_join(command, safely=False)
    exec_path = "/ssh-server-exec-bash.sh"
    exec_args = [exec_path, command]
    logging.info("Exec: {}".format(exec_args))
    os.execve(exec_args[0], exec_args, os.environ)
    return


def exec_by_user(command, run_user):
    command = cmd_join(command, safely=True)  # not expand vars
    exec_path = "/ssh-server-exec-su.sh"
    exec_path = cmd_get_path("su")
    exec_args = [exec_path, run_user, command]
    exec_args = [exec_path, "-l", run_user, "-c", command]
    logging.info("Exec: {}".format(exec_args))
    os.execve(exec_args[0], exec_args, os.environ)
    return


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Run a command or sshd -D",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-ru", "--run-user", help="The user to run the command", default=None
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run via proxy server",
        default=[],
    )
    args = parser.parse_args()
    pwd_user = pwd.getpwuid(os.getuid())
    cur_user = pwd_user.pw_name
    if args.run_user and args.run_user != cur_user:
        all_command = ["/usr/bin/env", "python3", sys.argv[0], *args.command]
        exec_by_user(all_command, args.run_user)
        return
    command = args.command
    if len(command) > 0:
        exec_command(command)
    else:
        exec_into_sshd()


if __name__ == "__main__":
    main()
