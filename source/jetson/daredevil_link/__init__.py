"""Jetson-side link to the Daredevil bracelets.

- daredevil_link.protocol : frame format, encoder, parser (pure Python, no deps)
- daredevil_link.bracelet : USB serial transport (needs pyserial)

Nothing is imported here so that protocol.py stays usable without pyserial.
"""
