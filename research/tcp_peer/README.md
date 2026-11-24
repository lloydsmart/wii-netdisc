# PC loopback TCP experiment

The peer and simulated client exercise the tag, fresh challenge and connection
ID measurements in the [IOS57 baseline plan](../ios57-baseline-plan.md).
Both endpoints use IPv4 TCP on `127.0.0.1`. Use synthetic data only. A pass
establishes the observed behaviour on PC loopback. The wired adapter, IOS57,
the hooked DI thread and ordering before GX cleanup still require hardware
evidence. This diagnostic format is independent of the proposed NBD transport.

## Run from the repository root

Run all scenarios with Python 3.10 or later and GNU timeout:

```sh
timeout 30s python3 -B -m unittest discover -s tests -p 'test_tcp_peer.py' -v
```

For an independent exchange, start the peer in one terminal:

```sh
python3 -B -m research.tcp_peer.peer --port 0
```

Use the port printed on the listening line in a second terminal. For example,
if the peer prints `listening local=127.0.0.1:49152`, run:

```sh
python3 -B -m research.tcp_peer.client --port 49152
```

The client generates a random tag and challenge, verifies both echoes and
requires a non-zero connection ID. It attempts the connection and exchange
once. A timeout or invalid reply produces an error and a non-zero exit status.
The peer also accepts a fixed port. Press Ctrl-C to stop it.

## Experimental wire format

Each exchange consists of one 24-byte request followed by one 28-byte reply.
Offsets are zero-based. Fields are contiguous with no padding, length prefix,
text encoding or terminator.

| Offset | Size in bytes | Request | Reply |
| ---: | ---: | --- | --- |
| 0 | 8 | Opaque run tag | Exact tag bytes |
| 8 | 16 | Fresh opaque challenge | Exact challenge bytes |
| 24 | 4 | Absent | Unsigned connection ID, most significant byte first |

Frame boundaries follow byte counts regardless of how TCP splits or combines
writes. A client can send its next request on the same socket after the reply.
IDs begin at 1 and increase on every accept, including connections that fail
mid-request. An ID lasts until that socket closes. The peer stops on ID
exhaustion. Restarting the peer starts a new ID sequence, so compare IDs only
within one peer run.

The peer services one connection at a time. It starts a monotonic five-second
budget before reading each frame, including the idle wait for its first byte.
All reads and reply writes share that deadline. A partial frame cannot extend
it. Each endpoint must observe its final socket operation complete before its
own deadline. Bytes already sent can reach the other endpoint even when the
sender records a timeout. Use `--timeout 0.75` on the peer for a shorter budget.
The client allows five seconds to connect and five seconds for the complete
send and reply.

## Read the evidence

- **A, persistent connection.** Two distinct challenges and the same run tag
  must echo exactly. Both replies must end with the ID from the same accept.
- **B, new connection.** The client closes the first socket and explicitly
  opens a second. The tag stays the same. The third challenge must echo with
  the new accept's ID.
- **C, bounded failure.** One client stalls after a partial request and sends
  a late byte. The peer records a timeout against the original deadline.
  Another client closes mid-request and produces a disconnect with a short
  byte count. Each case requires a successful exchange on the next connection.
- **Fragmentation.** The test waits for the peer to record the first byte
  before sending the remaining 23, then compares the complete binary reply.

The accept line associates an ID with both TCP endpoints. Each exchange logs
its absolute deadline in seconds on the peer's monotonic clock. For each ID, join
the request or reply hex chunks in order and use the frame sizes above. Each
line counts the bytes actually received or sent in that socket operation.
`disconnect received=0/24` means EOF between requests, while `3/24` means EOF
inside a frame. A timeout or socket error ends the connection. The peer logs
`closed` after releasing the accepted socket.
