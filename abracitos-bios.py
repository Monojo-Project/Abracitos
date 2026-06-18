#!/usr/bin/env python3

# Instalador Abracitos para LyndsOS.
# Versión OPTIMIZADA PARA BIOS / LEGACY MBR.
# Desarrollado por David Baña Szymaniak.

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import re
import time
import socket
import shutil
import sys
import pwd  # Gestor de información del usuario
from PIL import Image, ImageTk, ImageOps

# --- CONFIGURACIÓN GLOBAL DE INTERFAZ ---
resolucion_ventana = "1600x1100"
DARK_MODE = False  # Cambiar a True para activar el tema oscuro automáticamente
log_path = "/etc/abracitos/abracitos.log"

if DARK_MODE:
    COLOR_BG = "#1e1e2e"
    COLOR_SIDEBAR = "#11111b"
    COLOR_TEXT = "#cdd6f4"
    COLOR_TEXT_MUTED = "#a6adc8"
    COLOR_ACCENT = "#a6e3a1"
    COLOR_CONTAINER = "#1e1e2e"
    COLOR_CARD = "#313244"
else:
    COLOR_BG = "#ffffff"
    COLOR_SIDEBAR = "#2c3e50"
    COLOR_TEXT = "#2c3e50"
    COLOR_TEXT_MUTED = "#7f8c8d"
    COLOR_ACCENT = "#2ecc71"
    COLOR_CONTAINER = "#ffffff"
    COLOR_CARD = "#f8f9fa"


def check_root():
    print("[DEBUG] Verificando privilegios de root...")
    return os.geteuid() == 0
    
def check_internet():
    try:
        socket.create_connection(("deb.debian.org", 80), timeout=2)
        return True
    except OSError:
        return False
        
class Logger(object):
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def launch_chroot_terminal(target_path):
    print(f"[DEBUG] Solicitud para lanzar terminal chroot en: {target_path}")
    if not os.path.ismount(target_path):
        print("[DEBUG] Error: La partición raíz no está montada.")
        messagebox.showerror("Error", "La partición raíz no está montada.")
        return
    
    cmd = ["konsole", "-e", "sudo", "chroot", target_path, "/bin/bash"]
    try:
        subprocess.Popen(cmd)
        print("[DEBUG] Terminal chroot lanzada con éxito.")
    except Exception as e:
        print(f"[DEBUG] Fallo al abrir Konsole: {e}")
        messagebox.showerror("Error", f"No se pudo abrir Konsole: {e}")


