"""Serial IPv4 loopback peer for synthetic IOS57 baseline exchanges."""

import argparse
import socket
import time

LOOPBACK = "127.0.0.1"
TAG_SIZE = 8
CHALLENGE_SIZE = 16
REQUEST_SIZE = TAG_SIZE + CHALLENGE_SIZE
ID_SIZE = 4
DEADLINE = 5.0


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("exchange deadline reached")
    return seconds


def receive(sock, size, deadline, on_chunk=None):
    data = bytearray()
    while len(data) < size:
        sock.settimeout(remaining(deadline))
        chunk = sock.recv(size - len(data))
        completed = time.monotonic()
        if chunk and on_chunk is not None:
            on_chunk(chunk)
        if completed >= deadline:
            raise TimeoutError("receive completed at or after exchange deadline")
        if not chunk:
            raise EOFError(f"received={len(data)}/{size}")
        data.extend(chunk)
    return bytes(data)


def exchanges(sock, connection_id, timeout, log):
    def log_request(chunk):
        log(f"id={connection_id} request bytes={len(chunk)} hex={chunk.hex()}")

    while True:
        deadline = time.monotonic() + timeout
        log(f"id={connection_id} exchange deadline={deadline}")
        request = receive(sock, REQUEST_SIZE, deadline, log_request)
        reply = request + connection_id.to_bytes(ID_SIZE, "big")
        # Record only the bytes the socket accepted, including on a short write.
        while reply:
            sock.settimeout(remaining(deadline))
            sent = sock.send(reply)
            completed = time.monotonic()
            if not sent:
                raise ConnectionError("zero-byte send")
            log(f"id={connection_id} reply bytes={sent} hex={reply[:sent].hex()}")
            if completed >= deadline:
                raise TimeoutError("send completed at or after exchange deadline")
            reply = reply[sent:]


def serve(listener, timeout, log, stopping=lambda: False):
    connection_id = 0
    listener.settimeout(0.2)
    while not stopping():
        try:
            sock, remote = listener.accept()
        except TimeoutError:
            continue
        connection_id += 1
        try:
            with sock:
                if connection_id >= 1 << (8 * ID_SIZE):
                    raise OverflowError("connection IDs exhausted")
                host, port = sock.getsockname()
                log(f"id={connection_id} accept local={host}:{port} "
                    f"remote={remote[0]}:{remote[1]}")
                exchanges(sock, connection_id, timeout, log)
        except EOFError as exc:
            log(f"id={connection_id} disconnect {exc}")
        except TimeoutError as exc:
            log(f"id={connection_id} timeout budget={timeout:g}s reason={exc}")
        except OSError as exc:
            log(f"id={connection_id} error {exc}")
        finally:
            log(f"id={connection_id} closed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 selects a free port)")
    parser.add_argument("--timeout", type=float, default=DEADLINE, help="exchange budget in seconds")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or not 0 < args.timeout <= DEADLINE:
        parser.error("use a port from 0 to 65535 and a timeout greater than 0 and at most 5")

    def log(message):
        print(message, flush=True)

    with socket.create_server((LOOPBACK, args.port)) as listener:
        log(f"listening local={LOOPBACK}:{listener.getsockname()[1]}")
        try:
            serve(listener, args.timeout, log)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
