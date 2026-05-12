from vm import VM, MachineError, Err

# ── Smoke testers ────────────────────────────────────────────────────────────────

def make_tester():
    """Create a fresh VM and a w() helper bound to it."""
    vm = VM()
    def w(offset, *bytes_):
        for i, b in enumerate(bytes_):
            vm.mem[VM.PROGRAM_BASE + offset + i] = b
    return vm, w


def _run_alu_binary(vm, w, opcode, a_val, b_val):
    """Helper: load A,B → run opcode → return R."""
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00, a_val & 0xFF, (a_val >> 8) & 0xFF)
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00, b_val & 0xFF, (b_val >> 8) & 0xFF)
    w(16,  opcode,0x00,0x00,0x00)
    w(20,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    return vm._sr(2), vm._flag(VM.FZ), vm._flag(VM.FN)


# ── ALU Group ─────────────────────────────────────────────────────────────────

def test_add():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x01, 100, 50)
    print(f"  ADD  100 + 50 = {r}  Z={z} N={n}  ({'PASS' if r == 150 and not z and not n else 'FAIL'})")

def test_add_zero():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x01, 0, 0)
    print(f"  ADD  0 + 0   = {r}  Z={z} N={n}  ({'PASS' if r == 0 and z and not n else 'FAIL'})")

def test_add_overflow():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x01, 0xFFFF, 1)
    print(f"  ADD  0xFFFF + 1 = {r:#06x}  Z={z} N={n}  ({'PASS' if r == 0 and z and not n else 'FAIL'})")

def test_sub():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x02, 100, 30)
    print(f"  SUB  100 - 30 = {r}  Z={z} N={n}  ({'PASS' if r == 70 and not z and not n else 'FAIL'})")

def test_sub_negative():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x02, 10, 20)
    print(f"  SUB  10 - 20  = {r}  Z={z} N={n}  ({'PASS' if r == 0xFFF6 and not z and n else 'FAIL'})")

def test_mul():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x03, 7, 9)
    print(f"  MUL  7 * 9     = {r}  Z={z} N={n}  ({'PASS' if r == 63 and not z and not n else 'FAIL'})")

def test_div():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x04, 10, 3)
    rem = vm._sr(3)
    print(f"  DIV  10 / 3    = {r} rem {rem}  Z={z} N={n}  ({'PASS' if r == 3 and rem == 1 and not z and not n else 'FAIL'})")


# ── Logic Group ───────────────────────────────────────────────────────────────

def _run_logic_unary(vm, w, opcode, a_val):
    """Helper: load A → run opcode → return R."""
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00, a_val & 0xFF, (a_val >> 8) & 0xFF)
    w( 8,  opcode,0x00,0x00,0x00)
    w(12,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    return vm._sr(2), vm._flag(VM.FZ), vm._flag(VM.FN)

def test_and():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x05, 0xFF0F, 0x0FF0)
    print(f"  AND  0xFF0F & 0x0FF0 = {r:#06x}  ({'PASS' if r == 0x0F00 else 'FAIL'})")

def test_or():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x06, 0xFF00, 0x00FF)
    print(f"  OR   0xFF00 | 0x00FF = {r:#06x}  ({'PASS' if r == 0xFFFF else 'FAIL'})")

def test_xor():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x07, 0xAAAA, 0xFFFF)
    print(f"  XOR  0xAAAA ^ 0xFFFF = {r:#06x}  ({'PASS' if r == 0x5555 else 'FAIL'})")

def test_not():
    vm, w = make_tester()
    r, z, n = _run_logic_unary(vm, w, 0x08, 0xAAAA)
    print(f"  NOT  0xAAAA = {r:#06x}  ({'PASS' if r == 0x5555 else 'FAIL'})")

def test_neg():
    vm, w = make_tester()
    r, z, n = _run_logic_unary(vm, w, 0x09, 5)
    print(f"  NEG  5 = {r}  N={n}  ({'PASS' if r == 0xFFFB and n else 'FAIL'})")


