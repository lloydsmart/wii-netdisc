"""Send one synthetic challenge to the PC loopback peer."""

import argparse
import secrets
import socket
import time

from .peer import CHALLENGE_SIZE, DEADLINE, ID_SIZE, LOOPBACK, REQUEST_SIZE, TAG_SIZE
from .peer import receive, remaining


def connect(port):
    return socket.create_connection((LOOPBACK, port), timeout=DEADLINE)


def exchange(sock, tag, challenge):
    if len(tag) != TAG_SIZE or len(challenge) != CHALLENGE_SIZE:
        raise ValueError("expected an 8-byte run tag and a 16-byte challenge")
    request = tag + challenge
    deadline = time.monotonic() + DEADLINE
    sock.settimeout(remaining(deadline))
    sock.sendall(request)
    reply = receive(sock, REQUEST_SIZE + ID_SIZE, deadline)
    if reply[:REQUEST_SIZE] != request:
        raise ValueError(f"echo mismatch: sent {request.hex()}, received {reply.hex()}")
    connection_id = int.from_bytes(reply[REQUEST_SIZE:], "big")
    if connection_id == 0:
        raise ValueError("invalid connection ID 0")
    return reply[:TAG_SIZE], reply[TAG_SIZE:REQUEST_SIZE], connection_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("use a port from 1 to 65535")
    try:
        with connect(args.port) as sock:
            tag, challenge, connection_id = exchange(
                sock, secrets.token_bytes(TAG_SIZE), secrets.token_bytes(CHALLENGE_SIZE)
            )
    except (EOFError, OSError, ValueError) as exc:
        parser.exit(1, f"exchange failed: {exc}\n")
    print(f"echo verified id={connection_id} tag={tag.hex()} challenge={challenge.hex()}")


if __name__ == "__main__":
    main()
