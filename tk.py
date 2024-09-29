import tkinter as tk
from threading import Thread

def create_window():
    window = tk.Toplevel(root)
    window.title("Popup")
    label = tk.Label(window, text="This is a popup window")
    label.pack()

def create_multiple_windows():
    # 创建多个窗口并让它们显示
    for _ in range(3):
        root.after(0, create_window)  # 确保所有窗口在主线程中创建

root = tk.Tk()
root.title("Main Window")

# 在单独的线程中调用函数来创建窗口
thread = Thread(target=create_multiple_windows)
thread.start()

root.mainloop()
