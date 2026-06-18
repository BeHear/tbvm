CC = gcc
CFLAGS = -Wall -Wextra -O2

all: vm

vm: vm.c
	$(CC) $(CFLAGS) -o vm vm.c

iso: iso_engine.c
	$(CC) $(CFLAGS) -o iso_engine.exe iso_engine.c

clean:
	rm -f vm vm.exe iso_engine.exe *.o output.ppm

.PHONY: all clean
