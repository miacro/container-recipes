import os
import shutil
import sys
import shlex
import argparse
import pwd


def cmd_quote(cmd: str) -> str:
    assert isinstance(cmd, str), "cmd must be a string: {}".format(cmd)
    for label in ("'", '"'):
        if cmd.startswith(label) and cmd.endswith(label):
            return cmd
    return shlex.quote(cmd)


def cmd_join(cmd) -> str:
    if isinstance(cmd, list):
        cmd = " ".join(cmd_quote(_) for _ in cmd)
    elif not isinstance(cmd, str):
        assert 0, "cmd must be a string or a list of strings: {}".format(cmd)
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
    print("Exec {} -D".format(sshd_path), flush=True)
    os.execve(sshd_path, [sshd_path, "-D"], os.environ)


def exec_command(command):
    command = cmd_join(command)
    bash_path = cmd_get_path("bash")
    bash_args = [bash_path, "-c", command]
    print("Exec: {}".format(cmd_join(bash_args)), flush=True)
    os.execve(bash_path, bash_args, os.environ)
    return


def exec_by_user(command, run_user):
    command = cmd_join(command)
    su_path = cmd_get_path("su")
    su_args = [su_path, "-l", run_user, "-c", command]
    print("Exec: {}".format(cmd_join(su_args)), flush=True)
    os.execve(su_path, su_args, os.environ)
    return


def main():
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