# ── Shift Group ───────────────────────────────────────────────────────────────

def test_shift_left():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x0A, 0x0005, 0x0003)  # left 3
    print(f"  SHF  0x0005 << 3 = {r:#06x}  ({'PASS' if r == 0x0028 else 'FAIL'})")

def test_shift_right():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x0A, 0x00F0, 0x0014)  # right 4
    print(f"  SHF  0x00F0 >> 4 = {r:#06x}  ({'PASS' if r == 0x000F else 'FAIL'})")

def test_shift_flag_n():
    vm, w = make_tester()
    r, z, n = _run_alu_binary(vm, w, 0x0A, 0x8000, 0x0011)  # right 1
    print(f"  SHF  0x8000 >> 1 = {r:#06x}  N={n}  ({'PASS' if r == 0x4000 and not n else 'FAIL'})")


# ── Compare Group ─────────────────────────────────────────────────────────────

def test_cmp_eq():
    vm, w = make_tester()
    _, z, n = _run_alu_binary(vm, w, 0x0C, 42, 42)
    print(f"  CMP  42 == 42  Z={z} N={n}  ({'PASS' if z and not n else 'FAIL'})")

def test_cmp_gt():
    vm, w = make_tester()
    _, z, n = _run_alu_binary(vm, w, 0x0C, 100, 50)
    print(f"  CMP  100 > 50   Z={z} N={n}  ({'PASS' if not z and not n else 'FAIL'})")

def test_cmp_lt():
    vm, w = make_tester()
    _, z, n = _run_alu_binary(vm, w, 0x0C, 10, 20)
    print(f"  CMP  10 < 20    Z={z} N={n}  ({'PASS' if not z and n else 'FAIL'})")

# ── Flow Control Group ────────────────────────────────────────────────────────

def test_jmp():
    vm, w = make_tester()
    # Jump over the HALT at offset 20 to a NOP then HALT at offset 24
    w( 0,  0x10,0x00,0x05,0x00)   # SEL 5
    w( 4,  0x11,0x00,0x18,0x02)   # LD  target = 0x0218 (PROGRAM_BASE + 24)
    w( 8,  0x20,0x00,0x00,0x00)   # JMP
    w(12,  0xFF,0x00,0x00,0x00)   # HALT (should be skipped)
    w(16,  0xFF,0x00,0x00,0x00)   # HALT (should be skipped)
    # target lands here:
    w(24,  0x03,0x00,0x00,0x00)   # MUL  (harmless, proves we got here)
    w(28,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  JMP  target reached  PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")


def test_call_ret():
    vm, w = make_tester()
    # Main: CALL subroutine, then HALT
    # Subroutine at offset 24: ADD, then RET
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00,0x0A,0x00)   # LD  10
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00,0x05,0x00)   # LD  5
    w(16,  0x10,0x00,0x05,0x00)   # SEL 5
    w(20,  0x11,0x00,0x20,0x02)   # LD  target = 0x0220 (PROGRAM_BASE + 32)
    w(24,  0x30,0x00,0x00,0x00)   # CALL
    # return lands here:
    w(28,  0xFF,0x00,0x00,0x00)   # HALT
    # subroutine at offset 32:
    w(32,  0x01,0x00,0x00,0x00)   # ADD  (10 + 5 = 15)
    w(36,  0x31,0x00,0x00,0x00)   # RET
    vm.run()
    r = vm._sr(2)
    pc = vm._r16(VM.PC_ADDR)
    print(f"  CALL/RET  R={r}  PC={hex(pc)}  ({'PASS' if r == 15 and pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")

