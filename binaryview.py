import struct
import traceback
from binaryninja.architecture import Architecture
from binaryninja.binaryview import BinaryView
from binaryninja.types import Symbol
from binaryninja.enums import SymbolType, SegmentFlag, Endianness
from binaryninja.log import log_info, log_error
from . import mem

class Family8051View(BinaryView):
    """
    Let's review the memory model and its common uses, to better understand
    the choice between lifting register/memory accesses.
   
    All registers are mapped within the 256 byte internal RAM, and can be
    accessed using the direct addressing mode. The layout starts roughly as:

sz:  range:    contents:
08h  00..07h   R0-R7, register bank 0
18h  08..1Fh   register banks 1..3, also stack location after reset
10h  20..2Fh   bit-addressable region, via /bit syntax
50h  30..7Fh   free-to-use memory (early part is bit-addressable TODO mark iit)
80h  80..FFh   Special Function Registers, accessible via [mem] but not @R0/R1
80h  80..FFh   parallel chunk of internal RAM, accessible via @R0/@R1 only
               (can the stack be relocated here? presumably push/pop still work)

   -0  -1  -2  -3  -4  -5  -6  -7  -8   -9   -A  -B  -C  -D  -E  -F
8-[P0 ]SP  DPL DPH -   -   -   -  [TCON]TMOD TL0 TL1 TH0 TH1 -   -
9-[P1 ]-   -   -   -   -   -   -  [SCON]SBUF -   -   -   -   -   -
A-[P2 ]-   -   -   -   -   -   -  [IE  ]-    -   -   -   -   -   -
B-[P3 ]-   -   -   -   -   -   -  [IP  ]-    -   -   -   -   -   -
C-[-  ]-   -   -   -   -   -   -  [-   ]-    -   -   -   -   -   -
D-[PSW]-   -   -   -   -   -   -  [-   ]-    -   -   -   -   -   -
E-[A  ]-   -   -   -   -   -   -  [-   ]-    -   -   -   -   -   -
F-[B  ]-   -   -   -   -   -   -  [-   ]-    -   -   -   -   -   -

    The above is extended or changed by hardware, lots. See e.g. Table 6 
    in DS_1215F_003 (73S1215F Data Sheet) from Maxim. Bit-addressable
    SFR registers are [highlighted].

sz:  range:    dir   indir
08h  00..07h   IRAM
18h  08..1Fh   IRAM
10h  20..2Fh   IRAM
50h  30..7Fh   IRAM
80h  80..FFh   SFRs  IRAM
               

    """
    name = "8051"
    long_name = "Intel 8051 Family"

    xram_size = 0x10000  # initial assumption, override if desired

    @classmethod
    def is_valid_for_data(self, data):
        """Override this with a test for the file format you're loading.

        It's common to find chunks of 8051 firmware embedded in distant devices
        and memory spaces, with no context for what runs it or how it's loaded.

        An .ihex loader/editor would be cool, but random carved .bin is likely.
        """
        # example at: https://github.com/adamcritchley/binjaarmbe8
        return False  # this class is meant to be extended, not used directly

    def load_memory(self):
        """Creates basic IRAM/XRAM/SFR memory spaces required by the lifter.

        Extend with CODE loading for your particular image.

        XRAM is assumed to be the maximum possible size - override xram_size if
        you want more precision.
        """
        rw = (SegmentFlag.SegmentReadable | 
              SegmentFlag.SegmentWritable)

        # The indirect-access part of the IRAM (reachable via @R0, @R1,
        # push/pop, and DMA peripheral) is kept continuous with the
        # direct-access portion. SFRs are pushed off to a separate region 
        # given how special they are.
        # I think this will simplify the lift implementation compared to other
        # possible layouts.
        self.add_auto_segment(mem.IRAM, 0x100, 0, 0, rw)
        self.add_auto_section('.register_banks',        mem.IRAM + 0x00, 0x20)
        self.add_auto_section('.data_bitwise_access',   mem.IRAM + 0x20, 0x10)
        self.add_auto_section('.data',                  mem.IRAM + 0x30, 0x50)
        self.add_auto_section('.data_indirect_only',    mem.IRAM + 0x80, 0x80)

        # Provide nice markup for stuff like `pop 0h; pop 1h; pop 2h; pop 3h`
        # Sometimes, anyway. For some reason symbols aren't always created?
        bank_t = self.platform.parse_types_from_source('''
            struct register_bank __packed{uint8_t R[8];}; 
            /* register_bank bank[4]; */
        ''').types['register_bank']
        for index, ea in enumerate(range(mem.IRAM+0x00, mem.IRAM+0x20, 0x08)):
            name = 'RB%s' % (index,)
            self.define_auto_symbol(Symbol(SymbolType.DataSymbol, ea, name))
            self.define_user_data_var(ea, bank_t)


        # The SFR region is accessible directly within the address range
        # 0x80..0xff. The mem.SFRs offset is a type tag only; for example,
        # the accumulator is at address 0xe0, which is (mem.SFRs+0xe0) in the
        # flattened memory map. That's | what this addition is for. I think
        # that makes sense?            V
        self.add_auto_segment(mem.SFRs + 0x80, 0x80, 0, 0, rw)
        self.add_auto_section('.special_function_registers', 
                                mem.SFRs + 0x80, 0x80)

        self.add_auto_segment(mem.XRAM, self.xram_size, 0, 0, rw)
        self.add_auto_section('.xram', mem.XRAM, self.xram_size)

    def load_symbols(self):
        """Names common special function registers."""
        def sfr(addr, name, bit_addr_ok=0):
            sym = Symbol(SymbolType.DataSymbol, mem.SFRs + addr, name)
            self.define_auto_symbol(sym)
            t = self.parse_type_string('uint8_t foo')[0]
            self.define_user_data_var(mem.SFRs + addr, t)
        # TODO if this works parse it from an ASCII diagram
        # or at least add comments

        for ea in mem.regs:
            sfr(ea - mem.SFRs, mem.regs[ea], 1)
            # BinaryView can't add comments - huh?
            # Well, so much for the plan of warning about inconsistent lack of
            # xrefs. Magic, ho!
            
        ## TODO: this is probably worth piggybacking on top of mem.regs
        #sfr(0xe0, 'A', 1)  # not ACC, that's stupid
        #sfr(0xf0, 'B', 1)
        sfr(0xd0, 'PSW', 1)
        #sfr(0x81, 'SP')
        #sfr(0x82, 'DPL'); sfr(0x83, 'DPH')
        sfr(0x80, 'P0', 1); sfr(0x90, 'P1', 1)
        sfr(0xa0, 'P2', 1); sfr(0xb0, 'P3', 1)
        sfr(0xb8, 'IP', 1); sfr(0xa8, 'IE', 1)
        sfr(0x89, 'TMOD')
        sfr(0x88, 'TCON', 1)
        sfr(0xc8, 'T2CON', 1) # 8052 only
        sfr(0x8c, 'TH0'); sfr(0x8a, 'TL0')
        sfr(0x8d, 'TH1'); sfr(0x8b, 'TL1')
        # 8052 only:
        sfr(0xcd, 'TH2'); sfr(0xcc, 'TL2')
        sfr(0xcb, 'RCAP2H'); sfr(0xca, 'RCAP2L')
        # back to 8051
        sfr(0x98, 'SCON', 1)
        sfr(0x99, 'SBUF')
        sfr(0x87, 'PCON')

    def load_patches(self):
        """Insert patches into architecture internals here.

        The default does nothing; you probably want to catch
        AnalysisNotification events and insert patches via low-level hooks.
        """
        pass

    def perform_get_entry_point(self):
        """Will need an override if booting from unknown ROM."""
        ep = 0 # reset vector
        return ep

    def perform_is_executable(self):
        return True # eh sure

    def init(self):
        try:
            self.load_memory()
            self.load_symbols()
            self.load_patches()
            return True
        except:
            log_error(traceback.format_exc())
            return False

    def __init__(self, data):
        BinaryView.__init__(self, parent_view=data, file_metadata=data.file)
        # not sure what this is for, copied from somewhere:
        self.platform = Architecture['8051'].standalone_platform

        # See https://github.com/Vector35/binaryninja-api/issues/645
        # This ensures endianness is propagated; not a huge deal.
        # While SFRs are arranged in LE order, compilers often store things in
        # BE order. May be worth having 8051-LE and 8051-BE archs in the
        # future.
        self.arch = Architecture['8051']

        # Don't think this package uses them - leaving them for easy access
        # from REPL.
        self.CODE = mem.CODE
        self.SFRs = mem.SFRs
        self.IRAM = mem.IRAM
        self.XRAM = mem.XRAM
