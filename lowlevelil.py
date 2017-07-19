from binaryninja.log import log_info, log_warn
from binaryninja.lowlevelil import LLIL_TEMP, LowLevelILFunction
from binaryninja.enums import LowLevelILOperation
from binaryninja import Architecture, LowLevelILLabel
from . import mem
from .disassembler import ana

def unlifted_todo(opcodes, ops):
    # TODO debug hackery nuke when done lifting
    def _map_unlifted(code, size, name, ops):
        fmt = '%02x | %d | [%s](http://www.keil.com/support/man/docs/is51/is51_%s.htm) | %s'
        return fmt % (code, size, name, name, ', '.join(ops))
    unlifted = ' # | Size | | Instruction\n--- |:---:| ---:|:---\n'
    unlifted += '\n'.join([_map_unlifted(code, *opcodes[code]) 
                           for code in range(len(opcodes)) 
                           if ops[code] == unimpl])
    return unlifted
            

def unimpl(il,vs,ea): il.append(il.unimplemented())


def low_level_il(size, name, ops):
    if name.endswith('jmp') and ops[0] == 'code addr':
        return lambda il,vs,ea: il.append(il.jump(il.const_pointer(6, vs[0])))
    if name == 'jmp' and ops[0] == '@A+DPTR':
        def f(il,vs,ea):
            regs = il.add(2, il.reg(1, 'A'), il.reg(2, 'DPTR'))
            addr = il.add(6, il.const(6, mem.CODE), regs)
            il.append(il.jump(addr))
        return f

    def _tmp():
        def l_or_a_call(il,vs,ea):
            # TODO: inject a hook here that'll query the llil_mangler!!!
            # TODO: BV should have access to a hook interface inside A impl.
            #       granting capabilities commonly needed on that arch!
            #       Do analysis, add hooks, patch, re-analyze!
            il.append(il.call(il.const_pointer(6, vs[0])))
        lcall = l_or_a_call
        acall = l_or_a_call

        def nop(il,vs,ea): 
            il.append(il.nop())
        def reserved(il,vs,ea): 
            il.append(il.no_ret()) # FIXME warn in cleanup post-pass hooked on view
        def ret(il,vs,ea):
            # TODO: pull high bits from P1? (ARGH not arch-independant)
            il.append(il.ret(il.pop(2)))
        reti = ret  # actually identical if there's no interrupt!

        def push(il,vs,ea): 
            if 0:
                # FUN ASSUMPTION: if using for ret-stuff, it's push DPL; push DPH
                # If temporarily storing DPTR on the stack by hand, endianness
                # *might* be reversed. (Public example: coastermelt firmware.)
                # So, assumption must be propagated upwards and checked for
                # otherwise RIP analysis, LLIL lift ends up mis-disassembling
                # stuff and producing loops, complete type-2 disaster.

                # Special-case the return value pattern. :)
                if ops[0] == 'data addr' and vs[0] == mem.SFRs + 0x82:
                    # try using full-width register in case it's a merging issue
                    il.append(il.push(2, il.reg(2, 'DPTR')))
                    return 4
                elif ops[0] == 'data addr' and vs[0] == mem.SFRs + 0x83:
                    il.append(il.nop())
                else:
                    il.append(il.push(1, r(ops[0], il, vs[0])))
            else:
                il.append(il.push(1, r(ops[0], il, vs[0])))
        def pop(il,vs,ea):
            if 0:
                if ops[0] == 'data addr' and vs[0] == mem.SFRs + 0x82:
                    il.append(il.unimplemented())
                elif ops[0] == 'data addr' and vs[0] == mem.SFRs + 0x83:
                    # try using full-width register in case it's a merging issue
                    il.append(il.set_reg(2, 'DPTR', il.pop(2)))
                    return 4
                else:
                    w(ops[0], il, il.pop(1), vs[0])
            else:
                w(ops[0], il, il.pop(1), vs[0])

        def jz(il,vs,ea):
            branch(il, il.compare_equal(1, il.reg(1, 'A'), il.const(1, 0)), il.const_pointer(6, vs[0]))
        def jnz(il,vs,ea):
            branch(il, il.compare_not_equal(1, il.reg(1, 'A'), il.const(1, 0)), il.const_pointer(6, vs[0]))
        def jc(il,vs,ea):
            branch(il, il.flag('c'), il.const_pointer(6, vs[0]))
        def jnc(il,vs,ea):
            branch(il, il.not_expr(0, il.flag('c')), il.const_pointer(6, vs[0]))
        def jb(il,vs,ea):  # a465 
            #log_warn('jb @ '+hex(ea))
            branch(il, r(ops[0], il, vs[0]), il.const_pointer(6, vs[1]))
        def jnb(il,vs,ea):  # c5ac
            branch(il, il.not_expr(0, r(ops[0], il, vs[0])), il.const_pointer(6, vs[1]))
        def cjne(il,vs,ea): # currently not handling @R0 @R1 TODO or am I?
            # a5c2    ehh won't work at all this way, needs new wrapper that doesn't set result
            dst, src = r(ops[0], il), r(ops[1], il, vs[0])
            il.append(il.set_flag('c', il.compare_unsigned_less_than(1, dst, src)))
            ret = branch(il, il.compare_not_equal(1, dst, src), il.const_pointer(2, vs[1]))
            if ret: return ret
        def djnz(il,vs,ea):
            if size == 2:
                src = r(ops[0], il)
                dst = il.const_pointer(2, vs[0])
            else:
                src = r(ops[0], il, vs[0])
                dst = il.const_pointer(2, vs[1])
            decr = il.sub(1, src, il.const(1, 1))
            w(ops[0], il, decr)
            branch(il, il.compare_not_equal(1, decr, il.const(1, 0)), dst)

        def xch(il,vs,ea):  # a732 a8c3
            v = 0 if not len(vs) else vs[0]
            il.append(il.set_reg(1, LLIL_TEMP(0), r(ops[0], il)))
            w(ops[0], il, r(ops[1], il, v))
            w(ops[1], il, il.reg(1, LLIL_TEMP(0)), v)
        def swap(il,vs,ea):
            w('A', il, il.rotate_left(1, r('A', il), il.const(1, 4)))

        def mul(il,vs,ea): # mul AB   a732, a751
            product = il.mult(2, il.reg(1, 'A'), il.reg(1, 'B'), flags='*')
            lo_part = il.low_part(1, product)
            hi_part = il.low_part(1, il.logical_shift_right(1, product, il.const(1, 8)))
            il.append(il.set_reg(1, 'A', lo_part))
            il.append(il.set_reg(1, 'B', hi_part)) # TODO try making AB a 2-byte reg, split-assining hi-lo

            # Is this really the easiest way to explode a thing into register + memory? 
            # Or is it worth introducing a tempvar?
 
            if 0: # let's see if flags can be auto-derived...
                # always cleared
                il.append(il.set_flag('c', il.const(0, 0)))
                # overflow if result >0xFF
                #il.append(il.set_flag('ov', il.compare_equal(1, hi_part, il.const(0, 0)))) 
                il.append(il.set_flag('ov', il.compare_equal(1, il.reg(1, 'B'), il.const(0, 0)))) 
        def div(il,vs,ea):
            result = il.div_unsigned(1, il.reg(1, 'A'), il.reg(1, 'B'), flags='*')
            il.append(il.set_reg(1, 'A', il.low_part(1, result)))
            # TODO quotient into A, remainder into B this is hella wrong
            # TODO flags
            il.append(il.set_reg(1, 'B', il.low_part(1, il.logical_shift_right(1, result, il.const(1, 8)))))

        return locals()
    _tmp = _tmp()
    if name in _tmp:
        return _tmp[name]
        
    handler, flags = None, None
    if name in ['anl', 'orl']:
        def anl_orl(il,a,b,fl):
            fun = il.and_expr if name == 'anl' else il.or_expr
            return fun(1, a, b)
        # Technically this modifies 'c' flag, but I probably don't need to
        # pass flags= for it since it's written directly not implicitly?
        handler = anl_orl
        flags = None if ops[0] == 'C' else 'zsp'
    elif name == 'xrl':
        handler = lambda il,a,b,fl:il.xor_expr(1, a, b)
        flags = 'zsp'
    elif name == 'add':
        handler = lambda il,a,b,fl:il.add(1, a, b, flags=fl)
        flags = '*'
    elif name == 'addc':
        handler = lambda il,a,b,fl:il.add_carry(1, a, b, il.flag('c'), flags=fl)
        flags = '*'
    elif name == 'subb':  # a84f
        handler = lambda il,a,b,fl:il.sub_borrow(1, a, b, il.flag('c'), flags=fl) 
        #flags = '*'  # TODO should be *, but tired of warning lag
    if handler:
        ret = dispatch_2operand(ops, handler, flags)
        if ret: return ret
        
            
    if name in ['inc', 'dec']:
        if ops[0] == 'DPTR':
            def inc_dptr(il,vs,ea):
                w('DPTR', il, il.add(2, r('DPTR', il), il.const(2, 1)))
            return inc_dptr
        else: # Rx, A, or @Rn
            delta = 1 if name == 'inc' else -1
            def inc_dec(il,vs,ea):
                w(ops[0], il, il.add(1, r(ops[0], il), il.const(1, delta)))
            return inc_dec 
    if name == 'mov':
        if ops == ['DPTR', '#data']:
            def load_DPTR_imm(il,vs,ea):
                w('DPTR', il, il.const(2, vs[0]))
            return load_DPTR_imm
        if size == 1:
            def mov(il,vs,ea):
                val = r(ops[1], il)
                w(ops[0], il, val)
            return mov
        if size == 2:
            def mov_8bit(il,vs,ea):
                # variable operand always on the read, with one exception
                val = r(ops[1], il, vs[0]) # usages should sort themselves out
                w(ops[0], il, val, vs[0])  # fingers crossed
            return mov_8bit
        if size == 3:
            def mov_8bit_2x(il,vs,ea):
                # operands always dst,src ordered, but encoding is src,dst
                # core.ana takes care of ordering into operand-order
                val = r(ops[1], il, vs[1]) 
                w(ops[0], il, val, vs[0]) 
            return mov_8bit_2x
    if name in ['clr', 'setb', 'cpl']:
        is_reg = not ops[0].endswith('bit addr')
        sz = 1 if ops == ['A'] else 0
        def _tmp():
            def clr(il,vs,ea):
                w(ops[0], il, il.const(sz, 0), 0 if is_reg else vs[0])
            def setb(il,vs,ea):
                w(ops[0], il, il.const(sz,1), 0 if is_reg else vs[0])
            def cpl(il,vs,ea):
                v = 0 if is_reg else vs[0]
                val = il.neg_expr(sz, r(ops[0], il, v)) 
                w(ops[0], il, val, v)
            return locals()
        return _tmp()[name]
    if name in ['rlc', 'rl', 'rrc', 'rr']:  # rlc A
        def rot_A(il,vs,ea): # a88c
            fun = {
                'rlc':il.rotate_left_carry,
                'rl':il.rotate_left,
                'rrc':il.rotate_right_carry,
                'rr':il.rotate_right,
            }[name]
            if name.endswith('c'):
                w('A', il, fun(1, il.reg(1, 'A'), il.const(1, 1), 
                               il.flag('c'), flags='zsp')) # TODO add c flag, for some reason 'zspc' doesn't generate
                # a516 good example of this
            else:
                w('A', il, fun(1, il.reg(1, 'A'), il.const(1, 1), flags='zsp'))
        return rot_A


    if size != 1: 
        return unimpl


    if name == 'movc': # either A, @A+PC or A, @A+DPTR
        def movc(il,vs,ea): 
            base = il.reg(2, 'DPTR') if ops[1].endswith('DPTR') else il.const_pointer(2, ea)
            saddr = il.add(2,  il.reg(1, 'A'), base)
            eaddr = il.add(2, il.const(2, mem.CODE), saddr)
            w('A', il, il.load(1, eaddr))
        return movc
    if name == 'movx':
        if ops[0] == 'A': # load
            reg = ops[1][1:]
            if reg == 'DPTR':
                def movx_load_dptr(il,vs,ea): 
                    il.append(il.set_reg(1, ops[0], il.load(1, il.add(6, il.const(6, mem.XRAM), il.reg(2, reg)))))
                return movx_load_dptr
            else:
                # Haha how am I gonna work (P0 | @R{0,1}) into this? That's a
                # totally hardware-defined thing, since P0 might just be GPIO
                # or whatever. Or only a few lines will be connected. So it
                # needs to be in hardware-specific subclass code. But that
                # means I need to subclass the list of magic lifted mem.regs
                # too. Hmm.
                def movx_load_indirect(il,vs,ea): 
                    il.append(il.set_reg(1, ops[0], il.load(1, il.add(6, il.const(6, mem.XRAM), il.reg(1, reg)))))
                return movx_load_indirect
        else: # store
            # Note on il.operand(n, expr) annotations:
            # These only seem to apply to syntax that uses the 'memory access'
            # tokens ('[', ']') and shifts the {}-annotations inside the
            # brackets. Since round-trip syntax won't involve those, it doesn't
            # apply to MCS-51 and many others.
            reg = ops[0][1:]
            if reg == 'DPTR':
                def movx_store_dptr(il,vs,ea): 
                    il.append(il.store(1, il.add(6, il.const(6, mem.XRAM), il.reg(2, reg)), il.reg(1, 'A')))
                return movx_store_dptr
            else:
                def movx_store_indirect(il,vs,ea): 
                    il.append(il.store(1, il.add(6, il.const(6, mem.XRAM), il.reg(1, reg)), il.reg(1, 'A')))
                return movx_store_indirect

    return unimpl
        

