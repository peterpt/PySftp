import customtkinter as ctk
from customtkinter import CTkInputDialog
import tkinter
from tkinter import colorchooser
import os
import shutil
import argparse
from PIL import Image
import configparser
import stat
import threading
import base64
import io
import time
import re
from resources import FOLDER_ICON_B64, FILE_ICON_B64
from sftp_client import (
    connect_sftp, upload_file, download_remote_item,
    rename_remote_item, delete_remote_item, create_remote_directory,
    open_sftp_robust,
    perform_port_knock
)

class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, title, prompt):
        super().__init__()
        self.title(title); self.lift(); self.attributes("-topmost", True); self.grab_set(); self.result = None
        self.label = ctk.CTkLabel(self, text=prompt); self.label.pack(padx=20, pady=10)
        self.entry = ctk.CTkEntry(self, width=250, show="*"); self.entry.pack(padx=20, pady=5); self.entry.focus()
        self.show_password_var = ctk.StringVar(value="off")
        self.show_password_check = ctk.CTkCheckBox(self, text="Show password", variable=self.show_password_var, onvalue="on", offvalue="off", command=self.toggle_password_visibility); self.show_password_check.pack(padx=20, pady=5)
        self.button_frame = ctk.CTkFrame(self); self.button_frame.pack(pady=10)
        self.ok_button = ctk.CTkButton(self.button_frame, text="OK", command=self.on_ok); self.ok_button.pack(side="left", padx=10)
        self.cancel_button = ctk.CTkButton(self.button_frame, text="Cancel", command=self.on_cancel); self.cancel_button.pack(side="left", padx=10)
        self.bind("<Return>", lambda event: self.on_ok()); self.bind("<Escape>", lambda event: self.on_cancel())
    def toggle_password_visibility(self): self.entry.configure(show="" if self.show_password_var.get() == "on" else "*")
    def on_ok(self): self.result = self.entry.get(); self.destroy()
    def on_cancel(self): self.result = None; self.destroy()
    def get_input(self): self.wait_window(); return self.result

class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, title, message):
        super().__init__()
        self.title(title); self.lift(); self.attributes("-topmost", True); self.grab_set(); self.result = False
        self.label = ctk.CTkLabel(self, text=message, wraplength=300); self.label.pack(padx=20, pady=20)
        self.button_frame = ctk.CTkFrame(self); self.button_frame.pack(pady=(0, 20), padx=20, fill="x")
        self.yes_button = ctk.CTkButton(self.button_frame, text="Yes", command=self.on_yes); self.yes_button.pack(side="left", padx=10, expand=True)
        self.cancel_button = ctk.CTkButton(self.button_frame, text="Cancel", command=self.on_cancel); self.cancel_button.pack(side="right", padx=10, expand=True)
        self.bind("<Return>", lambda event: self.on_yes()); self.bind("<Escape>", lambda event: self.on_cancel())
    def on_yes(self): self.result = True; self.destroy()
    def on_cancel(self): self.result = False; self.destroy()
    def get_result(self): self.wait_window(); return self.result

class EditProfileDialog(ctk.CTkToplevel):
    def __init__(self, master, config, profile_name, is_new=False):
        super().__init__(master)
        self.config = config; self.profile_name = profile_name
        self.title(f"Edit Profile: {profile_name}"); self.lift(); self.attributes("-topmost", True); self.grab_set()
        self.conn_frame = ctk.CTkFrame(self); self.conn_frame.pack(padx=10, pady=(10, 5), fill="x")
        self.conn_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.conn_frame, text="Target Host:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.host_entry = ctk.CTkEntry(self.conn_frame); self.host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.conn_frame, text="Target User:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.user_entry = ctk.CTkEntry(self.conn_frame); self.user_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.conn_frame, text="Target Port:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.port_entry = ctk.CTkEntry(self.conn_frame); self.port_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.use_jump_var = ctk.BooleanVar()
        self.jump_check = ctk.CTkCheckBox(self, text="Use Jump Host (Bastion)", variable=self.use_jump_var, command=self.toggle_jump_frame)
        self.jump_check.pack(padx=10, pady=5, anchor="w")
        self.jump_frame = ctk.CTkFrame(self); self.jump_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.jump_frame, text="Jump Host:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.jump_host_entry = ctk.CTkEntry(self.jump_frame); self.jump_host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.jump_frame, text="Jump User:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.jump_user_entry = ctk.CTkEntry(self.jump_frame); self.jump_user_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.jump_frame, text="Jump Port:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.jump_port_entry = ctk.CTkEntry(self.jump_frame); self.jump_port_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.knock_frame = ctk.CTkFrame(self); self.knock_frame.pack(padx=10, pady=5, fill="x")
        self.knock_enabled_var = ctk.BooleanVar()
        self.knock_enabled_check = ctk.CTkCheckBox(self.knock_frame, text="Enable Port Knocking", variable=self.knock_enabled_var)
        self.knock_enabled_check.pack(padx=10, pady=5, anchor="w")
        ctk.CTkLabel(self.knock_frame, text="Ports (comma-separated):").pack(padx=10, anchor="w")
        self.ports_entry = ctk.CTkEntry(self.knock_frame, placeholder_text="e.g., 7000,8000,9000"); self.ports_entry.pack(padx=10, pady=(0, 5), fill="x")
        ctk.CTkLabel(self.knock_frame, text="Delay between knocks (s):").pack(padx=10, anchor="w")
        self.delay_entry = ctk.CTkEntry(self.knock_frame); self.delay_entry.pack(padx=10, pady=(0, 10), fill="x")
        if not is_new and self.config.has_section(self.profile_name):
            p = self.config[self.profile_name]
            self.host_entry.insert(0, p.get('host', '')); self.user_entry.insert(0, p.get('user', '')); self.port_entry.insert(0, p.get('port', '22'))
            use_jump = p.getboolean('use_jump', False); self.use_jump_var.set(use_jump)
            if use_jump:
                self.jump_host_entry.insert(0, p.get('jump_host', '')); self.jump_user_entry.insert(0, p.get('jump_user', '')); self.jump_port_entry.insert(0, p.get('jump_port', '22'))
            self.knock_enabled_var.set(p.getboolean('knock_enabled', False)); self.ports_entry.insert(0, p.get('knock_ports', '')); self.delay_entry.insert(0, p.get('knock_delay', '1'))
        self.toggle_jump_frame()
        self.save_button = ctk.CTkButton(self, text="Save Profile", command=self.save_and_close); self.save_button.pack(padx=10, pady=10, fill="x")
    def toggle_jump_frame(self):
        if self.use_jump_var.get(): self.jump_frame.pack(padx=10, pady=5, fill="x")
        else: self.jump_frame.pack_forget()
    def save_and_close(self):
        if not self.config.has_section(self.profile_name): self.config.add_section(self.profile_name)
        self.config.set(self.profile_name, 'host', self.host_entry.get()); self.config.set(self.profile_name, 'user', self.user_entry.get())
        self.config.set(self.profile_name, 'port', self.port_entry.get()); use_jump = self.use_jump_var.get(); self.config.set(self.profile_name, 'use_jump', str(use_jump))
        if use_jump:
            self.config.set(self.profile_name, 'jump_host', self.jump_host_entry.get()); self.config.set(self.profile_name, 'jump_user', self.jump_user_entry.get())
            self.config.set(self.profile_name, 'jump_port', self.jump_port_entry.get())
        self.config.set(self.profile_name, 'knock_enabled', str(self.knock_enabled_var.get())); self.config.set(self.profile_name, 'knock_ports', self.ports_entry.get())
        self.config.set(self.profile_name, 'knock_delay', self.delay_entry.get())
        with open('config.ini', 'w') as configfile: self.config.write(configfile)
        self.destroy()

