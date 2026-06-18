mod error;
mod sandbox;
mod vm;

use std::env;
use std::fs;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use vm::Vm;

const USAGE: &str = "\
TBVM — Telegram Bot Virtual Machine

Usage:
  tbvm run <file>              Execute bytecode file
  tbvm isolate <file> <dir>    Execute in sandboxed mode (iso_engine)
  tbvm disasm <file>           Disassemble bytecode to text
";

const MAX_BYTECODE_SIZE: usize = 4 * 1024 * 1024;

fn read_bytecode(path: &str) -> Result<Vec<i32>, String> {
    let meta = fs::metadata(path).map_err(|e| format!("cannot access '{}': {}", path, e))?;
    if !meta.is_file() {
        return Err(format!("'{}' is not a regular file", path));
    }
    if meta.len() > MAX_BYTECODE_SIZE as u64 {
        return Err(format!("bytecode too large (max {} bytes)", MAX_BYTECODE_SIZE));
    }
    let raw = fs::read(path).map_err(|e| format!("cannot read '{}': {}", path, e))?;
    if raw.len() % 4 != 0 {
        return Err("bytecode size must be multiple of 4".into());
    }
    Ok(raw
        .chunks_exact(4)
        .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect())
}

fn cmd_run(path: &str) -> Result<(), String> {
    let code = read_bytecode(path)?;
    let mut vm = Vm::new(code);
    let exit_code = vm.run().map_err(|e| format!("VM error: {}", e))?;

    let out_path = Path::new("output.png");
    let f = fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(out_path)
        .map_err(|e| format!("cannot create output.png: {}", e))?;
    vm.write_png_file(&f)
        .map_err(|e| format!("cannot write output.png: {}", e))?;

    if exit_code != 0 {
        eprintln!("Exit code: {}", exit_code);
    }
    Ok(())
}

fn extract_exec_string(code: &[i32], offset: usize) -> Result<(String, usize), String> {
    let mut bytes = Vec::new();
    for &w in &code[offset..] {
        let b = w.to_le_bytes();
        for &byte in &b {
            if byte == 0 {
                let s = std::str::from_utf8(&bytes)
                    .map_err(|_| "invalid UTF-8 in EXEC string".to_string())?;
                let words_consumed = bytes.len() / 4 + 1;
                return Ok((s.to_string(), words_consumed));
            }
            bytes.push(byte);
        }
    }
    Err("unterminated EXEC string".to_string())
}

fn cmd_isolate(path: &str, dir: &str) -> Result<(), String> {
    let code = read_bytecode(path)?;

    let dir_canon = fs::canonicalize(dir)
        .map_err(|_| format!("cannot resolve directory '{}'", dir))?;
    let dir_path = dir_canon.as_path();

    let mut ip = 0usize;
    let mut regs = [0i32; 8];

    while ip < code.len() {
        let op = code[ip];
        ip += 1;
        match op {
            0 => break,
            1 => {
                if ip + 2 > code.len() {
                    return Err("unexpected end of code".into());
                }
                let r = code[ip] as usize;
                ip += 1;
                let v = code[ip];
                ip += 1;
                if r >= 8 {
                    return Err(format!("invalid register r{}", r));
                }
                regs[r] = v;
            }
            2 => {
                if ip + 1 > code.len() {
                    return Err("unexpected end of code".into());
                }
                let r = code[ip] as usize;
                ip += 1;
                if r >= 8 {
                    return Err(format!("invalid register r{}", r));
                }
                println!("REG[{}] = {}", r, regs[r]);
            }
            3 => {
                let (cmd, words) = extract_exec_string(&code, ip)?;
                eprintln!("WARNING: executing system command from bytecode: {}", cmd);
                println!(">> {}", cmd);
                sandbox::run_isolated(&cmd, dir_path)
                    .map_err(|e| format!("sandbox error: {:?}", e))?;
                println!(">> OK");
                ip += words;
            }
            _ => return Err(format!("unknown opcode {} at ip={}", op, ip - 1)),
        }
    }
    Ok(())
}

const OP_NAMES: &[&str] = &[
    "HALT", "MOV", "ADD", "ADDI", "SUB", "SUBI", "CMP", "CMPI",
    "JMP", "JZ", "JNZ", "CALL", "RET", "STORE", "LOAD", "DRAW", "PRINT",
    "CLS", "RAND", "KEY",
    "INT", "IRET", "CLI", "STI", "SETMODE", "EXIT", "TIMER",
];

const OP_ARGS: &[&[&str]] = &[
    &[],                              // HALT
    &["reg", "val"],                  // MOV
    &["reg", "reg"],                  // ADD
    &["reg", "val"],                  // ADDI
    &["reg", "reg"],                  // SUB
    &["reg", "val"],                  // SUBI
    &["reg", "reg"],                  // CMP
    &["reg", "val"],                  // CMPI
    &["addr"],                        // JMP
    &["addr"],                        // JZ
    &["addr"],                        // JNZ
    &["addr"],                        // CALL
    &[],                              // RET
    &["addr", "reg"],                 // STORE
    &["reg", "addr"],                 // LOAD
    &["reg", "reg", "reg"],           // DRAW
    &["reg"],                         // PRINT
    &[],                              // CLS
    &["reg", "val"],                  // RAND
    &["reg"],                         // KEY
    &["val"],                         // INT
    &[],                              // IRET
    &[],                              // CLI
    &[],                              // STI
    &["reg"],                         // SETMODE
    &["reg"],                         // EXIT
    &["val"],                         // TIMER
];

fn cmd_disasm(path: &str) -> Result<(), String> {
    let code = read_bytecode(path)?;
    let mut ip = 0usize;
    while ip < code.len() {
        let raw = code[ip] as usize;
        ip += 1;
        if raw >= OP_NAMES.len() {
            println!("  .word {}", raw);
            continue;
        }
        let name = OP_NAMES[raw];
        let arg_types = OP_ARGS[raw];
        if ip + arg_types.len() > code.len() {
            return Err("unexpected end of code in disassembly".into());
        }
        let args = &code[ip..ip + arg_types.len()];
        ip += args.len();

        let mut out = format!("  {}", name);
        for (&val, &ty) in args.iter().zip(arg_types.iter()) {
            match ty {
                "reg" => out.push_str(&format!(" r{}", val)),
                _ => out.push_str(&format!(" {}", val)),
            }
        }
        println!("{}", out);
    }
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        println!("{}", USAGE);
        return;
    }
    let result = match args[1].as_str() {
        "run" => {
            if args.len() < 3 {
                Err("usage: tbvm run <file>".into())
            } else {
                cmd_run(&args[2])
            }
        }
        "isolate" => {
            if args.len() < 4 {
                Err("usage: tbvm isolate <file> <dir>".into())
            } else {
                cmd_isolate(&args[2], &args[3])
            }
        }
        "disasm" => {
            if args.len() < 3 {
                Err("usage: tbvm disasm <file>".into())
            } else {
                cmd_disasm(&args[2])
            }
        }
        _ => {
            println!("{}", USAGE);
            return;
        }
    };
    if let Err(e) = result {
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }
}
