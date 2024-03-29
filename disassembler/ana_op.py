"""Helper functions to decode instruction operands.

Since the host program only implements a flat memory space, different memory
types are flattened according to the model in `mem`.
"""
from .. import mem

# immediates
def imm8_0(data, addr, size): return data[1]  # first operand
def imm8_1(data, addr, size): return data[2]  # second operand
def imm16(data, addr, size): return int.from_bytes(data[1:3], 'big')

# code absolute and relative addresses
def addr16(data, addr, size): 
    target = int.from_bytes(data[1:3], 'big')
    return mem.flash_bank_virtual(target, addr)
def rel(data, addr, size):
    phys_addr = mem.flash_bank_physical(addr)
    target = phys_addr + size + int.from_bytes(data[size-1:size], "big", signed=True)
    return mem.flash_bank_virtual(target, addr)
def addr11(data, addr, size):
    rel = mem.flash_bank_physical(addr) >> 11 << 11
    opcode_steal = data[0] >> 5 << 8
    target = rel + opcode_steal + data[1]
    return mem.flash_bank_virtual(target, addr)

# IRAM/SFR absolute addressing
def direct_0(data, addr, size):
    val = data[1]
    return mem.IRAM + val if val < 0x80 else mem.SFRs + val
def direct_1(data, addr, size):
    val = data[2]
    return mem.IRAM + val if val < 0x80 else mem.SFRs + val
def bit(data, addr, size):
    """Returns `(byte_addr,bit)` instead of just `addr` like the rest."""
    val = data[1]
    byte,bit = val // 8, val % 8
    if val < 0x80:
        return mem.IRAM + 0x20 + byte, bit
    else:
        return mem.SFRs + byte * 8, bit
