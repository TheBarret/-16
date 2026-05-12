# μ16: A Pocket-Sized 16-Bit Virtual Machine

μ16 is a **minimalist, memory-mapped 16-bit virtual machine** designed for experimentation.  
A low-level computing concepts in a constrained, self-contained environment.  

---

## **Core Philosophy**

μ16 is built around a few key ideas:

- **Flat, unified memory**: All state (registers, stacks, flags) lives in a single 64KB little-endian address space.
- **Memory-mapped everything**: No external registers; even the program counter and stack pointers are just memory locations.
- **Fixed-point computation**: Slot 2 (`R`) is the central hub for all arithmetic, logic, and data movement.
- **Polymorphic operands**: Slot 1 (`B`) pulls double duty as an ALU operand *or* a shift control word.
- **Host-driven I/O**: The VM doesn’t handle I/O directly—it polls flags set by the host (e.g., `RX`, `TX`, `ERR`).

---

## **Memory Map**

The 64KB address space is divided into fixed regions:


| Address Range   | Size      | Purpose              | Notes                                    |
| --------------- | --------- | -------------------- | ---------------------------------------- |
| `0x0000–0x0007` | 8 bytes   | **System State**     | PC, SELECTOR, RSP, SCRATCH               |
| `0x0008–0x0027` | 32 bytes  | **Slot File**        | 16 × 16-bit general-purpose registers    |
| `0x0028–0x00FF` | 216 bytes | **Return Stack**     | Grows upward; stores return addresses    |
| `0x0100–0x017F` | 128 bytes | **Descriptor Table** | 64 × 16-bit pointers to data regions     |
| `0x0180–0x01FF` | 128 bytes | **Scope Stack**      | Grows upward; saves/restores slot values |
| `0x0200–0xFFFF` | ~64KB     | **Program + Data**   | Code and inline `.byte` regions          |


---

## **System Region (`0x0000–0x0007`)**

All values are **little-endian**. Word accesses require 16-bit alignment.


| Address | Size | Label    | Description                   |
| ------- | ---- | -------- | ----------------------------- |
| 0x0000  | 2    | PC       | Program counter               |
| 0x0002  | 2    | SELECTOR | Active slot index (for `LD`)  |
| 0x0004  | 2    | RSP      | Return stack pointer          |
| 0x0006  | 2    | SCRATCH  | Cross-frame temporary storage |


---

## **Slots (`0x0008–0x0027`)**

16 general-purpose 16-bit registers with **hard-wired roles**:


| Slot | Label | Role                                                      |
| ---- | ----- | --------------------------------------------------------- |
| 0    | A     | ALU left operand / Descriptor byte offset                 |
| 1    | B     | ALU right operand **or** shift control word (polymorphic) |
| 2    | R     | ALU result / Shift operand / Load/Store value             |
| 3    | REM   | Division remainder                                        |
| 4    | —     | General-purpose                                           |
| 5    | JT    | Jump/CALL target address                                  |
| 6–14 | —     | General-purpose                                           |
| 15   | FLAGS | Global status flags (see below)                           |


---

### **Global Flags (Slot 15)**

Flags are set by ALU ops (`ADD`, `SUB`, `CMP`, etc.) or the host (`RX`, `TX`, `ERR`).


| Bit  | Name | Set By          | Description            |
| ---- | ---- | --------------- | ---------------------- |
| 0    | Z    | ALU/CMP/CHK/SHF | Zero flag              |
| 1    | N    | ALU/CMP/CHK/SHF | Negative (signed) flag |
| 2    | RX   | Host            | Input data available   |
| 3    | TX   | Host            | Output channel ready   |
| 4    | ERR  | Host            | Device error           |
| 5–15 | —    | —               | Reserved               |


**Usage:**

- `Z` and `N` are read by conditional jumps (`IFEQ`, `IFNE`, `IFGT`, `IFLT`).
- `RX`, `TX`, `ERR` are polled via `CHK` (e.g., `CHK 0x04` to test `RX`).

---

## **Slot Selection Model**

Slots are accessed via a **persistent selector** (`SELECTOR` at `0x0002`).  
Example:

```asm
SEL 5    ; Point selector at slot 5
LD  0x1234 ; Write 0x1234 into slot 5
```

The selector persists until the next `SEL`.

---

## **Descriptor Table (`0x0100–0x017F`)**

A **64-entry pointer table** for structured memory regions (buffers, lookup tables, etc.).

- Each entry is a 16-bit LE address (`0x0000` = null/trap).
- **Slot 0 (`A`)** = byte offset into the region.
- **Slot 2 (`R`)** = value register for loads/stores.
- **Subset byte** controls auto-increment/decrement of `A`:
  - `0x00`: No offset change
  - `0x01`: Post-increment (`A += step`)
  - `0x02`: Post-decrement (`A -= step`)
  - `0x03`: Pre-increment (`A += step` before access)

**Step size:** 1 for byte ops, 2 for word ops (word ops trap on unaligned addresses).

### **Memory Directives**

```asm
; Initialized data
:message  .byte 10, "Hello"    ; 10-byte string
:buffer   .byte 64, <bytes>   ; Pre-filled buffer

; Uninitialized (zeroed)
:stdin    .byte? 64           ; Input buffer
:work     .byte? 256          ; Scratch space
```

