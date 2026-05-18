#!/usr/bin/env python3
import os
import sys
import pwd
import shlex
import shutil
import argparse
import subprocess
import logging


def check_command_compound(command_args, env_path):
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
        resolved_binary = shutil.which(raw_binary, path=env_path)

    # If the binary cannot be found on disk, let the shell handle it
    # (it could be an unlisted shell-bound alias or function unknown to Python).
    if resolved_binary is None:
        return True, None

    return False, resolved_binary


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
    cmd = ["su", "-", username, "-s", user_shell, "-c", "env"]

    try:
        # Capture the raw stream safely
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
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


def build_exec_args(user_shell, command_args, force_login, env_path):
    """
    Determines the final routing architecture and transforms arguments for os.execvpe.
    Handles distinct paradigms across POSIX shells, C-Shells, and Fish dynamically.

    :return: tuple (exec_binary, exec_args)
    """
    # First, test if raw binary execution is safely applicable
    if force_login:
        use_direct_exec = False
        resolved_binary = None
    else:
        must_use_shell, resolved_binary = check_command_compound(command_args, env_path)
        use_direct_exec = not must_use_shell

    # Route 1: Direct Binary Execution Mode (Bypass Shell completely)
    if use_direct_exec:
        return resolved_binary, command_args

    # Route 2: Shell Evaluation Mode (Login Shell vs Non-Login Shell Fallback)
    exec_binary = user_shell
    shell_binary = os.path.basename(user_shell)

    if force_login:
        # --- Strategy A: Full Login Shell Mapping ---
        login_shell_name = "-" + shell_binary
        needs_complex_shell, _ = check_command_compound(command_args, env_path)

        if needs_complex_shell:
            # Multi-command pipelines (e.g. "echo 1 && ls") require 'eval' string mapping
            if shell_binary in ("fish", "csh", "tcsh"):
                full_command_string = " ".join(shlex.quote(arg) for arg in command_args)
                exec_args = [
                    shell_binary,
                    "-l" if shell_binary == "fish" else "",
                    "-c",
                    full_command_string,
                ]
            else:
                # Fixed: login_shell_name injected at the end acts as $0 to pad parameters properly
                exec_args = [login_shell_name, "-c", 'eval "$@"', login_shell_name]
                exec_args.extend(command_args)
        else:
            # Standard single commands utilize 'exec' for transparent PID 1 signal forwarding
            if shell_binary in ("fish", "csh", "tcsh"):
                full_command_string = " ".join(shlex.quote(arg) for arg in command_args)
                exec_args = [
                    shell_binary,
                    "-l" if shell_binary == "fish" else "",
                    "-c",
                    "exec " + full_command_string,
                ]
            else:
                # Fixed: login_shell_name injected at the end acts as $0 to pad parameters properly
                exec_args = [login_shell_name, "-c", 'exec "$@"', login_shell_name]
                exec_args.extend(command_args)
    else:
        # --- Strategy B: Clean Adaptive Non-Login Shell Fallback ---
        full_command_string = " ".join(shlex.quote(arg) for arg in command_args)

        if shell_binary in ("csh", "tcsh"):
            exec_args = [shell_binary, "-c", "exec " + full_command_string]
        elif shell_binary == "fish":
            exec_args = [shell_binary, "-c", "exec " + full_command_string]
        else:
            # POSIX non-login fallback uses intact "$@" to ensure native quote boundaries
            exec_args = [shell_binary, "-c", 'exec "$@"', shell_binary]
            exec_args.extend(command_args)

    return exec_binary, exec_args


