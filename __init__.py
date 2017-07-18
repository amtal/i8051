from __future__ import absolute_import
from binaryninja import Architecture, BinaryViewType
from .architecture import MCS51
from .binaryview import Family8051View
from .experiments.calling_conventions import SDCCCall, KeilCall, IARCall
from .experiments.calling_conventions import YoloCall
from .devices import surface_ec, coastermelt  # self-.register() for now

__version__ = '0.0.0'
__all__ = ['MCS51']

MCS51.register()
Family8051View.register()

if 1:
    # experimental, not sure how useful it is yet
    arch = Architecture['8051']
    def reg_cc(cls):  # API change?
        cc = cls(arch, cls.name)
        arch.register_calling_convention(cc)
    [reg_cc(cc) for cc in [SDCCCall, KeilCall, IARCall, YoloCall]]

    yolo_cc = YoloCall(arch, YoloCall.name)
    arch.standalone_platform.default_calling_convention = yolo_cc
    arch.standalone_platform.system_calling_convention = yolo_cc
