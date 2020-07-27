#!/usr/bin/python

import gi
import time
import threading

import json
import requests
import websocket
import logging
import os

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from KlippyWebsocket import KlippyWebsocket
from KlippyGtk import KlippyGtk
from panels import *

logging.basicConfig(filename="/tmp/KlipperScreen.log", level=logging.INFO)

klippersreendir = os.getcwd()
config = klippersreendir + "/KlipperScreen.config"
logging.info("Config file: " + config)

class KlipperScreen(Gtk.Window):
    """ Class for creating a screen for Klipper via HDMI """
    currentPanel = None
    bed_temp_label = None
    number_tools = 1

    panels = {}
    _cur_panels = []
    filename = ""
    subscriptions = []
    last_update = {}

    def __init__(self):
        self.read_config()
        self.init_style()
        Gtk.Window.__init__(self)

        self.set_default_size(Gdk.Screen.get_width(Gdk.Screen.get_default()), Gdk.Screen.get_height(Gdk.Screen.get_default()))
        logging.info(str(Gdk.Screen.get_width(Gdk.Screen.get_default()))+"x"+str(Gdk.Screen.get_height(Gdk.Screen.get_default())))

        self.printer_initializing()

        ready = False

        while ready == False:
            r = requests.get("http://127.0.0.1:7125/printer/info") #, headers={"x-api-key":api_key})
            if r.status_code != 200:
                time.sleep(1)
                continue

            data = json.loads(r.content)

            if data['result']['is_ready'] != True:
                time.sleep(1)
                continue
            ready = True

        status_objects = [
            'idle_timeout',
            'configfile',
            'toolhead',
            'virtual_sdcard'
        ]
        r = requests.get("http://127.0.0.1:7125/printer/objects/status?" + "&".join(status_objects))
        self.create_websocket()

        requested_updates = {
            "toolhead": [],
            "virtual_sdcard": [],
            "heater_bed": [],
            "extruder": []
        }

        #TODO: Check that we get good data
        data = json.loads(r.content)
        for x in data:
            self.last_update[x] = data[x]

        self.printer_config = data['result']['configfile']['config']
        self.read_printer_config()

        if data['result']['toolhead']['status'] == "Printing" and data['result']['virtual_sdcard']['is_active'] == True:
            self.printer_printing()
        else:
            self.printer_ready()

        while (self._ws.is_connected() == False):
            continue

        self._ws.send_method(
            "post_printer_objects_subscription",
            requested_updates
        )


    def read_printer_config(self):
        logging.info("### Reading printer config")
        self.toolcount = 0
        self.extrudercount = 0
        for x in self.printer_config.keys():
            if x.startswith('extruder'):
                if x.startswith('extruder_stepper') or "shared_heater" in self.printer_config[x]:
                    self.toolcount += 1
                    continue
                self.extrudercount += 1

        logging.info("### Toolcount: " + str(self.toolcount) + " Heaters: " + str(self.extrudercount))

    def show_panel(self, panel_name, type, remove=None, pop=True, **kwargs):
        if remove == 2:
            self._remove_all_panels()
        elif remove == 1:
            self._remove_current_panel(pop)

        if panel_name not in self.panels:
            if type == "SplashScreenPanel":
                self.panels[panel_name] = SplashScreenPanel(self)
            elif type == "MainPanel":
                self.panels[panel_name] = MainPanel(self)
            elif type == "menu":
                self.panels[panel_name] = MenuPanel(self)
            elif type == "extrude":
                self.panels[panel_name] = ExtrudePanel(self)
            elif type == "JobStatusPanel":
                self.panels[panel_name] = JobStatusPanel(self)
            elif type == "move":
                self.panels[panel_name] = MovePanel(self)
            elif type == "temperature":
                self.panels[panel_name] = TemperaturePanel(self)
            elif type == "fan":
                self.panels[panel_name] = FanPanel(self)
            elif type == "system":
                self.panels[panel_name] = SystemPanel(self)
            elif type == "zcalibrate":
                self.panels[panel_name] = ZCalibratePanel(self)
            #Temporary for development
            else:
                self.panels[panel_name] = MovePanel(self)

            if kwargs != {}:
                print type
                self.panels[panel_name].initialize(panel_name, **kwargs)
            else:
                self.panels[panel_name].initialize(panel_name)

            if hasattr(self.panels[panel_name],"process_update"):
                self.panels[panel_name].process_update(self.last_update)

        self.add(self.panels[panel_name].get())
        self.show_all()
        self._cur_panels.append(panel_name)
        logging.info(self._cur_panels)


    def read_config (self):
        with open(config) as config_file:
            self._config = json.load(config_file)


    def init_style(self):
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path("/opt/printer/KlipperScreen/style.css")

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def create_websocket(self):
        self._ws = KlippyWebsocket(self._websocket_callback)
        self._ws.connect()
        self._curr = 0


    def _go_to_submenu(self, widget, name):
        logging.info("#### Go to submenu " + str(name))
        #self._remove_current_panel(False)

        # Find current menu item
        panels = list(self._cur_panels)
        if "job_status" not in self._cur_panels:
            cur_item = self._find_current_menu_item(name, self._config['mainmenu'], panels.pop(0))
            menu = cur_item['items']
        else:
            menu = self._config['printmenu']

        logging.info("#### Menu " + str(menu))
        #self.show_panel("_".join(self._cur_panels) + '_' + name, "menu", 1, False, menu=menu)

        print menu
        self.show_panel(self._cur_panels[-1] + '_' + name, "menu", 1, False, items=menu)
        return

        grid = self.arrangeMenuItems(menu, 4)

        b = KlippyGtk.ButtonImage('back', 'Back')
        b.connect("clicked", self._menu_go_back)
        grid.attach(b, 4, 2, 1, 1)

        self._cur_panels.append(cur_item['name']) #str(cur_item['name']))
        self.panels[cur_item['name']] = grid
        self.add(self.panels[cur_item['name']])
        self.show_all()



    def _find_current_menu_item(self, menu, items, names):
        for item in items:
            if item['name'] == menu:
                return item
        #TODO: Add error check

    def _remove_all_panels(self):
        while len(self._cur_panels) > 0:
            self._remove_current_panel()



    def _remove_current_panel(self, pop=True):
        if len(self._cur_panels) > 0:
            self.remove(
                self.panels[
                    self._cur_panels[-1]
                ].get()
            )
            if pop == True:
                self._cur_panels.pop()
                if len(self._cur_panels) > 0:
                    self.add(self.panels[self._cur_panels[-1]].get())
                    self.show_all()

    def _menu_go_back (self, widget):
        logging.info("#### Menu go back")
        self._remove_current_panel()


    def add_subscription (self, panel_name):
        add = True
        for sub in self.subscriptions:
            if sub == panel_name:
                return

        self.subscriptions.append(panel_name)

    def remove_subscription (self, panel_name):
        for i in range(len(self.subscriptions)):
            if self.subscriptions[i] == panel_name:
                self.subscriptions.pop(i)
                return

    def _websocket_callback(self, action, data):
        #print json.dumps(data, indent=2)

        for x in data:
            self.last_update[x] = data[x]

        if action == "notify_klippy_state_changed":
            if data == "ready":
                logging.info("### Going to ready state")
                self.printer_ready()
            elif data == "disconnect" or data == "shutdown":
                logging.info("### Going to disconnected state")
                self.printer_initializing()

        elif action == "notify_status_update":
            if "virtual_sdcard" in data:
                if data['virtual_sdcard']['is_active'] == True and "job_status" not in self._cur_panels:
                    self.printer_printing()
                elif data['virtual_sdcard']['is_active'] == False and "job_status" in self._cur_panels:
                    self.printer_ready()
                #if "job_panels" in self._cur_panels and :
            for sub in self.subscriptions:
                self.panels[sub].process_update(data)


    def _send_action(self, widget, method, params):
        self._ws.send_method(method, params)

    def printer_initializing(self):
        self.show_panel('splash_screen',"SplashScreenPanel", 2)

    def printer_ready(self):
        self.show_panel('main_panel', "MainPanel", 2, items=self._config['mainmenu'], extrudercount=self.extrudercount)

    def printer_printing(self):
        self.show_panel('job_status',"JobStatusPanel", 2)


win = KlipperScreen()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
