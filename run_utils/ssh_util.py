import logging
import socket
import time
import os
from . import base_util


def ssh_wait_for_ready(host, port=22, timeout=5, attempt=60):
    """
    Uses native Sockets to lightweightly detect if the SSH application layer is fully ready.
    """
    logging.info(
        "Starting to probe SSH service status on [{}:{}]...".format(host, port)
    )
    assert isinstance(host, str), host
    assert isinstance(timeout, int) and timeout > 0, timeout
    assert not attempt or isinstance(attempt, int), attempt
    port = int(port)
    all_attempt = attempt
    cur_attempt = 1

    while (not all_attempt) or (cur_attempt <= all_attempt):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)

        try:
            s.connect((host, port))
            banner_buffer = b""
            start_time = time.time()

            while True:
                chunk = s.recv(256)
                if not chunk:
                    raise ConnectionResetError(
                        "Server disconnected while transmitting the banner"
                    )

                banner_buffer += chunk

                if b"SSH-" in banner_buffer:
                    try:
                        banner_str = banner_buffer.decode("utf-8", errors="ignore")
                        ssh_line = banner_str.strip().split("\n")
                        ssh_line = [line for line in ssh_line if "SSH-" in line][-1]
                        logging.info(
                            "Successfully captured standard response: {}".format(
                                ssh_line
                            )
                        )
                    except Exception:
                        logging.info(
                            "Successfully captured standard SSH identification token!"
                        )
                    return True

                if time.time() - start_time > timeout:
                    raise socket.timeout(
                        "Timed out waiting for SSH identification token in server response"
                    )

        except (socket.timeout, ConnectionRefusedError, ConnectionResetError) as e:
            # Common network exceptions are swallowed here to continue the loop
            pass
        finally:
            s.close()

        logging.info(
            "Attempt {}: Service is not fully ready yet, retrying in 2 seconds...".format(
                cur_attempt
            )
        )

        cur_attempt += 1
        time.sleep(2)
    return False


def ssh_load_pubkey():
    _, pubkey_file = ssh_gen_rsa_key()
    with open(pubkey_file, "rt") as f:
        return f.read().strip()


def ssh_gen_rsa_key():
    ssh_dir = os.path.expanduser("~/.ssh")
    private_file = os.path.join(ssh_dir, "id_rsa")
    public_file = os.path.join(ssh_dir, "id_rsa.pub")
    if all(os.path.exists(_) for _ in [private_file, public_file]):
        return private_file, public_file
    user_info = base_util.get_user_info()
    ssh_user = user_info["name"]
    ssh_uid = user_info["uid"]
    ssh_gid = user_info["gid"]
    ssh_user = base_util.get_user_info()["name"]
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, mode=0o700)
    os.chmod(ssh_dir, 0o700)
    keygen_path = base_util.cmd_get_path("ssh-keygen", path="/usr/bin:/bin")
    comment = "{}@{}(by-ssh-server)".format(ssh_user, os.uname().nodename)
    cmd = "{} -t rsa -b 4096 -C '{}' -f {} -N ''".format(
        keygen_path, comment, private_file
    )
    base_util.cmd_run(cmd)
    os.chmod(private_file, 0o600)
    chown_path = base_util.cmd_get_path("chown")
    cmd = "{} -R {}:{} {}".format(chown_path, ssh_uid, ssh_gid, ssh_dir)
    base_util.cmd_run(cmd)
    return private_file, public_file
