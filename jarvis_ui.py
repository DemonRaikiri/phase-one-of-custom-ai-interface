"""A compact local dashboard for the Jarvis wake-word assistant."""

from __future__ import annotations

import math
import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk
import psutil
import requests
from dotenv import load_dotenv
from openai import OpenAI


def enable_windows_dpi_awareness() -> None:
    """Prevent Windows from bitmap-scaling the Tk dashboard on high-DPI displays."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


BG = "#050c13"
PANEL = "#0c1c28"
CYAN = "#49d9ff"
TEXT = "#c7f3ff"


class JarvisDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("VEGETA")
        self.configure(bg=BG)
        self.geometry("1280x760")
        self.minsize(980, 620)
        if os.name == "nt":
            self.state("zoomed")
        self._pulse = 0
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        self.client = OpenAI() if os.environ.get("OPENAI_API_KEY") else None

        header = tk.Frame(self, bg="#07111b", height=70)
        header.pack(fill="x")
        tk.Label(header, text="VEGETA", fg=CYAN, bg="#07111b", font=("Consolas", 22, "bold")).pack(side="left", padx=24, pady=18)
        tk.Label(header, text="● ONLINE", fg="#47e889", bg="#102d26", font=("Segoe UI", 10, "bold"), padx=12, pady=5).pack(side="left")
        tk.Label(header, text="Listening for wake word: Hey Vegeta", fg=TEXT, bg="#07111b", font=("Segoe UI", 11)).pack(side="right", padx=24)

        body = tk.Frame(self, bg=BG)
        body.pack(expand=True, fill="both", padx=24, pady=22)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        stats = tk.Frame(body, bg=PANEL, highlightbackground="#174763", highlightthickness=1)
        stats.grid(row=0, column=0, sticky="nsw", padx=(0, 24))
        self.stats_values = {}
        for title, value in (("SYSTEM STATUS", "Wake phrase active"), ("CPU / MEMORY", "Loading…"), ("GPU / TEMPERATURE", "Loading…"), ("FAN SPEED", "Loading…"), ("SYSTEM UPTIME", "Loading…")):
            tk.Label(stats, text=title, fg=CYAN, bg=PANEL, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(20, 4))
            value_label = tk.Label(stats, text=value, fg=TEXT, bg=PANEL, font=("Segoe UI", 11), wraplength=220, justify="left")
            value_label.pack(anchor="w", padx=20, pady=(0, 12))
            self.stats_values[title] = value_label

        center = tk.Frame(body, bg=BG)
        center.grid(row=0, column=1, sticky="nsew")
        self.canvas = tk.Canvas(center, bg=BG, highlightthickness=0, width=500, height=500)
        self.canvas.pack(expand=True)
        avatar_path = Path(__file__).resolve().parent / "assets" / "jarvis_avatar.png"
        image = Image.open(avatar_path).convert("RGBA")
        image.thumbnail((320, 390), Image.LANCZOS)
        self.avatar = ImageTk.PhotoImage(image)
        self.avatar_item = self.canvas.create_image(250, 260, image=self.avatar)
        self.rings = [self.canvas.create_oval(60 + i * 18, 45 + i * 18, 440 - i * 18, 425 - i * 18, outline="#125071", width=2) for i in range(3)]
        self.canvas.tag_raise(self.avatar_item)
        tk.Label(center, text="VEGETA", fg=TEXT, bg=BG, font=("Segoe UI", 22, "bold")).pack()
        tk.Label(center, text="● Listening for wake word…", fg=CYAN, bg="#092131", font=("Segoe UI", 12, "bold"), padx=18, pady=10).pack(pady=12)

        convo = tk.Frame(body, bg=PANEL, width=300, highlightbackground="#174763", highlightthickness=1)
        convo.grid(row=0, column=2, sticky="nse", padx=(24, 0))
        tk.Label(convo, text="CONVERSATION", fg=TEXT, bg=PANEL, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=18)
        self.chat_log = tk.Text(convo, height=23, width=33, bg="#14303e", fg=TEXT, relief="flat", wrap="word", padx=12, pady=12)
        self.chat_log.pack(padx=18, pady=(0, 10))
        self.chat_log.insert("end", "VEGETA: Ready. Say ‘Hey Vegeta’ to launch your apps, or type a message here.\n\n")
        self.chat_log.configure(state="disabled")
        self.chat_input = tk.Entry(convo, bg="#07111b", fg=TEXT, insertbackground=TEXT, relief="flat")
        self.chat_input.pack(fill="x", padx=18, pady=(0, 8))
        self.chat_input.bind("<Return>", lambda _event: self.send_chat())
        tk.Button(convo, text="Send", command=self.send_chat, bg="#23769d", fg="white", relief="flat").pack(anchor="e", padx=18, pady=(0, 18))

        self.after(30, self.animate)
        self.after(500, self.refresh_stats)

    def animate(self) -> None:
        self._pulse += 0.09
        radius = 6 + int(4 * (1 + math.sin(self._pulse)))
        for index, ring in enumerate(self.rings):
            inset = 54 + index * 18 - radius
            self.canvas.coords(ring, inset, inset - 10, 500 - inset, 500 - inset - 10)
        self.canvas.coords(self.avatar_item, 250, 255 + int(math.sin(self._pulse * 0.7) * 7))
        self.after(30, self.animate)

    def refresh_stats(self) -> None:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(Path.home().anchor)
        self.stats_values["CPU / MEMORY"].configure(text=f"CPU {psutil.cpu_percent()}%  •  Memory {memory.percent}%\nDisk {disk.percent}% used")
        uptime_s = int(__import__("time").time() - psutil.boot_time())
        self.stats_values["SYSTEM UPTIME"].configure(text=f"{uptime_s // 3600:02d}:{(uptime_s % 3600) // 60:02d}:{uptime_s % 60:02d}")
        gpu, fans = self.gpu_status()
        self.stats_values["GPU / TEMPERATURE"].configure(text=gpu)
        self.stats_values["FAN SPEED"].configure(text=fans)
        self.after(1500, self.refresh_stats)

    @staticmethod
    def gpu_status() -> tuple[str, str]:
        try:
            raw = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,fan.speed", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.DEVNULL, timeout=2).strip().split(",")
            return (f"GPU {raw[0].strip()}%  •  {raw[1].strip()}°C", f"GPU fan {raw[2].strip()}%")
        except Exception:
            return ("GPU telemetry unavailable", "Fan telemetry unavailable")

    def append_chat(self, who: str, text: str) -> None:
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", f"{who}: {text}\n\n")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    def send_chat(self) -> None:
        text = self.chat_input.get().strip()
        if not text:
            return
        self.chat_input.delete(0, "end")
        self.append_chat("You", text)
        if not self.client:
            self.append_chat("VEGETA", "OpenAI API key is not available. Restart the dashboard after setup.")
            return
        threading.Thread(target=self.ask_openai, args=(text,), daemon=True).start()

    def ask_openai(self, text: str) -> None:
        try:
            response = self.client.responses.create(model="gpt-5-mini", input=[{"role": "system", "content": "You are Jarvis, a helpful desktop assistant. Be concise."}, {"role": "user", "content": text}])
            answer = response.output_text or "I did not receive a text response."
        except Exception as exc:
            answer = f"Chat request failed: {exc}"
        self.after(0, lambda: self.append_chat("VEGETA", answer))


if __name__ == "__main__":
    enable_windows_dpi_awareness()
    JarvisDashboard().mainloop()
