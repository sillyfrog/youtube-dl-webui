#!/usr/bin/env python3

import shlex
from youtube_dl import options
import youtube_dl as youtube_dl_init

lastargs = None


class BreakerError(Exception):
    pass


class DummyYoutubeDL:
    to_screen = None
    _opener = None

    def __init__(self, argdict):
        global lastargs
        lastargs = argdict

    def warn_if_short_id(self, msg):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class DummySys:
    platform = "fake"

    def exit(self, retcode=0):
        if retcode == 0:
            raise BreakerError
        else:
            raise ValueError("Parser Exit Code: {}".format(retcode))


def dummy_update_self(*args):
    pass


def parsecmdargs(argstr):
    args = shlex.split(argstr)
    # This ensures the correct code path is taken in the monkey patch
    args.append("--update")
    youtube_dl_init.YoutubeDL = DummyYoutubeDL
    youtube_dl_init.sys = DummySys()
    youtube_dl_init.update_self = dummy_update_self
    try:
        youtube_dl_init._real_main(args)
    except BreakerError:
        pass
    return lastargs, args


def main():
    import pprint

    pprint.pprint(parsecmdargs("--extract-audio --audio-format mp3"))


if __name__ == "__main__":
    main()
