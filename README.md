μ16, Pocket-size 16-bit Virtual Machine
========================================

Key features:
- Flat 64KB memory array, little-endian  
- No external registers; all state is memory-mapped  
- 16-slot register file with persistent `SELECTOR`-based writes
- Dual upward-growing stacks (return + scope) with `SCRATCH` cross-frame convention
- Fixed 32-bit instruction encoding (opcode, subset, param)
- Descriptor table gateway for typed/structured memory regions
- `R` (slot 2) as computational fixed point; `B` (slot 1) as polymorphic operand/control
- Host-driven I/O flags polled via `CHK` + conditional skips

Memory Map
----------
```
0x0000 - 0x0007    System          PC (2), SELECTOR (2), RSP (2), SCRATCH (2)
0x0008 - 0x0027    Slots 0–15      16 × 16-bit words (32 bytes)
0x0028 - 0x00FF    Return Stack    216 bytes (grows upward)
0x0100 - 0x017F    Descriptor Table 64 × 16-bit pointers (128 bytes)
0x0180 - 0x01FF    Scope Stack     SSP (2) + 126 bytes data (grows upward)
0x0200 - 0xFFFF    Program         Code + inline .byte data (65024 bytes)
```

<img width="1408" height="768" src="https://github.com/user-attachments/assets/196d4c22-d444-40a9-ba51-3df642bc332e" />

System Region
-------------
All values stored little-endian.  
Word access requires 16-bit aligned addresses.

| Address | Size | Label    | Description              |
|---------|------|----------|--------------------------|
| 0x0000  | 2    | PC       | Program counter          |
| 0x0002  | 2    | SELECTOR | Slot selector (I)        |
| 0x0004  | 2    | RSP      | Return stack pointer     |
| 0x0006  | 2    | SCRATCH  | Unscoped cross-frame word|

Slots
-----
16 general-purpose 16-bit words at fixed addresses.  

Hard-wired roles:

| Slot | Label  | Role                                                         |
|------|--------|--------------------------------------------------------------|
| 0    | A      | ALU left operand / Descriptor byte offset                    |
| 1    | B      | ALU right operand **or** SHF control word (polymorphic)      |
| 2    | R      | ALU result / SHF operand / LDB/LDW dest / STB/STW src        |
| 3    | REM    | DIV remainder                                                |
| 4    |        | General purpose                                              |
| 5    | JT     | JMP / CALL destination address                               |
| 6-14 |        | General purpose                                              |
| 15   | FLAGS  | Global flags (see below)                                     |

Global Flags (Slot 15)
----------------------
| Bit | Name | Set by            | Description              |
|-----|------|-------------------|--------------------------|
| 0   | Z    | ALU / CMP / CHK / SHF | Zero                 |
| 1   | N    | ALU / CMP / CHK / SHF | Negative (signed)    |
| 2   | RX   | Host              | Input data waiting       |
| 3   | TX   | Host              | Output channel ready     |
| 4   | ERR  | Host              | Device error             |
| 5-15|      |                   | Reserved                 |

**Z and N** are set by:  
`ADD, SUB, MUL, DIV, AND, OR, XOR, NOT, NEG, SHF, CMP, CHK`  
*(Descriptor I/O ops do not modify flags.)*

**Z and N** are read by:  
`IFEQ, IFNE, IFGT, IFLT`

**RX, TX, ERR**  
Set by the host to signal I/O state changes.  
The VM reads them via `CHK` using bitmask immediates.

Slot Selection Model
--------------------
`SEL` and `LD` work together as a two-step immediate load:
```asm
    SEL 5       ; point selector at slot 5
    LD  0x1234  ; write 0x1234 into slot 5
```
The selector (`I`) persists across instructions until the next `SEL`.

Descriptor Table & Memory I/O
-----------------------------
A 64-entry pointer table at `0x0100–0x017F` that gates access to structured memory regions (buffers, lookup tables, sprite sheets, I/O rings, etc.).

- Each entry is a 16-bit LE address. `0x0000` = unused/null (traps on access).
- `A` (slot 0) acts as the **byte offset** into the targeted region.
- `R` (slot 2) is the **value register** for loads/stores.
- The `subset` byte controls automatic offset modification:

| Subset | Mode         | Behavior                              |
|--------|--------------|---------------------------------------|
| 0x00   | None         | Offset unchanged                      |
| 0x01   | Post-increment | `A ← A + step` after access         |
| 0x02   | Post-decrement | `A ← A - step` after access         |
| 0x03   | Pre-increment  | `A ← A + step` before access        |

