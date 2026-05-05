from . import base_util
import logging
import os


def exec_via_host(command):
    command = base_util.cmd_join(command)
    bash_path = base_util.cmd_get_path("bash")
    bash_args = [bash_path, "-c", command]
    logging.info("Exec: {}".format(base_util.cmd_join(bash_args)))
    os.execve(bash_path, bash_args, os.environ)
    return


def exec_via_ssh(ssh_host, ssh_port, command, tty=False, trusted_x11_forwarding=False):
    command = base_util.cmd_join(command)
    user_info = base_util.get_user_info()
    ssh_user = user_info["name"]
    ssh_home = user_info["home"]
    command = "cd {} 2>/dev/null || cd {} 2>/dev/null || true && {}".format(
        os.getcwd(), ssh_home, command
    )
    ssh_path = base_util.cmd_get_path("ssh")
    log_level = logging.getLogger().getEffectiveLevel()
    if log_level <= logging.DEBUG:
        log_text = "DEBUG"
    elif log_level <= logging.INFO:
        log_text = "INFO"
    elif log_level <= logging.WARNING:
        log_text = "ERROR"
    else:
        log_text = "ERROR"
    ssh_args = []
    if trusted_x11_forwarding:
        ssh_args.append("-Y")
    else:
        ssh_args.append("-X")
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
    logging.info("Exec: {} {}".format(base_util.cmd_join(ssh_args), command))
    ssh_args.append(command)
    ssh_env = {**os.environ, "SSH_AUTH_SOCK": "0"}
    os.execve(ssh_path, ssh_args, ssh_env)
    return
