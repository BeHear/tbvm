"""Final comprehensive test suite for TBVM Bot."""
import asyncio
import os
import struct
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from assembler import Assembler, AssembleError
from bot_aiogram import _normalize_code, _check_rate_limit, _run_sandboxed, VM_CMD, RATE_LIMIT_SEC, _last_run, asm

PASS = 0
FAIL = 0
RESULTS = []


def test(fn):
    global PASS, FAIL, RESULTS
    RESULTS.append(fn.__name__)
    try:
        fn()
        PASS += 1
        print(f"  ✅ {fn.__name__}")
    except Exception as e:
        FAIL += 1
        print(f"  ❌ {fn.__name__}: {e}")
        traceback.print_exc()
    return fn


# ── _normalize_code ────────────────────────────────────────────────

@test
def normalize_preserves_semicolon_comment_at_line_start():
    code = "; comment\nMOV r0 1\n; another\nHALT"
    n = _normalize_code(code)
    assert "; comment" in n
    assert "; another" in n
    assert "MOV r0 1" in n
    assert "HALT" in n


@test
def normalize_splits_inline_pipe():
    code = "MOV r0 42 | PRINT r0 | HALT"
    n = _normalize_code(code)
    lines = [l.strip() for l in n.split("\n") if l.strip()]
    assert lines == ["MOV r0 42", "PRINT r0", "HALT"], f"got {lines}"


@test
def normalize_preserves_hash_comment():
    n = _normalize_code("# comment\nHALT")
    assert "# comment" in n


@test
def normalize_preserves_inline_semicolon_as_comment():
    code = "; header\nMOV r0 10 ; set counter\n.loop\nPRINT r0\nSUBI r0 1\nCMPI r0 0\nJNZ .loop\n; done\nHALT"
    n = _normalize_code(code)
    assert "; header" in n
    assert "; done" in n
    assert "; set counter" in n
    assert "MOV r0 10" in n


@test
def normalize_empty_lines_survive():
    n = _normalize_code("\n\nMOV r0 1\n\nHALT\n")
    assert "MOV r0 1" in n
    assert "HALT" in n


@test
def normalize_trailing_semicolon():
    n = _normalize_code("MOV r0 1;\nHALT")
    lines = [l.strip() for l in n.split("\n") if l.strip()]
    assert "MOV r0 1;" in lines or "MOV r0 1" in lines


@test
def normalize_multiple_inline_pipe_separators():
    n = _normalize_code("MOV r0 1 | MOV r1 2 | ADD r0 r1 | HALT")
    lines = [l.strip() for l in n.split("\n") if l.strip()]
    assert len(lines) == 4, f"got {lines}"


@test
def normalize_tab_indented_comments():
    n = _normalize_code("\t; tab comment\nHALT")
    assert "; tab comment" in n


# ── _check_rate_limit ──────────────────────────────────────────────

@test
def ratelimit_first_call_passes():
    _last_run.pop(99991, None)
    assert _check_rate_limit(99991) is None


@test
def ratelimit_immediate_second_blocked():
    _last_run.pop(99992, None)
    _check_rate_limit(99992)
    assert _check_rate_limit(99992) is not None


@test
def ratelimit_different_users_independent():
    _last_run.pop(99993, None)
    _last_run.pop(99994, None)
    assert _check_rate_limit(99993) is None
    assert _check_rate_limit(99994) is None
    assert _check_rate_limit(99993) is not None


@test
def ratelimit_resets_after_cooldown():
    _last_run.pop(99995, None)
    _check_rate_limit(99995)
    _last_run[99995] = time.monotonic() - RATE_LIMIT_SEC - 1
    assert _check_rate_limit(99995) is None, "should have reset"


# ── asm.assemble ───────────────────────────────────────────────────

@test
def asm_simple_program():
    data = asm.assemble("MOV r0 42\nPRINT r0\nHALT")
    assert len(data) == 24
    dis = asm.disassemble(data)
    assert "MOV r0 42" in dis
    assert "PRINT r0" in dis
    assert "HALT" in dis


