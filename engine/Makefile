CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
FABRIC_INC := $(abspath fabric)

all: harness/differential harness/measure harness/rematch harness/circulate

fabric/fabric.o: fabric/fabric.c fabric/fabric.h
	$(CC) $(CFLAGS) -c $< -o $@

EDGE_SRC := edge/plant.c edge/pave.c edge/name.c edge/channel.c edge/convert.c
edge/edge.a: $(EDGE_SRC) edge/edge.h fabric/fabric.h
	$(CC) $(CFLAGS) -DFABRIC_INC='"$(FABRIC_INC)"' -c edge/plant.c -o edge/plant.o
	$(CC) $(CFLAGS) -DFABRIC_INC='"$(FABRIC_INC)"' -c edge/pave.c -o edge/pave.o
	$(CC) $(CFLAGS) -c edge/name.c -o edge/name.o
	$(CC) $(CFLAGS) -c edge/channel.c -o edge/channel.o
	$(CC) $(CFLAGS) -c edge/convert.c -o edge/convert.o
	ar rcs $@ edge/*.o

# G1: instructions from edge handoff (function entry) to road entry
# (the indirect call through the road table), straight-line worst path
harness/g1_count.h: fabric/fabric.o
	n=$$(objdump -d fabric/fabric.o --disassemble=nmo_arrive \
	     | awk '/^[[:space:]]+[0-9a-f]+:/ { c++ } /call[[:space:]]+\*/ { print c; exit }'); \
	echo "#define G1_DISPATCH_INSTRUCTIONS $$n" > $@

harness/differential: harness/differential.c fabric/fabric.o edge/edge.a
	$(CC) $(CFLAGS) $< fabric/fabric.o edge/edge.a -ldl -lm -o $@

harness/measure: harness/measure.c harness/g1_count.h fabric/fabric.o edge/edge.a
	$(CC) $(CFLAGS) -Iharness $< fabric/fabric.o edge/edge.a -ldl -lm -o $@

test: harness/differential
	mkdir -p /tmp/nmo-pave && NMO_JIT_DIR=/tmp/nmo-pave ./harness/differential

clean:
	rm -f fabric/*.o edge/*.o edge/edge.a harness/g1_count.h \
	      harness/differential harness/measure

.PHONY: all test clean

harness/rematch: harness/rematch.c harness/kernels.h fabric/fabric.o edge/edge.a
	$(CC) $(CFLAGS) -Iharness $< fabric/fabric.o edge/edge.a -ldl -lm -o $@

harness/circulate: harness/circulate.c harness/kernels.h fabric/fabric.o edge/edge.a
	$(CC) $(CFLAGS) -Iharness $< fabric/fabric.o edge/edge.a -ldl -lm -o $@
