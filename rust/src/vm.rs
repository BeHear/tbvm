use crate::error::VmError;
use std::fs::File;
use std::io::Read;

const VRAM_W: usize = 128;
const VRAM_H: usize = 128;
const NUM_REGS: usize = 8;
const MEM_SIZE: usize = 1024;
const STACK_SIZE: usize = 256;
const INT_STACK_SIZE: usize = 64;
const FAULT_VEC_INVALID_OP: usize = 0;
const FAULT_VEC_PRIVILEGE: usize = 1;
const _FAULT_VEC_MEMORY: usize = 2; // reserved for memory bounds fault
const FAULT_VEC_TIMER: usize = 3;

#[derive(Clone, Copy, Debug, PartialEq)]
enum Op {
    Halt, Mov, Add, Addi, Sub, Subi,
    Cmp, Cmpi, Jmp, Jz, Jnz,
    Call, Ret, Store, Load, Draw, Print,
    Cls, Rand, Key,
    Int, Iret, Cli, Sti, Setmode, Exit, Timer,
}

pub struct Vm {
    regs: [i32; NUM_REGS],
    memory: [i32; MEM_SIZE],
    call_stack: [usize; STACK_SIZE],
    sp: usize,
    flag_zero: bool,
    pub vram: [i32; VRAM_W * VRAM_H],
    code: Vec<i32>,
    ip: usize,
    rng_state: u32,

    mode: u8,
    int_enabled: bool,
    ivt_base: usize,
    int_stack: [usize; INT_STACK_SIZE],
    int_sp: usize,
    timer_interval: i32,
    timer_counter: i32,
}

fn decode_op(val: i32) -> Option<Op> {
    Some(match val {
        0 => Op::Halt,  1 => Op::Mov,  2 => Op::Add,  3 => Op::Addi,
        4 => Op::Sub,   5 => Op::Subi, 6 => Op::Cmp,  7 => Op::Cmpi,
        8 => Op::Jmp,   9 => Op::Jz,  10 => Op::Jnz, 11 => Op::Call,
        12 => Op::Ret, 13 => Op::Store, 14 => Op::Load,
         15 => Op::Draw, 16 => Op::Print,
         17 => Op::Cls, 18 => Op::Rand, 19 => Op::Key,
         20 => Op::Int, 21 => Op::Iret, 22 => Op::Cli, 23 => Op::Sti,
         24 => Op::Setmode, 25 => Op::Exit, 26 => Op::Timer,
        _ => return None,
    })
}

