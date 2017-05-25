from binaryninja.enums import InstructionTextTokenType as TTT
from binaryninja.function import InstructionTextToken as TT
from .. import mem
from .ana import needs_decoding

def render(row, vals):
    """Fill in dynamic portions that aren't precomputed.

    :: [[TT | (render_fn, decode_val_index)]] -> [val] -> [TT]
    """
    def remap(val):
        if type(val) != tuple:
            return val
        else:
            mapper,index = val
            return mapper(vals[index])
            
    return sum([remap(tok) for tok in row], [])

def tokens(_, name, operands):
    """Everything needed for perform_get_instruction_text(..)

    :: (..) -> [[TT | (render_fn, decoded_operand_index)]]
    """
    toks = [[TT(TTT.InstructionToken, name), 
             TT(TTT.OperandSeparatorToken, ' ')]]

    op_index = 0  # index of operand in decoded value list
    for i,op in enumerate(operands):
        if op.startswith('@') or op.startswith('/'):
            op_type, op = op[0], op[1:]
            toks += [[TT(TTT.BeginMemoryOperandToken, op_type)]]
        
        if op.startswith('R') or op in ['A','B','DPTR','C']:
            toks += [[TT(TTT.RegisterToken, op)]]
        else:
            toks += {
                'AB': 
                    [[TT(TTT.RegisterToken, 'A'),  # woo, properly clickable!
                      TT(TTT.RegisterToken, 'B')]],
                'A+PC': 
                    [[TT(TTT.RegisterToken, 'A'), 
                      TT(TTT.OperandSeparatorToken, '+'), 
                      TT(TTT.RegisterToken, 'PC')]],
                'A+DPTR':
                    [[TT(TTT.RegisterToken, 'A'), 
                      TT(TTT.OperandSeparatorToken, '+'),
                      TT(TTT.RegisterToken, 'DPTR')]],
                '#data': [(out_imm, op_index)],
                'code addr': [(out_code, op_index)],
                'data addr': [(out_direct, op_index)],
                'bit addr': [(out_bit, op_index)],
            }.get(op, [[TT(TTT.TextToken, op)]])

        if i + 1 < len(operands):  # intersperse
            toks += [[TT(TTT.OperandSeparatorToken, ', ')]]

        if needs_decoding(op):
            op_index += 1

    return toks

def hx(val):
    #return hex(int(val))  # just hex please
    #return hex(int(val))[2:].upper() + 'H'  # shouty manual style
    return hex(int(val))[2:] + 'h'  # not-shouty, but still deadbeefh

def out_code(target):
    return [TT(TTT.PossibleAddressToken, hx(target - mem.CODE),
                                         value=target, size=2)]

def out_direct(target):
    if target in mem.regs:  
        # for special memory-mapped registers, render them as proper regs
        if mem.regs[target] == 'A':
            # lol assembler roundtrip
            return [TT(TTT.RegisterToken, 'A'), TT(TTT.TextToken, 'CC')]
        return [TT(TTT.RegisterToken, mem.regs[target])]
    else:
        unmapped = target - mem.IRAM
        if unmapped < 0 or unmapped > 0x80:
            unmapped = target - mem.SFRs
        return [TT(TTT.PossibleAddressToken, hx(unmapped),
                                             value=target, size=1)]

def out_imm(val):
    return [TT(TTT.TextToken, '#'), TT(TTT.IntegerToken, hx(val), value=val)]

def out_bit(target):
    """This deviates from standard assembler syntax, I think. 
    
    I'm not sure if the BYTE_ADDR.BIT_ADDR notation used in IDA is used
    elsewhere.
    """
    byte,bit = target
    if byte == mem.PSW and bit in mem.flags:
        # Treat memory-mapped flag access as an actual flag.
        # This won't be sound for code that reads PSW then does manual
        # bitshifts to extract flags, but oh well. :(
        return [TT(TTT.RegisterToken, mem.flags[bit])]
    else:
        if byte not in mem.regs:
            unmapped = byte - mem.IRAM
            if unmapped < 0 or unmapped >= 0x80:
                unmapped = byte - mem.SFRs
            unmapped = hx(unmapped)
            return [TT(TTT.PossibleAddressToken, unmapped, value=byte, size=1),
                    TT(TTT.TextToken, '.'), # hmm, non-std syntax? :|
                    TT(TTT.IntegerToken, str(bit), value=bit)]
        else:
            return [TT(TTT.RegisterToken, mem.regs[byte]),
                    TT(TTT.TextToken, '.'),
                    TT(TTT.IntegerToken, str(bit), value=bit)]