class ManageProfilesDialog(ctk.CTkToplevel):
    def __init__(self, master, config):
        super().__init__(master)
        self.master_app = master; self.config = config; self.profile_to_load = None
        self.selected_profile_name = None; self.selected_profile_widget = None; self.highlight_color = "#36719F"
        self.title("Manage Profiles"); self.lift(); self.attributes("-topmost", True); self.grab_set()
        self.geometry("450x300"); self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        self.main_label = ctk.CTkLabel(self, text="Select a profile to manage:"); self.main_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)
        self.scrollable_frame = ctk.CTkScrollableFrame(self); self.scrollable_frame.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="nsew")
        self.button_frame = ctk.CTkFrame(self); self.button_frame.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="ns")
        self.load_button = ctk.CTkButton(self.button_frame, text="Load", command=self.load_selected_profile, state="disabled"); self.load_button.pack(pady=5, padx=10, fill="x")
        self.new_button = ctk.CTkButton(self.button_frame, text="New", command=self.new_profile); self.new_button.pack(pady=5, padx=10, fill="x")
        self.edit_button = ctk.CTkButton(self.button_frame, text="Edit", command=self.edit_selected_profile, state="disabled"); self.edit_button.pack(pady=5, padx=10, fill="x")
        self.delete_button = ctk.CTkButton(self.button_frame, text="Delete", fg_color="#D32F2F", hover_color="#B71C1C", command=self.delete_selected_profile, state="disabled"); self.delete_button.pack(pady=(10, 5), padx=10, fill="x")
        self.draw_profiles()
    def draw_profiles(self):
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        self.deselect_profile()
        profile_names = sorted([s for s in self.config.sections() if s != 'Settings'])
        if not profile_names: ctk.CTkLabel(self.scrollable_frame, text="No profiles saved.").pack(pady=10); return
        for name in profile_names:
            label = ctk.CTkLabel(self.scrollable_frame, text=name, anchor="w", corner_radius=5, padx=10); label.pack(fill="x", pady=2)
            label.bind("<Button-1>", lambda event, n=name, w=label: self.handle_profile_selection(n, w))
    def handle_profile_selection(self, profile_name, widget):
        if self.selected_profile_widget and self.selected_profile_widget.winfo_exists(): self.selected_profile_widget.configure(fg_color="transparent")
        widget.configure(fg_color=self.highlight_color); self.selected_profile_name = profile_name; self.selected_profile_widget = widget
        self.load_button.configure(state="normal"); self.edit_button.configure(state="normal"); self.delete_button.configure(state="normal")
    def deselect_profile(self):
        if self.selected_profile_widget and self.selected_profile_widget.winfo_exists(): self.selected_profile_widget.configure(fg_color="transparent")
        self.selected_profile_name = None; self.selected_profile_widget = None
        self.load_button.configure(state="disabled"); self.edit_button.configure(state="disabled"); self.delete_button.configure(state="disabled")
    def load_selected_profile(self):
        if self.selected_profile_name: self.profile_to_load = self.selected_profile_name; self.destroy()
    def new_profile(self):
        dialog = CTkInputDialog(title="New Profile", text="Enter a name for the new profile:"); new_name = dialog.get_input()
        if not new_name: return
        if self.config.has_section(new_name): ConfirmDialog(title="Profile Exists", message=f"A profile named '{new_name}' already exists."); return
        self.edit_profile(new_name, is_new=True)
    def edit_selected_profile(self):
        if self.selected_profile_name: self.edit_profile(self.selected_profile_name)
    def edit_profile(self, profile_name, is_new=False):
        edit_dialog = EditProfileDialog(self, self.config, profile_name, is_new=is_new); self.wait_window(edit_dialog)
        self.draw_profiles()
    def delete_selected_profile(self):
        if not self.selected_profile_name: return
        dialog = ConfirmDialog(title="Confirm Deletion", message=f"Are you sure you want to delete the profile '{self.selected_profile_name}'?")
        if dialog.get_result():
            self.config.remove_section(self.selected_profile_name)
            with open('config.ini', 'w') as configfile: self.config.write(configfile)
            self.master_app.status_bar.configure(text=f"Profile '{self.selected_profile_name}' deleted."); self.draw_profiles()
    def get_selection(self): self.wait_window(); return self.profile_to_load

