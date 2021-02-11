import math
from pathlib import Path
from PIL import ImageFont
from rpi_ws281x import *
import socket
import sys
import time
import threading
import traceback

try:
    from Queue import Queue
except ImportError:
    from queue import Queue

from demo_opts import get_device
from luma.core.render import canvas
from luma.core.virtual import viewport

try:
    import tweepy
except ImportError:
    print("The tweepy library was not found. Run 'sudo -H pip install tweepy' to install it.")
    sys.exit()


consumer_key = "TWITTER_API_CONSUMER_KEY"
consumer_secret = "TWITTER_API_CONSUMER_SECRET"
access_token = "TWITTER_API_ACCESS_TOKEN"
access_token_secret = "TWITTER_API_ACCESS_TOKEN_SECRET"

search_terms = ['python']


LED_COUNT      = 11
LED_PIN        = 18
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 255
LED_INVERT     = False
# LED_CHANNEL    = 0

# BUTTON_CHANNEL = 19


# MONITOR FUNCTIONS
class Listener(tweepy.StreamListener):
    def __init__(self, queue):
        super(Listener, self).__init__()
        self.queue = queue

    def on_status(self, status):
        self.queue.put(status)


def message_scroll_thread(queue):
    while True:
        status = queue.get()
        scroll_message(status, font=font)


def make_font(name, size):
    font_path = str(Path(__file__).resolve().parent.joinpath('fonts', name))
    return ImageFont.truetype(font_path, size)


def scroll_message(status, speed=1):
    author = u"@{0}".format(status.author.screen_name)
    full_text = u"{0}  {1}".format(author, status.text).replace("\n", " ")
    x = device.width

    with canvas(device) as draw:
        w, h = draw.textsize(full_text, font)

    virtual = viewport(device, width=max(device.width, w + x + x), height=max(h, device.height))
    with canvas(virtual) as draw:
        draw.text((x, 0), full_text, font=font, fill="white")
        draw.text((x, 0), author, font=font, fill="yellow")

    i = 0
    while i < x + w:
        virtual.set_position((i, 0))
        i += speed
        time.sleep(0.025)


# STRIP FUNCTIONS
def init_strip():
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
    colors = []
    strip.begin()

    for i in range(0, strip.numPixels(), 1):
        colors.append(Color(0, 0, 0))
    update_strip(strip, colors)
    return strip, colors


def update_strip(strip, colors):
    for i in range(0, strip.numPixels(), 1):
        strip.setPixelColor(i, colors[i])
    strip.show()


def clear_strip(strip, colors):
    for i in range(0, strip.numPixels(), 1):
        colors[i] = Color(0, 0, 0)
    update_strip(strip, colors)


def set_pixel(strip, colors, i, c):
    colors[i] = c
    update_strip(strip, colors)


def set_pixels(strip, colors, pixels, c):
    for i in pixels:
        colors[i] = c
    update_strip(strip, colors)


def set_all_pixels(strip, colors, c):
    set_pixels(strip, colors, range(0, strip.numPixels(), 1), c)


def main():
    # Hosting
    host = ""
    port = 8000
    backlog = 5
    # Display
    device = get_device()
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)
    queue = Queue()
    font = make_font("code2000.ttf", 12)
    # Strip
    size = 1024
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(backlog)
    strip, colors = init_strip()
    while True:
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
                    client.sendall(b"Client asked server to quit\n")
                    client.send(data)
                    return
                if data == b"clear":
                    client.sendall(b"Clearing strip")
                    clear_strip(strip, colors)

                try:
                    data_tokens = data.split(b" ")
                    # set <light index> <r> <g> <b>
                    if data_tokens[0] == b"set":
                        led_index = int(data_tokens[1])
                        r = int(data_tokens[2])
                        g = int(data_tokens[3])
                        b = int(data_tokens[4])
                        set_pixel(strip, colors, led_index, Color(r, g, b))
                    # setall <r> <g> <b>
                    if data_tokens[0] == b"setall":
                        r = int(data_tokens[1])
                        g = int(data_tokens[2])
                        b = int(data_tokens[3])
                        set_all_pixels(strip, colors, Color(r, g, b))
                    if data_tokens[0] == b"say":
                        text = data_tokens[1]
                        stream = tweepy.Stream(auth=api.auth, listener=Listener(queue))
                        scroll_message(queue.get(), font=font)
                        #message_thread = threading.Thread(target=message_scroll_thread, args=(queue,))
                        #message_thread.start()
                except Exception as err:
                    client.sendall(b"Error occured parsing input\n")
                    traceback.print_exc()
        except Exception as err:
            client.sendall(b"Error occured, Server shutting down\n")
            traceback.print_exc()
        finally:
            print("Closing server")
            client.close()
            clear_strip(strip, colors)
            if message_thread:
                message_thread.join()
            return


# Globals
device = None
font = None
message_thread = None

# Run
main()

