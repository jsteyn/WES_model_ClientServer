# Author -- Stuart Lewis
# Version: 1.1
# Version history:
# Version 1.0 - 10-02-2021 [Basic implementation for setting pixels remotely]
# Version 1.1 - 11-02-2021 [Addition of aliases and some small QOL improvements]

from __future__ import unicode_literals
import threading
from typing import *
import os
import math
from rpi_ws281x import *
import socket
import sys
import time
import traceback
import json
from pathlib import Path
from PIL import ImageFont

try:
    from Queue import Queue
except ImportError:
    from queue import Queue

from demo_opts import get_device
from luma.core.render import canvas
from luma.core.virtual import viewport


class InputError(Exception):
    def __init__(self):
        super().__init__("Input Exception")


class ScrollThread(threading.Thread):
    def __init__(self):
        super().__init__()

    def run(self):
        while do_thread:
            waiting_thread = WaitThread()
            waiting_thread.start()
            new_text = queue.get()
            waiting_thread.stop()
            waiting_thread.join()
            if new_text is not None:
                self.scroll_message(new_text, font, message_speed)

    def scroll_message(self, text, font, speed):
        with canvas(device) as draw:
            w, h = draw.textsize(text, font)
        x = device.width
        y = device.height // 2 - h // 2

        virtual = viewport(device, width=max(device.width, w + x + x), height=max(device.height, h))

        with canvas(virtual) as draw:
            draw.text((x, y), text, font=font, fill="white")

        i = 0
        while i < x + w and do_thread:
            virtual.set_position((i, 0))
            i += speed
            time.sleep(0.025)

        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, fill="black")


class WaitThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        global font_changed
        counter = 0
        with canvas(device) as draw:
            w, h = draw.textsize("Waiting...", font)
        while self.running:
            if font_changed:
                font_changed = False
                with canvas(device) as draw:
                    w, h = draw.textsize("Waiting...", font)
            text = "Waiting" + "." * counter
            with canvas(device) as draw:
                draw.text((device.width // 2 - w // 2, device.height // 2 - h // 2), text, font=font, fill="white")
            counter = (counter + 1) % 4
            time.sleep(0.2)

    def stop(self):
        self.running = False


def make_font(name, size):
    font_path = str(Path(__file__).resolve().parent.joinpath('fonts', name))
    return ImageFont.truetype(font_path, size)


def update_strip():
    """Update and show strip with currently set colors"""
    for i in range(0, strip.numPixels(), 1):
        strip.setPixelColor(i, colors[i])
    strip.show()


def clear_strip():
    """Set all strip colors to black"""
    for i in range(0, strip.numPixels(), 1):
        colors[i] = Color(0, 0, 0)
    update_strip()


def set_pixel(i: int, c: Color):
    """
    --i - Pixel index to assign color to
    --c - Color to set pixel index to
    """
    colors[i] = c
    update_strip()


def set_pixels(pixels: List[int], c: Color):
    """
    Set given pixels to the given color
    --pixels - List of pixel indexes to assign the given color to
    --c      - Color to set pixels to
    """
    for i in pixels:
        colors[i] = c
    update_strip()


def set_all_pixels(c: Color):
    """
    Set all pixels to the given color
    --c - Color to set the pixels to
    """
    set_pixels(range(0, strip.numPixels(), 1), c)


def set_alias(value: int, alias: str):
    """
    Assign given alias to the given pixel index
    --value - Pixel index to assign alias to
    --alias - New alias to apply to index
    """
    aliases[alias] = value

def save_aliases(name: str):
    """Save aliases to new store, or overwrite existing store"""
    filepath = "alias_store/" + name + ".json"
    if os.path.isfile(filepath):
        client.sendall(b"Alias store of name " + bytes(name, "utf-8") + b" already exists.\nOverwrite existing store? (yes/no)")
        if client.recv(size).rstrip() != b"yes":
            client.sendall(b"Aborting save\n")
            return
    with open(filepath, "w") as f:
        json.dump(aliases, f)


def load_aliases(name: str):
    """Load aliases from existing store"""
    global aliases
    with open("alias_store/" + name + ".json", "r") as f:
        aliases = json.load(f)


def clear_aliases():
    """Clear all current aliases"""
    global aliases
    aliases = {}


def list_aliases():
    """Print list of the currently assigned aliases"""
    inverse_aliases = { i: [str(i)] for i in range(strip.numPixels()) }
    for alias, index in aliases.items():
        inverse_aliases[index] = inverse_aliases.get(index, [])
        inverse_aliases[index].append(alias)
    for index, alias_list in inverse_aliases.items():
        client.sendall(bytes(str(index), "utf-8") + b" -> " + bytes(", ".join(alias_list), "utf-8") + b"\n")


def list_alias_stores():
    """Print list of all available alias stores"""
    files = [f for f in os.listdir("./alias_store/") if f.endswith(".json")]
    if len(files) == 0:
        client.sendall(b"There are no alias stores\n")
        return
    client.sendall(b"Existing alias stores:\n")
    for filename in files:
        client.sendall(b"- " + bytes(os.path.splitext(filename)[0], "utf-8") + b"\n")


def get_led(alias: str) -> int:
    """Retrieve the led index matching the given alias"""
    global cmd_fail_message
    if alias in aliases:
        return aliases[alias]
    else:
        try:
            if int(alias) < strip.numPixels():
                return int(alias)
            else:
                cmd_fail_message = "Pixel of index <" + alias + "> is out of bounds.\n Strip only has up to index <" + str(strip.numPixels() - 1) + ">."
        except ValueError:
            cmd_fail_message = "Pixel index alias <" + alias + "> not recognized."
        raise InputError()


def main():
    global client, strip, cmd_fail_message, colors, scroll_thread
    print("Setting up...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(backlog)

    print("Initialising threads...")
    scroll_thread = ScrollThread()
    scroll_thread.start()

    print("Initialising strip...")
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
    colors = [Color(0, 0, 0) for _ in range(strip.numPixels())]
    strip.begin()
    update_strip()

    print("Waiting for connections")
    try:
        while True:
            client, address = sock.accept()
            client.sendall(b"Client connected\n")
            print("Client connected")
            try:
                while True:
                    client.sendall(b"> ")
                    data = client.recv(size).rstrip().decode("utf-8")
                    if not data:
                        continue
                    if data == "disconnect":
                        client.sendall(b"Client disconnected\n")
                        client.close()
                        break
                    if data == "exit":
                        client.sendall(b"Client called exit protocol\n")
                        client.close()
                        clear_strip()
                        return
                    if data == "help":
                        client.sendall(b"-System Commands-\n")
                        client.sendall(b"disconnect\n")
                        client.sendall(b"exit\n")
                        client.sendall(b"help\n")
                        client.sendall(b"-Strip Commands-\n")
                        client.sendall(b"clear-pixels\n")
                        client.sendall(b"set <pixel> <r> <g> <b>\n")
                        client.sendall(b"setall <r> <g> <b>\n")
                        client.sendall(b"assign-alias <pixel> <alias>\n")
                        client.sendall(b"store-aliases <name>\n")
                        client.sendall(b"load-aliases <name>\n")
                        client.sendall(b"list-alias-stores\n")
                        client.sendall(b"list-aliases\n")
                        client.sendall(b"clear-aliases\n")
                        client.sendall(b"-Display Commands-\n")
                        client.sendall(b"say <message>\n")
                        client.sendall(b"message-speed <speed>\n")
                        client.sendall(b"font-size <size>\n")
                        continue
                    if data == "clear-pixels":
                        client.sendall(b"Clearing strip\n")
                        clear_strip()
                        continue
                    if data == "list-alias-stores":
                        list_alias_stores()
                        continue
                    if data == "list-aliases":
                        list_aliases()
                        continue
                    if data == "clear-aliases":
                        clear_aliases()
                        continue

                    try:
                        data_tokens = data.split(" ")
                        # set <light index> <r> <g> <b>
                        if data_tokens[0] == "set":
                            led_index = get_led(data_tokens[1])
                            r = int(data_tokens[2])
                            g = int(data_tokens[3])
                            b = int(data_tokens[4])
                            set_pixel(led_index, Color(r, g, b))
                            client.sendall(bytes("Set pixel " + data_tokens[1] + " to #" + format(r, "x") + format(g, "x") + format(b, "x") + "\n", "utf-8"))
                            continue
                        # setall <r> <g> <b>
                        if data_tokens[0] == "setall":
                            r = int(data_tokens[1])
                            g = int(data_tokens[2])
                            b = int(data_tokens[3])
                            set_all_pixels(Color(r, g, b))
                            client.sendall(bytes("Set all pixels to #" + format(r, "x") + format(g, "x") + format(b, "x") + "\n", "utf-8"))
                            continue
                        # assign-alias <light index> <alias>
                        if data_tokens[0] == "assign-alias":
                            led_index = get_led(data_tokens[1])
                            alias = data_tokens[2]
                            set_alias(led_index, alias)
                            client.sendall(bytes("Added alias " + alias + " to pixel " + str(led_index) + "\n", "utf-8"))
                            continue
                        # store-aliases <name>
                        if data_tokens[0] == "store-aliases":
                            name = data_tokens[1]
                            save_aliases(name)
                            client.sendall(bytes("Saved aliases to name " + name + "\n", "utf-8"))
                            continue
                        # load-aliases <name>
                        if data_tokens[0] == "load-aliases":
                            name = data_tokens[1]
                            load_aliases(name)
                            client.sendall(bytes("Loaded aliases from " + name + "\n", "utf-8"))
                            continue

                        # say <message>
                        if data_tokens[0] == "say":
                            message = " ".join(data_tokens[1:])
                            queue.put(message)
                            client.sendall(bytes("Added message '" + message + "' to queue\n", "utf-8"))
                            continue
                        # message-speed <speed>
                        if data_tokens[0] == "message-speed":
                            global message_speed
                            message_speed = int(data_tokens[1])
                            client.sendall(bytes("Set message speed to " + data_tokens[1] + "\n", "utf-8"))
                            continue
                        # font-size <size>
                        if data_tokens[0] == "font-size":
                            global font, font_changed
                            fsize = int(data_tokens[1])
                            font = make_font(u"code2000.ttf", fsize)
                            font_changed = True
                            client.sendall(bytes("Set font size to " + data_tokens[1] + "\n", "utf-8"))
                            continue
                        cmd_fail_message = "Command " + data_tokens[0] + " not recognised."
                        raise InputError()
                    except InputError as err:
                        client.sendall(b"Error occured parsing input:\n")
                        if cmd_fail_message is None:
                            client.sendall(b"-- Unknown Error.\n")
                        else:
                            client.sendall(bytes("-- " + cmd_fail_message + "\n", "utf-8"))
                            cmd_fail_message = None
            except Exception as err:
                client.sendall(b"Error occured, Server shutting down...\n")
                traceback.print_exc()
                return
    finally:
        global do_thread
        print("Closing server")
        do_thread = False
        with queue.mutex:
            queue.queue.clear()
        queue.put(None)
        clear_strip()
        sock.close()



# CONSTANTS
LED_COUNT      = 11
LED_PIN        = 18
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 255
LED_INVERT     = False

# GLOBAL VARIABLES
cmd_fail_message = None
aliases = {}
strip = None
colors = None

font_changed = False
do_thread = True

client = None
host = ""
port = 8001
backlog = 5
size = 1024

device = get_device()
queue = Queue()
font = make_font(u"code2000.ttf", 25)
message_speed = 10

# RUN
main()