@test
def asm_labels_resolve():
    data = asm.assemble("JMP .skip\nHALT\n.skip\nMOV r0 1\nHALT")
    words = list(struct.unpack(f"<{len(data)//4}i", data))
    assert words[0] == 8
    assert words[1] == 3


@test
def asm_reject_bad_register():
    try:
        asm.assemble("MOV r9 1")
        assert False
    except AssembleError:
        pass


@test
def asm_reject_unknown_instruction():
    try:
        asm.assemble("FOO r0")
        assert False
    except AssembleError:
        pass


@test
def asm_reject_wrong_arg_count():
    try:
        asm.assemble("MOV r0")
        assert False
    except AssembleError:
        pass


@test
def asm_reject_bad_value():
    try:
        asm.assemble("MOV r0 abc")
        assert False
    except AssembleError:
        pass


@test
def asm_reject_duplicate_label():
    try:
        asm.assemble(".loop\n.loop\nHALT")
        assert False
    except AssembleError:
        pass


@test
def asm_reject_unknown_label():
    try:
        asm.assemble("JMP .nonexistent\nHALT")
        assert False
    except AssembleError:
        pass


@test
def asm_draw_with_registers():
    data = asm.assemble("MOV r0 10\nMOV r1 20\nMOV r2 255\nDRAW r0 r1 r2\nHALT")
    dis = asm.disassemble(data)
    assert "DRAW r0 r1 r2" in dis


@test
def asm_call_ret_round_trip():
    data = asm.assemble("CALL .sub\nHALT\n.sub\nMOV r0 99\nRET")
    dis = asm.disassemble(data)
    assert "CALL" in dis
    assert "RET" in dis


@test
def asm_all_instructions():
    for instr in [
        "HALT",
        "MOV r0 1", "ADD r0 r1", "ADDI r0 1",
        "SUB r0 r1", "SUBI r0 1",
        "CMP r0 r1", "CMPI r0 1",
        "JMP 0", "JZ 0", "JNZ 0",
        "CALL 0", "RET",
        "STORE 0 r0", "LOAD r0 0",
        "DRAW r0 r1 r2",
        "PRINT r0",
        "CLS",
        "RAND r0 100",
        "KEY r0",
    ]:
        data = asm.assemble(instr)
        assert len(data) > 0, f"empty for {instr}"


@test
def asm_round_trip_consistency():
    code = "MOV r0 10\n.loop\nPRINT r0\nSUBI r0 1\nCMPI r0 0\nJNZ .loop\nHALT"
    data = asm.assemble(code)
    dis1 = asm.disassemble(data)
    data2 = asm.assemble(dis1.replace("  ", ""))
    dis2 = asm.disassemble(data2)
    assert dis1 == dis2, f"mismatch:\n{dis1}\n---\n{dis2}"


@test
def asm_long_values():
    data = asm.assemble("MOV r0 2147483647\nHALT")
    assert len(data) > 0


@test
def asm_negative_values():
    data = asm.assemble("MOV r0 -42\nHALT")
    assert "-42" in asm.disassemble(data)


@test
def asm_zero_values():
    data = asm.assemble("MOV r0 0\nHALT")
    assert len(data) > 0


# ── Sandbox (require VM binary) ───────────────────────────────────

@test
def sandbox_vm_binary_available():
    assert VM_CMD is not None, "No VM binary. Build with 'make' or 'make tbvm'"
    assert os.path.isfile(VM_CMD[0]), f"Binary {VM_CMD[0]} not found"


@test
def sandbox_normal_program():
    async def t():
        data = asm.assemble("MOV r0 42\nPRINT r0\nHALT")
        r = await _run_sandboxed(data)
        assert not r["timeout"], "unexpected timeout"
        assert b"OUT: 42" in r["stdout"], f"bad stdout: {r['stdout']!r}"
    asyncio.run(t())