def r(kind, il, v=0):
    """
    Never called with MOVX, handles IRAM/SFRs addresses only. The MOVX
    instruction is distinct from the others.
    
    Never called on 16-bit immediates. No way to distinguish from 8-bit.
    """
    if kind.startswith('@'):
        reg = il.reg(1, kind[1:])
        addr = il.add(6, reg, il.const(6, mem.IRAM))
        return il.load(1, addr)
    if kind == '#data':
        return il.const(1, v)
    if kind.endswith('addr'):
        if kind == 'code addr':
            return il.const_pointer(6, v)
        if kind == 'data addr':
            if v in mem.regs:
                return il.reg(1, mem.regs[v])
            # TODO: overlay PSW as register? how to compute from flags?
            return il.load(1, il.const_pointer(6, v))
        if kind.endswith('bit addr'): # cosmetic / prefix, optional
            byte,bit = v
            if byte == mem.PSW and bit in mem.flags:
                return il.flag(mem.flags[bit])
            if byte in mem.regs:
                if mem.regs[byte] == 'A' and bit == 7:  # a47e
                    return il.flag('s') # TODO TODO TODO how will setting this be tracked??
                # Strangely, based on LLIL pretty-printing, test_bit takes a
                # *mask* not a bit index.
                return il.test_bit(1, il.reg(1, mem.regs[byte]), il.const(0, 1 << bit))
            addr = il.const_pointer(6, byte)
            return il.test_bit(1, il.load(1, addr), il.const(0, 1 << bit))
    if kind == 'DPTR':
        return il.reg(2, kind)
    if kind.startswith('R') or kind in ['A', 'B'] or kind in mem.regs:
        return il.reg(1, kind)
    if kind == 'C':
        return il.flag('c')

    # @A+DPTR and @A+PC can be special-cased in their instructions

    log_warn('r '+repr((kind,il,v)))
    assert not "reachable"


