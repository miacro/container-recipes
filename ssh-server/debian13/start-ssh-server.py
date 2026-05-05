import os
import shutil
import sys
import shlex


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


def main():
    if len(sys.argv) > 1:
        exec_command(sys.argv[1:])
    else:
        exec_into_sshd()


if __name__ == "__main__":
    main()
