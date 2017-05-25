"""Map overlapping address spaces into a flat scheme by offsetting them.

This requires a bunch of work during instruction rendering to ensure the result
still looks like 8051. Lifting isn't significantly affected, since no matter
what it would need to encode memory type information.


Whatever section ends up mapped at 0 is significant, since it's the only one
that will have nice-looking addresses that match reality.

The end user will interact with the code section (through memory loading,
symbol markup, page swapping) the most. It also seems to have the most impact
on BN's naming schemes and automated, hard-to-hook data pointer markup.

IRAM/SFRs are small enough to scroll through if first, and code would be
amusing to place at 0xc0de. However, going with CODE == 0 for now.


Keeping this in a module makes it harder to special-case for inevitable
architecture variants. Wrapping it in classes would be more consistent with
Binary Ninja's API design, but should suffice for early prototyping.
"""
CODE = 0x0000 << 24  # (since this is 0, relocating it is poorly-tested)
SFRs = 0x80ff << 24  # special function registers, range from 0x80..0xff
IRAM = 0xda1a << 24  # internal RAM, 'little data'
XRAM = 0xda7a << 24  # external RAM, 'big data'

regs = {
    # Used often enough to make xrefs pointless. Maintains dataflow across
    # MUL/DIV.
    SFRs+0xE0: 'A',
    SFRs+0xF0: 'B',
    # Merge together into DPTR, want to maintain dataflow. Again, xrefs pretty
    # due to constant use.
    SFRs+0x82: 'DPL',
    SFRs+0x83: 'DPH',
    # Does Binary Ninja use this? No harm including it if not, rarely gets
    # touched.
    SFRs+0x81: 'SP',
}

# All real flags are stored in the PSW SFR at 0xD0. Exceptions are: 
# - zero flag (test A directly) 
# - signed flag (isn't specified)
PSW = SFRs + 0xD0
# Real flags have to be tracked while doing bit reads/writes, or reading PSW.
# Synthetic flags will be handled separately, and shouldn't need special
# treatment during lifting/output of bit operands or PSW read-writes.
flags = {
    7:'c',  # called CY in PSW description, and nowhere else
    6:'ac',
    # F0, RS1, RS0 aren't lifted to flag status
    2:'ov',
    # user-definable flag isn't lifted either
    0:'p',
}
# Ideally, would be nice to support register bitfield names.
# No can do until this, I think:
#    https://github.com/Vector35/binaryninja-api/issues/694

def flash_bank_virtual(target, addr):
    """Map physical code addresses into virtual ones, for flash banking.

    For PC changes inside flash banks, keep them inside the bank. 

    This is accurate only under the common banked calling convention where bank
    swaps are *only* done via a trampoline that jumps to DPTR after setup.
    Things outside that convention will lead to spurious CFG edges, which
    leads to a garbage image.

    Exceptions may show up in optimized code, but not typical compiler output.
    Obfuscated code has better tricks to play like branch over/underflows.

    TODO: analysis pass that warns on flash/register bank trickery.

    I don't think this'll work for movc as-is; needs to be explicitly done in
    lifter, since movc just does [mem.CODE+DPTR]. Now it needs a special case
    for high addresses to pull from register state, argh. Tradeoff between
    accuracy (emulation of port/flash remap register, which is very
    platform-dependant) and simplicity (do same local-page assumption as this
    code) again.

    target: absolute 8051 code address space (so not based at mem.CODE)
    addr: our virtual address space based at mem.CODE, with extra banks
    returns: target rebased to virtual address space
    """
    if addr > 0xFFff and target > 0x7Fff:  # 145bb
        bank_base_in_bndb = addr // 0x8000 * 0x8000
        target -= 0x8000  # relocate from bank 0 to origin
        target += bank_base_in_bndb  # relocate to own bank
    return target + CODE

def flash_bank_physical(addr):
    """Map virtual flash bank address back into 16-bit physical one."""
    addr -= CODE
    while addr > 0xFFff:
        addr -= 0x8000 
    return addr
 
