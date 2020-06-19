#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import logging
import json

from youtube_dl import YoutubeDL
from youtube_dl import DownloadError

from multiprocessing import Process
from time import time

from .parseytargs import parsecmdargs


class YdlHook(object):
    def __init__(self, tid, msg_cli):
        self.logger = logging.getLogger("ydl_webui")
        self.tid = tid
        self.msg_cli = msg_cli
        self._cache_d = {}

    def finished(self, d):
        self.logger.debug("finished status")
        d["_percent_str"] = "100%"
        d["speed"] = "0"
        d["elapsed"] = 0
        d["eta"] = 0
        d["downloaded_bytes"] = d["total_bytes"]
        return d

    def downloading(self, d):
        self.logger.debug("downloading status")
        return d

    def error(self, d):
        self.logger.debug("error status")
        #  d['_percent_str'] = '100%'
        return d

    def dispatcher(self, d):
        if "total_bytes_estimate" not in d:
            d["total_bytes_estimate"] = 0
        if "tmpfilename" not in d:
            d["tmpfilename"] = ""

        if d["status"] == "finished":
            d = self.finished(d)
        elif d["status"] == "downloading":
            d = self.downloading(d)
        elif d["error"] == "error":
            d = self.error(d)
        self._cache_d = d
        self.msg_cli.put("progress", {"tid": self.tid, "data": d})

    def updatefilename(self, newname):
        self._cache_d["filename"] = newname
        self.msg_cli.put("progress", {"tid": self.tid, "data": self._cache_d})


class LogFilter(object):
    NEW_FILE_NAME_START = [
        re.compile(r"\[ffmpeg\] Destination: (.+)"),
        re.compile(r'\[ffmpeg\] Merging formats into "(.+)"'),
    ]

    def __init__(self, tid, msg_cli, newfilenamecallback):
        self.logger = logging.getLogger("ydl_webui")
        self.tid = tid
        self.msg_cli = msg_cli
        self.newfilenamecallback = newfilenamecallback

    def debug(self, msg):
        for nfre in self.NEW_FILE_NAME_START:
            match = nfre.match(msg)
            if match:
                self.newfilenamecallback(match.group(1))
        self.logger.debug("debug: %s" % (self.ansi_escape(msg)))
        payload = {"time": int(time()), "type": "debug", "msg": self.ansi_escape(msg)}
        self.msg_cli.put("log", {"tid": self.tid, "data": payload})

    def warning(self, msg):
        self.logger.debug("warning: %s" % (self.ansi_escape(msg)))
        payload = {"time": int(time()), "type": "warning", "msg": self.ansi_escape(msg)}
        self.msg_cli.put("log", {"tid": self.tid, "data": payload})

    def error(self, msg):
        self.logger.debug("error: %s" % (self.ansi_escape(msg)))
        payload = {"time": int(time()), "type": "warning", "msg": self.ansi_escape(msg)}
        self.msg_cli.put("log", {"tid": self.tid, "data": payload})

    def ansi_escape(self, msg):
        reg = r"\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?"
        return re.sub(reg, "", msg)


class FatalEvent(object):
    def __init__(self, tid, msg_cli):
        self.logger = logging.getLogger("ydl_webui")
        self.tid = tid
        self.msg_cli = msg_cli

    def invalid_url(self, url):
        self.logger.debug("fatal error: invalid url")
        payload = {
            "time": int(time()),
            "type": "fatal",
            "msg": "invalid url: %s" % (url),
        }
        self.msg_cli.put("fatal", {"tid": self.tid, "data": payload})


class Worker(Process):
    def __init__(self, tid, url, msg_cli, ydl_opts=None, first_run=False):
        super(Worker, self).__init__()
        self.logger = logging.getLogger("ydl_webui")
        self.tid = tid
        self.url = url
        self.msg_cli = msg_cli
        self.ydl_opts = ydl_opts
        self.first_run = first_run
        self.log_filter = LogFilter(tid, msg_cli, self.newfilename_callback)
        self.ydl_hook = YdlHook(tid, msg_cli)
        self._newfilename = None

    def newfilename_callback(self, newname):
        self.ydl_hook.updatefilename(newname)

    def intercept_ydl_opts(self):
        args = {}
        if "args" in self.ydl_opts:
            strargs = self.ydl_opts["args"]
            if strargs:
                args, argsparts = parsecmdargs(strargs)
            if "-f" in argsparts or "--format" in argsparts:
                del self.ydl_opts["format"]
            del self.ydl_opts["args"]

        args.update(self.ydl_opts)
        self.ydl_opts = args
        self.ydl_opts["logger"] = self.log_filter
        self.ydl_opts["progress_hooks"] = [self.ydl_hook.dispatcher]
        self.ydl_opts["noplaylist"] = "false"
        self.ydl_opts["progress_with_newline"] = True

    def run(self):
        self.intercept_ydl_opts()
        with YoutubeDL(self.ydl_opts) as ydl:
            try:
                if self.first_run:
                    info_dict = ydl.extract_info(self.url, download=False)

                    #  self.logger.debug(json.dumps(info_dict, indent=4))

                    info_dict["description"] = info_dict["description"].replace(
                        "\n", "<br />"
                    )
                    payload = {"tid": self.tid, "data": info_dict}
                    self.msg_cli.put("info_dict", payload)

                self.logger.info("start downloading, url - %s" % (self.url))
                ydl.download([self.url])
            except DownloadError as e:
                # url error
                event_handler = FatalEvent(self.tid, self.msg_cli)
                event_handler.invalid_url(self.url)

        self.msg_cli.put("worker_done", {"tid": self.tid, "data": {}})

    def stop(self):
        self.logger.info("Terminating Process ...")
        self.terminate()
        self.join()