def w(kind, il, val, v=0):
    """
    kind: type of write
    il: LowLevelILFunction
    val: symbolic source
    v: constant source
    """
    if kind.startswith('@'):
        reg = il.reg(1, kind[1:])
        addr = il.add(6, reg, il.const(6, mem.IRAM))
        return il.append(il.store(1, addr, val))
    if kind.endswith('addr'):
        if kind == 'data addr':
            if v in mem.regs:
                return il.append(il.set_reg(1, mem.regs[v], val)) # aa5b good test aa68
            # TODO: overlay PSW as register? how to compute from flags?
            return il.append(il.store(1, il.const_pointer(6, v), val))
        if kind.endswith('bit addr'): # cosmetic / prefix, optional
            byte,bit = v
            if byte == mem.PSW and bit in mem.flags:
                return il.append(il.set_flag(mem.flags[bit], val))
            if byte in mem.regs:  # a465
                src = il.reg(1, mem.regs[byte])
                mask = il.shift_left(1, il.const(1, 1), il.const(1, bit))
                # TODO: endianness, also need to clear bit not just set it...
                return il.append(il.set_reg(1, mem.regs[byte], il.or_expr(1, src, mask)))
            # TODO sketchy bit-write endianness
            addr = il.const_pointer(6, byte)  # should be properly mapped by ana
            mask = il.shift_left(1, il.const(1, 1), il.const(1, bit))
            val = il.or_expr(1, il.load(1, addr), mask)  # <- also only sets, never clears :|
            return il.append(il.store(1, addr, val))
    if kind.startswith('R') or kind in ['A', 'B']:
        return il.append(il.set_reg(1, kind, val))
    if kind == 'DPTR':
        return il.append(il.set_reg(2, kind, val))
    if kind == 'C':
        return il.append(il.set_flag('c', val))

    log_warn('w '+repr((kind,il,val,v)))
    assert not "reachable"


