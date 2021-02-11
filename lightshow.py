import math
from rpi_ws281x import *
import socket
import sys
import time
import traceback


LED_COUNT      = 11
LED_PIN        = 18
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 255
LED_INVERT     = False
# LED_CHANNEL    = 0

# BUTTON_CHANNEL = 19


class InputError(Exception):
    def __init__(self):
        super().__init__("Input Exception")


def init():
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


def set_alias(value: int, alias: str):
    """
    -- value - Integer value to assign alias to
    -- alias - New alias to apply to value
    """
    aliases[alias] = value


def get_led(alias: str) -> int:
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
    global strip, cmd_fail_message
    print("Setting up...")
    host = ""
    port = 8001
    backlog = 5
    size = 1024
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(backlog)
    print("Initialising strip...")
    strip, colors = init()
    print("Waiting for connections")
    while True:
        client, address = sock.accept()
        client.sendall(b"Client connected")
        print("Client connected")
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
                    client.close()
                    clear_strip(strip, colors)
                    return
                if data == b"help":
                    client.sendall(b"disconnect\n")
                    client.sendall(b"exit\n")
                    client.sendall(b"clear\n")
                    client.sendall(b"set index r g b\n")
                    client.sendall(b"setall r g b\n")
                    continue
                if data == b"clear":
                    client.sendall(b"Clearing strip")
                    clear_strip(strip, colors)
                    continue

                try:
                    data_tokens = data.split(b" ")
                    # set <light index> <r> <g> <b>
                    if data_tokens[0] == b"set":
                        led_index = get_led(data_tokens[1].decode("utf-8"))
                        r = int(data_tokens[2])
                        g = int(data_tokens[3])
                        b = int(data_tokens[4])
                        set_pixel(strip, colors, led_index, Color(r, g, b))
                        continue
                    # setall <r> <g> <b>
                    if data_tokens[0] == b"setall":
                        r = int(data_tokens[1])
                        g = int(data_tokens[2])
                        b = int(data_tokens[3])
                        set_all_pixels(strip, colors, Color(r, g, b))
                        continue
                    # assign <light index> <alias>
                    if data_tokens[0] == b"assign":
                        led_index = get_led(data_tokens[1].decode("utf-8"))
                        alias = data_tokens[2].decode("utf-8")
                        set_alias(led_index, alias)
                        continue
                    cmd_fail_message = "Command " + str(data_tokens[0]) + " not recognised."
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
            print("Closing server")
            client.close()
            clear_strip(strip, colors)
            return


# GLOBAL VARIABLES
cmd_fail_message = None
aliases = {}
strip = None

# RUN
main()

