import re
from binaryninja.enums import BranchType as BT
from . import ana_op

def branch_type(size, name, _):
    """Everything needed for perform_get_instruction_info(..)

    (..) -> [(size, branch)]
      where
        branch :: None | (BranchType, target_parser | 0)
        target_parser :: (code, addr, size) -> ea
    """
    if re.match('cjne|djnz|jbc|jn?[bcz]$', name):
        # All branches are signed relative on the last byte.
        # (There may be a decrement-me byte in the middle.) 
        return size, (BT.TrueBranch, ana_op.rel)

    return size, {
        'sjmp': (BT.UnconditionalBranch, ana_op.rel),
        'ajmp': (BT.UnconditionalBranch, ana_op.addr11),
        'ljmp': (BT.UnconditionalBranch, ana_op.addr16),
        # @A+DPTR, another jump table sign
        'jmp': (BT.UnresolvedBranch, 0),
        # TODO watch for targets that POP DPL; POP DPH
        'acall': (BT.CallDestination, ana_op.addr11),
        'lcall': (BT.CallDestination, ana_op.addr16),
        'ret': (BT.FunctionReturn, 0),
        'reti': (BT.FunctionReturn, 0),
        # Going to handle 'reserved' as a silent return until I figure out
        # TODO the right way to flag unimpl. instruction for manual review.
        'reserved': (BT.FunctionReturn, 0),
    }.get(name, None)
