"""
The 8-bit type zoo isn't contained within type-agnostic calling convention,
but let's give it a go and see what binja does.

Good overview of compiler differences: 
    http://www.bound-t.com/doc-archive/an-8051-v2.pdf
"""
from binaryninja.callingconvention import CallingConvention

class YoloCall(CallingConvention):
    """Throwing things at the wall to see what works."""
    name = "yolo"
    int_arg_regs   = ['DPTR', 'Y0', 'Y4']
    int_return_reg = 'Y4'
    high_int_return_reg = 'Y0'
    # aand I'm out of return registers

    # maybe if I mark R1-R4 as caller-restored, it'll recognize they're dirty
    # on return?
    caller_saved_regs = ['A', 'B']

class SDCCCall(CallingConvention):
    name = "sdcc"
    int_arg_regs   = ['DPL', 'DPH', 'B', 'A']
    int_return_reg = 'DPL' # DPH, B, A if it's 2 to 4 bytes, but w/e
    caller_saved_regs = (['DPL', 'DPH', 'B', 'A'] + 
                         ['R'+str(n) for n in range(8)])

class KeilCall(CallingConvention):
    """Just going to try to implement the 'common' 1-byte argument case?"""
    name = "keil"
    # 1-byte args
    int_arg_regs   = ['R7', 'R5', 'R3']
    # 2-byte use T6, T4, T2
    # pointers are 3-byte in R1:3, dwords in Y4
    int_return_reg = 'R7' # C if just a bit flag, but w/e
    # 2 bytes in T6, 4 in Y4, pointer in R1:3
    caller_saved_regs = (['DPL', 'DPH', 'B', 'A'] +  
                         # should add PSW to this too
                         # once it's registerized
                         ['R'+str(n) for n in range(8)]) 

class IARCall(CallingConvention):
    """R6:7 is callee-saved, but otherwise relies on stack and IRAM storage"""
    name = "iar"
    # DPTR might also be calee-saved
    caller_saved_regs = (['B', 'A'] +  'R0 R1 R2 R3 R4 R5'.split())