@test
def sandbox_timeout_kills_infinite_loop():
    async def t():
        data = struct.pack("<ii", 8, 0)
        r = await _run_sandboxed(data)
        assert r["timeout"], "should have timed out"
    asyncio.run(t())


@test
def sandbox_png_captured():
    async def t():
        data = asm.assemble("MOV r0 10\nMOV r1 10\nMOV r2 255\nDRAW r0 r1 r2\nHALT")
        r = await _run_sandboxed(data)
        assert r["png"] is not None, "no PNG"
        assert len(r["png"]) > 100, f"PNG too small: {len(r['png'])}"
    asyncio.run(t())


@test
def sandbox_stderr_on_bad_opcode():
    async def t():
        data = struct.pack("<i", 99)
        r = await _run_sandboxed(data)
        combined = (r["stderr"] + r["stdout"]).decode().lower()
        assert "error" in combined or "unknown opcode" in combined, f"no error: {combined}"
    asyncio.run(t())


@test
def sandbox_countdown_matches():
    async def t():
        code = "MOV r0 3\n.loop\nPRINT r0\nSUBI r0 1\nCMPI r0 0\nJNZ .loop\nHALT"
        r = await _run_sandboxed(asm.assemble(code))
        assert not r["timeout"]
        assert b"OUT: 3\nOUT: 2\nOUT: 1" in r["stdout"], f"got {r['stdout'].decode()!r}"
    asyncio.run(t())


@test
def asm_cls_encodes():
    data = asm.assemble("CLS\nHALT")
    assert len(data) == 8
    dis = asm.disassemble(data)
    assert "CLS" in dis


@test
def asm_rand_encodes():
    data = asm.assemble("RAND r0 100\nHALT")
    assert len(data) == 16
    dis = asm.disassemble(data)
    assert "RAND r0 100" in dis


@test
def asm_key_encodes():
    data = asm.assemble("KEY r0\nHALT")
    assert len(data) == 12
    dis = asm.disassemble(data)
    assert "KEY r0" in dis


@test
def asm_rand_reject_bad_register():
    try:
        asm.assemble("RAND r9 1")
        assert False
    except AssembleError:
        pass


@test
def asm_rand_reject_non_integer():
    try:
        asm.assemble("RAND r0 abc")
        assert False
    except AssembleError:
        pass


@test
def asm_cls_round_trip():
    code = "CLS\nMOV r0 42\nDRAW r0 r1 r2\nCLS\nHALT"
    data = asm.assemble(code)
    dis = asm.disassemble(data)
    assert dis.count("CLS") == 2


@test
def sandbox_cls_produces_png():
    async def t():
        data = asm.assemble("CLS\nHALT")
        r = await _run_sandboxed(data)
        assert not r["timeout"]
        assert r["png"] is not None, "no PNG on CLS"
    asyncio.run(t())


@test
def sandbox_rand_returns_value():
    async def t():
        data = asm.assemble("RAND r0 100\nPRINT r0\nHALT")
        r = await _run_sandboxed(data)
        assert not r["timeout"]
        assert b"OUT:" in r["stdout"]
        val = int(r["stdout"].decode().strip().split()[-1])
        assert 0 <= val < 100, f"RAND out of range: {val}"
    asyncio.run(t())


@test
def sandbox_key_returns_neg1():
    async def t():
        data = asm.assemble("KEY r0\nPRINT r0\nHALT")
        r = await _run_sandboxed(data)
        assert not r["timeout"]
        assert b"OUT: -1" in r["stdout"], f"got {r['stdout'].decode()!r}"
    asyncio.run(t())


# ── Run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"  TBVM Bot — Final Test Suite")
    print(f"  {len(RESULTS)} tests registered ({PASS+FAIL} executed)")
    print(f"{'='*55}\n")

    # Each @test decorated function ran during import. Print summary.
    print(f"\n{'='*55}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'='*55}")
    sys.exit(0 if FAIL == 0 else 1)
