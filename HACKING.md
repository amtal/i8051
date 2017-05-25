Binary Ninja relies on emulation of an intermediate representation to do interesting things. The IR is essentially a custom architecture that assumes a flat memory space, isolation between registers and memory, flag semantics common to x86 and ARM processors, call semantics common to C compiler output, simple stack manipulation, and userland execution that doesn't interact with hardware peripherals. 

Lifting 8-bit microcontroller code to the abstract architecture requires bridging the gaps between abstract assumptions and the features actually used by the code. This project evaluates techniques for doing so, and so far they fall into two major categories:

- A memory and register mapping between the architectures, defined in [mem.py](mem.py).
- A set of low-level hooks in the `Architecture`'s guts, that allow it to be customized by a `BinaryView` loading a specific image. This is ugly and currently makes use of global state, but is the cleanest way I see to extend and tweak the base architecture to fit the wide range of MCS-51 SoCs out there. See [hooks.py](hooks.py) for the current API.

### Module Dependencies

```
mem                  Globally included flat memory map and special registers.

disassembler.*       IDA-style disassembly passes refined from an Intel manual.
  |
  +-lowlevelil       Lift to LLIL, detailed equivalent of disassembler.emu.
  | |        
  | +---freki        With geri, compares semantics against a 2nd source.
  | |  
  | | hooks          Hack allowing architecture extensions inside the binaryview.
  | | +--\
  | | |  |     
  \-+---architecture Top-level processor definition
      |   |    |
   binaryview--+     Extendable memory layout / SFR markup / extra analysis.
               |
           __init__  Register everything into Binary Ninja on import.

devices.*            Device-specific BinaryView examples.
experiments.*        Unstable stuff that might get migrated up in the future.
```

### Lifter Quality

The lifted LLIL semantics are currently hand-written and do not benefit from
the disassembler's assurance argument. (For what little that argument is worth,
anyway.) Instead, the intent is to use an SMT solver to check them for
equivalence against an independant 2nd source.

The optimal tradeoff between fidelity of the LLIL model of memory mapping
(especially on systems-type actions like bank swapping) versus effective
support of compiler-generated code is still being explored. Watch your step.

