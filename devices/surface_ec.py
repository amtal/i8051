import traceback
from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, Endianness
from binaryninja.enums import SectionSemantics
from binaryninja.log import log_info, log_error
from .. import mem
from ..binaryview import Family8051View
from ..experiments import llil_mangler

class SurfaceECView(Family8051View):
    name = "Surface EC"
    long_name = "Surface EC WIP"

    @classmethod
    def is_valid_for_data(self, data):
        if data.read(0xA1 + 8, 5) != b'\xa0\x03\x02\x01\x02':
            return False  # first element, integer, version number
        der_cert = data.read(0xA1, 1374)
        return der_cert.find(b'Surface Firmware Signing') != -1

    def perform_get_entry_point(self):
        return 0x2000  # as long as it's not 0

    def load_memory(self):
        super(SurfaceECView, self).load_memory()

        seg_f = SegmentFlag
        rw_ = seg_f.SegmentReadable | seg_f.SegmentWritable
        r_xc = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
                seg_f.SegmentContainsCode)
        r__d = seg_f.SegmentReadable | seg_f.SegmentContainsData


        image_base = 0x0182b  # probably signature before
        # bootloader @ first 0x2000, then this stub
        self.add_auto_segment(mem.CODE+0x2000, 0x6000, 
                                       image_base, 0x6000, r_xc)
        self.add_auto_section('.code', mem.CODE+0x2000, 0x6000, 
                SectionSemantics.ReadOnlyCodeSectionSemantics)
        for page in range(4):  # then 4 pages for high half of code
            self.add_auto_segment(mem.CODE+0x8000 + 0x8000*page, 
                    0x8000, image_base + 0x6000 + 0x8000 * page, 0x8000, r_xc)
            self.add_auto_section('.page%d' % page, 
                    mem.CODE+0x8000+0x8000*page, 0x8000,
                    SectionSemantics.ReadOnlyCodeSectionSemantics)
            self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol, 
                                    mem.CODE+0x8000+0x8000*page, 'page_%d' % page))
            self.add_function(mem.CODE+0x8000*(page+1))

    def load_symbols(self):
        super(SurfaceECView, self).load_symbols()
        # There's six sequential jump tables, used by functions that call
        # jump_R1:2.
        base = 0x45eb  # TODO pull from functions using them?
        for i in range(6):
            self.define_auto_symbol(Symbol(SymbolType.DataSymbol, 
                                    mem.CODE+base, 'jump_table_'+str(i)))
            self.define_user_data_var(mem.CODE+base,
                    self.parse_type_string('void*[16]')[0])
            for ea in range(base, base + 16 * 2, 2):
                fp = int.from_bytes(self.read(ea, 2), 'big')
                fp += mem.CODE
                self.add_function(fp)
            base += 16 * 2

        # Flash bank swapping trampolines at 0x3500, refs to them between
        # 0x3548 first one
        # 0x3ff8 last one
        # TODO: autodiscover this region with an instruction regex?
        for ea in range(0x3548, 0x3ff8+6, 6):
            if (self.read(ea, 1) != '\x90' or
                self.read(ea+3, 1) != '\x02'):
                msg = 'Bad instruction in trampoline jump at '+hex(ea)
                raise RuntimeError(msg)
            self.add_function(ea)

    def load_patches(self):
        super(SurfaceECView, self).load_patches()
        # TODO move EC-specific hooks out of llil_mangler during refactor

    def __init__(self, data):
        super(SurfaceECView, self).__init__(data)
        llil_mangler.register_hook(self)

SurfaceECView.register()
