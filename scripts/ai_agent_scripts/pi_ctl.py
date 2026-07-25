#!/usr/bin/env python3
"""Paramiko helper for the home-phone Pi (password auth, no keys).

Subcommands:
  run <command>               run a single shell command
  put <local> <remote>        upload a file
  get <remote> <local>        download a file
  batch <command-file>        run each line as a command in one SSH session
"""
import argparse
import os
import sys
import time
import paramiko

# Force UTF-8/replace for stdout/stderr on Windows so remote Unicode output
# (e.g. systemctl bullets/box-drawing) does not crash the local terminal.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HOST = '10.0.0.123'  # mDNS homephone.local is flaky; IP is reliable
USER = 'raspberry'
PASS = 'pi'


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        password=PASS,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    return client


def run_command(command: str, timeout: int = 30) -> int:
    client = connect()
    try:
        # Use a PTY so sudo prompts work and the remote shell sees a TTY.
        stdin, stdout, stderr = client.exec_command(
            command, timeout=timeout, get_pty=True
        )
        out = stdout.read().decode(errors='ignore')
        err = stderr.read().decode(errors='ignore')
        print(out, end='')
        if err:
            print(err, end='', file=sys.stderr)
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


def _progress(transferred: int, total: int, start: float):
    pct = transferred / total if total else 0
    now = time.time()
    # update every ~5 % or at completion
    if getattr(_progress, 'last_pct', -1) == -1 or pct >= _progress.last_pct + 0.05 or pct == 1:
        mb = transferred / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        elapsed = now - start
        rate = mb / elapsed if elapsed else 0
        print(f'\r  {pct*100:5.1f}%  {mb:.1f}/{total_mb:.1f} MB  {rate:.1f} MB/s', end='', flush=True)
        _progress.last_pct = pct


def put_file(local: str, remote: str) -> int:
    client = connect()
    try:
        sftp = client.open_sftp()
        size = os.path.getsize(local)
        start = time.time()
        _progress.last_pct = -1
        print(f'Uploading {local} -> {remote} ({size/(1024*1024):.1f} MB)')
        sftp.put(local, remote, callback=lambda t, tt: _progress(t, tt, start))
        print()  # newline after progress
        sftp.close()
        return 0
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    finally:
        client.close()


def get_file(remote: str, local: str) -> int:
    client = connect()
    try:
        sftp = client.open_sftp()
        info = sftp.stat(remote)
        start = time.time()
        _progress.last_pct = -1
        print(f'Downloading {remote} -> {local} ({info.st_size/(1024*1024):.1f} MB)')
        sftp.get(remote, local, callback=lambda t, tt: _progress(t, tt, start))
        print()
        sftp.close()
        return 0
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    finally:
        client.close()


def batch(commands_path: str, timeout: int = 60) -> int:
    """Open one interactive shell and feed commands from a file.

    This is useful when commands include sudo because the sudo timestamp
    is tied to the same TTY/session.
    """
    if not os.path.isfile(commands_path):
        print(f'error: file not found: {commands_path}', file=sys.stderr)
        return 1
    with open(commands_path) as f:
        commands = [line.rstrip('\n') for line in f if line.strip() and not line.strip().startswith('#')]
    if not commands:
        print('error: no commands in file', file=sys.stderr)
        return 1

    client = connect()
    try:
        shell = client.invoke_shell(term='xterm')
        shell.settimeout(timeout)
        # Give the shell time to start
        time.sleep(0.3)

        def drain():
            out = b''
            while shell.recv_ready():
                try:
                    out += shell.recv(4096)
                except Exception:
                    break
            return out.decode(errors='ignore')

        print(drain(), end='')
        for cmd in commands:
            print(f'>>> {cmd}')
            shell.send(cmd + '\n')
            # Wait for the command to produce output and prompt to return.
            # We poll until the prompt '$ ' reappears.
            buf = ''
            deadline = time.time() + timeout
            while time.time() < deadline:
                if shell.recv_ready():
                    buf += shell.recv(4096).decode(errors='ignore')
                    print(buf, end='')
                    # Prompt detection is heuristic; tweak if prompt differs.
                    if buf.rstrip().endswith(('$ ', '# ', '> ')):
                        break
                    buf = ''
                time.sleep(0.1)
            else:
                print('\nerror: timed out waiting for command to finish', file=sys.stderr)
                return 1
        return 0
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description='Pi control via Paramiko')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_run = sub.add_parser('run', help='run a shell command')
    p_run.add_argument('command', help='shell command')
    p_run.add_argument('-t', '--timeout', type=int, default=30)

    p_put = sub.add_parser('put', help='upload a file')
    p_put.add_argument('local')
    p_put.add_argument('remote')

    p_get = sub.add_parser('get', help='download a file')
    p_get.add_argument('remote')
    p_get.add_argument('local')

    p_batch = sub.add_parser('batch', help='run commands from a file in one SSH session')
    p_batch.add_argument('file')
    p_batch.add_argument('-t', '--timeout', type=int, default=60)

    args = parser.parse_args()
    if args.cmd == 'run':
        sys.exit(run_command(args.command, args.timeout))
    elif args.cmd == 'put':
        sys.exit(put_file(args.local, args.remote))
    elif args.cmd == 'get':
        sys.exit(get_file(args.remote, args.local))
    elif args.cmd == 'batch':
        sys.exit(batch(args.file, args.timeout))


if __name__ == '__main__':
    main()
