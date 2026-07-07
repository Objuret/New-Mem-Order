# The router (brief step 3): one event loop. Receive instruction → resolve
# IDs → fire whole tree → return output to demander.
#
# No locks, no queues, no overlap checking — there is nothing to coordinate
# (spec §2 "Router"). Multiple clients may be connected at once; each
# complete instruction fires whole and indivisibly, one at a time, which is
# exactly the atomicity the spec's "fires whole" grants. The demander is the
# connection the instruction arrived on; the output goes straight back on
# it, quoted as a literal instruction, so both directions of the wire carry
# only the one representation.
#
# Instrumentation (NOT part of the model, required by the brief's
# measurements): every top-level firing appends its composition shape and
# structure-invocation count to <stats_dir>/firings.log.
#
# Usage: python3 router.py <port> <data_dir>

import os
import selectors
import socket
import sys

import instruction
import structures


def serve(port, data_dir):
    structures.set_root(os.path.join(data_dir, "board"))
    os.makedirs(data_dir, exist_ok=True)
    stats_path = os.path.join(data_dir, "firings.log")

    sel = selectors.DefaultSelector()
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", port))
    lsock.listen()
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)
    print(f"router: listening on 127.0.0.1:{port}, root {data_dir}", flush=True)

    buffers = {}

    while True:
        for key, _mask in sel.select():
            if key.data is None:
                conn, _addr = key.fileobj.accept()
                conn.setblocking(False)
                sel.register(conn, selectors.EVENT_READ, data="conn")
                buffers[conn] = b""
                continue

            conn = key.fileobj
            try:
                chunk = conn.recv(65536)
            except ConnectionError:
                chunk = b""
            if not chunk:
                sel.unregister(conn)
                conn.close()
                del buffers[conn]
                continue

            buffers[conn] += chunk
            while buffers[conn]:
                try:
                    end = instruction.node_end(buffers[conn])
                except instruction.BadTag:
                    # Unexpressible bytes: nothing was selected; the
                    # stream carrying them ends here.
                    sel.unregister(conn)
                    conn.close()
                    del buffers[conn]
                    break
                if end is None:
                    break  # instruction not fully arrived yet
                instr = buffers[conn][:end]
                buffers[conn] = buffers[conn][end:]

                counter = [0]
                try:
                    reply = instruction.V(structures.fire(instr, counter))
                except (structures.FiringError, OSError) as e:
                    # The reserved error form: distinguishable from content
                    # by construction (spec-amendments.md #2).
                    reply = instruction.E(str(e).encode())

                sh, _ = instruction.shape(instr)
                with open(stats_path, "a") as f:
                    f.write(f"{sh}\t{counter[0]}\n")

                conn.sendall(reply)


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2])
