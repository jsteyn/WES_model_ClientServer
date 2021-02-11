from __future__ import unicode_literals

search_terms = ['python']

import sys
import threading
import time
from pathlib import Path
from PIL import ImageFont

import math
import socket
import traceback


try:
    from Queue import Queue
except ImportError:
    from queue import Queue

from demo_opts import get_device
from luma.core.render import canvas
from luma.core.virtual import viewport


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
                self.scroll_message(new_text, font, speed)


    def scroll_message(self, full_text, font=None, speed=4):
        x = device.width

        # First measure the text size
        with canvas(device) as draw:
            w, h = draw.textsize(full_text, font)
        y = device.height // 2 - h // 2

        virtual = viewport(device, width=max(device.width, w + x + x), height=max(h, device.height))
        with canvas(virtual) as draw:
            draw.text((x, y), full_text, font=font, fill="white")

        i = x + w
        while i >= 0 and do_thread:
            virtual.set_position((i, 0))
            i -= speed
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
                draw.text((device.width // 2 - w // 2, device.height // 2 - h // 2), text, font=font, fill="yellow")
            counter = (counter + 1) % 4

    def stop(self):
        self.running = False


def make_font(name, size):
    font_path = str(Path(__file__).resolve().parent.joinpath('fonts', name))
    return ImageFont.truetype(font_path, size)


def full_stop(client=None):
    global do_run, do_thread
    print("Shutting down")
    if client is not None:
        client.sendall(b"Server shutting down...\n")
        client.close()
    do_run = False
    do_thread = False
    with queue.mutex:
        queue.queue.clear()
    queue.put(None)
    print("Shut down")


#parser = argparse.ArgumentParser()
#parser.add_argument("--port", help="set the port to be hosted on", dest="port", default=8000)

#args, unknown = parser.parse_known_args()

device = get_device()
queue = Queue()

font = make_font(u"code2000.ttf", 20)
speed = 10

font_changed = False
do_thread = True
scroll_thread = ScrollThread()

host = ""
backlog = 5
size = 1024
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((host, 8000))
sock.listen(backlog)

scroll_thread.start()

do_run = True
while do_run:
    client, address = sock.accept()
    client.sendall(b"Client connected")
    try:
        while True:
            client.sendall(b"\n> ")
            data = client.recv(size).rstrip()
            if not data:
                continue
            client.sendall(b"Recieved command: " + data + b"\n")
            if data == b"disconnect":
                client.sendall(b"Client disconnected\n")
                client.send(data)
                client.close()
                break
            if data == b"exit":
                full_stop(client)
                break

            try:
                data_tokens = data.split(b" ")
                if data_tokens[0] == b"say":
                    client.sendall(b"Adding message to queue")
                    queue.put(data.decode("utf-8").replace("say ", "", 1))
                if data_tokens[0] == b"speed":
                    client.sendall(b"Setting speed")
                    speed = int(data_tokens[1])
                if data_tokens[0] == b"font":
                    client.sendall(b"Setting font size")
                    fsize = int(data_tokens[1])
                    font = make_font(u"code2000.ttf", fsize)
                    font_changed = True
            except Exception as err:
                client.sendall(b"Error occured parsing input\n")
                traceback.print_exc()
    except Exception as err:
        client.sendall(b"Error occured, Server shutting down\n")
        traceback.print_exc()
        full_stop(client)
