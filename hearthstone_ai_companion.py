"""
===================================================================
HEARTHSTONE AI - STANDALONE PC SCREEN READER & STRATEGY COMPANION
===================================================================
This Python program runs standalone on your PC:
1. Detects the Hearthstone game window.
2. Captures game screen automatically or on Hotkey (F1 / Space).
3. Transmits the frame to your HearthAI Engine.
4. Renders a transparent Always-On-Top Tactical HUD over your game.

Requirements:
  pip install pillow mss requests keyboard pygetwindow

Run:
  python hearthstone_ai_companion.py
===================================================================
"""

import sys
import time
import base64
import io
import json
import threading
import tkinter as tk
from tkinter import font
import requests

try:
    import mss
    import pygetwindow as gw
    from PIL import Image
    import keyboard
except ImportError:
    print("[!] Missing required modules. Please run:")
    print("    pip install pillow mss requests keyboard pygetwindow")
    sys.exit(1)

# Configuration
API_ENDPOINT = "https://ais-dev-v6u4urquzqzlmfxr5q5g4o-804622581119.europe-west2.run.app/api/analyze-hearthstone"
HOTKEY = "f1"  # Press F1 in game to trigger analysis
WINDOW_TITLE_KEYWORD = "Hearthstone"

class HearthstoneOverlayHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("HearthAI Tactical Overlay")
        
        # Configure transparent & always-on-top window
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)  # 90% opacity
        self.root.overrideredirect(True)      # Borderless HUD
        self.root.geometry("380x520+50+80")   # Placed on upper left by default
        self.root.configure(bg="#090d16")
        
        self.is_analyzing = False
        
        # Build UI Components
        self.setup_ui()
        
        # Allow dragging the HUD
        self.root.bind("<ButtonPress-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.on_drag)

    def setup_ui(self):
        # Header bar
        header = tk.Frame(self.root, bg="#131b2e", height=38)
        header.pack(fill=tk.X, side=tk.TOP)
        
        title_label = tk.Label(
            header,
            text="⚔️ HEARTH-AI OVERLAY",
            font=("Impact", 13),
            fg="#f59e0b",
            bg="#131b2e",
            padx=10,
            pady=6
        )
        title_label.pack(side=tk.LEFT)
        
        btn_close = tk.Button(
            header,
            text="✕",
            font=("Arial", 10, "bold"),
            fg="#94a3b8",
            bg="#131b2e",
            bd=0,
            command=self.root.destroy,
            padx=8
        )
        btn_close.pack(side=tk.RIGHT)
        
        # Lethal Banner
        self.lethal_frame = tk.Frame(self.root, bg="#ef4444", pady=4)
        self.lethal_label = tk.Label(
            self.lethal_frame,
            text="🔥 LETHAL DETECTED! 🔥",
            font=("Arial", 12, "bold"),
            fg="#ffffff",
            bg="#ef4444"
        )
        self.lethal_label.pack()
        # Initially hidden
        # self.lethal_frame.pack(fill=tk.X)
        
        # Status
        self.status_label = tk.Label(
            self.root,
            text="Press [F1] in game to analyze turn",
            font=("Arial", 9, "italic"),
            fg="#38bdf8",
            bg="#090d16",
            pady=4
        )
        self.status_label.pack()
        
        # Main Content Scrollable
        content_frame = tk.Frame(self.root, bg="#090d16", padx=10, pady=4)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Optimal Sequence Box
        tk.Label(content_frame, text="OPTIMAL TURN STEPS:", font=("Arial", 9, "bold"), fg="#e2e8f0", bg="#090d16").pack(anchor="w")
        self.steps_text = tk.Text(content_frame, height=8, bg="#0f172a", fg="#a5f3fc", font=("Consolas", 9), bd=0, padx=6, pady=6)
        self.steps_text.pack(fill=tk.X, pady=4)
        self.steps_text.insert(tk.END, "Ready. Waiting for Hearthstone game capture...")
        self.steps_text.configure(state="disabled")
        
        # Hand & Board summary
        tk.Label(content_frame, text="IDENTIFIED CARDS & BOARD:", font=("Arial", 9, "bold"), fg="#e2e8f0", bg="#090d16").pack(anchor="w")
        self.board_text = tk.Text(content_frame, height=5, bg="#0f172a", fg="#cbd5e1", font=("Consolas", 8), bd=0, padx=6, pady=6)
        self.board_text.pack(fill=tk.X, pady=4)
        self.board_text.insert(tk.END, "- Hand: ---\n- Mana: ---")
        self.board_text.configure(state="disabled")
        
        # Warning / Counterplay
        self.warning_label = tk.Label(
            content_frame,
            text="Counterplay note: --",
            font=("Arial", 8),
            fg="#fbbf24",
            bg="#090d16",
            wraplength=350,
            justify="left"
        )
        self.warning_label.pack(anchor="w", pady=4)

        # Trigger Button
        self.btn_capture = tk.Button(
            self.root,
            text="⚡ Analyze Screen Now (F1)",
            font=("Arial", 10, "bold"),
            bg="#d97706",
            fg="#ffffff",
            activebackground="#b45309",
            bd=0,
            pady=8,
            command=self.trigger_capture_async
        )
        self.btn_capture.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=8)

    def start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        deltax = event.x - self.drag_x
        deltay = event.y - self.drag_y
        new_x = self.root.winfo_x() + deltax
        new_y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{new_x}+{new_y}")

    def update_hud(self, data):
        self.status_label.config(text="✓ Turn Analysis Completed", fg="#4ade80")
        
        # Check Lethal
        lethal = data.get("lethal", {})
        if lethal.get("isLethalAvailable", False):
            self.lethal_frame.pack(fill=tk.X, before=self.status_label)
            self.lethal_label.config(text=f"🔥 LETHAL AVAILABLE ({lethal.get('exactDamagePossible', '?')} DMG) 🔥")
        else:
            self.lethal_frame.pack_forget()

        # Update Steps
        self.steps_text.configure(state="normal")
        self.steps_text.delete("1.0", tk.END)
        steps = data.get("optimalTurnPlan", [])
        if steps:
            for s in steps:
                step_no = s.get("stepNumber", "")
                src = s.get("sourceName", "")
                tgt = f" -> {s.get('targetName')}" if s.get('targetName') else ""
                reason = s.get("reasoning", "")
                self.steps_text.insert(tk.END, f"[{step_no}] {src}{tgt}\n    {reason}\n\n")
        else:
            self.steps_text.insert(tk.END, data.get("strategicSummary", "No actions found."))
        self.steps_text.configure(state="disabled")

        # Update Board & Hand
        self.board_text.configure(state="normal")
        self.board_text.delete("1.0", tk.END)
        cards = [c.get("name", "") for c in data.get("cardsInHand", [])]
        mana = data.get("mana", {})
        mana_str = f"{mana.get('current', '?')}/{mana.get('max', '?')}"
        self.board_text.insert(tk.END, f"• Mana: {mana_str}\n• Hand: {', '.join(cards) if cards else 'None detected'}")
        self.board_text.configure(state="disabled")

        # Warning
        warning = data.get("threatWarning", "")
        self.warning_label.config(text=f"⚠️ {warning}" if warning else "")

    def trigger_capture_async(self):
        if self.is_analyzing:
            return
        threading.Thread(target=self.capture_and_analyze, daemon=True).start()

    def capture_and_analyze(self):
        self.is_analyzing = True
        self.status_label.config(text="📷 Capturing Hearthstone Screen...", fg="#f59e0b")
        
        try:
            # 1. Locate Hearthstone Window if available
            hs_windows = [w for w in gw.getAllWindows() if WINDOW_TITLE_KEYWORD.lower() in w.title.lower()]
            
            with mss.mss() as sct:
                if hs_windows:
                    win = hs_windows[0]
                    bbox = {"top": max(0, win.top), "left": max(0, win.left), "width": max(300, win.width), "height": max(200, win.height)}
                    sct_img = sct.grab(bbox)
                else:
                    # Fallback to primary monitor full screen
                    sct_img = sct.grab(sct.monitors[1])
                
                # Convert to PIL Image and JPEG base64
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                # Resize slightly for optimal speed
                img.thumbnail((1280, 720))
                
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                base64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
            
            self.status_label.config(text="🤖 HearthAI is analyzing cards & lethal...", fg="#eab308")
            
            # Send to API
            payload = {
                "image": f"data:image/jpeg;base64,{base64_img}",
                "mode": "balanced"
            }
            res = requests.post(API_ENDPOINT, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                self.root.after(0, self.update_hud, data)
            else:
                self.status_label.config(text=f"Error {res.status_code}: Check server", fg="#ef4444")
        except Exception as e:
            print(f"[Error] {e}")
            self.status_label.config(text=f"Capture failed: {str(e)[:25]}...", fg="#ef4444")
        finally:
            self.is_analyzing = False

def register_hotkey(overlay):
    def on_press():
        overlay.trigger_capture_async()
    try:
        keyboard.add_hotkey(HOTKEY, on_press)
        print(f"[✓] Global Hotkey [{HOTKEY.upper()}] registered! Press while playing Hearthstone.")
    except Exception as e:
        print(f"[!] Could not register global keyboard hook: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print(" Starting HearthAI Standalone Overlay...")
    print(" Target server:", API_ENDPOINT)
    print("=" * 60)
    
    app = HearthstoneOverlayHUD()
    threading.Thread(target=register_hotkey, args=(app,), daemon=True).start()
    app.root.mainloop()
