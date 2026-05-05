#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess


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


def get_cmd_path(cmd, path=None):
    if path is not None:
        assert isinstance(path, str), "path must be a string"
        pre_path = os.getenv("PATH")
        if pre_path:
            path = "{}:{}".format(path, pre_path)
    cmd_path = shutil.which(cmd, path=path)
    if not cmd_path:
        raise FileNotFoundError("Command {} not found".format(cmd))
    return cmd_path


def get_ssh_login_info(not_found_ok=False):
    ssh_info = {}
    msg = []
    for ssh_key, env_name in [
        ("ssh_uid", "SSH_SERVING_UID"),
        ("ssh_user", "SSH_SERVING_USER"),
        ("ssh_shell", "SSH_SERVING_SHELL"),
    ]:
        env_value = os.getenv(env_name)
        if not env_value:
            err = "Environment variable {} is not set.".format(env_name)
            if not_found_ok:
                print(err, flush=True)
            else:
                msg.append(err)
            continue
        if not isinstance(env_value, str):
            msg.append("Environment variable {} must be a string.".format(env_name))
            continue
        if ssh_key == "ssh_shell":
            valid_shells = []
            comment = r"#[^\n]*\n"
            with open("/etc/shells", "rt") as f:
                for line in f.readlines():
                    line = re.sub(comment, "\n", line)
                    line = line.strip()
                    if line:
                        valid_shells.append(line)
            if all(env_value != shell for shell in valid_shells):
                err = "Shell path {} is not valid, shells: {}".format(
                    env_value, valid_shells
                )
                msg.append(err)
                continue
        elif ssh_key == "ssh_uid":
            if not env_value.isdigit():
                msg.append("Environment variable {} must be a digit.".format(env_name))
                continue
        ssh_info[ssh_key] = env_value
    if msg:
        assert 0, "\n".join(msg)
    return ssh_info


def get_sys_user_info(user_name, user_uid):
    new_name = user_name
    new_uid = user_uid
    with open("/etc/passwd", "rt") as f:
        for line in f.readlines():
            line = line.strip()
            if not line:
                continue
            items = line.split(":")
            if len(items) < 7:
                continue
            cur_name = items[0]
            cur_uid = items[2]
            matched = None
            if cur_name == new_name:
                matched = cur_uid == new_uid
            elif cur_uid == new_uid:
                matched = cur_name == new_name
            if matched is False:
                assert 0, "User mis-matched: new:{}, cur: {}".format(
                    (new_name, new_uid), (cur_name, cur_uid)
                )
            elif matched is True:
                return items
    return None


def add_ssh_user(ssh_info):
    new_uid = ssh_info["ssh_uid"]
    new_name = ssh_info["ssh_user"]
    new_shell = ssh_info["ssh_shell"]
    cmd, args = None, None
    sys_user = get_sys_user_info(new_name, new_uid)
    if sys_user is None:
        cmd = "useradd"
        args = "-m -s {} -u {} {}".format(new_shell, new_uid, new_name)
    else:
        sys_shell = sys_user[6]
        if sys_shell != new_shell:
            cmd = "chsh"
            args = "-s {} {}".format(new_shell, new_name)
    if cmd is None:
        return
    cmd_path = get_cmd_path(cmd, path="/usr/sbin:/sbin")
    run_cmd("{} {}".format(cmd_path, args))


def set_ssh_public_key(ssh_user, ssh_uid):
    sys_info = get_sys_user_info(ssh_user, ssh_uid)
    if sys_info is None:
        assert 0, "User {} with uid {} not found".format(ssh_user, ssh_uid)
    assert isinstance(sys_info, list), sys_info
    home_dir = sys_info[5]
    ssh_gid = sys_info[3]
    ssh_dir = os.path.join(home_dir, ".ssh")
    private_key = os.path.join(ssh_dir, "id_rsa")
    public_key = os.path.join(ssh_dir, "id_rsa.pub")
    if not all(os.path.isfile(key) for key in [private_key, public_key]):
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)
        os.chmod(ssh_dir, 0o700)
        keygen_path = get_cmd_path("ssh-keygen", path="/usr/bin:/bin")
        comment = "{}@{}(by-ssh-server)".format(ssh_user, os.uname().nodename)
        cmd = "{} -t rsa -b 4096 -C '{}' -f {} -N ''".format(
            keygen_path, comment, private_key
        )
        run_cmd(cmd)
        os.chmod(private_key, 0o600)
        cmd = "{} -R {}:{} {}".format(get_cmd_path("chown"), ssh_uid, ssh_gid, ssh_dir)
        run_cmd(cmd)
    with open(public_key, "rt") as f:
        pub_key = f.read().strip()
    auth_keys = os.path.join(ssh_dir, "authorized_keys")
    auth_lines = []
    if os.path.isfile(auth_keys):
        with open(auth_keys, "rt") as f:
            auth_lines = f.readlines()
    pub_found = False
    for auth_line in auth_lines:
        if auth_line.strip() == pub_key:
            pub_found = True
            break
    if not pub_found:
        auth_lines = "".join(auth_lines)
        auth_lines = [auth_lines, pub_key]
        auth_lines = "\n".join(auth_lines)
        with open(auth_keys, "wt") as f:
            f.writelines(auth_lines)
    os.chmod(auth_keys, 0o600)


def main():
    ssh_login_info = get_ssh_login_info(not_found_ok=True)
    for key in ("ssh_uid", "ssh_user", "ssh_shell"):
        if not ssh_login_info.get(key, None):
            print("SSH_SERVING user not specified, skip user setup", flush=True)
            return
    add_ssh_user(ssh_login_info)
    set_ssh_public_key(ssh_login_info["ssh_user"], ssh_login_info["ssh_uid"])


if __name__ == "__main__":
    main()
