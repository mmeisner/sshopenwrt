#!/usr/bin/env python3
"""
Log class and console coloring
"""
import os
import sys

################################################################################
# Simple console colouring (Mads Meisner-Jensen)
################################################################################

# This coloring code
from collections import namedtuple

Color = namedtuple('Color',
    "black red green yellow blue magenta cyan white " +
    "grey ired igreen iyellow iblue imagenta icyan iwhite reset")
Style = namedtuple('Color', "bold dim under inv")

Color.__new__.__defaults__ = ("",) * len(Color._fields)
Style.__new__.__defaults__ = ("",) * len(Style._fields)

# default is no colors, so all colors are empty strings
fg = Color()
style = Style()

ColorLog = namedtuple('ColorLog', "note info verb cmd good header error")
ColorLog.__new__.__defaults__ = ("",) * len(ColorLog._fields)
color = ColorLog()

def color_enable(force=False):
    global fg, style, color
    if force or (sys.stdout.isatty() and os.name != 'nt'):
        fg = Color(black="\033[30m", red="\033[31m", green="\033[32m", yellow="\033[33m",
                   blue="\033[34m", magenta="\033[35m", cyan="\033[36m", white="\033[37m",
                   grey="\033[90m", ired="\033[91m", igreen="\033[92m", iyellow="\033[93m",
                   iblue="\033[94m", imagenta="\033[95m", icyan="\033[96m", iwhite="\033[97m",
                   reset="\033[0m")
        style = Style(bold="\033[1m", dim="\033[2m", under="\033[4m", inv="\033[7m")

        color = ColorLog(
            note=fg.iyellow,
            info=fg.white + style.bold,
            verb=fg.white,
            cmd=fg.igreen,
            good=fg.imagenta,
            header=style.inv,
            error=fg.ired,
        )

class Log(object):
    """
    Log() can be instanced globally or as a member of the main class
    """
    def __init__(self, verbose=1, show_cmds=False):
        self.level = verbose
        self.show_cmds = show_cmds

    def note(self, s, level=0):
        if self.level >= level:
            print(f"{color.note}{s}{fg.reset}")

    def info(self, s, level=1):
        if self.level >= level:
            print(f"{color.info}{s}{fg.reset}")

    def verb(self, s, level=2):
        if self.level >= level:
            print(f"{color.info}{s}{fg.reset}")

    def cmd(self, s, prefix=None):
        if self.show_cmds:
            if prefix:
                print(f"{fg.cyan}{prefix}{color.cmd}{s}{fg.reset}")
            else:
                print(f"{color.cmd}{s}{fg.reset}")

    def good(self, s, level=1):
        if self.level >= level:
            print(f"{color.good}{s}{fg.reset}")

    def header(self, s, level=1):
        if self.level >= level:
            print(f"{color.header}{s}{fg.reset}")

    def error(self, s):
        print(f"{color.error}{s}{fg.reset}")

    def die(self, s):
        self.error(s)
        sys.exit(1)
