CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
LDLIBS = -ldl

all: libnmo.a tests/test_engine

libnmo.a: engine.o
	ar rcs $@ $^

engine.o: engine.c nmo.h
	$(CC) $(CFLAGS) -c engine.c -o $@

tests/test_engine: tests/test_engine.c libnmo.a nmo.h
	$(CC) $(CFLAGS) tests/test_engine.c libnmo.a $(LDLIBS) -o $@

test: tests/test_engine
	mkdir -p /tmp/nmo-jit && NMO_JIT_DIR=/tmp/nmo-jit ./tests/test_engine

clean:
	rm -f engine.o libnmo.a tests/test_engine

.PHONY: all test clean