def exec_via_user(username, command_args, force_login=False):
    """
    Executes a command as a specific user.
    - If force_login=True: Forces a full LOGIN shell (mimics su -l).
    - If force_login=False: Default. Tries clean direct binary exec.
      Auto-falls back to a NON-LOGIN shell if complex shell grammar is found.
    """
    # Pre-validation
    assert command_args and isinstance(
        command_args, list
    ), "command_args must be a non-empty list of strings."
    assert (
        isinstance(username, str) and username
    ), "username must be a non-empty string."

    # 1. Fetch the target user's system records
    pw_record = None
    try:
        pw_record = pwd.getpwnam(username)
    except KeyError:
        pass
    assert pw_record is not None, "Error: User '{}' does not exist.".format(username)

    uid = pw_record.pw_uid
    gid = pw_record.pw_gid
    home = pw_record.pw_dir
    user_shell = pw_record.pw_shell if pw_record.pw_shell else "/bin/sh"

    # 2. Invoke the Extracted Environment Builder
    new_env = build_user_environ(username, uid, home, user_shell)

    # 3. Smart Routing Decision based on --login flag
    if force_login:
        use_direct_exec = False
        resolved_binary = None
    else:
        # Default behavior: attempt raw bypass, scan if it's safe
        must_use_shell, resolved_binary = check_command_compound(
            command_args, new_env.get("PATH")
        )
        use_direct_exec = not must_use_shell

    # 4. Initialize supplementary groups
    has_groups_initialized = False
    try:
        os.initgroups(username, gid)
        has_groups_initialized = True
    except PermissionError:
        pass
    assert has_groups_initialized, "Error: Must be run as root to switch users."

    # 5. Switch GID and UID (Drop privileges irrevocably)
    has_switched_ids = False
    try:
        os.setgid(gid)
        os.setuid(uid)
        has_switched_ids = True
    except PermissionError:
        pass
    assert has_switched_ids, "Error: Failed to set UID/GID. Check permissions."

    # 6. Change directory ONLY if explicit Login Shell is requested
    # Non-login mode will bypass this entirely to preserve the caller's working directory.
    if force_login:
        try:
            os.chdir(home)
        except Exception:
            try:
                os.chdir("/")
            except Exception:
                pass

    # 7. Final Sanity Check for Direct Execution Under Dropped Privileges
    if use_direct_exec:
        if os.path.exists(resolved_binary) and os.access(resolved_binary, os.X_OK):
            exec_binary = resolved_binary
            exec_args = command_args
        else:
            # Fallback to shell if permissions or files are inaccessible post-suid drop
            use_direct_exec = False

    # 8. Shape arguments for os.execvpe (Handling Bash, Zsh, Ksh, Sh, Csh, Tcsh, Fish)
    if not use_direct_exec:
        exec_binary = user_shell
        shell_binary = os.path.basename(user_shell)

        if force_login:
            # ----------------------------------------------------
            # Strategy A: Full Login Shell Configuration
            # ----------------------------------------------------
            login_shell_name = "-" + shell_binary

            if shell_binary == "fish":
                # Fish uses explicit -l / --login flags
                full_command_string = " ".join(shlex.quote(arg) for arg in command_args)
                exec_args = [shell_binary, "-l", "-c", "exec " + full_command_string]

            elif shell_binary in ("csh", "tcsh"):
                # Csh family requires a single-string pipeline argument mapping
                full_command_string = " ".join(shlex.quote(arg) for arg in command_args)
                exec_args = [
                    login_shell_name,
                    "-c",
                    login_shell_name,
                    "exec " + full_command_string,
                ]

            else:
                # POSIX Family (bash, zsh, ksh, sh)
                # Uses standard "$@" forwarding to keep spaces/quotes pristine
                exec_args = [login_shell_name, "-c", 'exec "$@"', login_shell_name]
                exec_args.extend(command_args)
        else:
            # ----------------------------------------------------
            # Strategy B: Clean Adaptive Non-Login Shell Fallback
            # ----------------------------------------------------
            full_command_string = " ".join(shlex.quote(arg) for arg in command_args)

            if shell_binary in ("csh", "tcsh"):
                # Csh branch: standard exec string under non-login
                exec_args = [shell_binary, "-c", "exec " + full_command_string]

            elif shell_binary == "fish":
                # Fish branch: standard non-login, drop the -l flag
                exec_args = [shell_binary, "-c", "exec " + full_command_string]

            else:
                # POSIX Family (bash, zsh, ksh, sh) non-login fallback
                # Retains "$@" to completely bypass inner-string double evaluation issues
                exec_args = [shell_binary, "-c", 'exec "$@"']
                exec_args.extend(command_args)

    # 9. Perform process replacement
    print(new_env)
    print("{} {}".format(exec_binary, exec_args))
    os.execvpe(exec_binary, exec_args, new_env)


def main():
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
    # if len(args.command) == 1:
    # args.command = shlex.split(args.command[0])

    exec_via_user(args.username, args.command, force_login=args.login)


if __name__ == "__main__":
    main()
