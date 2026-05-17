import logging
import socket
import time


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
