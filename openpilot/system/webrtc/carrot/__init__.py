"""Self-contained Carrot Vision WebRTC variant.

Carried as its own package instead of patching the upstream `webrtcd` module:
the two share no code (upstream moved to ThreadingHTTPServer + teleoprtc
tracks, Carrot Vision runs an aiohttp app with its own session lifecycle), and
the encoder-side sockets differ on this fork (road -> narrow road). Nothing
here is imported by upstream webrtc paths.
"""
