μ16, Pocket size 16-bit Virtual Machine
========================================

Key features:
- Flat 64KB memory array  
- Little-endian  
- No external registers  
- All state is memory-mapped  

Memory Map
----------
```
0x0000 - 0x0007    System        PC (2), SELECTOR (2), RSP (2), SCRATCH (2)
0x0008 - 0x0027    Slots 0–15    16 × 16-bit words (32 bytes)
0x0028 - 0x00FF    Return Stack  216 bytes (grows upward)
0x0100 - 0x017F    Reserved      128 bytes
0x0180 - 0x01FF    Scope Stack   SSP (2) + 126 bytes data (grows upward)
0x0200 - 0xFFFF    Program       Code + .byte data (65024 bytes)
```

System Region
-------------

All values stored little-endian.  
Word access requires 16-bit aligned addresses.

| Address | Size | Label    | Description              |
|---------|------|----------|--------------------------|
| 0x0000  | 2    | PC       | Program counter          |
| 0x0002  | 2    | SELECTOR | Slot selector (I)        |
| 0x0004  | 2    | RSP      | Return stack pointer     |
| 0x0006  | 2    | SCRATCH  | Unscoped word            |

Slots
-----

16 general-purpose 16-bit words at fixed addresses.  

Hard-wired slots:  

| Slot | Label  | Role                                      |
|------|--------|-------------------------------------------|
| 0    | A      | ALU, SHIFT / left operand                 |
| 1    | B      | ALU, SHIFT / right operand / shift params |
| 2    | R      | ALU / SHIFT / SCRATCH result              |
| 3    | REM    | DIV remainder                             |
| 4    |        | General purpose                           |
| 5    | JT     | JMP destination                           |
| 6-14 |        | General purpose                           |
| 15   | FLAGS  | Global flags (see below)                  |


Global Flags (Slot 15)
---------------
| Bit | Name | Set by            | Description              |
|-----|------|-------------------|--------------------------|
| 0   | Z    | ALU / CMP / CHK   | Zero                     |
| 1   | N    | ALU / CMP / CHK   | Negative (signed)        |
| 2   | RX   | Host              | Input data waiting       |
| 3   | TX   | Host              | Output channel ready     |
| 4   | ERR  | Host              | Device error             |
| 5-15|,    |,                 | Reserved                 |

**Z and N** are set by:  
ADD, SUB, MUL, DIV, AND, OR, XOR, NOT, NEG, SHF, CMP, CHK.  

**Z and N** are read by:  
IFEQ, IFNE, IFGT, IFLT.  

**RX, TX, ERR**  
Set by the host to signal I/O state changes.  
The VM reads them via the CHK instruction using mask constants.  


Slot Selection Model
--------------------
SEL and LD work together as a two-step load:
```
    SEL 5       ; point selector at slot 5
    LD  0x1234  ; write 0x1234 into slot 5
```
The selector (I) persists across instructions until the next SEL.  


Scope Stack (STASH / UNSTASH)
------------------------------
A LIFO stack for saving and restoring slot values across CALL boundaries.  
Lives at `0x0180–0x01FF` (SSP at `0x0180`, data grows upward from `0x0182`).
```
    STASH n     ; push slot[n] onto scope stack
    UNSTASH n   ; pop top of scope stack into slot[n]
```
The stack pointer (SSP) moves in 2-byte steps.  
No bounds checking, overflow silently corrupts program space at `0x0200`.  

**Calling Convention:**
- Caller STASH'es slots it wants to preserve, CALLs, then UNSTASH'es them after RET.
- Callee must balance its own STASH / UNSTASH pairs before RET.
- Callee must not UNSTASH values it did not STASH in the same frame.
- SSP must be at the same position on RET as it was on entry to the callee.


SCRATCH (0x0006)
----------------
A single 16-bit word outside the slot file. Immune to STASH / UNSTASH.  
Used for passing values across call frames.  
```
    RDS         ; R (slot 2) ← SCRATCH
    WRS         ; SCRATCH ← R (slot 2)
```
Any frame can read or write SCRATCH.  
Convention callee writes result to SCRATCH before RET, caller reads SCRATCH after CALL.  


