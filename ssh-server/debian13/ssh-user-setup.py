#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import logging
import pwd


def run_cmd(cmd, cwd=None, capture=False):
    logging.info("Running command: {}".format(cmd))
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


def check_file_writable(file):
    if os.access(file, os.W_OK):
        return True
    else:
        return False


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
                logging.info(err)
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


def get_sys_user_info(user_name=None, user_uid=None):
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
            if new_name is not None and new_uid is not None:
                if cur_name == new_name:
                    matched = cur_uid == new_uid
                elif cur_uid == new_uid:
                    matched = cur_name == new_name
            elif new_name is not None:
                if cur_name == new_name:
                    matched = True
            elif new_uid is not None:
                if cur_uid == new_uid:
                    matched = True
            else:
                assert 0, (user_name, user_uid)
            if matched is False:
                assert 0, "User mis-matched: new:{}, cur: {}".format(
                    (new_name, new_uid), (cur_name, cur_uid)
                )
            elif matched is True:
                return {
                    "name": items[0],
                    "uid": items[2],
                    "gid": items[3],
                    "gecos": items[4],
                    "home": items[5],
                    "shell": items[6],
                }
    return None


def add_ssh_user(ssh_info):
    new_uid = ssh_info["ssh_uid"]
    new_name = ssh_info["ssh_user"]
    new_shell = ssh_info["ssh_shell"]
    new_home = "/home/{}".format(new_name)
    cmd, args = None, None
    sys_user = get_sys_user_info(user_name=new_name)
    sys_user_by_uid = get_sys_user_info(user_uid=new_uid)
    if sys_user_by_uid is not None and sys_user_by_uid["name"] != new_name:
        other_name = sys_user_by_uid["name"]
        msg = "Another user {} owns the uid {}, deleting".format(other_name, new_uid)
        logging.warning(msg)
        cmd_path = get_cmd_path("userdel", path="/usr/sbin:/sbin")
        run_cmd("{} -f {}".format(cmd_path, other_name))
        sys_user_by_uid = None

    if sys_user is not None:
        matched = True
        for val0, val1 in [
            (new_name, sys_user["name"]),
            (new_uid, sys_user["uid"]),
            (new_home, sys_user["home"]),
            (new_shell, sys_user["shell"]),
        ]:
            if val0 != val1:
                matched = True
                break
        if not matched:
            cmd = "usermod"
            args = "-d {} -u {} -s {} {}".format(new_home, new_uid, new_shell, new_name)
    else:
        assert sys_user_by_uid is None
        cmd = "useradd"
        args = "-m -d {} -u {} -s {} {}".format(new_home, new_uid, new_shell, new_name)

    if cmd is None:
        return
    cmd_path = get_cmd_path(cmd, path="/usr/sbin:/sbin")
    run_cmd("{} {}".format(cmd_path, args))


def set_ssh_public_key(ssh_user, ssh_uid):
    sys_info = get_sys_user_info(ssh_user, ssh_uid)
    if sys_info is None:
        assert 0, "User {} with uid {} not found".format(ssh_user, ssh_uid)
    assert isinstance(sys_info, dict), sys_info
    home_dir = sys_info["home"]
    ssh_gid = sys_info["gid"]
    ssh_dir = os.path.join(home_dir, ".ssh")
    private_file = os.path.join(ssh_dir, "id_rsa")
    public_file = os.path.join(ssh_dir, "id_rsa.pub")
    gen_key = False
    msg = None
    if all(os.path.exists(_) for _ in [private_file, public_file]):
        msg = "{} and {} already exists, skip ssh-keygen".format(
            private_file, public_file
        )
    elif not check_file_writable(ssh_dir):
        msg = "{} is not writable, skip ssh-keygen".format(ssh_dir)
    elif check_file_writable(ssh_dir):
        gen_key = True
        for cur_file in [private_file, public_file]:
            if os.path.exists(cur_file):
                if not check_file_writable(cur_file):
                    gen_key = False
                    msg = "{} is not writable, skip ssh-keygen".format(cur_file)
                    break
    if msg:
        logging.info(msg)
    if gen_key:
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)
        os.chmod(ssh_dir, 0o700)
        keygen_path = get_cmd_path("ssh-keygen", path="/usr/bin:/bin")
        comment = "{}@{}(by-ssh-server)".format(ssh_user, os.uname().nodename)
        cmd = "{} -t rsa -b 4096 -C '{}' -f {} -N ''".format(
            keygen_path, comment, private_file
        )
        run_cmd(cmd)
        os.chmod(private_file, 0o600)
        chown_path = get_cmd_path("chown")
        cmd = "{} -R {}:{} {}".format(chown_path, ssh_uid, ssh_gid, ssh_dir)
        run_cmd(cmd)
    if not os.path.exists(public_file):
        return
    with open(public_file, "rt") as f:
        pub_key = f.read().strip()
    auth_file = os.path.join(ssh_dir, "authorized_keys")
    if not check_file_writable(auth_file):
        msg = "{} is not writable, skip adding pubkey".format(auth_file)
        logging.info(msg)
        return
    auth_lines = []
    if os.path.isfile(auth_file):
        with open(auth_file, "rt") as f:
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
        with open(auth_file, "wt") as f:
            f.writelines(auth_lines)
    os.chmod(auth_file, 0o600)


def drop_into_user(user_name):
    pwd_cur = pwd.getpwuid(os.getuid())
    cur_name = pwd_cur.pw_name
    if cur_name == user_name:
        return
    pwd_user = pwd.getpwnam(user_name)
    logging.info("Dropping user from {} to {}".format(cur_name, user_name))
    user_uid = pwd_user.pw_uid
    user_gid = pwd_user.pw_gid
    os.initgroups(user_name, user_gid)
    os.setgid(user_gid)
    os.setuid(user_uid)


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")
    ssh_login_info = get_ssh_login_info(not_found_ok=True)
    for key in ("ssh_uid", "ssh_user", "ssh_shell"):
        if not ssh_login_info.get(key, None):
            logging.warning("SSH_SERVING user not specified, skip user setup")
            return
    add_ssh_user(ssh_login_info)
    drop_into_user(ssh_login_info["ssh_user"])
    set_ssh_public_key(ssh_login_info["ssh_user"], ssh_login_info["ssh_uid"])


if __name__ == "__main__":
    main()
