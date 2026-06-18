import struct
import re

OPCODES = {
    'HALT': 0, 'MOV': 1, 'ADD': 2, 'ADDI': 3,
    'SUB': 4, 'SUBI': 5, 'CMP': 6, 'CMPI': 7,
    'JMP': 8, 'JZ': 9, 'JNZ': 10, 'CALL': 11,
    'RET': 12, 'STORE': 13, 'LOAD': 14,
    'DRAW': 15, 'PRINT': 16,
}

INSTR_ARGS = {
    'HALT': [],
    'MOV': ['reg', 'val'],
    'ADD': ['reg', 'reg'],
    'ADDI': ['reg', 'val'],
    'SUB': ['reg', 'reg'],
    'SUBI': ['reg', 'val'],
    'CMP': ['reg', 'reg'],
    'CMPI': ['reg', 'val'],
    'JMP': ['addr'],
    'JZ': ['addr'],
    'JNZ': ['addr'],
    'CALL': ['addr'],
    'RET': [],
    'STORE': ['addr', 'reg'],
    'LOAD': ['reg', 'addr'],
    'DRAW': ['reg', 'reg', 'reg'],
    'PRINT': ['reg'],
}

OPCODE_NAMES = {v: k for k, v in OPCODES.items()}


class AssembleError(Exception):
    pass


class Assembler:
    def assemble(self, source):
        lines = source.strip().split('\n')
        labels = {}
        ip = 0
        parsed_lines = []

        for line_no, raw in enumerate(lines, 1):
            text = re.split(r'[;#]', raw)[0].strip()
            if not text:
                continue
            if text.startswith('.'):
                label = text[1:]
                if label in labels:
                    raise AssembleError(f"Duplicate label '{label}' at line {line_no}")
                labels[label] = ip
                continue
            parts = text.split()
            op = parts[0].upper()
            if op not in OPCODES:
                raise AssembleError(f"Unknown instruction '{op}' at line {line_no}")
            args = parts[1:]
            expected = INSTR_ARGS[op]
            if len(args) != len(expected):
                raise AssembleError(
                    f"'{op}' expects {len(expected)} arg(s), got {len(args)} at line {line_no}")
            parsed_lines.append((op, args, line_no))
            ip += 1 + len(expected)

        bytecode = []
        for op, args, line_no in parsed_lines:
            bytecode.append(OPCODES[op])
            for arg in args:
                if arg.startswith('.'):
                    if arg[1:] not in labels:
                        raise AssembleError(f"Unknown label '{arg}' at line {line_no}")
                    bytecode.append(labels[arg[1:]])
                elif re.match(r'^[rR]\d+$', arg):
                    n = int(arg[1:])
                    if n < 0 or n > 7:
                        raise AssembleError(f"Invalid register '{arg}' at line {line_no}")
                    bytecode.append(n)
                else:
                    try:
                        bytecode.append(int(arg))
                    except ValueError:
                        raise AssembleError(f"Invalid value '{arg}' at line {line_no}")

        return struct.pack('<' + 'i' * len(bytecode), *bytecode)

    def disassemble(self, data):
        words = list(struct.unpack('<' + 'i' * (len(data) // 4), data))
        ip = 0
        lines = []
        while ip < len(words):
            op = words[ip]
            ip += 1
            name = OPCODE_NAMES.get(op)
            if name is None:
                lines.append(f"  .word {op}")
                continue
            arg_specs = INSTR_ARGS[name]
            args = words[ip:ip + len(arg_specs)]
            ip += len(args)
            fmt = []
            for a, t in zip(args, arg_specs):
                if t == 'reg':
                    fmt.append(f"r{a}")
                else:
                    fmt.append(str(a))
            if fmt:
                lines.append(f"  {name} {' '.join(fmt)}")
            else:
                lines.append(f"  {name}")
        return '\n'.join(lines)

    def describe(self, data):
        words = list(struct.unpack('<' + 'i' * (len(data) // 4), data))
        return f"Instructions: {len(words)} words / {len(words) * 4} bytes"