*Step = 1 for byte ops, 2 for word ops. Word ops trap on unaligned effective addresses.*

Example: streaming bytes from a descriptor buffer
```asm
    SEL 0          ; A = offset register
    LD  0x0000     ; start at offset 0
    SEL 2          ; R = value register
.loop:
    LDB 0x01, 5    ; load byte from desc[5], post-inc A by 1
    ; ... process R ...
    CMP A, LIMIT   ; check bounds
    IFLT / JMP .loop
```

Scope Stack (STASH / UNSTASH)
------------------------------
A LIFO stack for saving/restoring slot values across `CALL` boundaries.  
Lives at `0x0180–0x01FF` (`SSP` at `0x0180`, data grows upward from `0x0182`).
```asm
    STASH n     ; push slot[n] onto scope stack
    UNSTASH n   ; pop top of scope stack into slot[n]
```
`SSP` moves in 2-byte steps. No bounds checking; overflow silently corrupts program space at `0x0200` (by design for bare-metal/embedded use).

**Calling Convention:**
- Caller `STASH`es slots it wants to preserve, `CALL`s, then `UNSTASH`es after `RET`.
- Callee must balance its own `STASH/UNSTASH` pairs before `RET`.
- Callee must not `UNSTASH` values it did not `STASH` in the same frame.
- `SSP` must return to its entry position on `RET`.

SCRATCH (0x0006)
----------------
A single 16-bit word outside the slot file. Immune to `STASH/UNSTASH`.  
Used for passing values across call frames.
```asm
    RDS         ; R (slot 2) ← SCRATCH
    WRS         ; SCRATCH ← R (slot 2)
```
Any frame can read/write `SCRATCH`.  
Convention: callee writes result to `SCRATCH` before `RET`; caller reads after `CALL`.

Instruction Format
------------------
Fixed 32-bit, little-endian:
```
Byte 0    Byte 1    Byte 2–3
opcode    subset    param (16-bit LE)
```

Opcode Table
------------
| Opcode | Subset | Mnemonic | Operands / Routing              | Description                                  |
|--------|--------|----------|---------------------------------|----------------------------------------------|
| 0x00   |        | NOP      |                                 | No operation                                 |
| 0x01   |        | ADD      | A, B → R                        | Addition                                     |
| 0x02   |        | SUB      | A, B → R                        | Subtraction                                  |
| 0x03   |        | MUL      | A, B → R                        | Multiplication (low 16 bits)                 |
| 0x04   |        | DIV      | A, B → R, REM                   | Division (quotient→R, remainder→slot 3)      |
| 0x05   |        | AND      | A, B → R                        | Bitwise AND                                  |
| 0x06   |        | OR       | A, B → R                        | Bitwise OR                                   |
| 0x07   |        | XOR      | A, B → R                        | Bitwise XOR                                  |
| 0x08   |        | NOT      | A → R                           | Bitwise NOT                                  |
| 0x09   |        | NEG      | A → R                           | Two's complement negation                    |
| 0x0A   |        | SHF      | R, B → R                        | Shift R by control word in B                 |
| 0x0C   | 0x00   | CMP      | A, B → FLAGS                    | Compare (A − B), sets Z and N                |
| 0x0C   | 0x01   | CHK      | mask → Z                        | Test flags: Z=1 if (FLAGS & mask) == mask    |
| 0x10   |        | SEL      | param → I                       | Set slot selector                            |
| 0x11   |        | LD       | param → slot[I]                 | Load immediate into selected slot            |
| 0x12   |        | STASH    | slot[n] → stack                 | Push slot to scope stack                     |
| 0x13   |        | UNSTASH  | stack → slot[n]                 | Pop scope stack into slot                    |
| 0x14   |        | RDS      | SCRATCH → R                     | Read scratch into R                          |
| 0x15   |        | WRS      | R → SCRATCH                     | Write R to scratch                           |
| 0x20   |        | JMP      | JT → PC                         | Jump to address in slot 5                    |
| 0x21   |        | IFEQ     |                                 | Skip next if Z = 1                           |
| 0x22   |        | IFNE     |                                 | Skip next if Z = 0                           |
| 0x23   |        | IFGT     |                                 | Skip next if N=0 and Z=0 (signed >)          |
| 0x24   |        | IFLT     |                                 | Skip next if N = 1 (signed <)                |
| 0x30   |        | CALL     |                                 | Push PC, then JMP                            |
| 0x31   |        | RET      |                                 | Pop PC from return stack                     |
| 0x40   | 0x00-03| LDB      | desc[n], A→offset, R←val        | Load byte (zero-extended)                    |
| 0x41   | 0x00-03| LDW      | desc[n], A→offset, R←val        | Load word (aligned)                          |
| 0x42   | 0x00-03| STB      | desc[n], A→offset, R→val        | Store byte                                   |
| 0x43   | 0x00-03| STW      | desc[n], A→offset, R→val        | Store word (aligned)                         |
| 0xFF   |        | HALT     |                                 | Stop execution                               |

