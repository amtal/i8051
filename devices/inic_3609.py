from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag
from .. import mem
from ..binaryview import Family8051View

class Initio3609(Family8051View):
    """

    """
    name = "INIC-3609"
    long_name = "Initio INIC-3609 USB-to-SATA"

    xram_size = 0x10000 # at least 0xc01c is mapped

    @classmethod
    def is_valid_for_data(self, data):
        """Holds for some random firmware images I found.

        Pulled from FANTEC_ER_U3_Firmware.zip:
        - Silicon-power_3609_3940_fw_v306RC01.bin
        - YuanJi_3609_3940_fw_v313.bin
        """
        if data.read(0xF030, 0x9) != 'INIC-3609':
            return False
        # don't know how to do this in BinaryView.init, doing it here:
        self.nullpad = 32
        while data.read(0x7c00 - self.nullpad, 32) == 32 * '\x00':
            self.nullpad += 32
        return True

    def perform_get_entry_point(self):
        return 0

    def load_memory(self):
        """The images I've got have a fair bit of empty space.

            File offsets:
        0x0000 unknown header
        0x0020 null-padded code @0x0000
        0x7c20 small config region breaking up padding
        0x7e20 null pad ends, ff-pad begins
        0x7fde 16-bit checksum
        0x7fe0 resume ff-pad
        0xf000 small config region, similar to last
        0xfffc 32-bit checksum

        Going to avoid loading pads to minimize impact of mis-disassembly
        causing UI-killing 'mov R7, A' * 1000 functions. Not the correct fix,
        just something worth trying. Plus, keeps scroll bar useful until such a
        time as fancy ones are added.
        """
        super(Initio3609, self).load_memory()

        seg_f = SegmentFlag
        r__ = seg_f.SegmentReadable
        rw_ = seg_f.SegmentReadable | seg_f.SegmentWritable
        r_x = (seg_f.SegmentReadable | seg_f.SegmentExecutable |
                seg_f.SegmentContainsCode)

        self.add_auto_segment(mem.CODE+0x0000, 0x7c00 - self.nullpad, 
                                       0x0020, 0x7c00 - self.nullpad, r_x)
        self.add_auto_segment(mem.CODE+0x7c00, 0x0090, 0x7c20, 0x0090, r__)
        self.add_auto_segment(mem.CODE+0x7fbe, 0x0002, 0x7fde, 0x0002, r__)
        self.add_auto_segment(mem.CODE+0xf000, 0x0090, 0xf000, 0x0090, r__)
        # last one is misplaced - doubt the 0x20 offset applies

    def load_symbols(self):
        super(Initio3609, self).load_symbols()

        def isr(name, ea):
            self.define_auto_symbol(Symbol(SymbolType.FunctionSymbol,
                                           mem.CODE+ea, name))
            self.add_function(mem.CODE+ea)
        isr('isr_ext0', 0)
        isr('isr_timer_ctr_0', 0x03)
        isr('isr_unknown_0', 0x0b)  # not bothering to name these right
        isr('isr_unknown_1', 0x0e)  # (yet)
        isr('isr_ext1', 0x13)

    def load_patches(self):
        super(Initio3609, self).load_patches()

Initio3609.register()
