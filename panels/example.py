import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from KlippyGtk import KlippyGtk
from KlippyGcodes import KlippyGcodes

class ExamplePanel:
    _screen = None
    labels = {}

    def __init__(self, screen):
        self._screen = screen


    def initialize(self, panel_name):
        # Create gtk items here

    def get(self):
        # Return gtk item
        return self.grid
