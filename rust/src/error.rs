use std::fmt;

#[derive(Debug)]
pub enum VmError {
    InvalidOpcode(i32, usize),
    InvalidRegister(usize),
    InvalidMemory(usize),
    InvalidJump(usize, usize),
    StackOverflow,
    StackUnderflow,
    OutOfCode,
    InvalidInterrupt(usize),
    UnhandledInterrupt(usize),
    DoubleFault(usize),
    IntStackOverflow,
    IntStackUnderflow,
    InvalidMode(i32),
}

impl fmt::Display for VmError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            VmError::InvalidOpcode(op, ip) => write!(f, "invalid opcode {} at ip={}", op, ip),
            VmError::InvalidRegister(r) => write!(f, "invalid register r{} (0-7)", r),
            VmError::InvalidMemory(a) => write!(f, "invalid memory address {} (0-1023)", a),
            VmError::InvalidJump(t, s) => write!(f, "invalid jump target {} (code size {})", t, s),
            VmError::StackOverflow => write!(f, "call stack overflow (256)"),
            VmError::StackUnderflow => write!(f, "call stack underflow"),
            VmError::OutOfCode => write!(f, "unexpected end of code"),
            VmError::InvalidInterrupt(v) => write!(f, "invalid interrupt vector {}", v),
            VmError::UnhandledInterrupt(v) => write!(f, "unhandled interrupt vector {}", v),
            VmError::DoubleFault(v) => write!(f, "double fault (vector {})", v),
            VmError::IntStackOverflow => write!(f, "interrupt stack overflow (64)"),
            VmError::IntStackUnderflow => write!(f, "interrupt stack underflow"),
            VmError::InvalidMode(m) => write!(f, "invalid mode {} (must be 0 or 1)", m),
        }
    }
}

impl std::error::Error for VmError {}
