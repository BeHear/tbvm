CARGO = cargo

all: tbvm

tbvm:
	$(CARGO) build --release --manifest-path rust/Cargo.toml
	cp rust/target/release/tbvm tbvm

clean:
	rm -f tbvm tbvm.exe *.o output.png output.gif
	$(CARGO) clean --manifest-path rust/Cargo.toml

.PHONY: all clean
