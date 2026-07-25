#!/usr/bin/env python3
"""Small Paramiko helper for the home-phone Pi (password auth, no keys)."""
import argparse
import sys
import paramiko

HOST = '10.0.0.123'
USER = 'raspberry'
PASS = 'pi'


def run(command: str, timeout: int = 30) -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            HOST,
            username=USER,
            password=PASS,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=True)
        # get_pty merges stdout/stderr, but we can still read them separately.
        out = stdout.read().decode(errors='ignore')
        err = stderr.read().decode(errors='ignore')
        print(out, end='')
        if err:
            print(err, end='', file=sys.stderr)
        return stdout.channel.recv_exit_status()
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run a command on the Pi via Paramiko')
    parser.add_argument('command', help='shell command to run')
    parser.add_argument('-t', '--timeout', type=int, default=30)
    args = parser.parse_args()
    sys.exit(run(args.command, args.timeout))
