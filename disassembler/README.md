The code is structured roughly like an IDA processor module. An analysis pass
to decode instructions (`ana`) is followed by separate pretty-printers (`out`)
and enough emulation (`emu`) for recursive disassembly to work. This structure
is conceptually useful for separating the disassembler into pre-computable and
runtime-dependant parts.

Decoding and pretty-printing are refined from an opcode specification pulled
from a 1994 Intel manual. From it, lookup tables for a typical table-based
disassembler are generated. This should allow efficient decoding (and a
possible port to C later) while maintaining very high confidence in the
accuracy<sup>1</sup> of the disassembler and pretty printer.

## Module Dependencies

```
                     Global include, maps 8051 memory into a flat space and
..mem                defines which memory mapped registers/flags to lift.
  |
  | specification    MCS-51 Microncontroller Family User's Manual, Table 11.
  +---|-ana_op       Operand decoder functions. Take care of memory flattening.
  |   | |           
  |   +-+-+-emu      Enough branch semantics for fast recursive disassembly.
  |   |   \-ana      Full instruction decoder.
  \---+-----out      Pretty-printing.
```

1. Emulation details have been formed to fit the platform, not the other way
around. Common memory-mapped registers and flags are currently rendered as
registers, not memory references. This is because registers and flags are
well-supported and (presumably) are lighter-weight, and xrefs to the equivalent
of `eax` aren't useful.