Instruction Format
------------------
Fixed 32-bit, little-endian:

```
Byte 0    Byte 1    Byte 2–3
opcode    subset    param (16-bit LE)
```


Opcode Table
------------
| Opcode | Subset | Mnemonic | Operands        | Description                            |
|--------|--------|----------|-----------------|----------------------------------------|
| 0x00   |,      | NOP      |                 | No operation                           |
| 0x01   |,      | ADD      | A, B → R        | Addition                               |
| 0x02   |,      | SUB      | A, B → R        | Subtraction                            |
| 0x03   |,      | MUL      | A, B → R        | Multiplication (low 16 bits)           |
| 0x04   |,      | DIV      | A, B → R, REM   | Division (quotient→R, remainder→slot 3)|
| 0x05   |,      | AND      | A, B → R        | Bitwise AND                            |
| 0x06   |,      | OR       | A, B → R        | Bitwise OR                             |
| 0x07   |,      | XOR      | A, B → R        | Bitwise XOR                            |
| 0x08   |,      | NOT      | A → R           | Bitwise NOT                            |
| 0x09   |,      | NEG      | A → R           | Two's complement negation              |
| 0x0A   |,      | SHF      | A, B → R        | Shift (see Shift Control Word)         |
| 0x0C   | 0x00   | CMP      | A, B → FLAGS    | Compare (A − B), sets Z and N          |
| 0x0C   | 0x01   | CHK      | mask → Z        | Test flags: Z=1 if (FLAGS & mask) == mask |
| 0x10   |,      | SEL      | param → I       | Set slot selector to param             |
| 0x11   |,      | LD       | param → slot[I] | Load param into selected slot          |
| 0x12   |,      | STASH    | slot[n] → stack | Push slot[n] to scope stack            |
| 0x13   |,      | UNSTASH  | stack → slot[n] | Pop scope stack into slot[n]           |
| 0x14   |,      | RDS      | SCRATCH → R     | Read SCRATCH into slot 2               |
| 0x15   |,      | WRS      | R → SCRATCH     | Write slot 2 to SCRATCH                |
| 0x20   |,      | JMP      | JT → PC         | Jump to address in slot 5              |
| 0x21   |,      | IFEQ     |                 | Skip next if Z = 1                     |
| 0x22   |,      | IFNE     |                 | Skip next if Z = 0                     |
| 0x23   |,      | IFGT     |                 | Skip next if N=0 and Z=0 (signed >)    |
| 0x24   |,      | IFLT     |                 | Skip next if N = 1 (signed <)          |
| 0x30   |,      | CALL     |                 | Push PC, then JMP                      |
| 0x31   |,      | RET      |                 | Pop PC from return stack               |
| 0xFF   |,      | HALT     |                 | Stop execution                         |


CHK Instruction
---------------
Subset 0x01 of CMP (opcode 0x0C).  
Tests whether all bits specified by the mask are set in slot 15 (FLAGS).  
```
    CHK  mask    ; Z = 1 if (FLAGS & mask) == mask
```
The mask is a 16-bit immediate value carried in the param field.  

Example, polling for input:  
```
:rx_rdy    .byte 2 0x04, 0x00    ; mask for RX flag (bit 2)

.wait:
    CHK  rx_rdy                  ; test RX bit
    IFEQ / JMP .wait             ; loop until set
    ; read input...
```

Example, checking for any error:  
```
:err_flag  .byte 2 0x10, 0x00    ; mask for ERR flag (bit 4)

    CHK  err_flag
    IFNE / JMP .no_error         ; skip if ERR not set
    ; handle error...
```


Shift Control Word (Slot 1 for SHF)
------------------------------------
| Bits    | Field     | Description                       |
|---------|-----------|-----------------------------------|
| 0–3     | Amount    | Shift steps (0–15)                |
| 4       | Direction | 0 = left, 1 = right               |
| 5–15    |           | Reserved                          |
