μ16, Pocket size 16-bit Virtual Machine
========================================

A 16-bit VM where everything lives inside a flat 64KB memory array.  
No external registers, all state is memory-mapped.  


Memory Map
----------
```
0x0000 - 0x0007    System        PC (2), SELECTOR (2), Reserved (4)
0x0008 - 0x0027    Slots 0–15    16 × 16-bit words (32 bytes)
0x0028 - 0x00FF    Return Stack  216 bytes (108 slots, grows upward)
0x0100 - 0x01FF    Syscall       256 bytes (stdio, decoupled buffer)
0x0200 - 0xFFFF    Program       Code + .byte data (65024 bytes)
```

All values stored little-endian.  
All addresses must be 16-bit aligned for word access.  


Slots
-----
16 general-purpose 16-bit words at fixed addresses.  
Some slots have hard-wired roles for general purpose operations:  

| Slot | Label  | Role                                      |
|------|--------|-------------------------------------------|
| 0    | A      | ALU, SHIFT / left operand                 |
| 1    | B      | ALU, SHIFT / right operand / shift params |
| 2    | R      | ALU / SHIFT result                        |
| 3    | REM    | DIV remainder                             |
| 4    |        | General purpose                           |
| 5    | JT     | JMP destination                           |
| 6-14 |        | General purpose                           |
| 15   | FLAGS  | Condition flags (see below)               |

Flags (Slot 15)
-------------------------------------
| Bit | Name | Description          |
|-----|------|----------------------|
| 0   | Z    | Zero                 |
| 1   | N    | Negative (signed)    |

*Bits 2–15 reserved.*

Flags `Z` and `N` are used by: 
- ADD, SUB, MUL, DIV
- AND, OR, XOR, NOT, NEG
- SHF, CMP
- JMP, IFEQ, IFNE, IFGT, IFLT


Instruction Format
------------------
Fixed 32-bit, little-endian:

```
Byte 0    Byte 1    Byte 2–3
opcode    reserved  param (16-bit LE)
```


Opcode Table
------------
| Opcode | Mnemonic | Operands        | Description                            |
|--------|----------|-----------------|----------------------------------------|
| 0x00   | NOP      |                 | No operation                           |
| 0x01   | ADD      | A, B → R        | Addition                               |
| 0x02   | SUB      | A, B → R        | Subtraction                            |
| 0x03   | MUL      | A, B → R        | Multiplication (low 16 bits)           |
| 0x04   | DIV      | A, B → R, REM   | Division (quotient→R, remainder→slot3) |
| 0x05   | AND      | A, B → R        | Bitwise AND                            |
| 0x06   | OR       | A, B → R        | Bitwise OR                             |
| 0x07   | XOR      | A, B → R        | Bitwise XOR                            |
| 0x08   | NOT      | A → R           | Bitwise NOT                            |
| 0x09   | NEG      | A → R           | Two's complement negation              |
| 0x0A   | SHF      | A, B → R        | Shift (see Shift Control Word)         |
| 0x0C   | CMP      | A, B → FLAGS    | Compare (A − B, flags only)            |
| 0x10   | SEL      | param → I       | Set slot selector to param             |
| 0x11   | LD       | param → slot[I] | Load param into selected slot          |
| 0x20   | JMP      | JT → PC         | Jump to address in slot 5              |
| 0x21   | IFEQ     |                | Skip next if Z = 1                      |
| 0x22   | IFNE     |                | Skip next if Z = 0                      |
| 0x23   | IFGT     |                | Skip next if N=0 and Z=0 (signed >)     |
| 0x24   | IFLT     |                | Skip next if N = 1 (signed <)           |
| 0x30   | CALL     |                | Push PC, then JMP                       |
| 0x31   | RET      |                | Pop PC from return stack                |
| 0xFF   | HALT     |                | Stop execution                          |


Shift Control Word (Slot 1: SHF parameters)
----------------------------------------------------------
| Bits    | Field     | Description                       |
|---------|-----------|-----------------------------------|
| 0–3     | Amount    | Shift steps (0–15)                |
| 4       | Direction | 0 = left, 1 = right               |
| 5–15    |           | Reserved (return mask planned)    |

Slot Selection Model
--------------------
SEL and LD work together as a two-step load:

    SEL 5       ; point selector at slot 5
    LD  0x1234  ; write 0x1234 into slot 5

The selector (I) persists across instructions until the next SEL.  
No STORE opcode yet, stores go through slot manipulation.  
