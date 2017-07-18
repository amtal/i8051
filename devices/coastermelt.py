import struct, traceback
from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, Endianness
from binaryninja.log import log_info, log_error
from .. import mem
from ..binaryview import Family8051View
from ..experiments import llil_mangler

class CoastermeltUSBView(Family8051View):
    """See @scanlime's coastermelt git repo for docs.

    Assumes you've already carved the image out. There's two identical ones in
    the firmware upgrade referenced in backdoor/Makefile (original link is
    dead, but there's plenty of mirrors) as described in doc/cpu-8051.txt and
    doc/multiprocessor.txt
    """
    name = "coastermelt USB processor"
    long_name = "USB coproc in SE-506CB BD Writer"

    xram_size = 0x9000  # TODO probably less, TODO do MMIO right

    @classmethod
    def is_valid_for_data(self, data):
        return data.read(0x60, 0x20) == 'MoaiEasterIslandThomasYoyo(^o^)/'

    def perform_get_entry_point(self):
        return 0

    def load_memory(self):
        super(CoastermeltUSBView, self).load_memory()

        seg_f = SegmentFlag
        rw_ = seg_f.SegmentReadable | seg_f.SegmentWritable
        r_xc = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
                seg_f.SegmentContainsCode)
        r__d = seg_f.SegmentReadable | seg_f.SegmentContainsData


        self.add_auto_segment(mem.CODE+0x0000, 0x2000, 
                                       0x0000, 0x2000, r_xc)

    def load_symbols(self):
        super(CoastermeltUSBView, self).load_symbols()

        def isr(name, ea):
            self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol,
                                    mem.CODE+ea, 'isr__'+name))
            self.add_function(mem.CODE+ea)
        isr('ext0', 0)
        isr('timer_ctr_0', 0x03)
        isr('ext1', 0x13)

    def load_patches(self):
        super(CoastermeltUSBView, self).load_patches()

CoastermeltUSBView.register()
