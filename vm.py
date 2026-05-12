from enum import Enum, auto

"""
    μ16, Minimal 16-bit Virtual Machine

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

    # ── Descriptor Table Operations ─────────────────────────────────────────────────────────────────
    # - Capacity: 64 entries
    # - Pointer: 2 bytes each
    # - State: 0x0000 means unused
    # - Read logic: word at 0x0100 + n*2

    # Descriptors:
    # 0x0100    desc[0].addr_lo
    # 0x0101    desc[0].addr_hi
    # 0x0102    desc[1].addr_lo
    # 0x0103    desc[1].addr_hi
    # ...
    # 0x017E    desc[63].addr_lo
    # 0x017F    desc[63].addr_hi

    # Descriptor symbols:
    # .byte  <n> <values...>    → explicit data, n bytes filled
    # .byte? <n>                → empty buffer, n bytes zeroed

    # Capacitance
    # Empty containers for I/O buffers work the same way:
    # :stdin_buf  .byte? 64       ; stdio read buffer
    # :stdout_buf .byte? 64       ; stdio write buffer
    # :work_area  .byte? 256      ; general purpose

    # Descriptor Address Lookup
    def _desc_addr(self, n: int) -> int:
        """Return the absolute address stored in descriptor n.
        Traps if index out of range or descriptor is 0x0000 (unused)."""
        if n < 0 or n >= 64:
            raise MachineError(Err.SLOT_OOB, f"Descriptor {n} out of range")
        addr = self._r16(0x0100 + n * 2)
        if addr == 0:
            raise MachineError(Err.ADDR_OOB, f"Descriptor {n} is null")
        return addr


    # Each takes a descriptor index n (0–63) and uses slot 0 (A) as the byte offset into that container.
    # Slot 2 (R) is the value, the subset byte controls offset modification.
    # The VM._chk guard in LDW/STW will trap on unaligned addresses (addr % 2 != 0).
    # That's correct behavior, word access requires alignment.
    # But it means if you LDW at offset 1, it'll fault,
    # it needs to be word accesses aligned at assembler time.

    def op_LDB(self, subset, n):
        if subset == 0x03:  # pre-increment
            self._sw(0, (self._sr(0) + 1) & 0xFFFF)
        addr = self._desc_addr(n) + self._sr(0)
        self._sw(2, self._r8(addr))          # zero-extended byte → R
        self._sset_omod(subset, 0, 1)        # post-inc/dec

    def op_LDW(self, subset, n):
        if subset == 0x03:
            self._sw(0, (self._sr(0) + 2) & 0xFFFF)
        addr = self._desc_addr(n) + self._sr(0)
        self._chk(addr, 2)                   # alignment guard
        self._sw(2, self._r16(addr))
        self._sset_omod(subset, 0, 2)

    def op_STB(self, subset, n):
        if subset == 0x03:
            self._sw(0, (self._sr(0) + 1) & 0xFFFF)
        addr = self._desc_addr(n) + self._sr(0)
        self._w8(addr, self._sr(2) & 0xFF)
        self._sset_omod(subset, 0, 1)

    def op_STW(self, subset, n):
        if subset == 0x03:
            self._sw(0, (self._sr(0) + 2) & 0xFFFF)
        addr = self._desc_addr(n) + self._sr(0)
        self._chk(addr, 2)
        self._w16(addr, self._sr(2))
        self._sset_omod(subset, 0, 2)

    # Subset Offset Modes
    def _sset_omod(self, subset, slot_n, step):
        """Apply post-increment or post-decrement to slot_n.
        subset 0x00: no change
        subset 0x01: post-increment by step
        subset 0x02: post-decrement by step
        subset 0x03: already handled as pre-increment by caller"""
        if subset == 0x01:
            self._sw(slot_n, (self._sr(slot_n) + step) & 0xFFFF)
        elif subset == 0x02:
            self._sw(slot_n, (self._sr(slot_n) - step) & 0xFFFF)
        # Note: 0x00, 0x03: no operation, or derrived

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
        # TODO: do bounds check here!
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

    # ALU Primitive Operations -----------------------------------------------------------
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

    # ALU Logic Operations -----------------------------------------------------------
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

    # Bit Shifting Operations -----------------------------------------------------------
    # Control:
    #  Slot      : 2 (R)
    #  bits 0-3  : shift amount (0-15)
    #  bit  4    : direction (0=left, 1=right)
    #  bits 5-15 : unused (return mask planned)

    def op_SHF(self):
        a = self._sr(2)              # READ R
        control = self._sr(1)        # READ CTL BITS
        amount = control & 0xF       # nibble step value
        right = (control >> 4) & 0x1 # nibble direction value

        if amount == 0:
            r = a
        elif right:
            r = a >> amount
        else:
            r = (a << amount) & 0xFFFF

        self._sw(2, r)
        self._flags(r)

    # Stack Scope | Scratch Operations -----------------------------------------------------------
    # Leverage:
    # - Backup slotted data, stack based, 126 bytes, 63 words
    # - Scratch field is an unscoped word, 2 bytes
    # - Must be correctly unwind in paired cycles

    # STASH <slot>, push slot[n] to scope stack
    def op_STASH(self, param):
        n = param & 0xF
        if n >= self.NUM_SLOTS:
            raise MachineError(Err.SLOT_OOB, f"STASH slot {n}")
        self._spush(self._sr(n))

    # UNSTASH <slot>, pop scope stack into slot[n]
    def op_UNSTASH(self, param):
        n = param & 0xF
        if n >= self.NUM_SLOTS:
            raise MachineError(Err.SLOT_OOB, f"UNSTASH slot {n}")
        self._sw(n, self._spop())

    # RDS, copy SCRATCH into R (slot 2)
    def op_RDS(self):
        self._sw(2, self._r16(self.SCRATCH_ADDR))

    # WRS, copy R (slot 2) into SCRATCH
    def op_WRS(self):
        self._w16(self.SCRATCH_ADDR, self._sr(2))

    # -----------------------------------------------------------

    def op_JMP(self):
        addr = self._sr(self.JT)
        self._chk(addr, 2)
        self._w16(self.PC_ADDR, addr)

    # -----------------------------------------------------------
    # Compare operations

    def op_CMP(self, subset, param):
        if subset == 0x00:
            # CMP: OPERANDS -> FLAGS
            self._flags((self._sr(0) - self._sr(1)) & 0xFFFF)
        elif subset == 0x01:
            # CHK <MASK>: MASK -> FLAGS -> Z
            flags = self._sr(self.FLAG_SLOT)
            match = (flags & param) == param
            self._setf(self.FZ, match)
            self._setf(self.FN, False)

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

    def fetch(self) -> tuple[int, int, int]:
        pc = self._r16(self.PC_ADDR)
        if pc % 2 != 0:
            raise MachineError(Err.ADDR_ALIGN, f"PC {hex(pc)} not aligned")
        opcode = self._r8(pc)
        subset = self._r8(pc + 1)
        param  = self._r16(pc + 2)
        self._w16(self.PC_ADDR, pc + 4)
        return opcode, subset, param

    def step(self) -> bool:
        opcode, subset, param = self.fetch()
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
            # Comparator
            case 0x0C: self.op_CMP(subset, param)   # passes subset + mask
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
            # Descriptor Memory Operations
            case 0x40: self.op_LDB(subset, param)
            case 0x41: self.op_LDW(subset, param)
            case 0x42: self.op_STB(subset, param)
            case 0x43: self.op_STW(subset, param)
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
        print(f"  PC={hex(self._r16(self.PC_ADDR))}  I={self._r16(self.SELECTOR)}  RSP={hex(self._r16(self.RSP_ADDR))}  SSP={hex(self._r16(self.SSP_ADDR))}  SCRATCH={self._r16(self.SCRATCH_ADDR):#06x}")
        for n in range(self.NUM_SLOTS):
            v   = self._sr(n)
            tag = f"[{labels[n]}]" if n in labels else ""
            print(f"  slot[{n:02d}] {tag:<7} = {v:#06x}  ({v})")
        print(80 * "*")
