"""Exercise the PC peer and simulated client over real IPv4 loopback sockets."""

import queue
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from research.tcp_peer import client, peer


class ExchangeTests(unittest.TestCase):
    request = bytes(range(24))

    @patch.object(time, "monotonic")
    def test_final_read_must_finish_before_deadline(self, clock):
        for duration in (5.0, 5.3):
            with self.subTest(duration=duration):
                clock.return_value = 100.0
                sock = Mock(spec=socket.socket)

                def final_read(size):
                    clock.return_value = 100.0 + duration
                    return self.request + bytes.fromhex("00000001")

                sock.recv.side_effect = final_read
                with self.assertRaises(TimeoutError):
                    client.exchange(sock, self.request[:8], self.request[8:])
                sock.recv.assert_called_once_with(28)

    @patch.object(time, "monotonic")
    def test_final_short_write_must_finish_before_deadline(self, clock):
        for duration in (5.0, 5.3):
            with self.subTest(duration=duration):
                clock.return_value = 100.0
                sock = Mock(spec=socket.socket)
                sock.recv.side_effect = [self.request, b""]
                sent = bytearray()

                def short_write(data):
                    chunk = data[:3]
                    sent.extend(chunk)
                    if len(sent) == 28:
                        clock.return_value = 100.0 + duration
                    return len(chunk)

                sock.send.side_effect = short_write
                with self.assertRaises(TimeoutError):
                    peer.exchanges(sock, 1, 5, lambda message: None)
                self.assertEqual(sent, self.request + bytes.fromhex("00000001"))
                sock.recv.assert_called_once_with(24)

    def test_zero_connection_id_rejected(self):
        sock = Mock(spec=socket.socket)
        sock.recv.return_value = self.request + bytes(4)
        with self.assertRaisesRegex(ValueError, "connection ID"):
            client.exchange(sock, self.request[:8], self.request[8:])


class LoopbackTests(unittest.TestCase):
    def start_peer(self, timeout=peer.DEADLINE):
        listener = socket.create_server((peer.LOOPBACK, 0))
        self.port = listener.getsockname()[1]
        self.addCleanup(listener.close)
        stopping = threading.Event()
        self.events = queue.Queue()
        errors = []

        def log(message):
            self.events.put(message)
            print(message, flush=True)

        def run():
            try:
                peer.serve(listener, timeout, log, stopping.is_set)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=run, name="loopback-peer", daemon=True)
        thread.start()

        def stop():
            stopping.set()
            thread.join(timeout + 1)
            self.assertFalse(thread.is_alive(), "peer thread failed to stop")
            listener.close()
            self.assertEqual(listener.fileno(), -1)
            if errors:
                raise errors[0]

        self.addCleanup(stop)

    def wait_for_log(self, prefix):
        deadline = time.monotonic() + 2
        while True:
            try:
                message = self.events.get(timeout=peer.remaining(deadline))
            except queue.Empty:
                self.fail(f"missing peer log: {prefix}")
            if message.startswith(prefix):
                return message

    def check_echo(self, sock, tag, challenge):
        echoed_tag, echoed_challenge, connection_id = client.exchange(sock, tag, challenge)
        self.assertEqual(echoed_tag, tag)
        self.assertEqual(echoed_challenge, challenge)
        self.assertGreater(connection_id, 0)
        return connection_id

    def test_cli_rejects_zero_connection_id(self):
        with socket.create_server((peer.LOOPBACK, 0)) as listener:
            listener.settimeout(3)
            port = listener.getsockname()[1]
            command = [sys.executable, "-B", "-m", "research.tcp_peer.client", "--port", str(port)]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) as cli:
                try:
                    sock, _ = listener.accept()
                    with sock:
                        request = peer.receive(sock, 24, time.monotonic() + 2)
                        sock.sendall(request + bytes(4))
                    stdout, stderr = cli.communicate(timeout=3)
                finally:
                    if cli.poll() is None:
                        cli.kill()
                        cli.wait(timeout=2)
        self.assertNotEqual(cli.returncode, 0)
        self.assertNotIn("echo verified", stdout)
        self.assertIn("connection ID", stderr)

    def test_persistent_then_new_connection(self):
        """A and B: same tag, three fresh challenges, two TCP connections."""
        self.start_peer()
        tag = secrets.token_bytes(8)
        challenges = [secrets.token_bytes(16) for _ in range(3)]
        self.assertEqual(len(set(challenges)), 3)
        with client.connect(self.port) as first:
            first_id = self.check_echo(first, tag, challenges[0])
            same_id = self.check_echo(first, tag, challenges[1])
            self.assertEqual(same_id, first_id)
            print(f"A: two distinct challenges echoed on id={first_id}", flush=True)
        with client.connect(self.port) as second:
            new_id = self.check_echo(second, tag, challenges[2])
            self.assertNotEqual(new_id, first_id)
            print(f"B: third challenge echoed on new id={new_id} (was {first_id})", flush=True)

    def test_stalled_partial_request(self):
        """C: a late byte cannot restart the exchange deadline."""
        budget = 0.75
        self.start_peer(budget)
        with client.connect(self.port) as stalled:
            stalled.sendall(b"s")
            prefix = "id=1 exchange deadline="
            deadline = float(self.wait_for_log(prefix).removeprefix(prefix))
            self.wait_for_log("id=1 request bytes=1 hex=73")
            # Deliberately stall partway through the frame, then make progress.
            pause = peer.remaining(deadline - budget * 0.4)
            readable, _, _ = select.select([stalled], [], [], pause)
            self.assertFalse(readable, "peer closed before the exchange deadline")
            stalled.sendall(b"t")
            self.wait_for_log("id=1 request bytes=1 hex=74")
            # Allow scheduling of both threads after expiry, less than the late byte's delay.
            latest_close = deadline + 0.15
            stalled.settimeout(peer.remaining(latest_close))
            self.assertEqual(stalled.recv(1), b"")
            closed = time.monotonic()
            self.assertGreaterEqual(closed, deadline)
            self.assertLess(closed, latest_close)
            self.wait_for_log("id=1 timeout ")
            self.wait_for_log("id=1 closed")
        with client.connect(self.port) as valid:
            self.assertEqual(self.check_echo(valid, b"recovery", secrets.token_bytes(16)), 2)
        elapsed = closed - (deadline - budget)
        print(f"C: partial request closed in {elapsed:.3f}s, next connection passed", flush=True)

    def test_disconnected_partial_request(self):
        """C: premature EOF is recorded separately and the next client succeeds."""
        self.start_peer()
        with client.connect(self.port) as partial:
            partial.sendall(b"cut")
        self.wait_for_log("id=1 disconnect received=3/24")
        self.wait_for_log("id=1 closed")
        with client.connect(self.port) as valid:
            self.assertEqual(self.check_echo(valid, b"recovery", secrets.token_bytes(16)), 2)
        print("C: disconnect after 3 bytes, next connection passed", flush=True)

    def test_fragmented_request(self):
        """The peer reads the first fragment before the client sends the rest."""
        self.start_peer()
        request = bytes(range(24))
        with client.connect(self.port) as sock:
            sock.sendall(request[:1])
            self.wait_for_log("id=1 request bytes=1 hex=00")
            sock.sendall(request[1:])
            reply = peer.receive(sock, 28, time.monotonic() + 2)
            self.assertEqual(reply, request + bytes.fromhex("00000001"))