impl Vm {
    pub fn new(code: Vec<i32>) -> Self {
        use std::time::{SystemTime, UNIX_EPOCH};
        let seed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos() as u32)
            .unwrap_or(12345);
        Vm {
            regs: [0; NUM_REGS],
            memory: [0; MEM_SIZE],
            call_stack: [0; STACK_SIZE],
            sp: 0,
            flag_zero: false,
            vram: [0; VRAM_W * VRAM_H],
            code,
            ip: 0,
            rng_state: seed,

            mode: 0,
            int_enabled: false,
            ivt_base: 0,
            int_stack: [0; INT_STACK_SIZE],
            int_sp: 0,
            timer_interval: 0,
            timer_counter: 0,
        }
    }

    fn read(&mut self) -> Result<i32, VmError> {
        if self.ip >= self.code.len() {
            return Err(VmError::OutOfCode);
        }
        let v = self.code[self.ip];
        self.ip += 1;
        Ok(v)
    }

    fn reg_idx(&mut self) -> Result<usize, VmError> {
        let r = self.read()?;
        if r < 0 || r as usize >= NUM_REGS {
            return Err(VmError::InvalidRegister(r as usize));
        }
        Ok(r as usize)
    }

    fn addr_idx(&mut self) -> Result<usize, VmError> {
        let a = self.read()? as usize;
        if a >= MEM_SIZE {
            return Err(VmError::InvalidMemory(a));
        }
        Ok(a)
    }

    fn jump_target(&mut self) -> Result<usize, VmError> {
        let t = self.read()? as usize;
        if t >= self.code.len() {
            return Err(VmError::InvalidJump(t, self.code.len()));
        }
        Ok(t)
    }

    fn trigger_interrupt(&mut self, vector: usize) -> Result<(), VmError> {
        if vector >= 256 {
            return Err(VmError::InvalidInterrupt(vector));
        }
        if self.int_sp + 3 > INT_STACK_SIZE {
            return Err(VmError::IntStackOverflow);
        }
        let ivt_addr = self.ivt_base + vector;
        if ivt_addr >= MEM_SIZE {
            return Err(VmError::InvalidInterrupt(vector));
        }
        let handler = self.memory[ivt_addr] as usize;
        if handler >= self.code.len() || handler == 0 {
            return Err(VmError::UnhandledInterrupt(vector));
        }
        self.int_stack[self.int_sp] = self.ip;
        self.int_stack[self.int_sp + 1] = self.mode as usize;
        self.int_stack[self.int_sp + 2] = self.int_enabled as usize;
        self.int_sp += 3;
        self.mode = 0;
        self.int_enabled = false;
        self.ip = handler;
        Ok(())
    }

    fn fault(&mut self, vector: usize) -> Result<(), VmError> {
        if self.mode == 0 {
            return Err(VmError::DoubleFault(vector));
        }
        self.trigger_interrupt(vector)
    }

    pub fn run(&mut self) -> Result<i32, VmError> {
        loop {
            if self.ip >= self.code.len() {
                return Ok(0);
            }
            let raw = self.read()?;
            let op = match decode_op(raw) {
                Some(op) => op,
                None => {
                    if self.mode != 0 && self.ivt_base + FAULT_VEC_INVALID_OP < MEM_SIZE {
                        let handler = self.memory[self.ivt_base + FAULT_VEC_INVALID_OP];
                        if handler != 0 {
                            self.fault(FAULT_VEC_INVALID_OP)?;
                            continue;
                        }
                    }
                    return Err(VmError::InvalidOpcode(raw, self.ip - 1));
                }
            };

            match op {
                Op::Halt => return Ok(0),

                Op::Exit => {
                    let r = self.reg_idx()?;
                    return Ok(self.regs[r]);
                }

                Op::Mov => {
                    let r = self.reg_idx()?;
                    let v = self.read()?;
                    self.regs[r] = v;
                }

                Op::Add => {
                    let r1 = self.reg_idx()?;
                    let r2 = self.reg_idx()?;
                    self.regs[r1] = self.regs[r1].wrapping_add(self.regs[r2]);
                }

                Op::Addi => {
                    let r1 = self.reg_idx()?;
                    self.regs[r1] = self.regs[r1].wrapping_add(self.read()?);
                }

                Op::Sub => {
                    let r1 = self.reg_idx()?;
                    let r2 = self.reg_idx()?;
                    self.regs[r1] = self.regs[r1].wrapping_sub(self.regs[r2]);
                }

                Op::Subi => {
                    let r1 = self.reg_idx()?;
                    self.regs[r1] = self.regs[r1].wrapping_sub(self.read()?);
                }

                Op::Cmp => {
                    let r1 = self.reg_idx()?;
                    let r2 = self.reg_idx()?;
                    self.flag_zero = self.regs[r1] == self.regs[r2];
                }

                Op::Cmpi => {
                    let r1 = self.reg_idx()?;
                    self.flag_zero = self.regs[r1] == self.read()?;
                }

                Op::Jmp => {
                    self.ip = self.jump_target()?;
                }

                Op::Jz => {
                    let t = self.jump_target()?;
                    if self.flag_zero {
                        self.ip = t;
                    }
                }

                Op::Jnz => {
                    let t = self.jump_target()?;
                    if !self.flag_zero {
                        self.ip = t;
                    }
                }

                Op::Call => {
                    if self.sp >= STACK_SIZE {
                        return Err(VmError::StackOverflow);
                    }
                    let t = self.jump_target()?;
                    self.call_stack[self.sp] = self.ip;
                    self.sp += 1;
                    self.ip = t;
                }

                Op::Ret => {
                    if self.sp == 0 {
                        return Err(VmError::StackUnderflow);
                    }
                    self.sp -= 1;
                    self.ip = self.call_stack[self.sp];
                }

                Op::Store => {
                    let a = self.addr_idx()?;
                    let r = self.reg_idx()?;
                    self.memory[a] = self.regs[r];
                }

                Op::Load => {
                    let r = self.reg_idx()?;
                    let a = self.addr_idx()?;
                    self.regs[r] = self.memory[a];
                }

                Op::Draw => {
                    let rx = self.reg_idx()?;
                    let ry = self.reg_idx()?;
                    let rc = self.reg_idx()?;
                    let x = self.regs[rx];
                    let y = self.regs[ry];
                    if x >= 0 && (x as usize) < VRAM_W && y >= 0 && (y as usize) < VRAM_H {
                        self.vram[y as usize * VRAM_W + x as usize] = self.regs[rc];
                    }
                }

                Op::Print => {
                    let r = self.reg_idx()?;
                    println!("OUT: {}", self.regs[r]);
                }

                Op::Cls => {
                    self.vram.fill(0);
                }

                Op::Rand => {
                    let r = self.reg_idx()?;
                    let m = self.read()?;
                    self.rng_state = self.rng_state.wrapping_mul(1103515245).wrapping_add(12345);
                    let val = (self.rng_state >> 16) as i32;
                    self.regs[r] = if m > 0 { val % m } else { 0 };
                }

                Op::Key => {
                    let r = self.reg_idx()?;
                    let mut buf = [0u8; 1];
                    match std::io::stdin().read_exact(&mut buf) {
                        Ok(()) => self.regs[r] = buf[0] as i32,
                        Err(_) => self.regs[r] = -1,
                    }
                }

                Op::Int => {
                    let vec = self.read()? as usize;
                    self.trigger_interrupt(vec)?;
                }

                Op::Iret => {
                    if self.mode != 0 {
                        self.fault(FAULT_VEC_PRIVILEGE)?;
                        continue;
                    }
                    if self.int_sp < 3 {
                        return Err(VmError::IntStackUnderflow);
                    }
                    self.int_sp -= 3;
                    self.ip = self.int_stack[self.int_sp];
                    self.mode = self.int_stack[self.int_sp + 1] as u8;
                    self.int_enabled = self.int_stack[self.int_sp + 2] != 0;
                }

                Op::Cli => {
                    self.int_enabled = false;
                }

                Op::Sti => {
                    self.int_enabled = true;
                }

                Op::Setmode => {
                    if self.mode != 0 {
                        self.fault(FAULT_VEC_PRIVILEGE)?;
                        continue;
                    }
                    let r = self.reg_idx()?;
                    let m = self.regs[r];
                    if m != 0 && m != 1 {
                        return Err(VmError::InvalidMode(m));
                    }
                    self.mode = m as u8;
                }

                Op::Timer => {
                    if self.mode != 0 {
                        self.fault(FAULT_VEC_PRIVILEGE)?;
                        continue;
                    }
                    let n = self.read()?;
                    self.timer_interval = if n > 0 { n } else { 0 };
                    self.timer_counter = 0;
                }
            }

            if self.int_enabled && self.timer_interval > 0 {
                self.timer_counter += 1;
                if self.timer_counter >= self.timer_interval {
                    self.timer_counter = 0;
                    let ivt_addr = self.ivt_base + FAULT_VEC_TIMER;
                    if ivt_addr < MEM_SIZE && self.memory[ivt_addr] != 0 {
                        self.trigger_interrupt(FAULT_VEC_TIMER)?;
                    }
                }
            }
        }
    }

    #[allow(dead_code)]
    pub fn write_ppm(&self, path: &str) -> std::io::Result<()> {
        let mut f = std::fs::File::create(path)?;
        self.write_ppm_inner(&mut f)
    }

    pub fn write_ppm_file(&self, f: &File) -> std::io::Result<()> {
        let mut f = f.try_clone()?;
        self.write_ppm_inner(&mut f)
    }

    fn write_ppm_inner(&self, f: &mut impl std::io::Write) -> std::io::Result<()> {
        write!(f, "P3\n{} {}\n255\n", VRAM_W, VRAM_H)?;
        for &p in &self.vram {
            write!(f, "{} {} {} ", (p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF)?;
        }
        Ok(())
    }
}