class TerminalChoiceDialog(ctk.CTkToplevel):
    def __init__(self, target_name, jump_name):
        super().__init__()
        self.title("Choose Terminal"); self.lift(); self.attributes("-topmost", True); self.grab_set(); self.result = None
        self.label = ctk.CTkLabel(self, text="Open SSH terminal to which server?"); self.label.pack(padx=20, pady=10)
        self.button_frame = ctk.CTkFrame(self); self.button_frame.pack(pady=10, padx=20, fill="x")
        self.target_button = ctk.CTkButton(self.button_frame, text=f"Target: {target_name}", command=lambda: self.select("target")); self.target_button.pack(pady=5, fill="x")
        if jump_name:
            self.jump_button = ctk.CTkButton(self.button_frame, text=f"Jump Host: {jump_name}", command=lambda: self.select("jump")); self.jump_button.pack(pady=5, fill="x")
    def select(self, choice): self.result = choice; self.destroy()
    def get_choice(self): self.wait_window(); return self.result

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, current_bg, current_fg):
        super().__init__(master)
        self.title("Settings"); self.lift(); self.attributes("-topmost", True); self.grab_set()
        self.bg_color = current_bg; self.fg_color = current_fg; self.saved = False
        self.label = ctk.CTkLabel(self, text="Terminal Colors", font=ctk.CTkFont(weight="bold")); self.label.grid(row=0, column=0, columnspan=2, padx=20, pady=10)
        self.bg_button = ctk.CTkButton(self, text="Choose Background Color", command=self.choose_bg); self.bg_button.grid(row=1, column=0, padx=20, pady=10)
        self.fg_button = ctk.CTkButton(self, text="Choose Text Color", command=self.choose_fg); self.fg_button.grid(row=1, column=1, padx=20, pady=10)
        self.preview_label = ctk.CTkLabel(self, text="Color Preview", fg_color=self.bg_color, text_color=self.fg_color, corner_radius=5); self.preview_label.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.save_button = ctk.CTkButton(self, text="Save", command=self.save_and_close); self.save_button.grid(row=3, column=0, columnspan=2, padx=20, pady=20)
    def choose_bg(self):
        color_code = colorchooser.askcolor(title="Choose background color")
        if color_code[1]: self.bg_color = color_code[1]; self.update_preview()
    def choose_fg(self):
        color_code = colorchooser.askcolor(title="Choose text color")
        if color_code[1]: self.fg_color = color_code[1]; self.update_preview()
    def update_preview(self): self.preview_label.configure(fg_color=self.bg_color, text_color=self.fg_color)
    def save_and_close(self): self.saved = True; self.destroy()
    def get_settings(self): self.wait_window(); return (self.bg_color, self.fg_color) if self.saved else None

class TerminalWindow(ctk.CTkToplevel):
    def __init__(self, master, channel, title, bg_color, fg_color):
        super().__init__(master)
        self.title(f"SSH Terminal - {title}"); self.geometry("800x600"); self.channel = channel
        self.textbox = ctk.CTkTextbox(self, font=("monospace", 12), fg_color=bg_color, text_color=fg_color)
        self.textbox.pack(expand=True, fill="both")
        self.textbox.bind("<Key>", self.on_key_press, add="+")
        self.textbox.bind("<Control-c>", self.copy_text); self.textbox.bind("<Control-v>", self.paste_text)
        self.textbox.bind("<Control-Shift-C>", self.copy_text); self.textbox.bind("<Control-Shift-V>", self.paste_text)
        self.read_thread = threading.Thread(target=self.read_from_shell, daemon=True); self.read_thread.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.ansi_escape_pattern = re.compile(r'(\x1B\[[0-?]*[ -/]*[@-~]|\x1B].*?(\x07|\x1B\\))')
    def copy_text(self, event=None):
        try:
            selected_text = self.textbox.get("sel.first", "sel.last")
            if selected_text: self.clipboard_clear(); self.clipboard_append(selected_text)
        except tkinter.TclError: pass
        return "break"
    def paste_text(self, event=None):
        try:
            clipboard_text = self.clipboard_get()
            if clipboard_text and self.channel.send_ready(): self.channel.send(clipboard_text)
        except tkinter.TclError: pass
        return "break"
    def on_key_press(self, event):
        if not self.channel.send_ready(): return "break"
        if event.keysym == 'Return': self.channel.send('\n')
        elif event.keysym == 'BackSpace': self.channel.send('\x08')
        elif event.keysym == 'Tab': self.channel.send('\t')
        elif event.keysym == 'Up': self.channel.send('\x1b[A')
        elif event.keysym == 'Down': self.channel.send('\x1b[B')
        elif event.keysym == 'Right': self.channel.send('\x1b[C')
        elif event.keysym == 'Left': self.channel.send('\x1b[D')
        elif event.char and event.char.isprintable(): self.channel.send(event.char)
        return "break"
    def read_from_shell(self):
        try:
            while self.channel and not self.channel.closed:
                data = self.channel.recv(1024).decode('utf-8', errors='ignore')
                if data: self.after(0, self.insert_text, data)
                else: break
        except Exception: pass
        finally: self.after(0, self.on_close)
    def insert_text(self, text):
        if self.textbox.winfo_exists():
            clean_text = self.ansi_escape_pattern.sub('', text); clean_text = clean_text.replace('\r', '')
            self.textbox.insert("end", clean_text); self.textbox.see("end")
    def on_close(self):
        if self.channel and not self.channel.closed: self.channel.close()
        self.destroy()