### **Example: Iterating Over a Buffer**

```asm
SEL 0       ; A = offset register
LD  0       ; Start at offset 0
SEL 2       ; R = value register
.loop:
    LDB 0x01, 5  ; Load byte from desc[5], post-inc A by 1
    ; ... process R ...
    CMP A, LIMIT
    IFLT / JMP .loop
```

---

## **Scope Stack (`0x0180–0x01FF`)**

A **LIFO stack** for saving/restoring slot values across function calls.

- `**SSP**` (Scope Stack Pointer) starts at `0x0180`; data grows upward.
- **No bounds checking** (overflow corrupts program space at `0x0200`—intentional for bare-metal use).

### **Calling Convention**

- **Caller**: `STASH` slots to preserve → `CALL` → `UNSTASH` after `RET`.
- **Callee**: Must balance its own `STASH/UNSTASH` pairs.
- `**SCRATCH` (`0x0006`)**: Immune to `STASH/UNSTASH`; used for cross-frame values.
  - Convention: Callee writes result to `SCRATCH` before `RET`; caller reads it after `CALL`.

```asm
STASH 2    ; Save R
CALL func
UNSTASH 2  ; Restore R
RDS        ; R ← SCRATCH (result from func)
```

---

## **Instruction Format**

All instructions are **32-bit little-endian**:

```
Byte 0: Opcode
Byte 1: Subset (modes for some ops)
Bytes 2–3: 16-bit parameter (LE)
```

---

## **Opcode Summary**


| Opcode    | Mnemonic            | Operands/Behavior                    | Description                               |
| --------- | ------------------- | ------------------------------------ | ----------------------------------------- |
| 0x00      | NOP                 | —                                    | No operation                              |
| 0x01      | ADD                 | A, B → R                             | Addition                                  |
| 0x02      | SUB                 | A, B → R                             | Subtraction                               |
| 0x03      | MUL                 | A, B → R                             | Multiply (low 16 bits)                    |
| 0x04      | DIV                 | A, B → R (quotient), REM (remainder) | Division                                  |
| 0x05–0x07 | AND/OR/XOR          | A, B → R                             | Bitwise ops                               |
| 0x08      | NOT                 | A → R                                | Bitwise NOT                               |
| 0x09      | NEG                 | A → R                                | Two’s complement                          |
| 0x0A      | SHF                 | R, B → R                             | Shift R by control word in B              |
| 0x0C      | CMP                 | A, B → FLAGS[Z,N]                    | Compare (A - B)                           |
| 0x0C      | CHK                 | mask → Z                             | Test flags: Z=1 if (FLAGS & mask) == mask |
| 0x10      | SEL                 | param → SELECTOR                     | Set slot selector                         |
| 0x11      | LD                  | param → slot[SELECTOR]               | Load immediate into selected slot         |
| 0x12      | STASH               | slot[n] → scope stack                | Push slot to scope stack                  |
| 0x13      | UNSTASH             | scope stack → slot[n]                | Pop scope stack into slot                 |
| 0x14      | RDS                 | SCRATCH → R                          | Read SCRATCH into R                       |
| 0x15      | WRS                 | R → SCRATCH                          | Write R to SCRATCH                        |
| 0x20      | JMP                 | JT → PC                              | Jump to address in slot 5                 |
| 0x21–0x24 | IFEQ/IFNE/IFGT/IFLT | —                                    | Conditional skips (based on Z/N)          |
| 0x30      | CALL                | —                                    | Push PC, jump to JT                       |
| 0x31      | RET                 | —                                    | Pop PC from return stack                  |
| 0x40–0x43 | LDB/LDW/STB/STW     | desc[n], A→offset, R↔val             | Load/store byte/word via descriptor       |
| 0xFF      | HALT                | —                                    | Stop execution                            |


---

### **Shift Control Word (Slot 1)**

For `SHF`, slot 1 (`B`) acts as a **control word**:


| Bits | Field     | Description         |
| ---- | --------- | ------------------- |
| 0–3  | Amount    | Shift steps (0–15)  |
| 4    | Direction | 0 = left, 1 = right |
| 5–15 | —         | Ignored             |


**Example: Chaining ALU → SHF**

```asm
ADD      ; R = A + B
SEL 1    ; Target B
LD ctrl  ; Load shift control word (e.g., 0x03 = left by 3)
SHF      ; R = R << 3
```

---

## **Architectural Model**

μ16 is a **parameterized state machine**:

```
δ : State × Instruction → State
State = (PC, SELECTOR, RSP, SSP, SCRATCH, Slots[0..15], FLAGS[Z,N,RX,TX,ERR], Memory[0..65535])
```

- **Fixed point**: Slot 2 (`R`) is the central register for computation, shifts, and data movement.
- **Polymorphic operand**: Slot 1 (`B`) is either an ALU operand or a shift control word.
- **Branching**: Only `Z` and `N` flags (from `R`) are used for conditional jumps.
- **Hot path**: `A,B → ALU → R → SHF → R → FLAGS → branch`.

**Compact notation:**

> μ16 = `δ(PC, I, S, F, M | opcode, subset, param)`  
> where `δ` routes `(S[0], S[1], S[2])` through opcode-selected transforms, updates `F[Z,N]` from `S[2]`, and advances `PC ← PC+4`.

