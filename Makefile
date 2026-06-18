CC = gcc
CFLAGS = -Wall -Wextra -O2

all: vm iso_engine

vm: vm.c
	$(CC) $(CFLAGS) -o vm vm.c

iso_engine: iso_engine.c
	$(CC) $(CFLAGS) -o iso_engine iso_engine.c

clean:
	rm -f vm vm.exe iso_engine iso_engine.exe *.o output.ppm

.PHONY: all clean
