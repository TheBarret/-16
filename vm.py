from enum import Enum, auto

"""
    μ16 — Minimal 16-bit Virtual Machine

"""


# ── Errors ────────────────────────────────────────────────────────────────────

class Err(Enum):
    OPCODE_OOB  = auto()
    ADDR_OOB    = auto()
    ADDR_ALIGN  = auto()
    SLOT_OOB    = auto()
    DIV_ZERO    = auto()
    STACK_OVER  = auto()
    STACK_UNDER = auto()


class MachineError(Exception):
    def __init__(self, code: Err, msg: str):
        self.code = code
        super().__init__(msg)


# ── VM ────────────────────────────────────────────────────────────────────────

class VM:

    # Memory map
    PC_ADDR      = 0x0000   # program counter     (2 bytes)
    SELECTOR     = 0x0002   # slot selector       (2 bytes)
    SLOT_BASE    = 0x0008   # slot[0]–slot[15]    (32 bytes)
    STACK_BASE   = 0x0028   # return stack        (grows up)
    STACK_LIMIT  = 0x0100   # return stack ceiling
    PROGRAM_BASE = 0x0200
    MEM_SIZE     = 65536

    NUM_SLOTS = 16
    FLAG_SLOT = 15   # Z and N live here

    # Hard Wired slots
    A  = 0   # ALU operand A
    B  = 1   # ALU operand B
    R  = 2   # ALU result
    JT = 5   # jump target

    # Flag bits in slot[15]
    FZ = 0   # Zero
    FN = 1   # Negative

    def __init__(self):
        self.mem = [0] * self.MEM_SIZE
        self.rsp = self.STACK_BASE
        self._w16(self.PC_ADDR, self.PROGRAM_BASE)
        self._w16(self.SELECTOR,  0)
        for n in range(self.NUM_SLOTS):
            self._sw(n, 0)

    # ── Memory Operations ────────────────────────────────────────────────────────────────

    def _r8(self, addr: int) -> int:
        self._chk(addr, 1)
        return self.mem[addr]

    def _r16(self, addr: int) -> int:
        self._chk(addr, 2)
        return (self.mem[addr + 1] << 8) | self.mem[addr]

    def _w8(self, addr: int, v: int):
        self._chk(addr, 1)
        self.mem[addr] = v & 0xFF

    def _w16(self, addr: int, v: int):
        self._chk(addr, 2)
        self.mem[addr]     = v & 0xFF
        self.mem[addr + 1] = (v >> 8) & 0xFF

    # ── Slot Operations ─────────────────────────────────────────────────────────────────

    def _sa(self, n: int) -> int:
        if not (0 <= n < self.NUM_SLOTS):
            raise MachineError(Err.SLOT_OOB, f"Slot {n} out of range")
        return self.SLOT_BASE + n * 2

    def _sr(self, n: int) -> int:        return self._r16(self._sa(n))
    def _sw(self, n: int, v: int):       self._w16(self._sa(n), v & 0xFFFF)

    # ── Flag Operations ─────────────────────────────────────────────────────────────────

    def _flag(self, bit: int) -> bool:
        return bool((self._sr(self.FLAG_SLOT) >> bit) & 1)

    def _setf(self, bit: int, cond: bool):
        f = self._sr(self.FLAG_SLOT)
        self._sw(self.FLAG_SLOT, (f | (1 << bit)) if cond else (f & ~(1 << bit)))

    def _flags(self, result: int):
        r = result & 0xFFFF
        self._setf(self.FZ, r == 0)
        self._setf(self.FN, bool(r & 0x8000))

    # ── Call | Return Stack Operations ──────────────────────────────────────────────────────────

    def _rpush(self, v: int):
        if self.rsp >= self.STACK_LIMIT:
            raise MachineError(Err.STACK_OVER, "Return stack overflow")
        self._w16(self.rsp, v)
        self.rsp += 2

    def _rpop(self) -> int:
        if self.rsp <= self.STACK_BASE:
            raise MachineError(Err.STACK_UNDER, "Return stack underflow")
        self.rsp -= 2
        return self._r16(self.rsp)

    # ── Opcodes Operations ───────────────────────────────────────────────────────────────

    def op_SEL(self, param):
        n = param & 0xFFFF
        if n >= self.NUM_SLOTS:
            raise MachineError(Err.SLOT_OOB, f"SEL {n} out of range")
        self._w16(self.SELECTOR, n)

    def op_LD(self, param):
        self._sw(self._r16(self.SELECTOR), param & 0xFFFF)

    # -----------------------------------------------------------
    def op_ADD(self):
        a, b = self._sr(0), self._sr(1)
        r = (a + b) & 0xFFFF;  self._sw(2, r);  self._flags(r)

    def op_SUB(self):
        a, b = self._sr(0), self._sr(1)
        r = (a - b) & 0xFFFF;  self._sw(2, r);  self._flags(r)

    def op_MUL(self):
        a, b = self._sr(0), self._sr(1)
        r = (a * b) & 0xFFFF;  self._sw(2, r);  self._flags(r)

    def op_DIV(self):
        a, b = self._sr(0), self._sr(1)
        if b == 0:
            raise MachineError(Err.DIV_ZERO, "Division by zero")
        self._sw(2, (a // b) & 0xFFFF)   # quotient
        self._sw(3, (a %  b) & 0xFFFF)   # remainder → slot[3]
        self._flags((a // b) & 0xFFFF)

    # -----------------------------------------------------------
    def op_AND(self):
        r = self._sr(0) & self._sr(1);  self._sw(2, r);  self._flags(r)

    def op_OR(self):
        r = self._sr(0) | self._sr(1);  self._sw(2, r);  self._flags(r)

    def op_XOR(self):
        r = self._sr(0) ^ self._sr(1);  self._sw(2, r);  self._flags(r)

    def op_NOT(self):
        r = (~self._sr(0)) & 0xFFFF;    self._sw(2, r);  self._flags(r)

    def op_NEG(self):
        r = (-self._sr(0)) & 0xFFFF;    self._sw(2, r);  self._flags(r)

    # -----------------------------------------------------------
    # Shift Controller:
    #  Slot      : 1
    #  bits 0-3  : shift amount (0-15)
    #  bit  4    : direction (0=left, 1=right)
    #  bits 5-15 : unused (return mask planned)

    def op_SHF(self):
        a = self._sr(0)
        control = self._sr(1)
        amount = control & 0xF
        right = (control >> 4) & 0x1


        if amount == 0:
            r = a
        elif right:
            r = a >> amount
        else:
            r = (a << amount) & 0xFFFF

        self._sw(2, r)
        self._flags(r)

    # -----------------------------------------------------------

    def op_JMP(self):
        addr = self._sr(self.JT)
        self._chk(addr, 2)
        self._w16(self.PC_ADDR, addr)

    # -----------------------------------------------------------

    def op_CMP(self):
        """Compare slot[0] − slot[1], update flags, discard result."""
        self._flags((self._sr(0) - self._sr(1)) & 0xFFFF)

    def _skip(self):
        """Advance PC by one instruction (skip next 4 bytes)."""
        self._w16(self.PC_ADDR, self._r16(self.PC_ADDR) + 4)

    def op_IFEQ(self):
        if self._flag(self.FZ):
            self._skip()

    def op_IFNE(self):
        if not self._flag(self.FZ):
            self._skip()

    def op_IFGT(self):
        if not self._flag(self.FN) and not self._flag(self.FZ):
            self._skip()

    def op_IFLT(self):
        if self._flag(self.FN):
            self._skip()

    # -----------------------------------------------------------
    def op_CALL(self):
        self._rpush(self._r16(self.PC_ADDR))
        self.op_JMP()

    def op_RET(self):
        self._w16(self.PC_ADDR, self._rpop())

    # -----------------------------------------------------------

    def op_HALT(self) -> bool:
        return False

    # ── Fetch / Execute ───────────────────────────────────────────────────────

    def fetch(self) -> tuple[int, int]:
        pc = self._r16(self.PC_ADDR)
        if pc % 2 != 0:
            raise MachineError(Err.ADDR_ALIGN, f"PC {hex(pc)} not aligned")
        opcode = self._r8(pc)
        param  = self._r16(pc + 2)
        self._w16(self.PC_ADDR, pc + 4)
        return opcode, param

    def step(self) -> bool:
        opcode, param = self.fetch()
        match opcode:
            case 0x00: pass                    # NOP
            case 0x01: self.op_ADD()
            case 0x02: self.op_SUB()
            case 0x03: self.op_MUL()
            case 0x04: self.op_DIV()
            case 0x05: self.op_AND()
            case 0x06: self.op_OR()
            case 0x07: self.op_XOR()
            case 0x08: self.op_NOT()
            case 0x09: self.op_NEG()
            case 0x0A: self.op_SHF()
            #case 0x0B: unused
            case 0x0C: self.op_CMP()
            case 0x10: self.op_SEL(param)
            case 0x11: self.op_LD(param)
            case 0x20: self.op_JMP()
            case 0x21: self.op_IFEQ()
            case 0x22: self.op_IFNE()
            case 0x23: self.op_IFGT()
            case 0x24: self.op_IFLT()
            case 0x30: self.op_CALL()
            case 0x31: self.op_RET()
            case 0xFF: return self.op_HALT()
            case _:
                raise MachineError(Err.OPCODE_OOB, f"Unknown opcode: {hex(opcode)}")
        return True

    def run(self):
        while self.step():
            pass

    # ── Guards ────────────────────────────────────────────────────────────────

    def _chk(self, addr: int, size: int):
        if addr < 0 or addr + size > self.MEM_SIZE:
            raise MachineError(Err.ADDR_OOB, f"Address {hex(addr)} out of bounds")
        if size == 2 and addr % 2 != 0:
            raise MachineError(Err.ADDR_ALIGN, f"Address {hex(addr)} not aligned")

    # ── Debug ─────────────────────────────────────────────────────────────────

    def dump(self):
        labels = {0:"A", 1:"B", 2:"R", 3:"REM", 5:"JT", 15:"FLAGS"}
        print(f"  PC={hex(self._r16(self.PC_ADDR))}  I={self._r16(self.SELECTOR)}  RSP={hex(self.rsp)}")
        for n in range(self.NUM_SLOTS):
            v   = self._sr(n)
            tag = f"[{labels[n]}]" if n in labels else ""
            print(f"  slot[{n:02d}] {tag:<7} = {v:#06x}  ({v})")

# ── Smoke testers ────────────────────────────────────────────────────────────────

def make_tester():
    """Create a fresh VM and a w() helper bound to it."""
    vm = VM()
    def w(offset, *bytes_):
        for i, b in enumerate(bytes_):
            vm.mem[VM.PROGRAM_BASE + offset + i] = b
    return vm, w


def test_division():
    vm, w = make_tester()

    # Goal: 10 / 3 → slot[2]=3, slot[3]=1
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00,0x0A,0x00)   # LD  10
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00,0x03,0x00)   # LD  3
    w(16,  0x04,0x00,0x00,0x00)   # DIV
    w(20,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    q, r = vm._sr(2), vm._sr(3)
    print(f"operation: 10 / 3 = {q} rem {r}  ({'PASS' if q == 3 and r == 1 else 'FAIL'})")


def test_shift_left():
    vm, w = make_tester()

    # 0x0005 << 3 = 0x0028
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00,0x05,0x00)   # LD  0x0005
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00,0x03,0x00)   # LD  0x0003  (amount=3, dir=0 → left)
    w(16,  0x0A,0x00,0x00,0x00)   # SHF
    w(20,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    result = vm._sr(2)
    print(f"operation: 0x0005 << 3 = {result:#06x}  ({'PASS' if result == 0x0028 else 'FAIL'})")


def test_shift_right():
    vm, w = make_tester()

    # 0x00F0 >> 4 = 0x000F
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00,0xF0,0x00)   # LD  0x00F0
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00,0x14,0x00)   # LD  0x0014  (amount=4, dir=1 → right)
    w(16,  0x0A,0x00,0x00,0x00)   # SHF
    w(20,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    result = vm._sr(2)
    print(f"operation: 0x00F0 >> 4 = {result:#06x}  ({'PASS' if result == 0x000F else 'FAIL'})")


def test_shift_flag():
    vm, w = make_tester()

    # 0x8000 >> 1 = 0x4000, N flag should be clear
    w( 0,  0x10,0x00,0x00,0x00)   # SEL 0
    w( 4,  0x11,0x00,0x00,0x80)   # LD  0x8000
    w( 8,  0x10,0x00,0x01,0x00)   # SEL 1
    w(12,  0x11,0x00,0x11,0x00)   # LD  0x0011  (amount=1, dir=1 → right)
    w(16,  0x0A,0x00,0x00,0x00)   # SHF
    w(20,  0xFF,0x00,0x00,0x00)   # HALT
    vm.run()
    result = vm._sr(2)
    neg = vm._flag(VM.FN)
    print(f"operation: 0x8000 >> 1 = {result:#06x}  N={neg}  ({'PASS' if result == 0x4000 and not neg else 'FAIL'})")


# --- Entrypoint --------------------------------------------------------------------
if __name__ == "__main__":
    test_division()
    test_shift_left()
    test_shift_right()
    test_shift_flag()
