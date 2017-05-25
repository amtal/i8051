import re, struct
from binaryninja.log import log_info
from . import ana_op

def operand_decoders(size, name, ops):
    """Decode anything past the first 8 bits of an instruction.

    Returns (instruction size, [op_decoders]), where decoders are functions
    that take (data, addr, size) as argument and return the value of that
    particular operand. Operand ordering matches argument ordering in assembly
    usyntax used by manual.
    """
    return size, _get_operand_decoders(size, name, ops)

def _get_operand_decoders(size, name, ops):
    ops = tuple(filter(needs_decoding, ops))  # tuples are hashable

    if size == 1: return []

    if size == 2:
        if re.match('a(call|jmp)$', name): 
            return [ana_op.addr11]  # steals bits from opcode

        return [{
            'code addr':ana_op.rel,
            'data addr':ana_op.direct_0,
            '#data':ana_op.imm8_0,
            'bit addr':ana_op.bit,
            '/bit addr':ana_op.bit,
        }[ops[0]]]

    # size-3 instructions:
    return {
        # 16-bit operands:
        ('code addr',): [ana_op.addr16],
        ('#data',): [ana_op.imm16],
        # dual-op (or more):
        ('bit addr', 'code addr'): [ana_op.bit, ana_op.rel],
        ('data addr', 'code addr'): [ana_op.direct_0, ana_op.rel],
        ('data addr', '#data'): [ana_op.direct_0, ana_op.imm8_1],
        ('data addr', 'data addr'): [ana_op.direct_1, ana_op.direct_0], # !
        ('#data', 'code addr'): [ana_op.imm8_0, ana_op.rel],
    }[ops]
        
    assert not "reachable"  # function is total for input

def needs_decoding(op):
    """Operands that require more decoding than an 8-bit lookup."""
    return op.endswith('addr') or op == '#data'