def test_call_nested():
    vm, w = make_tester()
    # Main: CALL sub1, HALT
    # sub1: CALL sub2, RET
    # sub2: RET
    w( 0, 0x10, 0x00, 0x05, 0x00)  # SEL 5 (JT)
    w( 4, 0x11, 0x00, 0x20, 0x02)  # LD 0x0220 → JT (sub1 address)
    w( 8, 0x30, 0x00, 0x00, 0x00)  # CALL
    w(12, 0xFF, 0x00, 0x00, 0x00)  # HALT

    # sub1 at 0x0220
    w(32, 0x10, 0x00, 0x05, 0x00)  # SEL 5 (JT)
    w(36, 0x11, 0x00, 0x40, 0x02)  # LD 0x0240 → JT (sub2 address)
    w(40, 0x30, 0x00, 0x00, 0x00)  # CALL
    w(44, 0x31, 0x00, 0x00, 0x00)  # RET

    # sub2 at 0x0240
    w(64, 0x31, 0x00, 0x00, 0x00)  # RET

    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  CALL Nested  PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 16 else 'FAIL'})")

# ── Conditional Group ─────────────────────────────────────────────────────────

def test_ifeq_skip():
    vm, w = make_tester()
    # A=5, B=5 → CMP sets Z=1 → IFEQ skips NOP
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x05,0x00)  # LD 5
    w( 8, 0x10,0x00,0x01,0x00)  # SEL 1
    w(12, 0x11,0x00,0x05,0x00)  # LD 5
    w(16, 0x0C,0x00,0x00,0x00)  # CMP → Z=1
    w(20, 0x21,0x00,0x00,0x00)  # IFEQ (skip next)
    w(24, 0x00,0x00,0x00,0x00)  # NOP (skipped)
    w(28, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFEQ (skip)   PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")


def test_ifne_noskip():
    vm, w = make_tester()
    # Set A=5, B=10 → CMP sets Z=0
    w( 0, 0x10, 0x00, 0x00, 0x00)  # SEL 0 (A)
    w( 4, 0x11, 0x00, 0x05, 0x00)  # LD 5 → A
    w( 8, 0x10, 0x00, 0x01, 0x00)  # SEL 1 (B)
    w(12, 0x11, 0x00, 0x0A, 0x00)  # LD 10 → B
    w(16, 0x0C, 0x00, 0x00, 0x00)  # CMP A,B → Z=0
    w(20, 0x22, 0x00, 0x00, 0x00)  # IFNE (skip next if Z=0)
    w(24, 0x00, 0x00, 0x00, 0x00)  # NOP (should be skipped)
    w(28, 0xFF, 0x00, 0x00, 0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFNE (skip)  PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")

def test_ifgt():
    vm, w = make_tester()
    # Set A=10, B=5 → CMP sets N=0, Z=0
    w( 0, 0x10, 0x00, 0x00, 0x00)  # SEL 0 (A)
    w( 4, 0x11, 0x00, 0x0A, 0x00)  # LD 10 → A
    w( 8, 0x10, 0x00, 0x01, 0x00)  # SEL 1 (B)
    w(12, 0x11, 0x00, 0x05, 0x00)  # LD 5 → B
    w(16, 0x0C, 0x00, 0x00, 0x00)  # CMP A,B → N=0, Z=0
    w(20, 0x23, 0x00, 0x00, 0x00)  # IFGT (skip next if N=0 and Z=0)
    w(24, 0x00, 0x00, 0x00, 0x00)  # NOP (should be skipped)
    w(28, 0xFF, 0x00, 0x00, 0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFGT  PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")


def test_iflt():
    vm, w = make_tester()
    # Set A=5, B=10 → CMP sets N=1
    w( 0, 0x10, 0x00, 0x00, 0x00)  # SEL 0 (A)
    w( 4, 0x11, 0x00, 0x05, 0x00)  # LD 5 → A
    w( 8, 0x10, 0x00, 0x01, 0x00)  # SEL 1 (B)
    w(12, 0x11, 0x00, 0x0A, 0x00)  # LD 10 → B
    w(16, 0x0C, 0x00, 0x00, 0x00)  # CMP A,B → N=1
    w(20, 0x24, 0x00, 0x00, 0x00)  # IFLT (skip next if N=1)
    w(24, 0x00, 0x00, 0x00, 0x00)  # NOP (should be skipped)
    w(28, 0xFF, 0x00, 0x00, 0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFLT  PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")


def test_ifeq_noskip():
    vm, w = make_tester()
    # A=5, B=6 → CMP sets Z=0 → IFEQ does NOT skip NOP
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x05,0x00)  # LD 5
    w( 8, 0x10,0x00,0x01,0x00)  # SEL 1
    w(12, 0x11,0x00,0x06,0x00)  # LD 6
    w(16, 0x0C,0x00,0x00,0x00)  # CMP → Z=0
    w(20, 0x21,0x00,0x00,0x00)  # IFEQ (no skip)
    w(24, 0x00,0x00,0x00,0x00)  # NOP (executed)
    w(28, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFEQ (noskip) PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")

def test_ifne_noskip():
    vm, w = make_tester()
    # A=5, B=5 → CMP sets Z=1 → IFNE does NOT skip NOP
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x05,0x00)  # LD 5
    w( 8, 0x10,0x00,0x01,0x00)  # SEL 1
    w(12, 0x11,0x00,0x05,0x00)  # LD 5
    w(16, 0x0C,0x00,0x00,0x00)  # CMP → Z=1
    w(20, 0x22,0x00,0x00,0x00)  # IFNE (no skip)
    w(24, 0x00,0x00,0x00,0x00)  # NOP (executed)
    w(28, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    pc = vm._r16(VM.PC_ADDR)
    print(f"  IFNE (noskip) PC={hex(pc)}  ({'PASS' if pc == VM.PROGRAM_BASE + 32 else 'FAIL'})")



# ------------------------------------------------------------------------------------------


def test_stash_unstash_nested():
    vm, w = make_tester()
    # Main: STASH A, CALL sub1, UNSTASH A, HALT
    # sub1: STASH B, CALL sub2, UNSTASH B, RET
    # sub2: LD 0x1234 → R, RET
    w( 0, 0x10, 0x00, 0x00, 0x00)  # SEL 0 (A)
    w( 4, 0x11, 0x00, 0xAAAA, 0x00)  # LD 0xAAAA → A
    w( 8, 0x12, 0x00, 0x00, 0x00)  # STASH 0 (A)
    w(12, 0x10, 0x00, 0x05, 0x00)  # SEL 5 (JT)
    w(16, 0x11, 0x00, 0x20, 0x02)  # LD 0x0220 → JT (sub1 address)
    w(20, 0x30, 0x00, 0x00, 0x00)  # CALL
    w(24, 0x13, 0x00, 0x00, 0x00)  # UNSTASH 0 (A)
    w(28, 0xFF, 0x00, 0x00, 0x00)  # HALT

    # sub1 at 0x0220
    w(32, 0x10, 0x00, 0x01, 0x00)  # SEL 1 (B)
    w(36, 0x11, 0x00, 0xBBBB, 0x00)  # LD 0xBBBB → B
    w(40, 0x12, 0x00, 0x01, 0x00)  # STASH 1 (B)
    w(44, 0x10, 0x00, 0x05, 0x00)  # SEL 5 (JT)
    w(48, 0x11, 0x00, 0x40, 0x02)  # LD 0x0240 → JT (sub2 address)
    w(52, 0x30, 0x00, 0x00, 0x00)  # CALL
    w(56, 0x13, 0x00, 0x01, 0x00)  # UNSTASH 1 (B)
    w(60, 0x31, 0x00, 0x00, 0x00)  # RET

    # sub2 at 0x0240
    w(64, 0x10, 0x00, 0x02, 0x00)  # SEL 2 (R)
    w(68, 0x11, 0x00, 0x1234, 0x00)  # LD 0x1234 → R
    w(72, 0x31, 0x00, 0x00, 0x00)  # RET

    vm.run()
    a = vm._sr(0)
    b = vm._sr(1)
    r = vm._sr(2)
    print(f"  STASH/UNSTASH Nested  A={hex(a)}  B={hex(b)}  R={hex(r)}  ({'PASS' if a == 0xAAAA and b == 0xBBBB and r == 0x1234 else 'FAIL'})")

def test_scratch():
    vm, w = make_tester()
    # Main: LD 0x5555 → R, WRS, CALL sub, RDS, HALT
    # sub: LD 0x6666 → R, WRS, RET
    w( 0, 0x10, 0x00, 0x02, 0x00)  # SEL 2 (R)
    w( 4, 0x11, 0x00, 0x5555, 0x00)  # LD 0x5555 → R
    w( 8, 0x15, 0x00, 0x00, 0x00)  # WRS (R → SCRATCH)
    w(12, 0x10, 0x00, 0x05, 0x00)  # SEL 5 (JT)
    w(16, 0x11, 0x00, 0x20, 0x02)  # LD 0x0220 → JT (sub address)
    w(20, 0x30, 0x00, 0x00, 0x00)  # CALL
    w(24, 0x14, 0x00, 0x00, 0x00)  # RDS (SCRATCH → R)
    w(28, 0xFF, 0x00, 0x00, 0x00)  # HALT

    # sub at 0x0220
    w(32, 0x10, 0x00, 0x02, 0x00)  # SEL 2 (R)
    w(36, 0x11, 0x00, 0x6666, 0x00)  # LD 0x6666 → R
    w(40, 0x15, 0x00, 0x00, 0x00)  # WRS (R → SCRATCH)
    w(44, 0x31, 0x00, 0x00, 0x00)  # RET

    vm.run()
    r = vm._sr(2)
    print(f"  SCRATCH  R={hex(r)}  ({'PASS' if r == 0x6666 else 'FAIL'})")


 #── CHK & Host Flags ──────────────────────────────────────────────────────────

def test_chk_match():
    vm, w = make_tester()
    # Simulate host setting RX flag (bit 2)
    vm._sw(15, 0x0004)
    # CHK mask=0x0004 → should set Z=1
    w( 0, 0x0C,0x01,0x04,0x00)  # CHK 0x0004
    w( 4, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    z, n = vm._flag(VM.FZ), vm._flag(VM.FN)
    print(f"  CHK (match)   Z={z} N={n}  ({'PASS' if z and not n else 'FAIL'})")

def test_chk_partial():
    vm, w = make_tester()
    # Host sets RX (bit 2). Mask asks for RX+TX (bits 2&3)
    vm._sw(15, 0x0004)
    w( 0, 0x0C,0x01,0x0C,0x00)  # CHK 0x000C
    w( 4, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    z, n = vm._flag(VM.FZ), vm._flag(VM.FN)
    print(f"  CHK (partial) Z={z} N={n}  ({'PASS' if not z and not n else 'FAIL'})")


# ── Error Traps ───────────────────────────────────────────────────────────────

def test_div_zero():
    vm, w = make_tester()
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x0A,0x00)  # LD 10
    w( 8, 0x10,0x00,0x01,0x00)  # SEL 1
    w(12, 0x11,0x00,0x00,0x00)  # LD 0
    w(16, 0x04,0x00,0x00,0x00)  # DIV
    w(20, 0xFF,0x00,0x00,0x00)  # HALT
    try:
        vm.run()
        print("  DIV_ZERO      (FAIL: no exception)")
    except MachineError as e:
        print(f"  DIV_ZERO      ({'PASS' if e.code == Err.DIV_ZERO else 'FAIL'})")

def test_slot_oob():
    vm, w = make_tester()
    w( 0, 0x10,0x00,0x10,0x00)  # SEL 16 (out of bounds)
    w( 4, 0xFF,0x00,0x00,0x00)  # HALT
    try:
        vm.run()
        print("  SLOT_OOB      (FAIL: no exception)")
    except MachineError as e:
        print(f"  SLOT_OOB      ({'PASS' if e.code == Err.SLOT_OOB else 'FAIL'})")

def test_stack_under():
    vm, w = make_tester()
    w( 0, 0x31,0x00,0x00,0x00)  # RET (empty return stack)
    w( 4, 0xFF,0x00,0x00,0x00)  # HALT
    try:
        vm.run()
        print("  STACK_UNDER   (FAIL: no exception)")
    except MachineError as e:
        print(f"  STACK_UNDER   ({'PASS' if e.code == Err.STACK_UNDER else 'FAIL'})")

def test_addr_align():
    vm, w = make_tester()
    w( 0, 0x10,0x00,0x05,0x00)  # SEL 5
    w( 4, 0x11,0x00,0x01,0x02)  # LD 0x0201 (odd address)
    w( 8, 0x20,0x00,0x00,0x00)  # JMP
    w(12, 0xFF,0x00,0x00,0x00)  # HALT
    try:
        vm.run()
        print("  ADDR_ALIGN    (FAIL: no exception)")
    except MachineError as e:
        print(f"  ADDR_ALIGN    ({'PASS' if e.code == Err.ADDR_ALIGN else 'FAIL'})")


# ── Flag Persistence & Edge Cases ─────────────────────────────────────────────

def test_flag_persistence():
    vm, w = make_tester()
    # CMP sets Z=1, then LD/SEL/JMP should NOT clobber flags
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x05,0x00)  # LD 5
    w( 8, 0x10,0x00,0x01,0x00)  # SEL 1
    w(12, 0x11,0x00,0x05,0x00)  # LD 5
    w(16, 0x0C,0x00,0x00,0x00)  # CMP → Z=1
    w(20, 0x10,0x00,0x04,0x00)  # SEL 4
    w(24, 0x11,0x00,0xFF,0x00)  # LD 0xFF
    w(28, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    z, n = vm._flag(VM.FZ), vm._flag(VM.FN)
    print(f"  Flag Persist  Z={z} N={n}  ({'PASS' if z and not n else 'FAIL'})")

def test_neg_0X8000():
    vm, w = make_tester()
    # -0x8000 wraps to 0x8000 in 16-bit two's complement
    w( 0, 0x10,0x00,0x00,0x00)  # SEL 0
    w( 4, 0x11,0x00,0x00,0x80)  # LD 0x8000
    w( 8, 0x09,0x00,0x00,0x00)  # NEG
    w(12, 0xFF,0x00,0x00,0x00)  # HALT
    vm.run()
    r, z, n = vm._sr(2), vm._flag(VM.FZ), vm._flag(VM.FN)
    print(f"  NEG 0x8000    R={r:#06x} Z={z} N={n}  ({'PASS' if r == 0x8000 and not z and n else 'FAIL'})")

# --- Entrypoint --------------------------------------------------------------------
if __name__ == "__main__":
    print("── ALU ──")
    test_add()
    test_add_zero()
    test_add_overflow()
    test_sub()
    test_sub_negative()
    test_mul()
    test_div()

    print("\n── Logic ──")
    test_and()
    test_or()
    test_xor()
    test_not()
    test_neg()

    print("\n── Shift ──")
    test_shift_left()
    test_shift_right()
    test_shift_flag_n()

    print("\n── Compare ──")
    test_cmp_eq()
    test_cmp_gt()
    test_cmp_lt()

    print("\n── Flow Control ──")
    test_jmp()
    test_call_ret()
    test_call_nested()

    print("\n── Conditionals ──")
    test_ifeq_skip()
    test_ifne_noskip()
    test_ifgt()
    test_iflt()
    test_ifeq_noskip()
    test_ifne_noskip()

    print("\n── Nested STASH/UNSTASH ──")
    test_stash_unstash_nested()

    print("\n── SCRATCH ──")
    test_scratch()

    print("\n── CHK Flags ──")
    test_chk_match()
    test_chk_partial()

    print("\n── Predictable errors ──")
    test_div_zero()
    test_slot_oob()
    test_stack_under()
    test_addr_align()
    test_flag_persistence()
    test_neg_0X8000()