class AbracitosInstaller:
    def __init__(self, root):
        print("[DEBUG] Inicializando AbracitosInstaller (Optimizado para BIOS)...")
        self.root = root
        
        self.root.title("LyndsOS 1.0 Light - Instalador Abracitos (BIOS Edition)")
        self.root.geometry(resolucion_ventana)
        self.root.configure(bg=COLOR_BG)

        try:
            img_icon = tk.PhotoImage(file='/usr/share/icons/LyndsOS/lynds-64x64.png')
            self.root.iconphoto(False, img_icon)
        except Exception as e:
            print(f"[DEBUG] Aviso: No se pudo cargar el icono ({e})")

        self.target_mnt = "/mnt/lyndsos"
        self.config_dir = "/etc/abracitos"
        self.ads_dir = os.path.join(self.config_dir, "anuncios")
        self.includes_dir = os.path.join(self.config_dir, "includes.chroot")
        self.packages_file = os.path.join(self.config_dir, "packages.conf")
        self.is_installing = False
        
        # FORZADO ESTRICTO DE BIOS / LEGACY
        self.is_efi = False
        print("[DEBUG] Arquitectura del Host Forzada: BIOS / Legacy MBR")
        
        self.real_name = tk.StringVar(value="Usuario Lynds")
        self.username = tk.StringVar(value="user")
        self.hostname = tk.StringVar(value="lyndsos")
        self.autologin_var = tk.BooleanVar(value=False)
        self.session_type = tk.StringVar(value="Wayland")
        self.skip_grub_var = tk.BooleanVar(value=False)
        self.is_expert_mode = False
    
        self.u_pass_var = tk.StringVar()
        self.r_pass_var = tk.StringVar()
        self.u_pass_val = ""
        self.r_pass_val = ""
        
        self.detected_root_fs = ""
        self.detected_efi_fs = ""
        
        self.lang_map = {
            "Español (España)": "es_ES.UTF-8",
            "Español (México)": "es_MX.UTF-8",
            "Español (Argentina)": "es_AR.UTF-8",
            "Inglés (USA)": "en_US.UTF-8",
            "Francés": "fr_FR.UTF-8"
        }
        self.selected_lang_label = tk.StringVar(value="Español (España)")

        self.kb_map = {
            "Español (Windows)": {"layout": "es", "variant": "winkeys"},
            "Español (Latino)": {"layout": "latam", "variant": ""},
            "Inglés (US)": {"layout": "us", "variant": ""},
            "Inglés (UK)": {"layout": "gb", "variant": ""}
        }
        self.kb_layout_name = tk.StringVar(value="Español (Windows)")

        self.tz_map = {
            "Madrid (Península)": "Europe/Madrid",
            "Canarias": "Atlantic/Canary",
            "México (CDMX)": "America/Mexico_City",
            "Argentina (B.A.)": "America/Argentina/Buenos_Aires",
            "UTC": "UTC"
        }
        self.selected_tz_label = tk.StringVar(value="Madrid (Península)")

        self.root_part_full = tk.StringVar()
        self.efi_part_full = tk.StringVar()
        self.selected_drive = tk.StringVar()

        self.vcmd_user = (self.root.register(self.validate_user_input), '%S')
        self.vcmd_host = (self.root.register(self.validate_hostname_input), '%S')
         
        self.setup_styles()
        self.create_layout()

    def validate_user_input(self, char):
        return re.match(r'[a-z0-9]', char) is not None

    def validate_hostname_input(self, char):
        return re.match(r'[a-z0-9-]', char) is not None

    def get_uuid(self, partition):
        try:
            output = subprocess.check_output(["blkid", "-s", "UUID", "-o", "value", partition], text=True)
            return output.strip()
        except Exception as e: 
            print(f"[DEBUG] Error al obtener UUID para {partition}: {e}")
            return ""

    def open_partition_manager(self):
        if not shutil.which("partitionmanager"):
            messagebox.showwarning("Aviso", "KDE Partition Manager no está instalado.")
            return

        sudo_user = os.environ.get("SUDO_USER")
        try:
            if sudo_user:
                user_info = pwd.getpwnam(sudo_user)
                user_uid = user_info.pw_uid
                user_home = user_info.pw_dir
                
                custom_env = os.environ.copy()
                custom_env["HOME"] = user_home
                custom_env["USER"] = sudo_user
                custom_env["LOGNAME"] = sudo_user
                custom_env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{user_uid}/bus"
                custom_env["XDG_RUNTIME_DIR"] = f"/run/user/{user_uid}"

                subprocess.Popen(["sudo", "-E", "-u", sudo_user, "partitionmanager"], env=custom_env)
            else:
                subprocess.Popen(["partitionmanager"])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar el gestor de particiones: {e}")

    def get_device_list(self, only_parts=True, allowed_fs=None):
        devices = []
        try:
            output = subprocess.check_output(["lsblk", "-Pno", "NAME,SIZE,TYPE,LABEL,FSTYPE"], text=True)
            for line in output.strip().split('\n'):
                if not line: continue
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', line))
                
                name = attrs.get("NAME", "")
                size = attrs.get("SIZE", "")
                dev_type = attrs.get("TYPE", "")
                label = attrs.get("LABEL", "") or "Sin Etiqueta"
                fstype = attrs.get("FSTYPE", "") or "Sin Formato"
                
                path = f"/dev/{name}"
                if only_parts and dev_type == "part":
                    if allowed_fs and fstype.lower() not in [fs.lower() for fs in allowed_fs]:
                        continue
                    devices.append(f"{path} - {size} ({label}) [{fstype}]")
                elif not only_parts and dev_type == "disk":
                    devices.append(f"{path} - {size}")
        except Exception as e: 
            print(f"[DEBUG] Error en lsblk: {e}")
        return devices

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Sidebar.TFrame", background=COLOR_SIDEBAR)
        self.style.configure("Step.TLabel", background=COLOR_SIDEBAR, foreground="#bdc3c7", font=("Segoe UI", 11))
        self.style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        self.style.configure("Refresh.TButton", font=("Segoe UI", 9))

    def create_layout(self):
        self.sidebar = ttk.Frame(self.root, style="Sidebar.TFrame", width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="LyndsOS BIOS", font=("Segoe UI", 20, "bold"), bg=COLOR_SIDEBAR, fg=COLOR_ACCENT, pady=25).pack()
        
        self.steps_labels = []
        pasos = ["Bienvenida", "Identidad", "Localización", "Particionado", "Resumen", "Instalación"]
        for p in pasos:
            l = ttk.Label(self.sidebar, text=f"  {p}", style="Step.TLabel")
            l.pack(fill="x", pady=10)
            self.steps_labels.append(l)

        self.container = tk.Frame(self.root, bg=COLOR_CONTAINER)
        self.container.pack(side="right", expand=True, fill="both", padx=40, pady=20)
        self.show_welcome()

    def set_step_active(self, index):
        for i, l in enumerate(self.steps_labels):
            color = COLOR_ACCENT if i == index else "#bdc3c7"
            l.configure(foreground=color)

    def clear_container(self):
        for w in self.container.winfo_children(): w.destroy()

    def show_welcome(self):
        self.set_step_active(0)
        self.clear_container()
        tk.Label(self.container, text="Instalador Abracitos (Optimizado para BIOS)", font=("Segoe UI", 24, "bold"), bg=COLOR_CONTAINER, fg=COLOR_TEXT).pack(pady=(60, 20))
        
        self.net_status_lbl = tk.Label(self.container, font=("Segoe UI", 11, "bold"), bg=COLOR_CONTAINER)
        self.net_status_lbl.pack()

        frame = tk.Frame(self.container, bg=COLOR_CONTAINER)
        frame.pack(pady=50)
        
        self.btn_novato = ttk.Button(frame, text="Modo Novato (Auto MBR)", command=lambda: self.set_mode(False))
        self.btn_novato.pack(side="left", padx=15)
        
        self.btn_experto = ttk.Button(frame, text="Modo Experto (Manual BIOS)", command=lambda: self.set_mode(True))
        self.btn_experto.pack(side="left", padx=15)

        self.update_network_status()

    def update_network_status(self):
        if self.steps_labels[0].cget("foreground") != COLOR_ACCENT:
            return
        if self.check_internet():
            self.net_status_lbl.config(text="✅ Conexión a Internet establecida.", fg=COLOR_ACCENT)
            self.btn_novato.config(state="normal")
            self.btn_experto.config(state="normal")
        else:
            self.net_status_lbl.config(text="⚠️ ERROR: Conéctate a Internet para continuar.", fg="#e74c3c")
            self.btn_novato.config(state="disabled")
            self.btn_experto.config(state="disabled")
            self.root.after(3000, self.update_network_status)

    def set_mode(self, expert):
        self.is_expert_mode = expert
        self.show_identity()

    def show_identity(self):
        self.set_step_active(1)
        self.clear_container()
        tk.Label(self.container, text="Configuración de Usuario", font=("Segoe UI", 20, "bold"), bg=COLOR_CONTAINER, fg=COLOR_TEXT).pack(pady=20)
        f = tk.Frame(self.container, bg=COLOR_CONTAINER)
        f.pack()

        tk.Label(f, text="Nombre Real:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=0, column=0, sticky="e", pady=8)
        ttk.Entry(f, textvariable=self.real_name, width=35).grid(row=0, column=1, padx=10)

        tk.Label(f, text="Usuario Linux:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=1, column=0, sticky="e", pady=8)
        ttk.Entry(f, textvariable=self.username, width=35, validate="key", validatecommand=self.vcmd_user).grid(row=1, column=1, padx=10)

        tk.Label(f, text="Contraseña Usuario:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=2, column=0, sticky="e", pady=8)
        self.u_pass = ttk.Entry(f, show="*", textvariable=self.u_pass_var, width=35)
        self.u_pass.grid(row=2, column=1, padx=10)

        tk.Label(f, text="Contraseña ROOT:", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="e", pady=8)
        self.r_pass = ttk.Entry(f, show="*", textvariable=self.r_pass_var, width=35)
        self.r_pass.grid(row=3, column=1, padx=10)

        tk.Label(f, text="Hostname:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=4, column=0, sticky="e", pady=8)
        ttk.Entry(f, textvariable=self.hostname, width=35, validate="key", validatecommand=self.vcmd_host).grid(row=4, column=1, padx=10)

        self.session_frame = tk.Frame(f, bg=COLOR_CONTAINER)
        tk.Label(self.session_frame, text="Servidor Gráfico:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=0, column=0, sticky="e", pady=8)
        self.cmb_session = ttk.Combobox(self.session_frame, textvariable=self.session_type, values=["Wayland", "X11"], state="readonly", width=32)
        self.cmb_session.grid(row=0, column=1, padx=10)

        def toggle_session_visibility():
            if self.autologin_var.get():
                self.session_frame.grid(row=6, columnspan=2, pady=5)
            else:
                self.session_frame.grid_forget()

        ttk.Checkbutton(f, text="Activar inicio de sesión automático (Auto-login)", variable=self.autologin_var, command=toggle_session_visibility).grid(row=5, columnspan=2, pady=10)
        toggle_session_visibility()

        btn_frame = tk.Frame(self.container, bg=COLOR_CONTAINER)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Atrás", command=self.show_welcome).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Siguiente", command=self.validate_identity).pack(side="left", padx=10)

    def validate_identity(self):
        self.u_pass_val = self.u_pass_var.get()
        self.r_pass_val = self.r_pass_var.get()
        if not all([self.username.get(), self.u_pass_val, self.r_pass_val, self.hostname.get()]):
            messagebox.showerror("Error", "Campos incompletos.")
            return
        self.show_localization()

    def show_localization(self):
        self.set_step_active(2)
        self.clear_container()
        tk.Label(self.container, text="Idioma y Región", font=("Segoe UI", 20, "bold"), bg=COLOR_CONTAINER, fg=COLOR_TEXT).pack(pady=20)
        f = tk.Frame(self.container, bg=COLOR_CONTAINER)
        f.pack()
        
        tk.Label(f, text="Idioma del Sistema:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=0, column=0, sticky="e", pady=10, padx=10)
        ttk.Combobox(f, textvariable=self.selected_lang_label, values=list(self.lang_map.keys()), state="readonly", width=30).grid(row=0, column=1, pady=10, sticky="w")
        
        tk.Label(f, text="Zona Horaria:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=1, column=0, sticky="e", pady=10, padx=10)
        ttk.Combobox(f, textvariable=self.selected_tz_label, values=list(self.tz_map.keys()), state="readonly", width=30).grid(row=1, column=1, pady=10, sticky="w")
        
        tk.Label(f, text="Distribución de Teclado:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=2, column=0, sticky="e", pady=10, padx=10)
        ttk.Combobox(f, textvariable=self.kb_layout_name, values=list(self.kb_map.keys()), state="readonly", width=30).grid(row=2, column=1, pady=10, sticky="w")

        btn_frame = tk.Frame(self.container, bg=COLOR_CONTAINER)
        btn_frame.pack(pady=30)
        ttk.Button(btn_frame, text="Atrás", command=self.show_identity).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Siguiente", command=self.show_partitions).pack(side="left", padx=10)

    def show_partitions(self):
        self.set_step_active(3)
        self.clear_container()
        tk.Label(self.container, text="Gestión de Discos (Modo BIOS)", font=("Segoe UI", 20, "bold"), bg=COLOR_CONTAINER, fg=COLOR_TEXT).pack(pady=10)
        f = tk.Frame(self.container, bg=COLOR_CONTAINER)
        f.pack(pady=10)

        if self.is_expert_mode:
            ttk.Button(self.container, text="🛠 Abrir KDE Partition Manager", command=self.open_partition_manager).pack(pady=5)
            root_devs = self.get_device_list(only_parts=True, allowed_fs=['ext4', 'btrfs'])
            
            tk.Label(f, text="Partición Raíz ( / ) [ext4/btrfs]:", bg=COLOR_CONTAINER, fg=COLOR_TEXT).grid(row=0, column=0, pady=5)
            self.cmb_root = ttk.Combobox(f, values=root_devs, width=55, state="readonly")
            self.cmb_root.grid(row=0, column=1, padx=10)
        
            if self.root_part_full.get() in root_devs:
                self.cmb_root.set(self.root_part_full.get())
            elif root_devs:
                self.cmb_root.current(0)
  
            tk.Label(f, text="Arranque BIOS Forzado: GRUB se instalará en el MBR del disco físico contenedor.", 
                     fg=COLOR_TEXT_MUTED, bg=COLOR_CONTAINER, font=("Segoe UI", 9, "italic")).grid(row=1, columnspan=2, pady=10)

            ttk.Checkbutton(f, text="Omitir instalación de GRUB en el MBR.", variable=self.skip_grub_var).grid(row=2, columnspan=2, pady=10)
        else:
            tk.Label(self.container, text="⚠️ SE BORRARÁ EL DISCO ENTERO (Creando Tabla MBR limpia)", fg="red", bg=COLOR_CONTAINER, font=("Segoe UI", 10, "bold")).pack()
            drives = self.get_device_list(only_parts=False)
            self.cmb_drive = ttk.Combobox(self.container, values=drives, width=50, state="readonly")
            self.cmb_drive.pack(pady=20)
  
            if self.selected_drive.get() in drives:
                self.cmb_drive.set(self.selected_drive.get())
            elif drives:
                self.cmb_drive.current(0)

        ttk.Button(self.container, text="🔄 Refrescar", style="Refresh.TButton", command=self.show_partitions).pack(pady=5)
        
        btn_frame = tk.Frame(self.container, bg=COLOR_CONTAINER)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Atrás", command=self.show_localization).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Siguiente", command=self.validate_partitions).pack(side="left", padx=10)

    def validate_partitions(self):
        if self.is_expert_mode:
            if not self.cmb_root.get():
                messagebox.showerror("Error", "Falta seleccionar la partición raíz.")
                return
            
            root_match = re.match(r"^(/dev/\S+)\s+-\s+.*\[(.*)\]$", self.cmb_root.get())
            if not root_match:
                messagebox.showerror("Error", "Error al procesar el formato.")
                return
            
            rp_fs = root_match.group(2).lower().strip()
            if rp_fs not in ['ext4', 'btrfs']:
                messagebox.showerror("Error", "La partición raíz debe ser ext4 o btrfs.")
                return

            self.root_part_full.set(self.cmb_root.get())
            self.detected_root_fs = rp_fs
            self.efi_part_full.set("")
            self.detected_efi_fs = ""
        else:
            if not self.cmb_drive.get():
                messagebox.showerror("Error", "Selecciona un disco.")
                return
            self.selected_drive.set(self.cmb_drive.get())
            
        self.show_summary()

    def show_summary(self):
        self.set_step_active(4)
        self.clear_container()
        tk.Label(self.container, text="Resumen de Instalación BIOS", font=("Segoe UI", 20, "bold"), bg=COLOR_CONTAINER, fg=COLOR_TEXT).pack(pady=10)
        
        sum_text = f"• Modo: {'EXPERTO' if self.is_expert_mode else 'NOVATO'}\n"
        sum_text += f"• Usuario: {self.username.get()}\n"
        sum_text += f"• Auto-login: {'SÍ' if self.autologin_var.get() else 'NO'}\n"
        sum_text += f"• Hostname: {self.hostname.get()}\n"
        sum_text += f"• Idioma: {self.selected_lang_label.get()}\n"
        sum_text += f"• Tipo de Arranque: BIOS / Legacy MBR (Optimizado)\n"
        
        if self.is_expert_mode:
            sum_text += f"• Raíz destino: {self.root_part_full.get()}\n"
            sum_text += f"• Omitir GRUB MBR: {'SÍ' if self.skip_grub_var.get() else 'NO'}"
        else:
            sum_text += f"• Disco completo seleccionado: {self.selected_drive.get()}\n"
            sum_text += " (Acción: Estructura MBR clásica + Partición Única 100% EXT4 Activa)\n"
        sum_text += f"• Cargador de Arranque: GRUB de Arquitectura i386-pc"

        tk.Label(self.container, text=sum_text, justify="left", bg=COLOR_CARD, fg=COLOR_TEXT, padx=25, pady=25, font=("Consolas", 10), relief="solid", borderwidth=1).pack(pady=20)

        btn_frame = tk.Frame(self.container, bg=COLOR_CONTAINER)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Atrás", command=self.show_partitions).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="CONFIRMAR E INSTALAR", style="Action.TButton", command=self.start_install).pack(side="left", padx=10)

    def start_install(self):
        self.set_step_active(5)
        self.clear_container()
        self.status_lbl = tk.Label(self.container, text="Iniciando...", font=("Segoe UI", 12), bg=COLOR_CONTAINER, fg=COLOR_TEXT)
        self.status_lbl.pack(pady=10)
        self.pbar = ttk.Progressbar(self.container, length=500, mode='determinate')
        self.pbar.pack(pady=10)
        
        self.canvas_ad = tk.Canvas(self.container, width=1300, height=1000, bg=COLOR_CARD, highlightthickness=0)
        self.canvas_ad.pack(pady=20)
        
        self.is_installing = True
        threading.Thread(target=self.install_engine, daemon=True).start()

    def force_umount_target(self):
        subprocess.run(["umount", "-R", self.target_mnt], stderr=subprocess.DEVNULL)

    def install_engine(self):
        try:
            ep, rp = "", ""
            target_disk = ""

            # ---------------------------------------------------------
            # FASE 1: Particionado MBR (Modo Novato)
            # ---------------------------------------------------------
            if not self.is_expert_mode:
                drive = self.selected_drive.get().split(" - ")[0].strip()
                target_disk = drive
                self.root.after(0, lambda: self.status_lbl.config(text="Escribiendo tabla de particiones MBR (msdos)..."))
                self.pbar.after(0, lambda: self.pbar.config(value=10))

                # Forzar desmontaje preventivo
                subprocess.run(["umount", "-R", f"{drive}1"], stderr=subprocess.DEVNULL)
                if "nvme" in drive or "mmcblk" in drive:
                    subprocess.run(["umount", "-R", f"{drive}p1"], stderr=subprocess.DEVNULL)

                subprocess.run(["wipefs", "-a", drive], check=True)
                
                # OPTIMIZACIÓN BIOS: Tabla MBR + Partición Primaria Única Activa al 100%
                subprocess.run(["parted", "-s", drive, "mklabel", "msdos"], check=True)
                subprocess.run(["parted", "-s", drive, "mkpart", "primary", "ext4", "1MiB", "100%"], check=True)
                subprocess.run(["parted", "-s", drive, "set", "1", "boot", "on"], check=True)
                
                subprocess.run(["partprobe", drive], check=True)
                time.sleep(2)

                if "nvme" in drive or "mmcblk" in drive:
                    rp = f"{drive}p1"
                else:
                    rp = f"{drive}1"
            else:
                rp = self.root_part_full.get().split(" - ")[0].strip()
                target_disk = re.sub(r'(?:p?\d+|\d+)$', '', rp)

            # ---------------------------------------------------------
            # FASE 2: Formateo y montaje inicial
            # ---------------------------------------------------------
            self.root.after(0, lambda: self.status_lbl.config(text="Formateando la partición raíz en ext4..."))
            self.pbar.after(0, lambda: self.pbar.config(value=25))
            self.force_umount_target()
            
            if not self.is_expert_mode:
                subprocess.run(["mkfs.ext4", "-F", "-L", "LyndsOS", rp], check=True)

            os.makedirs(self.target_mnt, exist_ok=True)
            subprocess.run(["mount", rp, self.target_mnt], check=True)

            # ---------------------------------------------------------
            # FASE 3: Debootstrap
            # ---------------------------------------------------------
            self.root.after(0, lambda: self.status_lbl.config(text="Desplegando el sistema base (debootstrap)..."))
            self.pbar.after(0, lambda: self.pbar.config(value=40))
            
            cmd_debootstrap = ["debootstrap", "--arch=amd64", "trixie", self.target_mnt, "http://deb.debian.org/debian/"]
            subprocess.run(cmd_debootstrap, check=True)

            # ---------------------------------------------------------
            # FASE 4: Montajes virtuales
            # ---------------------------------------------------------
            self.root.after(0, lambda: self.status_lbl.config(text="Montando entornos virtuales de kernel..."))
            self.pbar.after(0, lambda: self.pbar.config(value=55))
            for sys_dir in ["/sys", "/proc", "/dev", "/dev/pts"]:
                subprocess.run(["mount", "--bind", sys_dir, f"{self.target_mnt}{sys_dir}"], check=True)

            # ---------------------------------------------------------
            # FASE 5: Configuración Base Interna (Chroot)
            # ---------------------------------------------------------
            self.root.after(0, lambda: self.status_lbl.config(text="Configurando Sistema Base y Entorno de Arranque..."))
            self.pbar.after(0, lambda: self.pbar.config(value=75))
            
            locale_val = self.lang_map[self.selected_lang_label.get()]
            timezone = self.tz_map[self.selected_tz_label.get()]
            
            grub_packages = "grub-pc"  # Forzado estricto BIOS
            grub_install_block = ""
            if not self.skip_grub_var.get():
                grub_install_block = f"""
                echo "[GRUB] Instalando cargador en el MBR de {target_disk}..."
                grub-install --target=i386-pc --recheck {target_disk}
                """

            autologin_script_block = ""
            if self.autologin_var.get():
                session_value = "plasma.desktop" if self.session_type.get() == "Wayland" else "plasmax11.desktop"
                autologin_script_block = f"""
                mkdir -p /etc/sddm.conf.d
                cat <<EOF > /etc/sddm.conf.d/autologin.conf
                [Autologin]
                User={self.username.get()}
                Session={session_value}
                EOF
                """

            config_script = f"""#!/bin/bash
            export DEBIAN_FRONTEND=noninteractive
            echo "Configurando repositorios..."
            cat <<EOF > /etc/apt/sources.list
            deb http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware
            deb http://deb.debian.org/debian-security/ trixie-security main contrib non-free non-free-firmware
            deb http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware
            EOF
            apt-get update
            
            echo "Configurando idioma y localización..."
            apt-get install -y locales
            echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
            echo "{locale_val} UTF-8" >> /etc/locale.gen
            dpkg-reconfigure -f noninteractive locales
            update-locale LANG={locale_val}
            
            echo "Instalando kernel linux y paquetes básicos..."
            apt-get install -y linux-image-amd64 sudo network-manager console-setup sddm plasma-desktop {grub_packages}
            
            echo "lyndsos" > /etc/hostname
            ln -sf /usr/share/zoneinfo/{timezone} /etc/localtime
            dpkg-reconfigure -f noninteractive tzdata
            
            {grub_install_block}
            update-grub
            
            {autologin_script_block}
            systemctl enable NetworkManager
            systemctl enable sddm
            exit 0
            """
            
            ruta_script_temporal = os.path.join(self.target_mnt, "tmp", "chroot_install.sh")
            os.makedirs(os.path.dirname(ruta_script_temporal), exist_ok=True)
            with open(ruta_script_temporal, "w", encoding="utf-8") as f:
                f.write(config_script)
            os.chmod(ruta_script_temporal, 0o755)
            
            subprocess.run(["chroot", self.target_mnt, "/tmp/chroot_install.sh"], check=True)
            os.remove(ruta_script_temporal)

            # ---------------------------------------------------------
            # FASE 6: Copia de configuraciones de LyndsOS
            # ---------------------------------------------------------
            if os.path.exists(self.includes_dir):
                subprocess.run(["cp", "-a", f"{self.includes_dir}/.", self.target_mnt], check=True)

            # ---------------------------------------------------------
            # FASE 7: Creación del Usuario Físico e Inyección del fstab
            # ---------------------------------------------------------
            self.root.after(0, lambda: self.status_lbl.config(text="Estableciendo credenciales y fstab..."))
            self.pbar.after(0, lambda: self.pbar.config(value=90))
            
            subprocess.run(["chroot", self.target_mnt, "useradd", "-m", "-c", self.real_name.get(), "-s", "/bin/bash", self.username.get()], check=True)
            subprocess.run(["chroot", self.target_mnt, "usermod", "-aG", "sudo,video,render,audio,input", self.username.get()], check=True)
            
            proc_u = subprocess.Popen(["chroot", self.target_mnt, "chpasswd"], stdin=subprocess.PIPE, text=True)
            proc_u.communicate(input=f"{self.username.get()}:{self.u_pass_val}\nroot:{self.r_pass_val}\n")
            
            uuid_root = self.get_uuid(rp)
            
            # Generar fstab optimizado para BIOS (Sin montajes EFI innecesarios)
            fstab_content = f"""# /etc/fstab: static file system information.
            UUID={uuid_root}  /  ext4  noatime,errors=remount-ro  0  1
            proc  /proc  proc  defaults  0  0
            """
            with open(os.path.join(self.target_mnt, "etc", "fstab"), "w", encoding="utf-8") as fstf:
                fstf.write(fstab_content)

            # Finalización limpia
            self.root.after(0, lambda: self.status_lbl.config(text="Instalación completada con éxito."))
            self.pbar.after(0, lambda: self.pbar.config(value=100))
            self.is_installing = False
            self.force_umount_target()
            self.root.after(0, lambda: messagebox.showinfo("Éxito", "LyndsOS se ha instalado correctamente en modo BIOS. Puedes reiniciar."))

        except Exception as err:
            self.is_installing = False
            print(f"[DEBUG] ERROR CRÍTICO DETECTADO: {err}")
            self.force_umount_target()
            self.root.after(0, lambda: self.status_lbl.config(text="Instalación fallida."))
            self.root.after(0, lambda msg=str(err): messagebox.showerror("Error Crítico", f"Fallo en el despliegue BIOS:\n{msg}"))


if __name__ == "__main__":
    if not check_root():
        root_prem = tk.Tk()
        root_prem.withdraw()
        messagebox.showerror("Error de Permisos", "Abracitos requiere privilegios de Administrador (sudo).")
        sys.exit(1)

    if not check_internet():
        root_net = tk.Tk()
        root_net.withdraw()
        messagebox.showerror("Error de Conexión", "Es necesaria una conexión a Internet activa.")
        sys.exit(1)
        
    sys.stdout = Logger(log_path)
    sys.stderr = sys.stdout
        
    root_win = tk.Tk()
    app = AbracitosInstaller(root_win)
    root_win.mainloop()
