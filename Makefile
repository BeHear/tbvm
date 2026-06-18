CC = gcc
CFLAGS = -Wall -Wextra -O2
CARGO = cargo

all: vm iso_engine tbvm

vm: vm.c
	$(CC) $(CFLAGS) -o vm vm.c

iso_engine: iso_engine.c
	$(CC) $(CFLAGS) -o iso_engine iso_engine.c

tbvm:
	$(CARGO) build --release --manifest-path rust/Cargo.toml
	cp rust/target/release/tbvm tbvm

clean:
	rm -f vm vm.exe iso_engine iso_engine.exe tbvm *.o output.ppm
	$(CARGO) clean --manifest-path rust/Cargo.toml

.PHONY: all clean
