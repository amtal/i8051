from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, SectionSemantics
from .. import mem
from ..binaryview import Family8051View

class VL811View(Family8051View):
    """There's no docs lol"""
    name = "VL811"
    long_name = "VIA VL811 USB 3.0 hub"

    xram_size = 0x10000  # largest addr seen: 0x7037

    @classmethod
    def is_valid_for_data(self, data):
        """USB descriptor makes a poor magic value, but there's little else."""
        return data.read(0x3fa2, 25) == 'VIA Labs, Inc'.encode('utf-16-le')

    def perform_get_entry_point(self):
        return 0

    def load_memory(self):
        """No idea what the 32-byte header is, mostly 0s anyway."""
        super().load_memory()
        seg_f = SegmentFlag
        r_x = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
               seg_f.SegmentContainsCode)
        self.add_auto_section('.code', mem.CODE+0x0000, 0x4000, 
                SectionSemantics.ReadOnlyCodeSectionSemantics)
        self.add_auto_segment(mem.CODE+0x0000, 0x4000, 
                                       0x0020, 0x4000, r_x)

    def load_symbols(self):
        super().load_symbols()

        def isr(name, ea):
            self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol,
                                           mem.CODE+ea, name))
            self.add_function(mem.CODE+ea)
        # these prooobably aren't actually reset vectors
        # dunno where the entry points are, presumably a table somewhere
        isr('isr_ext0', 0)
        isr('isr_timer_ctr_0', 0x03)
        isr('isr_probably_not_an_isr', 0x1d)
        # w/e ship it

    def load_patches(self):
        super().load_patches()

VL811View.register()
