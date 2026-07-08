"""A message-board client: the world side of the model's edge.

This file only constructs instructions (with the one encoder), sends them
to the router, and displays outputs. The workload logic itself lives in
the instructions, not here.

The shape the model gave the message board (brief step 6 -- discovering
this shape IS the experiment):

- A message is an unsent instruction file at msgs/<id>:
      concat(demand(<previous message>), "[", ts, "] ", user, ": ", text, "\n")
  Demanding the newest message fires the whole chain -- reading is
  running, and the rendered thread is the output. The chain terminates in
  a genesis message that is a plain literal.

- A thread's head is an unsent instruction file at threads/<name>: a
  literal node whose value is the reference of the newest message. The
  fixed path is the reference every demander holds (spec section 7:
  same burden as knowing a file path); the file behind it is world-state,
  replaced through the emit-disk terminal on each post.

- Posting fires one instruction, whole:
      concat(emit_disk(msgs/<new id>, <message instruction bytes>),
             emit_disk(threads/<name>, <literal node naming msgs/<new id>>))

Anything that varies enters as a value from here, the world: timestamps
and message-id uniqueness come from the client's clock (spec section 7).
"""

import os
import socket
import sys
import time

from .instruction import Incomplete, comp, demand, lit, outcome, skip
from .structures import CONCAT, EMIT_DISK

HOST = os.environ.get("AM_HOST", "127.0.0.1")
PORT = int(os.environ.get("AM_PORT", "7799"))


def call(instr):
    """Send one instruction, receive its output (the demand return path)."""
    with socket.create_connection((HOST, PORT)) as s:
        s.sendall(instr)
        buf = b""
        while True:
            try:
                end = skip(buf, 0)
                break
            except Incomplete:
                data = s.recv(65536)
                if not data:
                    return "error", b"router closed the connection"
                buf += data
    return outcome(buf[:end])


def head_ref(thread):
    return "threads/" + thread


def new_thread(thread):
    kind, value = call(demand(head_ref(thread)))
    if kind == "value":
        return "error", ("thread already exists: " + thread).encode()
    genesis = "msgs/" + thread + "-genesis"
    instr = comp(
        CONCAT,
        comp(EMIT_DISK, lit(genesis),
             lit(lit("=== thread %s ===\n" % thread))),
        comp(EMIT_DISK, lit(head_ref(thread)), lit(lit(genesis))),
    )
    return call(instr)


def post(thread, user, text):
    # Step 1: demand the head -- its firing returns the reference of the
    # newest message. (Two firings, because a demand reference must be a
    # held literal, never computed inside a firing; see FRICTION.md.)
    kind, prev = call(demand(head_ref(thread)))
    if kind == "error":
        return kind, prev
    now = time.time()  # the world supplying what varies (spec section 7)
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    mid = "msgs/%d-%s" % (int(now * 1000), user)
    message = comp(
        CONCAT,
        demand(prev.decode()),
        lit("["), lit(ts), lit("] "), lit(user), lit(": "), lit(text),
        lit("\n"),
    )
    # Step 2: one firing, whole -- the message comes to rest as an unsent
    # instruction, and the head reference now names it.
    instr = comp(
        CONCAT,
        comp(EMIT_DISK, lit(mid), lit(message)),
        comp(EMIT_DISK, lit(head_ref(thread)), lit(lit(mid))),
    )
    kind, value = call(instr)
    if kind == "value":
        return kind, mid.encode()
    return kind, value


def read(thread):
    kind, ref = call(demand(head_ref(thread)))
    if kind == "error":
        return kind, ref
    # Demanding the newest message fires the whole chain: reading is running.
    return call(demand(ref.decode()))


def main():
    argv = sys.argv[1:]
    usage = "usage: client.py new-thread NAME | post THREAD USER TEXT | read THREAD"
    if not argv:
        print(usage, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "new-thread" and len(args) == 1:
        kind, value = new_thread(args[0])
        ok_msg = "created thread " + args[0]
    elif cmd == "post" and len(args) == 3:
        kind, value = post(*args)
        ok_msg = "posted " + (value.decode() if kind == "value" else "")
    elif cmd == "read" and len(args) == 1:
        kind, value = read(args[0])
        ok_msg = None
    else:
        print(usage, file=sys.stderr)
        return 2
    if kind == "error":
        print("error: " + value.decode(errors="replace"), file=sys.stderr)
        return 1
    sys.stdout.write(value.decode(errors="replace") if ok_msg is None
                     else ok_msg + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
