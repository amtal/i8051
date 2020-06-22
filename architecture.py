from __future__ import print_function
import time, traceback
import binaryninja
from binaryninja.architecture import Architecture
from binaryninja.lowlevelil import LowLevelILFunction, LowLevelILLabel, LLIL_TEMP
from binaryninja.function import RegisterInfo, InstructionInfo
from binaryninja.log import log_info, log_warn, log_error
from binaryninja.enums import (BranchType, LowLevelILOperation,
                            LowLevelILFlagCondition, FlagRole, Endianness)
from . import mem
from .disassembler import specification
from .disassembler import ana, emu, out
from . import lowlevelil
from .experiments import llil_mangler

class MCS51(Architecture):
    """
    Capitalization convention: memory-mapped stuff in allcaps, bits and true
    registers lower? Except r0-r7, also lower? Foolish consistency.
    """
    name = "8051"

    # C 'pointers' tend to be 3 bytes, but architecture-wise it's just 2?
    # Our fake address space that keeps all flash banks mapped needs 3.
    # Full XRAM/IRAM tags need 5.
    address_size = 2  # sets default return value size, nothing else... ???

    endianness = Endianness.BigEndian  # up to compiler... needs to be chosen

    default_int_size = 1
    max_instr_length = 3
    stack_pointer = 'SP'

    regs = {r:RegisterInfo(r,1) for r in ['SP', 'A', 'B',]}
    regs['DPTR'] = RegisterInfo('DPTR',2)
    regs['DPL'] = RegisterInfo('DPTR',1)
    regs['DPH'] = RegisterInfo('DPTR',1,1) # FIXME what endianness is this?

    if 0:
        regs.update({r:RegisterInfo(r,1) 
                     for r in ['R%d' % n for n in range(8)]})
    else:
        # This is cute, but I'm not yet sure if it's useful. Register merging
        # doesn't come in until HLIL?
        # 
        # On closer look, this might be the only way to make calling
        # conventions work. At least as they are now.
        # Need to re-visit once this subregister bug is fixed:
        # https://github.com/Vector35/binaryninja-api/issues/715
        regs['PTR'] = RegisterInfo('Y0',3,1)  # C pointers under some compilers

        regs['Y0'] = RegisterInfo('Y0',4)
        regs['Y4'] = RegisterInfo('Y4',4)

        regs['T0'] = RegisterInfo('Y0',2)
        regs['T2'] = RegisterInfo('Y0',2,2)
        regs['T4'] = RegisterInfo('Y4',2)
        regs['T6'] = RegisterInfo('Y4',2,2)

        regs['R0'] = RegisterInfo('Y0',1)
        regs['R1'] = RegisterInfo('Y0',1,1)
        regs['R2'] = RegisterInfo('Y0',1,2)
        regs['R3'] = RegisterInfo('Y0',1,3)
        regs['R4'] = RegisterInfo('Y4',1)
        regs['R5'] = RegisterInfo('Y4',1,1)
        regs['R6'] = RegisterInfo('Y4',1,2)
        regs['R7'] = RegisterInfo('Y4',1,3)

    flags = [
        # actual flags stored in PSW special function register:
        'p', # parity of accumulator
        #'ud', # user defined/unused by base hardware
        'ov', # signed overflow on add
        #'rs0', 'rs1', # R0-R7 register bank select
        #'f0', # software use, like ud
        'ac', # aux carry, because BCD is *important*!
        'c',

        # synthesized flags:
        'z', # "There is no zero bit in the PSW. The JZ and JNZ instructions
        's', #  test the Accumulator data for that condition."
    ]
    flag_write_types = [
        '', # first element *might* be ignored due to known bug
        'c',
        'zsp',  # modify A, without touching other flags
        'zspc', # modify A and carry flag
        'zspc ov',    # */ operations
        #'zspc ov ac', # +- operations
        '*',          # +- operations
        # should mov indirect into PSW/ACC have its own flag settings?
    ]
    flags_written_by_flag_write_type = {
        'c': ['c'],
        'zsp': ['z','s','p'],
        'zspc': ['z','s','p','c'],
        #'zspc ov': ['z','s','p','c','ov'],
        '*': ['z','s','p','c','ov','ac'],
    }
    flag_roles = {
        # real:
        'c': FlagRole.CarryFlagRole,
        'ac': FlagRole.HalfCarryFlagRole,
        'ov': FlagRole.OverflowFlagRole,
        'p': FlagRole.OddParityFlagRole,
        # imaginary:
        's': FlagRole.NegativeSignFlagRole,
        'z': FlagRole.ZeroFlagRole,
    }
    flags_required_for_flag_condition = {
        LowLevelILFlagCondition.LLFC_E: ["z"],
        LowLevelILFlagCondition.LLFC_NE: ["z"],
        LowLevelILFlagCondition.LLFC_NEG: ["s"],
        LowLevelILFlagCondition.LLFC_POS: ["s"],
        LowLevelILFlagCondition.LLFC_UGE: ["c"],
        LowLevelILFlagCondition.LLFC_ULT: ["c"],
        # not set by nes.py, going to try setting:
        LowLevelILFlagCondition.LLFC_O: ["ov"],
        LowLevelILFlagCondition.LLFC_NO: ["ov"],
    }

    def get_instruction_info(self, data, addr):
        if not len(data):
            return  # edge case during linear sweep
        nfo = InstructionInfo()
        # ana
        size, branch = self.lut.branches[data[0]]
        nfo.length = size
        # emu
        if branch:
            branch_type, target = branch
            if callable(target):
                target = target(data, addr, size) if size <= len(data) else 0
            if branch_type == BranchType.CallDestination:
                # TODO: keep track of return-effect functions, tweak target +=dx
                pass
                # TODO: arch is probably global; need to store this in bv somehow :|
            nfo.add_branch(branch_type, target=target)
            if branch_type == BranchType.TrueBranch:
                nfo.add_branch(BranchType.FalseBranch, addr + size)
        return nfo
        
    def get_instruction_text(self, data, addr):
        # ana
        size, vals = self.lut.decoders[data[0]]
        assert len(data) >= size
        vals = [decoder(data, addr, size) for decoder in vals]
        # out / outop
        toks = self.lut.text[data[0]]
        return out.render(toks, vals), size

    def get_instruction_low_level_il(self, data, addr, il):
        # ana
        code = data[0]
        size, vals = self.lut.decoders[code]
        if len(data) < size:
            # incomplete code due to disassembling data or missing memory
            return size  # abort further analysis before it errors
        vals = [decoder(data, addr, size) for decoder in vals]
        # sem
        build = llil_mangler.patch_at(self, addr) or self.lut.llil[code]
        size_override = build(il, vals, addr)
        return size_override if size_override != None else size
        
    #def get_flag_condition_low_level_il(self, cond, il):
    #    il.append(il.unimplemented())
    def get_flag_write_low_level_il(self, op, size, write_type, flag,
                                            operands, il):
        # This can't be right; why doesn't it work on its own?
        if 0 and flag == 'c':
            fun = self.get_default_flag_write_low_level_il
            return fun(op, size, FlagRole.CarryFlagRole, operands, il)
        elif 0 and op == LowLevelILOperation.LLIL_RLC:
            #return il.const(0, 1)
            return il.test_bit(1, il.reg(1, operands[0]), il.const(0, 0x80))
        elif 0 and op == LowLevelILOperation.LLIL_RRC:
            #return il.const(0, 1)
            return il.test_bit(1, il.reg(1, operands[0]), il.const(0, 0x01))
        else:
            fun = Architecture.get_flag_write_low_level_il
            retval = fun(self, op, size, write_type, flag, operands, il)
            #log_info('flag_write '+hex(il.current_address)+' | '+repr(retval)+' | '+repr((op, size, write_type, flag, operands, il)))
            return retval

            flag = self.get_flag_index(flag)
            return self.get_default_flag_write_low_level_il(op, size, self._flag_roles[flag], operands, il)
            # default fallback

        if 0 and op == LowLevelILOperation.LLIL_SBB and flag == 'c':
            left, right, carry = operands
            return il.logical_shift_right(1, il.sub(1, left, il.add(1, right, carry)), il.const(1, 8))
        if 0 and flag == 'c':
            fun = self.get_default_flag_write_low_level_il
            return fun(op, size, FlagRole.CarryFlagRole, operands, il)
        if 0:
            fun = self.get_default_flag_write_low_level_il
            return fun(op, size, FlagRole.CarryFlagRole, operands, il)
    
    @specification.lazy_memoized_property
    def lut(self):
        """Look up tables generated once.

        All available architectures are *instantiated* on start, even if never
        used. To be a good neighbour but still get to write fun code, complex
        processing should be deferred until needed using this decorator.
        """

        luts = Tables()
        if 1:  # DEBUG
            urls = [
                ('spu plugin',
            'https://github.com/bambu/binaryninja-spu/blob/master/spu.py'),
                ('nes plugin',
            'https://github.com/Vector35/binaryninja-api/blob/dev/python/examples/nes.py'),
                ('m68k plugin',
            'https://github.com/alexforencich/binaryninja-m68k/blob/master/__init__.py'),
            ]
            md = '## Still Unlifted\n\n' + luts.unlifted
            md += '\n\n## Reference Examples\n\n'
            for title,url in urls:
                md += '- [{0}]({1})\n'.format(title, url)
            binaryninja.show_markdown_report("Architecture Progress", md)
        return luts
        

    def get_associated_arch_by_address(self, addr):
        # Waaait a second. add_branch has an optional 'arch' argument
        #
        # Can I branch from x86 into BPF? Or .NET IL? Or obfs. interpreter
        # uops? In one idb?
        # OMG IF YES TEST TEST TEST THIS omg, there's even a hinter
        #
        # guess this is from arm thumb shenanigans? or 32/64 in general?
        return self, addr

    ##
    ## That from-IDA patching thing them game hackers are so keen on...
    ##

    def always_branch(self, data, addr):
        return # TODO do this, even if that's not how you normally patch
    def convert_to_nop(data, addr):
        return
    def assemble(code, addr):
        # TODO either hand-assemble, or find some nice embeddable asm /w
        # macros and proper labels and stuff? will need to double-check syntax
        # compat
        # also TODO: sdcc 8051 training binary
        return


class Tables:
    def __init__(self):
        elapsed = time.time()

        spec = specification.InstructionSpec()
        self.decoders = spec.refine(ana.operand_decoders)
        self.branches = spec.refine(emu.branch_type)
        self.text = spec.refine(out.tokens)
        self.llil = spec.refine(lowlevelil.low_level_il)

        # FIXME hack until I refactor this a bit:
        self.unlifted = lowlevelil.unlifted_todo(spec.spec, self.llil)
        
        elapsed = time.time() - elapsed
        log_info('Building 8051 tables took %0.3f seconds' % elapsed)
        
