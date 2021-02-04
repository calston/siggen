import os

import asyncio

from math import pi

import serial_asyncio

import json

import pygame
from pygame.locals import *

from pyhmi import App


T_BLUE = pygame.Color(51, 185, 232)


class Output(asyncio.Protocol):
    def __init__(self, parent):
        self.parent = parent

    def connection_made(self, transport):
        self.transport = transport
        self.parent.siggen_protocol = self
        self.parent.siggen_connected()

    def set_frequency(self, f):
        self.transport.write(bytes('%s\n' % f, 'ascii'))

    def data_received(self, data):
        data = str(data, 'ascii')

    def connection_lost(self, exc):
        self.transport.loop.stop()

class Spectrum(asyncio.Protocol):
    def __init__(self, parent):
        self.parent = parent
        self.ser_buffer = ""
        self.updating = True

    def pause_updates(self):
        self.updating = False

    def resume_updates(self):
        self.updating = True

    def connection_made(self, transport):
        self.transport = transport
        self.parent.spectrum_protocol = self
        self.parent.sa_connected()

    def set_span(self, start, stop):
        self.transport.write(bytes('1,%s,%s\n' % (start, stop), 'ascii'))

    def set_buckets(self, buckets):
        self.transport.write(bytes('4,%s\n' % (buckets), 'ascii'))

    def set_filter(self, f):
        self.transport.write(bytes('2,%s\n' % f, 'ascii'))

    def line_received(self, line):
        if self.updating and line.startswith('S'):
            try:
                data = json.loads(line.lstrip('S'))
                self.parent.main_screen.scope.update_data(data)
            except:
                pass

    def data_received(self, data):
        self.transport.pause_reading()

        data = str(data, 'ascii').replace('\r', '')
        if '\n' in data:
            parts = data.split('\n')

            self.line_received(self.ser_buffer + parts[0])

            if len(parts) > 1:
                self.ser_buffer = parts[-1]
            else:
                self.ser_buffer = ""

            for l in parts[1:-1]:
                self.line_received(l)
        else:
            self.ser_buffer += data

        self.transport.resume_reading()

    def connection_lost(self, exc):
        self.transport.loop.stop()

class Siggen(App):
    views = {
        'main': 'siggen/main.yaml'
    }

    def __init__(self):
        App.__init__(self)
        self.siggen_protocol = None
        self.spectrum_protocol = None

        self.f_span = 500000000
        self.f_center = 1000000000
        self.r_bw = 1

        self.tmp_val = 0

    def siggen_connected(self):
        self.siggen_protocol.set_frequency(1000000000)

    def sa_connected(self):
        self.set_spectrum()

    def set_spectrum(self):
        self.main_screen.txt_span.text = "Span: %skHz" % (self.f_span/1000)
        self.main_screen.txt_center.text = "Center: %skHz" % (self.f_center/1000)

        if (self.r_bw == 2):
            rbw_val = "100kHz"

        if (self.r_bw == 1):
            rbw_val = "1Mhz"

        if (self.r_bw == 0):
            rbw_val = "5Mhz"

        self.main_screen.txt_rbw.text = "RBW: " + rbw_val

        start = self.f_center - (self.f_span//2)
        stop = self.f_center + (self.f_span//2)
        self.spectrum_protocol.set_span(start, stop)

        buckets, _ = self.main_screen.scope.get_size()
        self.spectrum_protocol.set_buckets(buckets//2)

        self.spectrum_protocol.set_filter(self.r_bw)

    def rbw_click(self, button):
        if self.r_bw < 2:
            self.r_bw += 1
        else:
            self.r_bw = 0

        self.set_spectrum()


    def center_click(self, button):
        pass

    def button1_click(self, button):
        self.stop()

    def set_frequency(self, f):
        self.siggen_protocol.set_frequency(f.value)

    def on_start(self):
        pygame.mouse.set_cursor((8,8), (0, 0), (0,0,0,0,0,0,0,0), (0,0,0,0,0,0,0,0))

        self.start_serial()

    def start_serial(self):
        self.serial = serial_asyncio.create_serial_connection(
            self.ev_loop,
            lambda: Spectrum(self),
            '/dev/ttyACM0',
            baudrate=921600
        )
        self.ev_loop.run_until_complete(self.serial)

        self.output_serial = serial_asyncio.create_serial_connection(
            self.ev_loop,
            lambda: Output(self),
            '/dev/ttyACM1',
            baudrate=115200
        )
        self.ev_loop.run_until_complete(self.output_serial)

    def func_open(self, button):
        self.main_screen.grp_function.show = True
        self.spectrum_protocol.pause_updates()
        self.selected = self.main_screen.grp_function.frequency
        self.main_screen.grp_function.frequency.selected_digit=0
        self.request_update = True

    def func_okay(self, button):
        self.main_screen.grp_function.show = False
        self.spectrum_protocol.resume_updates()
        self.selected = None
 
    def center_click(self, button):
        self.main_screen.grp_center.show = True
        self.spectrum_protocol.pause_updates()
        self.tmp_dec = 0
        self.tmp_val = 0
        self.main_screen.grp_center.value.text = '_'
        self.selected = self.main_screen.grp_center
        self.request_update = True
        
    def center_okay(self, btn):
        self.main_screen.grp_center.show = False
        self.spectrum_protocol.resume_updates()
        if (int(self.tmp_val) - (self.f_span//2)) < 45000000:
            self.tmp_val = 45000000 + (self.f_span//2)
        if (int(self.tmp_val) + (self.f_span//2)) > 4000000000:
            self.tmp_val = 4000000000 - (self.f_span//2)
        self.f_center = int(self.tmp_val)
        self.set_spectrum()
        self.request_update = True
        self.selected = None

    def span_click(self, button):
        self.main_screen.grp_span.show = True
        self.spectrum_protocol.pause_updates()
        self.tmp_dec = 0
        self.tmp_val = 0
        self.main_screen.grp_span.value.text = '_'
        self.selected = self.main_screen.grp_span
        self.request_update = True

    def span_okay(self, btn):
        self.main_screen.grp_span.show = False
        self.spectrum_protocol.resume_updates()
        if (self.f_center - (int(self.tmp_val)//2)) < 45000000:
            self.tmp_val = 90000000
        if (self.f_center + (int(self.tmp_val)//2)) > 4000000000:
            self.tmp_val = (4000000000 - self.f_center)//2
        self.f_span = int(self.tmp_val)
        self.set_spectrum()
        self.request_update = True
        self.selected = None

    def val_keydown(self, w, key):
        if key.isdigit():
            if self.tmp_dec:
                self.tmp_val = self.tmp_val + (int(key) * (1.0/(10*self.tmp_dec)))
                formatter = "%%0.%sf" % self.tmp_dec
                self.tmp_dec += 1
                w.value.text = formatter % self.tmp_val
            else:
                self.tmp_val = (self.tmp_val * 10) + int(key)
                w.value.text = str(self.tmp_val)

        if (self.tmp_dec==0) and (key == '.'):
            w.value.text = str(self.tmp_val) + '.'
            self.tmp_dec = 1

        if key in ['g', 'm', 'k']:
            if key == 'g':
                val = self.tmp_val * 1000000000
            if key == 'm':
                val = self.tmp_val * 1000000
            if key == 'k':
                val = self.tmp_val * 1000

            if val > 4000000000:
                val = 4000000000
            self.tmp_val = val
            w.value.text = str(self.tmp_val)

        self.request_update = True

