- the python OO model is a fairly thin wrapper around the C model
    - scratch it, and you find that in BN, architectures are these static monolithic things
- low-level devices often aren't, and often see extensions/customization

- these are handled in BinaryView, you need to subclass it for your device
    - (SFR names/firmware image loading/entry points)
- compiler differences miiight be doable via just calling conventions
    - TODO
- but then there's still weirdness left (banking via SFRs, pop retaddr)

- so, Architecture exposes a pile of hooks that BinaryView can hit
    - BinaryView does auto-analysis specific to target device, applies patches
      at IL or disassembly levels! Woo correct code!
    - BinaryDataNotification analysis feeds patches into hooks
        - marks xrefs for re-analysis once patches are inserted
    - Since Architecture is a singleton, this does mean that you can't
      disassemble two things in one process. Eggs, omelette.