Descriptor Table [0x0100 - 0x017F]
------------------------------------

**Key features**
- Capacity: 64 entries
- Pointer: 2 bytes each
- State: `0x0000` means unused
- Read logic: word at `0x0100 + n*2`

**Descriptor Mapping**
```asm
0x0100    desc[0].addr_lo
0x0101    desc[0].addr_hi
0x0102    desc[1].addr_lo
0x0103    desc[1].addr_hi
  ...
0x017E    desc[63].addr_lo
0x017F    desc[63].addr_hi
```

**Format**
```asm
.byte  <n> <values>    ;→ explicit data, n bytes filled
.byte? <n>             ;→ empty buffer, n bytes zeroed
```

**Examples**
```asm
:stdin_buf  .byte? 64       ; stdio read buffer
:stdout_buf .byte? 64       ; stdio write buffer
:work_area  .byte? 256      ; general purpose
```

CHK Instruction
---------------
Subset `0x01` of `CMP` (opcode `0x0C`).  
Tests whether all bits specified by the mask are set in slot 15 (`FLAGS`).
```asm
    CHK  mask    ; Z = 1 if (FLAGS & mask) == mask
```
The mask is a 16-bit immediate in the param field.

Polling example:
```asm
:rx_mask  .byte 2 0x04, 0x00    ; RX flag (bit 2)

.wait:
    CHK  rx_mask
    IFEQ / JMP .wait            ; loop until RX set
    ; read input...
```

Shift Control Word
------------------
`SHF` reads its **operand from `R` (slot 2)** and its **control word from `B` (slot 1)**.  
This enables direct `ALU → SHF` chaining without slot shuffling.

Control word layout (slot 1):
| Bits | Field     | Description                       |
|------|-----------|-----------------------------------|
| 0–3  | Amount    | Shift steps (0–15)                |
| 4    | Direction | 0 = left, 1 = right               |
| 5–15 |           | Ignored (masked internally)       |

```asm
:ctrl  .byte 2 0x03, 0x00   ; left shift by 3

    ADD          ; R = A + B
    SEL 1        ; target B
    LD  ctrl     ; load control word
    SHF          ; R = R << 3 (direct chain)
```
*Note: If `B` is not reloaded between ALU and SHF, the lower bits of the ALU operand become the shift amount. This enables compact data-dependent transforms (common in ARX ciphers & DSP scaling).*

Architectural Model
-------------------
μ16 is a **parameterized state machine** with a single computational throughput node:

```
δ : State × Instr → State
State = (PC, I, RSP, SSP, SCR, S[0..15], F[Z,N], M[0..65535])
```

- **`R` (slot 2)** is the fixed point: all ALU results, shift outputs, descriptor loads, and scratch reads converge here.
- **`B` (slot 1)** is polymorphic: full 16-bit math operand for ALU, 5-bit control word for SHF.
- **`FLAGS`** are the only branching observables. `Z/N` derive from `R`; `RX/TX/ERR` are host-injected.
- **Descriptor Table** gates untyped `.byte` regions. Type semantics live at the assembler/host layer.
- **Hot path**: `A,B → ALU → R → SHF → R → FLAGS → branch`. Stacks, scratch, and descriptors orbit this core.

Compact notation:
> **μ16** = `δ(PC, I, S, F, M | opc, sub, param)`  
> where `δ` routes `(S[0], S[1], S[2])` through opcode-selected transforms, updates `F[Z,N]` from `S[2]`, and advances `PC ← PC+4`.  
> `S[1]` is polymorphic, `S[2]` is the computational fixed point, and branching observes only `F[Z,N]`.
