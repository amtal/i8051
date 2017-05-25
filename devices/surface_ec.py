import struct, traceback
from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, Endianness
from binaryninja.log import log_info, log_error
from .. import mem
from ..binaryview import Family8051View
from ..experiments import llil_mangler

class SurfaceECView(Family8051View):
    name = "Surface EC"
    long_name = "Surface EC WIP"

    def __init__(self, data):
        Family8051View.__init__(self, data)
        llil_mangler.register_hook(self)

    def init(self):
        #assert self.perform_read(0x000E, 8) == 'UMHD0004'
        try:
            super(SurfaceECView, self).init()

            seg_f = SegmentFlag
            rw_ = seg_f.SegmentReadable | seg_f.SegmentWritable
            r_xc = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
                    seg_f.SegmentContainsCode)
            r__d = seg_f.SegmentReadable | seg_f.SegmentContainsData


            image_base = 0x0182b  # probably signature before
            # bootloader @ first 0x2000, then this stub
            self.add_auto_segment(mem.CODE+0x2000, 0x6000, 
                                           image_base, 0x6000, r_xc)
            for page in range(4):  # then 4 pages for high half of code
                self.add_auto_segment(mem.CODE+0x8000 + 0x8000*page, 0x8000, 
                                      image_base + 0x6000 + 0x8000 * page, 0x8000, r_xc)
                self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol, 
                                        mem.CODE+0x8000+0x8000*page, 'page_%d' % page))
                self.add_function(mem.CODE+0x8000*(page+1))

            def isr(name, ea):
                self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol, 
                                        mem.CODE+ea, 'isr__'+name))
                self.add_function(mem.CODE+ea)
            #isr('reset', 0x0000)
            #isr('good_entry', 0x6000)

            #isr('IE0', 0x03)
            #isr('TF0', 0x0B)
            #isr('unknown', 0x5B)


            # There's six sequential jump tables, used by functions that call
            # jump_R1:2.
            try:
                base = 0x45eb  # TODO pull from functions using them?
                for i in range(6):
                    self.define_auto_symbol(Symbol(SymbolType.DataSymbol, 
                                            mem.CODE+base, 'jump_table_'+str(i)))
                    self.define_user_data_var(mem.CODE+base,
                            self.parse_type_string('void*[16]')[0])
                    for ea in range(base, base + 16 * 2, 2):
                        fp = struct.unpack('>H', self.read(ea, 2))[0]
                        fp += mem.CODE
                        self.add_function(fp)
                    base += 16 * 2
            except:
                log_error(traceback.format_exc())
                log_error("Function table markup aborted.")

            # Flash bank swapping trampolines at 0x3500, refs to them between
            # 0x3548 first one
            # 0x3ff8 last one
            # TODO: autodiscover this region with an instruction regex?
            try:
                for ea in range(0x3548, 0x3ff8+6, 6):
                    if (self.read(ea, 1) != '\x90' or
                        self.read(ea+3, 1) != '\x02'):
                        msg = 'Bad instruction in trampoline jump at '+hex(ea)
                        raise RuntimeError(msg)
                    self.add_function(ea)
            except:
                log_error(traceback.format_exc())
                log_error("Flash bank trampoline reference markup aborted.")


            return True
        except:
            log_error(traceback.format_exc())
            return False

    @classmethod
    def is_valid_for_data(self, data):
        if data.read(0xA1 + 8, 5) != '\xa0\x03\x02\x01\x02':
            return False  # first element, integer, version number
        der_cert = data.read(0xA1, 1374)
        return der_cert.find('Surface Firmware Signing') != -1

    def perform_get_entry_point(self):
        return 0x2000  # as long as it's not 0

SurfaceECView.register()
