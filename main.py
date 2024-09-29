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
from toolz.curried import curry, reduceby, valmap , map,juxt
from itertools import compress
from aw_core import Event
from aw_transform import flood
from typing import List
from fn import F
import operator

import aw_client 
from aw_client import queries
import socket
from datetime import datetime, timedelta

from treetype import TreeType

CAT_PATH = r"%USERPROFILE%\AppData\Local\activitywatch\activitywatch\aw-server\settings.json".replace('%USERPROFILE%', os.environ['USERPROFILE'])

td1d = timedelta(days=1)
day_offset = timedelta(hours=4)


def read_config(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        logging.error(f"Error reading config file: {e}")
        sys.exit(1)


class Monitor:
    def __init__(self, config_path='config.json'):
        logging.basicConfig(filename='monitor.log', level=logging.INFO, 
                            format='%(asctime)s - %(levelname)s - %(message)s')
        self.config = read_config(config_path)
        self.catconfig = list(map(lambda x: (x["name"], x["rule"]),read_config(CAT_PATH)['classes'])) #type:ignore
        self.aw = aw_client.ActivityWatchClient()
        self.icon:pystray.Icon
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
        self.tkroot = tk.Tk()
        self.tkroot.withdraw()
        self.tkroot.mainloop()

    def setup_icontray(self):
        image = Image.new('RGB', (64, 64), color = (0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((0, 0, 64, 64), fill = (0, 255, 0))
        menu = pystray.Menu(
            pystray.MenuItem("Exit", self.exit_action)
        )
        self.icon = pystray.Icon("monitor", image, "Monitor Program", menu)
        
    def exit_action(self):
        self.icon.stop()
        sys.exit(0)

    # Call ActivityWatch
    
    def query_events(self,interval:int):
        hostname = socket.gethostname()
        
        canonicalQuery = queries.canonicalEvents(
            queries.DesktopQueryParams(
                bid_window=f"aw-watcher-window_{hostname}",
                bid_afk=f"aw-watcher-afk_{hostname}",
                classes=self.catconfig,
            )
        )

        query = f"""
        {canonicalQuery}
        duration = sum_durations(events);
        RETURN = {{"events": events, "duration": duration}};
        """


        now = datetime.now().astimezone()
        
        timeperiods = [(now - timedelta(minutes=interval), now)]
        
        return self.aw.query(query, timeperiods)[0]
    
    def cat_ratio(self,interval:int):
        res = self.query_events(interval)
        dur = res['duration']
        events = res['events']
        
        cats = ( F()
            << reduceby(lambda x: x['data']['$category'].__repr__(), 
                lambda acc,x: acc+x['duration'].total_seconds(), 
                init=0
                )
            << curry(flood)(pulsetime=0)
            << map(lambda x: Event(**x))
            ) (events) 
        
        catratio:dict[str,float] = valmap(lambda x: x/dur, cats) #type:ignore
        
        return dur, TreeType.tree_expand(catratio)


    # Check Indicator

    def _check_cons(self,cons,tree):
        return getattr(operator,cons['op']) (tree.get_term(cons['term']).sum(),cons['value'])
    
    def _check_conses(self,cons, tree):
        return list(juxt(map(curry(self._check_cons),cons))(tree)) #type:ignore
    
    
    def _minimize_desktop(self):
        import win32com.client
        shell = win32com.client.Dispatch("Shell.Application")
        shell.MinimizeAll()

    def _show_popup(self, message):
        def show():
            messagebox.showwarning("Warning", message)
        
        self.tkroot.after(0,show)

    def loop(self):
        # haspop=False
        while True:
            time.sleep(self.config['check_interval'])
            
            mon_ret = self.cat_ratio(self.config['monitor_interval'])
            
            if mon_ret is None:
                logging.warning("Failed to get indicator value")
                continue
            
            logging.info(f"Current indicator value: {mon_ret}")
            dur, catratio = mon_ret
            indicator_value = self._check_conses(self.config['constraint'],catratio)
            
            if all(indicator_value):
                continue
            
            
            # check if the constraint is still not met in the local time period
            
            loc_tree = self.cat_ratio(self.config['check_interval']/60)[1]
            
            loc_satisfy = self._check_conses(self.config['constraint'],loc_tree)
            
            # If in a small local time period, the time allocation is satisfiable, then we regard it as a false alarm
            if loc_tree.isempty() or all(loc_satisfy):
                continue
            
            fail_cons = list(
                compress(self.config['constraint'],
                            map(operator.not_,indicator_value)) #type:ignore
                )
            
            warning_str = f"Constraint not met!! \n{fail_cons}"
            
            self._minimize_desktop()
            self._show_popup(warning_str)
            logging.warning(warning_str)
            


def main():
    monitor = Monitor()
    monitor.run()

if __name__ == "__main__":
    main()