import time
import json
import tkinter as tk
from tkinter import messagebox
import requests
import logging
import sys
import threading
from PIL import Image, ImageDraw
import pystray
import os
from toolz.curried import curry, reduceby, reduce, valmap, map, juxt
from itertools import compress
from aw_core import Event
from aw_transform import flood
from typing import List, Tuple
from fn import F
import operator
import win32gui
import win32api
import aw_client
import socket
from datetime import datetime, timedelta

import pprint
from treetype import TreeType
from query import canonicalEvents, DesktopQueryParams

DEBUG:bool = os.environ.get("DEBUG", 'False').lower()=="true"


def read_config(file_path):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        logging.error(f"Error reading config file: {e}")
        sys.exit(1)


class Monitor:
    def __init__(self, config_path="config.json"):
        if not os.path.exists("logs"):
            os.makedirs("logs")
        logging.basicConfig(
            filename=f'logs/{"debug_" if DEBUG else ""}monitor_{datetime.now().strftime("%Y-%m-%d-%H")}.log',
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.config = read_config(config_path)

        self.aw = aw_client.ActivityWatchClient()
        self.catconfig = list(
            map(
                lambda x: (x["name"], x["rule"]), self.aw.get_setting("classes")
            )  # type:ignore
        )

        self.icon: pystray.Icon  # type: ignore
        self.setup_icontray()

        threading.Thread(target=self.setup_tk, daemon=True).start()

    def run(self):
        thread = threading.Thread(target=self.loop, daemon=True)
        thread.start()
        self.icon.run()
        # thread = threading.Thread(target=self.icon.run, daemon=True)
        # thread.start()
        # self.loop()

    # Icon Tray

    def setup_tk(self):
        self.tkroot = tk.Tk("aw-pop")
        self.tkroot.withdraw()
        self.tkroot.mainloop()

    def setup_icontray(self):

        # read from a .ico file
        image = Image.open(r"icon6.ico")
        dc = ImageDraw.Draw(image)
        dc.ellipse((0, 0, 64, 64), fill=(80, 240, 80))
        menu = pystray.Menu(pystray.MenuItem("Exit", self.exit_action))
        self.icon = pystray.Icon("monitor", image, "aw-pop", menu)

    def exit_action(self):
        self.icon.stop()
        sys.exit(0)

    # Call ActivityWatch

    def query_events(self, now: datetime, interval: int):
        hostname = socket.gethostname()

        query_body = canonicalEvents(
            DesktopQueryParams(
                bid_window=f"aw-watcher-window_{hostname}",
                bid_afk=f"aw-watcher-afk_{hostname}",
                bid_browsers=[
                    f"aw-watcher-web-edge",
                ],
                classes=self.catconfig,
            )
        )
        # reseq_query = list(
        #     map(# type: ignore
        #         lambda x: x.replace(" ", ""), 
        #         query_body.split(";")
        #         )
        # )  
        # reseq_query.insert(-3, "events = union_no_overlap(browser_events,events)")
        # query_body = ";\n".join(reseq_query)

        query = f"""
        {query_body}
        duration = sum_durations(events);
        RETURN = {{"events": events, "duration": duration}};
        """


        timeperiods = [(now - timedelta(minutes=interval), now)]

        return self.aw.query(query, timeperiods)[0]

    def cat_ratio(self, now: datetime, interval: int, verbose: bool=False)-> Tuple[float, TreeType]:
        res = self.query_events(now, interval)
        # dur = res["duration"]
        events = res["events"]
        
        if verbose:
            events_str = f"DEBUG: events[:5]=\n{pprint.pformat(events[:5])}"
            logging.info(events_str)
            if DEBUG :
                print(events_str)
            
        cats:dict[str,float] = (
            F()
            << reduceby(
                lambda x: x["data"]["$category"].__repr__(),
                lambda acc, x: acc + x["duration"].total_seconds(),
                init=0,
            )
            << curry(flood)(pulsetime=0)
            << map(lambda x: Event(**x))
        )(events)
        
        if DEBUG and verbose:
            pprint.pprint(cats)
        
        cats.pop("['Uncategorized']",None)
        dur = sum(cats.values())
        
        if verbose:
            cat_str = f"DEBUG: {dur=} \n{pprint.pformat(cats)}"
            logging.info(cat_str)
            if DEBUG :
                print(cat_str)

        catratio: dict[str, float] = valmap(lambda x: x / dur, cats)   # type: ignore
                # it may not divide by zero

        return dur, TreeType.tree_expand(catratio)

    # Check Indicator

    def _check_cons(self, cons, tree):
        return getattr(operator, cons["op"])(
            tree.get_term(cons["term"]).sum(), cons["value"]
        )

    def _check_conses(self, cons, tree):
        return list(juxt(map(curry(self._check_cons), cons))(tree))  # type:ignore

    def _minimize_desktop(self):
        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")
        shell.MinimizeAll()

    def _show_popup(self, message):
        def show():
            messagebox.showwarning("Warning", message)

        self.tkroot.after(0, show)

    def loop(self):
        # haspop=False
        while True:
            time.sleep(self.config["check_interval"])
            now = datetime.now().astimezone()

            mon_ret = self.cat_ratio(now, self.config["monitor_interval"])

            if mon_ret is None:
                logging.warning("Failed to get indicator value")
                continue

            dur, catratio = mon_ret
            indicator_value = self._check_conses(self.config["constraint"], catratio)

            logging.info(
                f"Current Status: \n"
                f"duration={dur}\n"
                f"catratio=\n{pprint.pformat(catratio.map(curry(round)(ndigits=3)))}\n"
                f"indicators={indicator_value}"
            )
            if all(indicator_value):
                continue

            # check if the constraint is still not met in the local time period

            loc_tree = self.cat_ratio(now, self.config["check_interval"] / 60, DEBUG)[1]

            loc_satisfy = self._check_conses(self.config["constraint"], loc_tree)

            # If in a small local time period, the time allocation is satisfiable, then we regard it as a false alarm
            if loc_tree.isempty() or all(loc_satisfy):
                # print(f"DEBUG: {loc_tree.isempty()=}, {all(loc_satisfy)=}")
                # print(f"DEBUG: {loc_tree=}")
                continue

            fail_cons = list(
                compress(
                    self.config["constraint"],
                    map(operator.not_, indicator_value),  # type:ignore
                )
            )

            fail_term = list(
                map( # type: ignore
                    lambda x: (x["term"], catratio.get_term(x["term"]).sum()), fail_cons
                )
            )

            warning_str = (
                f"Constraints not meet ! !\n"
                + f"Fail Conses :  {pprint.pformat(fail_cons)}\n"
                + f"Fail Terms  :  {pprint.pformat(fail_term)}"
            )

            self._minimize_desktop()
            self._show_popup(warning_str)
            logging.warning(warning_str)


def main():
    monitor = Monitor(config_path="config_debug.json" if DEBUG else "config.json")
    monitor.run()


if __name__ == "__main__":
    main()
