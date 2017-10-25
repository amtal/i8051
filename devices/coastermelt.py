from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, SectionSemantics
from .. import mem
from ..binaryview import Family8051View

class CoastermeltUSBView(Family8051View):
    """See @scanlime's coastermelt git repo for docs.

    Loader assumes you've already carved the image out of the larger update. 
    - See backdoor/Makefile for the main firmware image - original link is
      dead, but there's plenty of sketchy driver mirrors. 
    - See doc/multiprocessor.txt and doc/cpu-8051.txt for location in overall
      image, and integration with the rest of the SoC. Code for both contained
      payloads is the same except for a few bytes at the end. :)
    """
    name = "coastermelt-8051"
    long_name = "SE-506CB SoC 8051"

    xram_size = 0xe00  # we'll be loading manually, this is ignored

    @classmethod
    def is_valid_for_data(self, data):
        """Fun fact: at least one of these strings is transmitted, but not by
        reference. Looks like the compiler emitted it in the string table, but
        inlined constants rather than wasting instructions loading them."""
        return data.read(0x60, 0x20) == 'MoaiEasterIslandThomasYoyo(^o^)/'

    def perform_get_entry_point(self):
        return 0

    def load_memory(self):
        # Going to load manually to set up only memory that sees use.
        #super(CoastermeltUSBView, self).load_memory()
        seg_f = SegmentFlag
        rw_ = seg_f.SegmentReadable | seg_f.SegmentWritable
        r_x = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
                seg_f.SegmentContainsCode)
        sem_rwd = SectionSemantics.ReadWriteDataSemantics

        self.add_auto_segment(mem.IRAM, 0x80, 0, 0, rw_)
        self.add_auto_section('.registers',     mem.IRAM + 0x00, 0x20, sem_rwd)
        self.add_auto_section('.bits',          mem.IRAM + 0x20, 0x10, sem_rwd)
        self.add_auto_section('.data',          mem.IRAM + 0x30, 0x50, sem_rwd)

        self.add_auto_segment(mem.SFRs + 0x80, 0x80, 0, 0, rw_)
        self.add_auto_section('.special_function_registers', 
                              mem.SFRs + 0x80, 0x80, sem_rwd)

        self.add_auto_segment(mem.XRAM + 0x4000, 0x0e00, 0, 0, rw_)
        self.add_auto_section('.xram_and_mmio', 
                              mem.XRAM + 0x4000, 0x0e00, sem_rwd)

        # Only portion loaded from firmware file.
        self.add_auto_segment(mem.CODE+0x0000, 0x2000, 
                                       0x0000, 0x2000, r_x)
        self.add_auto_section('.code', mem.CODE+0x0000, 0x2000, 
                SectionSemantics.ReadOnlyCodeSectionSemantics)

    def load_symbols(self):
        super(CoastermeltUSBView, self).load_symbols()

        def isr(name, ea):
            self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol,
                                           mem.CODE+ea, name))
            self.add_function(mem.CODE+ea)
        isr('isr_ext0', 0)
        isr('isr_timer_ctr_0', 0x03)
        isr('isr_ext1', 0x13)
        isr('no_calls_to_this_hmm', 0x1b14)

    def load_patches(self):
        super(CoastermeltUSBView, self).load_patches()

CoastermeltUSBView.register()