def branch(il, pred, dst):
    """Copying from example w/o understanding"""
    t = None
    if il[dst].operation == LowLevelILOperation.LLIL_CONST:
        # Hmm. Should I be doing this for all SFRs?
        
        t = il.get_label_for_address(Architecture['8051'], il[dst].value)
        # And arch is cached, right?
    
    indirect = t is None
    if indirect:
        t = LowLevelILLabel()

    f = LowLevelILLabel()
    il.append(il.if_expr(pred, t, f))
    if indirect:
        il.mark_label(t)
        il.append(il.jump(dst))
    il.mark_label(f)
    return None


def dispatch_2operand(ops, op_f, flags=None):
    """Handles common parts of ORL, ADD, ADDC, SUB, XRL, ..."""
    # mov has a ton of other cases too
    if ops[0] == 'data addr': # ORL/XRL/ANL only, not ADD/SUBB
        if ops[1] == 'A':
            def f(il,vs,ea):
                dst = il.const_pointer(1, vs[0])
                src = il.load(1, dst)
                il.append(il.store(1, dst, op_f(il, src, il.reg(1, ops[1]), None)))
            return f
        elif ops[1] == '#data':
            def f(il,vs,ea):
                dst = il.const_pointer(1, vs[0])
                src = il.load(1, dst)
                val = il.const(1, vs[1])
                il.append(il.store(1, dst, op_f(il, src, val, None)))
            return f
    elif ops[0] == 'A': # ADD/SUBB/ORL/XRL
        if ops[1] == '#data':
            def f(il,vs,ea):
                val = il.const(1, vs[0])
                il.append(il.set_reg(1, 'A', op_f(il, il.reg(1, 'A'), val, flags)))
            return f
        elif ops[1] == 'data addr':
            def f(il,vs,ea):
                val = r(ops[1], il, vs[0])
                a = il.reg(1, ops[0])
                il.append(il.set_reg(1, 'A', op_f(il, il.reg(1, 'A'), val, flags)))
            return f
        elif ops[1][0] == '@':
            def f(il,vs,ea):
                val = il.load(1, il.add(1, il.const(1, mem.IRAM), il.reg(1, ops[1][1:])))
                il.append(il.set_reg(1, 'A', op_f(il, il.reg(1, 'A'), val, flags)))
            return f
        elif ops[1][0] == 'R':  # R0..R7
            def f(il,vs,ea):
                il.append(il.set_reg(1, 'A', op_f(il, il.reg(1, 'A'), il.reg(1, ops[1]), flags)))
            return f
