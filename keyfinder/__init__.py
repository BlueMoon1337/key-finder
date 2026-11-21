"""KeyFinder: a practice tool for musicians - key, tempo and chord detection,
stem separation, pitch shifting and speed control."""

__version__ = "1.4.0"

# What the interface can count on from this engine. Raise it when the engine changes in a way an
# older interface can't work with, or a newer one needs (an endpoint added, renamed or reshaped):
# update packages carry only the interface, and KeyFinder refuses one that needs a newer engine
# than the one installed. Engines from before this number count as 1.
ENGINE_API = 1
