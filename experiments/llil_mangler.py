"""Inlines small helper functions in LLIL, greatly simplifying effects.

Wide operations on 8-bit architectures are often handled via a set of helper
functions sharing a register ABI. This is an experiment in aiding existing
Binja auto-analysis by hiding the architecture-specific weirdness and
pretending the helpers are inlined.

...

To do this it passes state from a BinaryDataNotification registered with a
particular BinaryView, straight into the get_low_level_il(..) of an
Architecture.

This... Is supported for Function and BinaryView objects via .session_data, but
not for LowLevelILFunction since il.source_function isn't initialized at the
time of IL lift, just il.handle is.

Long story short, bad things happened and this code will break horribly if you
open more than one tab or window. If I understood how Architecture worked,
maybe the damage would be limited to the 8051 arch, but w/e right now.
"""
import inspect, ctypes
from binaryninja import BinaryDataNotification
from .. import mem

state = {}

def arch_data(arch):
    """Ghetto replacement for a session_state between BV and Arch."""
    global state
    unique_id = ctypes.addressof(arch.handle.contents)
    if unique_id not in state:
        state[unique_id] = {}
    return state[unique_id]

def register_hook(bv):
    """
    Initializes some global state in a place it shouldn't, and registers an
    analysis hook to fill that state with aptches.
    """
    bv.register_notification(AnalysisNotification(bv))
    bv.add_analysis_completion_event(lambda:fixup_page_trampolines(bv))

def patch_at(arch, addr):
    """Checks global state for stashed LLIL patches."""
    #if addr in self.__class__.session_data:
    #    log_info('## patched in %s at 0x%x' % (repr(build), addr))
    return arch_data(arch).get(addr)

class AnalysisNotification(BinaryDataNotification):
    def __init__(self, view): pass

    def function_added(self, bv, func):
        inline_xref_calls(bv, func)
    def function_updated(self, bv, func):
        inline_xref_calls(bv, func)

    #def function_updated(self, *args):
    #    log_info(inspect.stack()[0][3] + str(args))

def inline_xref_calls(bv, func):
    if func.name in patches:
        patch = patches[func.name]
        for ref in bv.get_code_refs(func.start):
            # TODO ensure it's actually a call being stomped on
            arch_data(func.arch)[ref.address] = patch
            ref.function.reanalyze()  # probably needed to set up xrefs

def patches():
    def xstore_ptr_call(il,vs,ea):
        'x[DPTR] := PTR'
        #'\xeb\xf0\xa3\xea\xf0\xa3\xe9\xf0"'
        il.append(il.call(il.const_pointer(6, vs[0])))  # keep initial call for ptr
        if 1:
            il.append(il.store(1, il.add(6, il.const(6, mem.XRAM + 0), il.reg(2, 'DPTR')), il.reg(1, 'R3')))
            il.append(il.store(1, il.add(6, il.const(6, mem.XRAM + 1), il.reg(2, 'DPTR')), il.reg(1, 'R2')))
            il.append(il.store(1, il.add(6, il.const(6, mem.XRAM + 2), il.reg(2, 'DPTR')), il.reg(1, 'R1')))
        else:
            il.append(il.store(3, il.add(6, il.const(6, mem.XRAM + 0), il.reg(2, 'DPTR')), il.reg(3, 'PTR')))
        il.append(il.set_reg(2, 'DPTR', il.add(2, il.const(1, 1), il.reg(2, 'DPTR'))))
        return 3  # patch call

    def xload_ptr_call(il,vs,ea):
        'PTR := x[DPTR]'
        # '\xe0\xfb\xa3\xe0\xfa\xa3\xe0\xf9"'
        il.append(il.call(il.const_pointer(6, vs[0])))
        if 1:
            il.append(il.set_reg(1, 'R3', il.load(1, il.add(6, il.const(6, mem.XRAM + 0), il.reg(2, 'DPTR')))))
            il.append(il.set_reg(1, 'R2', il.load(1, il.add(6, il.const(6, mem.XRAM + 1), il.reg(2, 'DPTR')))))
            il.append(il.set_reg(1, 'R1', il.load(1, il.add(6, il.const(6, mem.XRAM + 2), il.reg(2, 'DPTR')))))
        else:
            il.append(il.set_reg(3, 'PTR', il.load(3, il.add(6, il.const(6, mem.XRAM + 0), il.reg(2, 'DPTR')))))
        il.append(il.set_reg(2, 'DPTR', il.add(2, il.const(1, 1), il.reg(2, 'DPTR'))))
        return 3

    def read_code_word(il,vs,ea):
        'x[R0:B++] := c[DPTR++]'
        il.append(il.call(il.const_pointer(6, vs[0])))
        dst = il.add(2, il.reg(1, 'R0'), il.shift_left(2, il.reg(1, 'B'), il.const(1, 8)))
        il.append(il.store(1, il.add(6, il.const(6, mem.XRAM), dst), 
                           il.load(1, il.add(6, il.const(6, mem.CODE), il.reg(2, 'DPTR')))))
        il.append(il.set_reg(2, 'DPTR', il.add(6, il.const(6, 1), il.reg(2, 'DPTR'))))
        il.append(il.set_reg(1, 'R0', il.add(6, il.const(6, 1), il.reg(1, 'R0'))))
        return 3

    return locals()
patches = patches()
patches = {patches[name].__doc__:patches[name] for name in patches}
# oh my god did I just write Javascript to avoid OOP, ugggghhggh

def fixup_page_trampolines(bv):
    def jump_page(page):
        def page_trampoline(il,vs,ea):
            target = il.add(6, il.const(6, mem.CODE + 0x8000 * page), il.reg(2, 'DPTR'))
            il.append(il.call(target))  
            # TODO figure out if there's a way to force jump to create functions
            #il.set_indirect_branches([target])  # <- this ain't it
            return 3  # patch ljmp
        return page_trampoline

    # TODO find these by searching for P1.{0,1} writes iff works well
    # TODO or at least move pointers to Surface bv and have it push 'em
    # '\xc0\x08t5\xc0\xe0\xc0\x82\xc0\x83u\x08\n\xc2\x90\xc2\x91"'  # page 0
    trampolines = {0:0x3500, 1:0x3512, 2:0x3524, 3:0x3536}   # note exact stride
    added = 0
    for page in trampolines:
        for ref in bv.get_code_refs(trampolines[page]):
            mailbox = arch_data(bv.arch)
            if ref.address not in mailbox:
                mailbox[ref.address] = jump_page(page)
                ref.function.reanalyze()
                added += 1
    print ('Trampoline LLIL patch found %d new paged calls.' % (added,))
    if added:  # recurse until no new branches discovered?
        # TODO don't think it's triggering recursively, bummer
        # for now:
        # > from i8051.experiments import llil_mangler
        # > llil_mangler.fixup_page_trampolines(bv)
        bv.add_analysis_completion_event(lambda:fixup_page_trampolines(bv))
