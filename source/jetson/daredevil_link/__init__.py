"""Jetson-side link to the Daredevil bracelets.

- daredevil_link.protocol  : frame format, encoder, parser (pure Python, no deps)
- daredevil_link.bracelet  : Bracelet (one wrist, over any transport), find_bracelets (USB)
- daredevil_link.transport : Transport interface, SerialTransport (needs pyserial)
- daredevil_link.udp       : UdpHub (Wi-Fi discovery and routing), UdpTransport

Nothing is imported here so that the package stays usable without pyserial.
"""