class App(ctk.CTk):
    def __init__(self, cli_args):
        super().__init__()
        self.cli_args = cli_args; self.jump_client = None; self.ssh_client = None; self.config_file = 'config.ini'
        self.sftp_client = None; self.local_path = os.getcwd(); self.remote_path = "."; self.context_menu_item = None
        self.selected_local_widget = None; self.selected_remote_widget = None; self.highlight_color = "#36719F"
        self.terminal_bg_color = "#000000"; self.terminal_fg_color = "#FFFFFF"; self.current_knock_config = {'enabled': False}
        self.current_scroll_widget = None  # To track which widget is being hovered for scrolling
        
        self.title("PySFTP - Secure File Transfer"); self.geometry("1200x800"); self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        try:
            folder_data = base64.b64decode(FOLDER_ICON_B64); file_data = base64.b64decode(FILE_ICON_B64)
            self.folder_icon = ctk.CTkImage(Image.open(io.BytesIO(folder_data)), size=(20, 20))
            self.file_icon = ctk.CTkImage(Image.open(io.BytesIO(file_data)), size=(20, 20))
        except Exception as e:
            print(f"Error loading embedded icons: {e}.")
            self.folder_icon = ctk.CTkImage(Image.new("RGB", (20, 20), "blue")); self.file_icon = ctk.CTkImage(Image.new("RGB", (20, 20), "gray"))
        self.connection_container = ctk.CTkFrame(self); self.connection_container.grid(row=0, column=0, padx=10, pady=(10,5), sticky="new"); self.connection_container.grid_columnconfigure(0, weight=1)
        self.top_frame = ctk.CTkFrame(self.connection_container, fg_color="transparent"); self.top_frame.grid(row=0, column=0, padx=10, pady=(5,10), sticky="ew")
        self.top_frame.grid_columnconfigure((1, 2, 3, 4), weight=1); self.top_frame.grid_columnconfigure((5, 6, 7, 8, 9), weight=0)
        self.target_label = ctk.CTkLabel(self.top_frame, text="Target Server:", font=ctk.CTkFont(weight="bold")); self.target_label.grid(row=0, column=0, padx=(0,10), pady=5, sticky="w")
        self.host_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Target Host"); self.host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")
        self.username_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Target Username"); self.username_entry.grid(row=0, column=2, padx=5, pady=5, sticky="we")
        self.password_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Target Password", show="*"); self.password_entry.grid(row=0, column=3, padx=5, pady=5, sticky="we")
        self.port_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Target Port"); self.port_entry.grid(row=0, column=4, padx=5, pady=5, sticky="we")
        self.settings_button = ctk.CTkButton(self.top_frame, text="Settings", width=70, command=self.open_settings_dialog); self.settings_button.grid(row=0, column=5, padx=(10,0), pady=5)
        self.profiles_button = ctk.CTkButton(self.top_frame, text="Profiles", width=70, command=self.manage_profiles_dialog); self.profiles_button.grid(row=0, column=6, padx=(5,0), pady=5)
        self.save_button = ctk.CTkButton(self.top_frame, text="Save", width=60, command=self.save_profile); self.save_button.grid(row=0, column=7, padx=(5,0), pady=5)
        self.connect_button = ctk.CTkButton(self.top_frame, text="Connect", width=100, command=self.toggle_connection); self.connect_button.grid(row=0, column=8, padx=5, pady=5)
        self.terminal_button = ctk.CTkButton(self.top_frame, text="SSH Terminal", width=100, command=self.open_terminal_choice, state="disabled"); self.terminal_button.grid(row=0, column=9, padx=5, pady=5)
        self.use_jump_host_var = ctk.BooleanVar(); self.jump_checkbox = ctk.CTkCheckBox(self.connection_container, text="Use Jump Host (Bastion)", variable=self.use_jump_host_var, command=self.toggle_jump_host_frame)
        self.jump_checkbox.grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.jump_host_frame = ctk.CTkFrame(self.connection_container, fg_color="transparent")
        self.jump_host_frame.grid(row=2, column=0, padx=10, pady=(0,10), sticky="ew"); self.jump_host_frame.grid_columnconfigure((1, 2, 3, 4), weight=1)
        self.jump_label = ctk.CTkLabel(self.jump_host_frame, text="Jump Host:", font=ctk.CTkFont(weight="bold")); self.jump_label.grid(row=0, column=0, padx=(0,10), pady=5, sticky="w")
        self.jump_host_entry = ctk.CTkEntry(self.jump_host_frame, placeholder_text="Jump Host"); self.jump_host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")
        self.jump_user_entry = ctk.CTkEntry(self.jump_host_frame, placeholder_text="Jump Username"); self.jump_user_entry.grid(row=0, column=2, padx=5, pady=5, sticky="we")
        self.jump_password_entry = ctk.CTkEntry(self.jump_host_frame, placeholder_text="Jump Password", show="*"); self.jump_password_entry.grid(row=0, column=3, padx=5, pady=5, sticky="we")
        self.jump_port_entry = ctk.CTkEntry(self.jump_host_frame, placeholder_text="Jump Port (22)"); self.jump_port_entry.grid(row=0, column=4, padx=5, pady=5, sticky="we")
        self.main_frame = ctk.CTkFrame(self); self.main_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.main_frame.grid_columnconfigure((0, 1), weight=1); self.main_frame.grid_rowconfigure(1, weight=1)
        self.local_frame = ctk.CTkFrame(self.main_frame); self.local_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew"); self.local_frame.grid_columnconfigure(0, weight=1)
        self.local_path_label = ctk.CTkLabel(self.main_frame, text=f"Local: {self.local_path}", anchor="w"); self.local_path_label.grid(row=0, column=0, padx=10, pady=(5,0), sticky="ew")
        self.local_file_list = ctk.CTkScrollableFrame(self.local_frame, label_text="Local Files"); self.local_file_list.pack(expand=True, fill="both", padx=5, pady=5)
        self.remote_frame = ctk.CTkFrame(self.main_frame); self.remote_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew"); self.remote_frame.grid_columnconfigure(0, weight=1)
        self.remote_path_label = ctk.CTkLabel(self.main_frame, text="Remote: Not Connected", anchor="w"); self.remote_path_label.grid(row=0, column=1, padx=10, pady=(5,0), sticky="ew")
        self.remote_file_list = ctk.CTkScrollableFrame(self.remote_frame, label_text="Remote Server"); self.remote_file_list.pack(expand=True, fill="both", padx=5, pady=5)
        self.status_bar = ctk.CTkLabel(self, text="Ready", anchor="w"); self.status_bar.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.remote_context_menu = tkinter.Menu(self, tearoff=0); self.remote_context_menu.add_command(label="Download", command=self.context_download); self.remote_context_menu.add_command(label="Move/Rename", command=self.context_remote_move)
        self.remote_context_menu.add_command(label="Delete", command=self.context_remote_delete); self.remote_context_menu.add_separator(); self.remote_context_menu.add_command(label="Create Folder", command=self.context_remote_create_folder)
        self.local_context_menu = tkinter.Menu(self, tearoff=0); self.local_context_menu.add_command(label="Upload", command=self.context_upload); self.local_context_menu.add_command(label="Move/Rename", command=self.context_local_move)
        self.local_context_menu.add_command(label="Delete", command=self.context_local_delete); self.local_context_menu.add_separator(); self.local_context_menu.add_command(label="Create Folder", command=self.context_local_create_folder)
        self.local_file_list.bind("<Button-3>", lambda event: self.show_local_context_menu(event)); self.remote_file_list.bind("<Button-3>", lambda event: self.show_remote_context_menu(event))
        self.local_file_list.bind("<Button-1>", lambda event: self.handle_selection(None, "local")); self.remote_file_list.bind("<Button-1>", lambda event: self.handle_selection(None, "remote"))
        self.load_app_settings()
        if cli_args.host and cli_args.username:
            self.host_entry.insert(0, cli_args.host); self.username_entry.insert(0, cli_args.username)
            if cli_args.password: self.password_entry.insert(0, cli_args.password)
            if cli_args.port: self.port_entry.insert(0, str(cli_args.port))
        if cli_args.jump_host: self.jump_host_entry.insert(0, cli_args.jump_host); self.jump_user_entry.insert(0, cli_args.jump_user)
        if cli_args.jump_password: self.jump_password_entry.insert(0, cli_args.jump_password)
        if cli_args.jump_port: self.jump_port_entry.insert(0, str(cli_args.jump_port))
        if cli_args.jump_host and cli_args.jump_user: self.jump_checkbox.select()
        self.toggle_jump_host_frame(); self.populate_local_files()
        if self.cli_args.host and self.cli_args.username: self.after(200, self.toggle_connection)
        
        # --- INIT SCROLL BINDINGS ---
        self._setup_scroll_bindings()
        # ----------------------------

        self.host_entry.bind("<KeyRelease>", self.clear_knock_config); self.username_entry.bind("<KeyRelease>", self.clear_knock_config); self.port_entry.bind("<KeyRelease>", self.clear_knock_config)
    def clear_knock_config(self, event=None):
        if self.current_knock_config.get('enabled'):
            self.status_bar.configure(text="Ready (Profile-specific settings cleared by manual edit)")
        self.current_knock_config = {'enabled': False}
    def toggle_connection(self):
        if self.sftp_client: threading.Thread(target=self._perform_disconnect, daemon=True).start()
        else: self.initiate_connection()
    def initiate_connection(self):
        target_host = self.host_entry.get(); target_user = self.username_entry.get(); target_pass = self.password_entry.get(); target_port_str = self.port_entry.get()
        if not target_host or not target_user: self.status_bar.configure(text="Error: Target Host and Username are required."); return
        target_port = int(target_port_str) if target_port_str.isdigit() else 22
        if not target_port_str: self.port_entry.insert(0, str(target_port))
        if not target_pass:
            dialog = PasswordDialog(title="Target Password", prompt=f"Password for {target_user}@{target_host}:"); target_pass = dialog.get_input()
            if target_pass is None: self.status_bar.configure(text="Connection canceled."); return
            if not self.password_entry.get(): self.password_entry.insert(0, target_pass)
        jump_host, jump_user, jump_pass, jump_port = (None, None, None, None)
        if self.use_jump_host_var.get():
            jump_host = self.jump_host_entry.get(); jump_user = self.jump_user_entry.get(); jump_pass = self.jump_password_entry.get(); jump_port_str = self.jump_port_entry.get()
            if not jump_host or not jump_user: self.status_bar.configure(text="Error: Jump Host and Username are required."); return
            jump_port = int(jump_port_str) if jump_port_str.isdigit() else 22
            if not jump_port_str: self.jump_port_entry.insert(0, str(jump_port))
            if not jump_pass:
                dialog = PasswordDialog(title="Jump Host Password", prompt=f"Password for {jump_user}@{jump_host}:"); jump_pass = dialog.get_input()
                if jump_pass is None: self.status_bar.configure(text="Connection canceled."); return
                if not self.jump_password_entry.get(): self.jump_password_entry.insert(0, jump_pass)
        self.status_bar.configure(text="Connecting..."); self.connect_button.configure(text="Connecting...", state="disabled")
        args = (target_host, target_port, target_user, target_pass, jump_host, jump_port, jump_user, jump_pass, self.current_knock_config.copy())
        threading.Thread(target=self._perform_connect, args=args, daemon=True).start()
    def _perform_connect(self, target_host, target_port, target_user, target_pass, jump_host, jump_port, jump_user, jump_pass, knock_config):
        if knock_config.get('enabled'):
            knock_host = jump_host if jump_host else target_host
            self.status_bar.configure(text=f"Performing port knock on {knock_host}...")
            ports_str = knock_config.get('ports', "");
            if not ports_str: self.after(0, self.on_connection_failure, "Port knocking enabled but no ports specified."); return
            try:
                ports = [int(p.strip()) for p in ports_str.split(',')]; delay = float(knock_config.get('delay', 1.0))
            except (ValueError, TypeError): self.after(0, self.on_connection_failure, "Invalid port or delay format for port knocking."); return
            knock_success, knock_msg = perform_port_knock(knock_host, ports, delay)
            if not knock_success: self.after(0, self.on_connection_failure, knock_msg); return
            self.status_bar.configure(text="Knock complete. Connecting...")
        self.jump_client, self.ssh_client, err = connect_sftp(target_host, target_port, target_user, target_pass, jump_host, jump_port, jump_user, jump_pass)
        if self.ssh_client:
            try:
                self.sftp_client = open_sftp_robust(self.ssh_client); self.remote_path = self.sftp_client.normalize('.')
                self.after(0, self.on_connection_success, target_host)
            except Exception as e:
                print(f"Robust SFTP connection failed: {e}. Trying standard method...")
                try:
                    self.sftp_client = self.ssh_client.open_sftp(); self.remote_path = self.sftp_client.normalize('.')
                    self.after(0, self.on_connection_success, target_host)
                except Exception as sftp_e: self.after(0, self.on_connection_failure, sftp_e)
        else: self.after(0, self.on_connection_failure, err)
    def on_connection_success(self, target_host):
        self.status_bar.configure(text=f"Successfully connected to {target_host}."); self.connect_button.configure(text="Disconnect", state="normal")
        self.terminal_button.configure(state="normal"); self.populate_remote_files()
    def on_connection_failure(self, error_message):
        self.status_bar.configure(text=f"Connection Failed: {error_message}"); self.connect_button.configure(text="Connect", state="normal"); self._clear_remote_pane()
    def _perform_disconnect(self):
        if self.sftp_client: self.sftp_client.close()
        if self.ssh_client: self.ssh_client.close()
        if self.jump_client: self.jump_client.close()
        self.ssh_client = self.sftp_client = self.jump_client = None; self.after(0, self.on_disconnection_complete)
    def on_disconnection_complete(self):
        self.status_bar.configure(text="Disconnected."); self.connect_button.configure(text="Connect", state="normal")
        self.terminal_button.configure(state="disabled"); self._clear_remote_pane()
    def toggle_jump_host_frame(self):
        if self.use_jump_host_var.get(): self.jump_host_frame.grid()
        else: self.jump_host_frame.grid_remove()
    def on_remote_double_click(self, name, is_dir):
        if is_dir:
            new_path = os.path.dirname(self.remote_path.rstrip('/')) if name == ".." else f"{self.remote_path.rstrip('/')}/{name}"
            self.remote_path = new_path if new_path else "/"; self.populate_remote_files()
    def on_local_double_click(self, name, is_dir):
        if is_dir: self.local_path = os.path.normpath(os.path.join(self.local_path, name)); self.populate_local_files()
    def populate_local_files(self):
        self.handle_selection(None, "local"); [w.destroy() for w in self.local_file_list.winfo_children()]; self.local_path_label.configure(text=f"Local: {self.local_path}")
        parent_dir = os.path.dirname(self.local_path)
        if parent_dir != self.local_path: self.create_file_entry(self.local_file_list, "..", True, self.on_local_double_click, pane="local")
        try:
            items = os.listdir(self.local_path); dirs = sorted([d for d in items if os.path.isdir(os.path.join(self.local_path, d))]); files = sorted([f for f in items if not os.path.isdir(os.path.join(self.local_path, f))])
            for item in dirs + files: self.create_file_entry(self.local_file_list, item, os.path.isdir(os.path.join(self.local_path, item)), self.on_local_double_click, pane="local")
        except Exception as e: self.status_bar.configure(text=f"Error reading local directory: {e}")
    def populate_remote_files(self):
        if not self.sftp_client: return
        self.handle_selection(None, "remote"); [w.destroy() for w in self.remote_file_list.winfo_children()]; self.remote_path_label.configure(text=f"Remote: {self.remote_path}")
        if self.remote_path != "/": self.create_file_entry(self.remote_file_list, "..", True, self.on_remote_double_click, pane="remote")
        try:
            items = self.sftp_client.listdir_attr(self.remote_path); dirs = sorted([item for item in items if stat.S_ISDIR(item.st_mode)], key=lambda item: item.filename); files = sorted([item for item in items if not stat.S_ISDIR(item.st_mode)], key=lambda item: item.filename)
            for item in dirs + files: self.create_file_entry(self.remote_file_list, item.filename, stat.S_ISDIR(item.st_mode), self.on_remote_double_click, pane="remote")
        except Exception as e: self.status_bar.configure(text=f"Error reading remote directory: {e}")
    def _clear_remote_pane(self):
        self.handle_selection(None, "remote"); [w.destroy() for w in self.remote_file_list.winfo_children()]; self.remote_path_label.configure(text="Remote: Not Connected")
    def create_file_entry(self, parent_frame, name, is_dir, double_click_handler, pane):
        icon = self.folder_icon if is_dir else self.file_icon; entry = ctk.CTkLabel(parent_frame, text=f" {name}", image=icon, compound="left", anchor="w"); entry.pack(fill="x", pady=1)
        entry.bind("<Double-1>", lambda event, n=name, d=is_dir: double_click_handler(n, d)); entry.bind("<Button-1>", lambda event, w=entry, p=pane: self.handle_selection(w, p))
        if pane == 'remote': entry.bind("<Button-3>", lambda event, w=entry: self.show_remote_context_menu(event, w))
        elif pane == 'local': entry.bind("<Button-3>", lambda event, w=entry: self.show_local_context_menu(event, w))
    def handle_selection(self, widget, pane):
        self.hide_context_menus()
        if pane == "local":
            if self.selected_local_widget and self.selected_local_widget.winfo_exists(): self.selected_local_widget.configure(fg_color="transparent")
            if widget and widget.winfo_exists(): widget.configure(fg_color=self.highlight_color)
            self.selected_local_widget = widget
        elif pane == "remote":
            if self.selected_remote_widget and self.selected_remote_widget.winfo_exists(): self.selected_remote_widget.configure(fg_color="transparent")
            if widget and widget.winfo_exists(): widget.configure(fg_color=self.highlight_color)
            self.selected_remote_widget = widget
    def open_settings_dialog(self):
        dialog = SettingsDialog(self, current_bg=self.terminal_bg_color, current_fg=self.terminal_fg_color)
        new_settings = dialog.get_settings()
        if new_settings: self.terminal_bg_color, self.terminal_fg_color = new_settings; self.status_bar.configure(text="Terminal color settings saved."); self.save_app_settings()
    def load_app_settings(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            config.read(self.config_file)
            if 'Settings' in config: self.terminal_bg_color = config['Settings'].get('terminal_bg', '#000000'); self.terminal_fg_color = config['Settings'].get('terminal_fg', '#FFFFFF')
    def save_app_settings(self):
        config = configparser.ConfigParser();
        if os.path.exists(self.config_file): config.read(self.config_file)
        if 'Settings' not in config: config['Settings'] = {}
        config['Settings']['terminal_bg'] = self.terminal_bg_color; config['Settings']['terminal_fg'] = self.terminal_fg_color
        with open(self.config_file, 'w') as configfile: config.write(configfile)
    def manage_profiles_dialog(self):
        if not os.path.exists(self.config_file):
            with open(self.config_file, 'w') as f: pass
        config = configparser.ConfigParser(); config.read(self.config_file)
        dialog = ManageProfilesDialog(self, config); selection = dialog.get_selection()
        if selection: self.load_profile(selection)
    def load_profile(self, profile_name):
        self.clear_knock_config(); config = configparser.ConfigParser(); config.read(self.config_file)
        if not config.has_section(profile_name): return
        p = config[profile_name]
        for entry in [self.host_entry, self.username_entry, self.password_entry, self.port_entry, self.jump_host_entry, self.jump_user_entry, self.jump_password_entry, self.jump_port_entry]: entry.delete(0, 'end')
        self.host_entry.insert(0, p.get('host', '')); self.username_entry.insert(0, p.get('user', '')); self.port_entry.insert(0, p.get('port', ''))
        use_jump = p.getboolean('use_jump', False); self.use_jump_host_var.set(use_jump)
        if use_jump:
            self.jump_host_entry.insert(0, p.get('jump_host', '')); self.jump_user_entry.insert(0, p.get('jump_user', '')); self.jump_port_entry.insert(0, p.get('jump_port', ''))
        self.toggle_jump_host_frame()
        self.current_knock_config['enabled'] = p.getboolean('knock_enabled', False)
        if self.current_knock_config['enabled']:
            self.current_knock_config['ports'] = p.get('knock_ports', ''); self.current_knock_config['delay'] = p.get('knock_delay', '1')
            self.status_bar.configure(text=f"Profile '{profile_name}' loaded (Port Knocking Enabled).")
        else: self.status_bar.configure(text=f"Profile '{profile_name}' loaded.")
    def save_profile(self):
        dialog = CTkInputDialog(title="Save Profile", text="Enter a name for the current connection details:"); profile_name = dialog.get_input()
        if not profile_name: return
        config = configparser.ConfigParser();
        if os.path.exists(self.config_file): config.read(self.config_file)
        if config.has_section(profile_name):
            confirm = ConfirmDialog(title="Overwrite Profile", message=f"A profile named '{profile_name}' already exists. Overwrite it with current connection details?")
            if not confirm.get_result(): return
        else: config.add_section(profile_name)
        config.set(profile_name, 'host', self.host_entry.get()); config.set(profile_name, 'user', self.username_entry.get())
        config.set(profile_name, 'port', self.port_entry.get()); config.set(profile_name, 'use_jump', str(self.use_jump_host_var.get()))
        if self.use_jump_host_var.get():
            config.set(profile_name, 'jump_host', self.jump_host_entry.get()); config.set(profile_name, 'jump_user', self.jump_user_entry.get()); config.set(profile_name, 'jump_port', self.jump_port_entry.get())
        with open(self.config_file, 'w') as configfile: config.write(configfile)
        self.status_bar.configure(text=f"Profile '{profile_name}' saved (passwords not stored).")
    def show_remote_context_menu(self, event, widget=None):
        self.handle_selection(widget, "remote"); is_item_selected = widget and widget.cget("text").strip() != ".."
        self.context_menu_item = widget.cget("text").strip() if is_item_selected else None
        for item in ["Download", "Move/Rename", "Delete"]: self.remote_context_menu.entryconfigure(item, state="normal" if is_item_selected else "disabled")
        self.remote_context_menu.post(event.x_root, event.y_root)
    def show_local_context_menu(self, event, widget=None):
        self.handle_selection(widget, "local"); is_item_selected = widget and widget.cget("text").strip() != ".."
        self.context_menu_item = widget.cget("text").strip() if is_item_selected else None
        for item in ["Upload", "Move/Rename", "Delete"]: self.local_context_menu.entryconfigure(item, state="normal" if is_item_selected else "disabled")
        self.local_context_menu.post(event.x_root, event.y_root)
    def hide_context_menus(self):
        try: self.remote_context_menu.unpost(); self.local_context_menu.unpost()
        except tkinter.TclError: pass
    def context_remote_create_folder(self):
        if not self.sftp_client: self.status_bar.configure(text="Not connected."); return
        dialog = CTkInputDialog(title="Create Remote Folder", text="Enter new folder name:"); name = dialog.get_input()
        if name: path = f"{self.remote_path.rstrip('/')}/{name}"; success, msg = create_remote_directory(self.sftp_client, path); self.status_bar.configure(text=msg);
        if success: self.populate_remote_files()
    def context_local_create_folder(self):
        dialog = CTkInputDialog(title="Create Local Folder", text="Enter new folder name:"); name = dialog.get_input()
        if name:
            path = os.path.join(self.local_path, name)
            try: os.mkdir(path); self.status_bar.configure(text=f"Created folder '{name}'"); self.populate_local_files()
            except Exception as e: self.status_bar.configure(text=f"Error: {e}")
    def context_download(self):
        if not self.context_menu_item: return
        self.status_bar.configure(text=f"Downloading {self.context_menu_item}..."); remote_item_path = f"{self.remote_path.rstrip('/')}/{self.context_menu_item}"; local_item_path = os.path.join(self.local_path, self.context_menu_item)
        threading.Thread(target=self._threaded_download, args=(remote_item_path, local_item_path), daemon=True).start()
    def _threaded_download(self, remote_path, local_path):
        success, msg = download_remote_item(self.sftp_client, remote_path, local_path); self.status_bar.configure(text=msg)
        if success: self.after(0, self.populate_local_files)
    def context_upload(self):
        if not self.context_menu_item or not self.sftp_client: self.status_bar.configure(text="Not connected."); return
        local_path = os.path.join(self.local_path, self.context_menu_item); remote_path = f"{self.remote_path.rstrip('/')}/{self.context_menu_item}"; self.status_bar.configure(text=f"Uploading {self.context_menu_item}...")
        threading.Thread(target=self._threaded_upload, args=(local_path, remote_path), daemon=True).start()
    def _threaded_upload(self, local_path, remote_path):
        success, msg = upload_file(self.sftp_client, local_path, remote_path); self.status_bar.configure(text=msg)
        if success: self.after(0, self.populate_remote_files)
    def context_remote_move(self):
        if not self.context_menu_item: return
        old_path = f"{self.remote_path.rstrip('/')}/{self.context_menu_item}"; dialog = CTkInputDialog(title="Move/Rename Remote", text=f"New path/name for '{self.context_menu_item}':"); new_path_str = dialog.get_input()
        if new_path_str: new_path = new_path_str if new_path_str.startswith('/') else f"{self.remote_path.rstrip('/')}/{new_path_str}"; success, msg = rename_remote_item(self.sftp_client, old_path, new_path); self.status_bar.configure(text=msg);
        if success: self.populate_remote_files()
    def context_local_move(self):
        if not self.context_menu_item: return
        old_path = os.path.join(self.local_path, self.context_menu_item); dialog = CTkInputDialog(title="Move/Rename Local", text=f"New name for '{self.context_menu_item}':"); new_name = dialog.get_input()
        if new_name:
            try: shutil.move(old_path, os.path.join(self.local_path, new_name)); self.status_bar.configure(text=f"Moved to '{new_name}'"); self.populate_local_files()
            except Exception as e: self.status_bar.configure(text=f"Error moving: {e}")
    def context_remote_delete(self):
        if not self.context_menu_item: return
        dialog = ConfirmDialog(title="Confirm Deletion", message=f"Delete '{self.context_menu_item}' on the remote server?")
        if dialog.get_result(): path = f"{self.remote_path.rstrip('/')}/{self.context_menu_item}"; success, msg = delete_remote_item(self.sftp_client, path); self.status_bar.configure(text=msg);
        if success: self.populate_remote_files()
        else: self.status_bar.configure(text="Deletion canceled.")
    def context_local_delete(self):
        if not self.context_menu_item: return
        dialog = ConfirmDialog(title="Confirm Deletion", message=f"Delete '{self.context_menu_item}' from the local machine?")
        if dialog.get_result():
            path = os.path.join(self.local_path, self.context_menu_item)
            try:
                if os.path.isdir(path): shutil.rmtree(path)
                else: os.remove(path)
                self.status_bar.configure(text=f"Deleted '{self.context_menu_item}'"); self.populate_local_files()
            except Exception as e: self.status_bar.configure(text=f"Error deleting: {e}")
        else: self.status_bar.configure(text="Deletion canceled.")
    def open_terminal_choice(self):
        target_name = self.host_entry.get(); jump_name = self.jump_host_entry.get() if self.use_jump_host_var.get() else None
        dialog = TerminalChoiceDialog(target_name=target_name, jump_name=jump_name); choice = dialog.get_choice()
        if choice == "target" and self.ssh_client: channel = self.ssh_client.invoke_shell(term='xterm'); TerminalWindow(self, channel, target_name, self.terminal_bg_color, self.terminal_fg_color)
        elif choice == "jump" and self.jump_client: channel = self.jump_client.invoke_shell(term='xterm'); TerminalWindow(self, channel, jump_name, self.terminal_bg_color, self.terminal_fg_color)
    
    # --- MOUSE WHEEL SCROLLING LOGIC ---
    def _setup_scroll_bindings(self):
        # Bind the Enter/Leave events to the main frames
        self.local_file_list.bind("<Enter>", lambda e: self._bind_mouse_wheel(self.local_file_list))
        self.local_file_list.bind("<Leave>", lambda e: self._unbind_mouse_wheel())
        
        self.remote_file_list.bind("<Enter>", lambda e: self._bind_mouse_wheel(self.remote_file_list))
        self.remote_file_list.bind("<Leave>", lambda e: self._unbind_mouse_wheel())

    def _bind_mouse_wheel(self, widget):
        self.current_scroll_widget = widget
        # Bind globally while hovering so it works without clicking
        self.bind_all("<MouseWheel>", self._on_mouse_wheel)  # Windows
        self.bind_all("<Button-4>", self._on_mouse_wheel)    # Linux Up
        self.bind_all("<Button-5>", self._on_mouse_wheel)    # Linux Down

    def _unbind_mouse_wheel(self):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")
        self.current_scroll_widget = None

    def _on_mouse_wheel(self, event):
        if not hasattr(self, 'current_scroll_widget') or not self.current_scroll_widget:
            return
        
        # Access the internal canvas of the CTkScrollableFrame
        canvas = self.current_scroll_widget._parent_canvas
        
        if os.name == 'nt': # Windows
            # Standard Windows scrolling: event.delta is usually +/- 120
            # Dividing by 120 gives 1 unit. Multiplied by -1 because Tkinter coordinates are inverted relative to wheel
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else: # Linux/Posix
            if event.num == 4: # Linux scroll up
                canvas.yview_scroll(-1, "units")
            elif event.num == 5: # Linux scroll down
                canvas.yview_scroll(1, "units")
    # -----------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PySFTP - A Secure File Transfer Client.")
    parser.add_argument("-H", "--host", help="Target server hostname"); parser.add_argument("-u", "--username", help="Target server username"); parser.add_argument("-p", "--password", help="Target server password"); parser.add_argument("--port", type=int, help="Target server port")
    parser.add_argument("--jump-host", help="Jump host hostname"); parser.add_argument("--jump-user", help="Jump host username"); parser.add_argument("--jump-password", help="Jump host password"); parser.add_argument("--jump-port", type=int, help="Jump host port (default 22)")
    args = parser.parse_args()
    ctk.set_appearance_mode("System"); ctk.set_default_color_theme("blue")
    app = App(cli_args=args)
    app.mainloop()
