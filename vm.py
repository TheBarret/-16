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
    RSP_ADDR     = 0x0004   # return stack pointer (2 bytes)
    SCRATCH_ADDR = 0x0006   # unscoped word (2 bytes)
    STASH_LIMIT  = 0x0200   # scope stack ceiling (shared)
    SLOT_BASE    = 0x0008   # slot[0]–slot[15]    (32 bytes)
    STACK_BASE   = 0x0028   # return stack        (grows up)
    STACK_LIMIT  = 0x0100   # return stack ceiling
    SSP_ADDR     = 0x0180   # scope stack pointer (2 bytes)
    STASH_BASE   = 0x0182   # scope stack data (126 bytes)
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
        # Allocate
        self.mem = [0] * self.MEM_SIZE
        #self.rsp = self.STACK_BASE
        self._w16(self.PC_ADDR, self.PROGRAM_BASE)
        self._w16(self.SELECTOR,  0)
        self._w16(self.RSP_ADDR,  self.STACK_BASE)
        self._w16(self.SCRATCH_ADDR, 0)
        self._w16(self.SSP_ADDR, self.STASH_BASE)
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

    # ── Scope Operations ──────────────────────────────────────────────────────────

    def _spush(self, v: int):
        ssp = self._r16(self.SSP_ADDR)
        # Has no bounds check,
        # silent overflow per retro spec
        # TODO!
        self._w16(ssp, v)
        self._w16(self.SSP_ADDR, ssp + 2)

    def _spop(self) -> int:
        ssp = self._r16(self.SSP_ADDR)
        self._w16(self.SSP_ADDR, ssp - 2)
        return self._r16(ssp - 2)

    # ── Call | Return Stack Operations ──────────────────────────────────────────────────────────

    def _rpush(self, v: int):
        rsp = self._r16(self.RSP_ADDR)
        if rsp >= self.STACK_LIMIT:
            raise MachineError(Err.STACK_OVER, "Return stack overflow")
        self._w16(rsp, v)
        self._w16(self.RSP_ADDR, rsp + 2)

    def _rpop(self) -> int:
        rsp = self._r16(self.RSP_ADDR)
        if rsp <= self.STACK_BASE:
            raise MachineError(Err.STACK_UNDER, "Return stack underflow")
        self._w16(self.RSP_ADDR, rsp - 2)
        return self._r16(rsp - 2)

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
    # STASH FEATURE
    # - Backup slotted data, stack based, 126 bytes, 63 words
    # - Scratch field is an unscoped word, 2 bytes

    # STASH <slot> — push slot[n] to scope stack
    def op_STASH(self, param):
        n = param & 0xF
        if n >= self.NUM_SLOTS:
            raise MachineError(Err.SLOT_OOB, f"STASH slot {n}")
        self._spush(self._sr(n))

    # UNSTASH <slot> — pop scope stack into slot[n]
    def op_UNSTASH(self, param):
        n = param & 0xF
        if n >= self.NUM_SLOTS:
            raise MachineError(Err.SLOT_OOB, f"UNSTASH slot {n}")
        self._sw(n, self._spop())

    # RDS — copy SCRATCH into R (slot 2)
    def op_RDS(self):
        self._sw(2, self._r16(self.SCRATCH_ADDR))

    # WRS — copy R (slot 2) into SCRATCH
    def op_WRS(self):
        self._w16(self.SCRATCH_ADDR, self._sr(2))

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
            # ALU
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
            # Comparator
            case 0x0C: self.op_CMP()
            # Movement
            case 0x10: self.op_SEL(param)
            case 0x11: self.op_LD(param)
            # STASH Feature
            case 0x12: self.op_STASH(param)
            case 0x13: self.op_UNSTASH(param)
            case 0x14: self.op_RDS()
            case 0x15: self.op_WRS()
            # Jump
            case 0x20: self.op_JMP()
            # Skip
            case 0x21: self.op_IFEQ()
            case 0x22: self.op_IFNE()
            case 0x23: self.op_IFGT()
            case 0x24: self.op_IFLT()
            # Call/Ret
            case 0x30: self.op_CALL()
            case 0x31: self.op_RET()
            # Exit
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
        #print(f"  PC={hex(self._r16(self.PC_ADDR))}  I={self._r16(self.SELECTOR)}  RSP={hex(self._r16(self.RSP_ADDR))}")
        print(f"  PC={hex(self._r16(self.PC_ADDR))}  I={self._r16(self.SELECTOR)}  RSP={hex(self._r16(self.RSP_ADDR))}  SSP={hex(self._r16(self.SSP_ADDR))}  SCRATCH={self._r16(self.SCRATCH_ADDR):#06x}")
        for n in range(self.NUM_SLOTS):
            v   = self._sr(n)
            tag = f"[{labels[n]}]" if n in labels else ""
            print(f"  slot[{n:02d}] {tag:<7} = {v:#06x}  ({v})")
