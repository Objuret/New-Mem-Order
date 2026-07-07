# Message-board workload (brief step 6), expressed purely as instructions
# over the structure library. This file contains NO workload logic that the
# router executes as ordinary code — it only composes instruction trees and
# sends them. The board's behavior lives entirely in the composition.
#
# References the board uses (spec §2 "Reference" — the demander holds them,
# there is no lookup subsystem):
#   t/<name>   a thread: a file that IS an unsent instruction which, when
#              fired, yields the thread's rendered content
#   index      the list of thread names — itself just a thread, maintained
#              with the same compositions; its reference is well-known,
#              like a root path
#
# The compositions (structures: 1 concat, 2 quote, 3 write; demand `D` is a
# grammar node, not a structure — core machinery per spec §3.1/A4):
#
#   read a thread:    D(ref) — demanding = reading = firing, nothing else
#   post to thread:   write(ref, quote(concat(D(ref), line)))
#                     — the read-append-write is ONE instruction, so it
#                     fires whole and indivisibly (spec §2)
#   create thread:    concat(write(t/N, quote("")), write-index-entry)
#                     — a series of two writes sequenced by concat, one tree
#
# Anything that varies — timestamps — enters as a value composed by the
# demander, never conjured inside a structure (spec §7).

import socket
import sys

import instruction
from instruction import D, ERROR, F, V
from structures import CONCAT, QUOTE, WRITE_FILE

INDEX_REF = b"index"


def thread_ref(name):
    return b"t/" + name.encode()


def read_instr(ref):
    return D(ref)


def post_instr(ref, line):
    return F(
        WRITE_FILE,
        V(ref),
        F(QUOTE, F(CONCAT, D(ref), V(line))),
    )


def init_board_instr():
    # Establishing the board = writing the empty index. Explicit, like mkdir
    # today: a missing reference selects nothing, and no conditional
    # structure exists to paper over that (see friction-log.md #2).
    return F(WRITE_FILE, V(INDEX_REF), F(QUOTE, V(b"")))


def create_thread_instr(name):
    return F(
        CONCAT,
        F(WRITE_FILE, V(thread_ref(name)), F(QUOTE, V(b""))),
        post_instr(INDEX_REF, name.encode() + b"\n"),
    )


def format_line(ts, author, text):
    return f"[{ts}] {author}: {text}\n".encode()


class Client:
    def __init__(self, port, host="127.0.0.1"):
        self.sock = socket.create_connection((host, port))

    def demand(self, instr):
        """Send an instruction, receive the output (spec §3: the demand is
        the return path). The reply is a value or the reserved error form —
        distinguishable by construction, so a refusal raises here instead
        of masquerading as content."""
        self.sock.sendall(instr)
        buf = b""
        while True:
            end = instruction.node_end(buf) if buf else None
            if end is not None:
                tag, payload = instruction.payload_of(buf[:end])
                if tag == ERROR:
                    raise RuntimeError(payload.decode())
                return payload
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("router closed the connection")
            buf += chunk

    def init_board(self):
        return self.demand(init_board_instr())

    def create_thread(self, name):
        return self.demand(create_thread_instr(name))

    def post(self, thread, ts, author, text):
        return self.demand(post_instr(thread_ref(thread), format_line(ts, author, text)))

    def read(self, thread):
        return self.demand(read_instr(thread_ref(thread)))

    def list_threads(self):
        return self.demand(read_instr(INDEX_REF))

    def close(self):
        self.sock.close()


if __name__ == "__main__":
    # CLI: python3 client.py <port> init
    #      python3 client.py <port> create <thread>
    #      python3 client.py <port> post <thread> <ts> <author> <text>
    #      python3 client.py <port> read <thread>
    #      python3 client.py <port> threads
    port, op = int(sys.argv[1]), sys.argv[2]
    c = Client(port)
    if op == "init":
        print(c.init_board().decode())
    elif op == "create":
        print(c.create_thread(sys.argv[3]).decode())
    elif op == "post":
        print(c.post(sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]).decode())
    elif op == "read":
        sys.stdout.write(c.read(sys.argv[3]).decode())
    elif op == "threads":
        sys.stdout.write(c.list_threads().decode())
    c.close()
