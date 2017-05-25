from __future__ import absolute_import
from binaryninja import Architecture, BinaryViewType
from .architecture import MCS51
from .binaryview import Family8051View
from .experiments.calling_conventions import SDCCCall, KeilCall, IARCall
from .experiments.calling_conventions import YoloCall
from .devices import surface_ec  # .register() inside until stabilized

__version__ = '0.0.0'
__all__ = ['MCS51']

MCS51.register()
Family8051View.register()

if 1:
    # experimental, not sure how useful it is yet
    arch = Architecture['8051']
    arch.register_calling_convention(SDCCCall(arch))
    arch.register_calling_convention(KeilCall(arch))
    arch.register_calling_convention(IARCall(arch))
    arch.register_calling_convention(YoloCall(arch))

    arch.standalone_platform.default_calling_convention = YoloCall(arch)
    arch.standalone_platform.system_calling_convention = YoloCall(arch)
