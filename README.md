
This is a small tool to supervise your time allocation on different tasks, build on [ActivityWatch](https://github.com/ActivityWatch/activitywatch).

If your current time allocation is not what you want, you can use this tool to help you. It will show warning message and minimize all windows when you have been working on one wrong task for a period of time.

Currently only works on Windows.



# Usage
Just change `config.json`, and run `main.py`.

To run as a background service, you can add `start pythonw.exe main.py` to your startup programs, see `run_bg.bat`.


Config:
```
{
    "monitor_interval": 100,  # monitor interval in minutes
    "check_interval": 5,  # check time period in seconds
    "constraint":
    [
        {
            "term": ["Work"], #  categories to monitor
            "op": "ge", # operator to check, see python `operator` module
            "value": 0.7 # threshold
        }
    ]
}
```

It means all events under `Work` category should occupy at least 70% of afk time in the last 100 minutes. The program will check if this constraint is still not met in the last 5 seconds. If so, it will pop up a warning message and minimize all windows.


