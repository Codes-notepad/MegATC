import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import socket
import random
import re
import time
import threading

SERVER_PORT = 5065
PUBLIC_SERVER_IP = "127.0.0.1"

CLIENT_PRESETS = [
    "MicroSIP / PortGo (стандарт)",
    "Zoiper (ПК и смартфон)",
    "Linphone (формат SIP URI)",
    "Другой SIP-клиент (универсальные поля)",
]


def generate_unique_credentials(existing_numbers=None):
    if existing_numbers is None:
        existing_numbers = set()
    while True:
        digits = "".join([str(random.randint(0, 9)) for _ in range(10)])
        number = f"+0{digits}"
        if number not in existing_numbers:
            password = str(random.randint(100000, 999999))
            return number, password


def request_number_from_host(host_ip, port=SERVER_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.5)
    try:
        sock.sendto(b"MEGATS_ALLOC_NUMBER", (host_ip, port))
        data, _ = sock.recvfrom(1024)
        resp = data.decode("utf-8", errors="ignore").strip()
        if resp.startswith("ASSIGNED:"):
            parts = resp.split(":")
            if len(parts) == 3:
                return parts[1], parts[2], True
    except Exception:
        pass
    finally:
        sock.close()
    num, pwd = generate_unique_credentials()
    return num, pwd, False


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_header(msg, header_name):
    match = re.search(rf"^{header_name}:\s*(.+)$", msg, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_user(header_value):
    match = re.search(r"sip:([^@>;]+)@", header_value, re.IGNORECASE)
    if match:
        return re.sub(r"[\s\-\(\)]", "", match.group(1).strip())
    return ""


def build_response(status_code, status_text, request_msg, extra_headers=""):
    via = get_header(request_msg, "Via")
    from_hdr = get_header(request_msg, "From")
    to_hdr = get_header(request_msg, "To")
    call_id = get_header(request_msg, "Call-ID")
    cseq = get_header(request_msg, "CSeq")

    if "tag=" not in to_hdr:
        to_hdr += f";tag=megats{random.randint(10000, 99999)}"

    response = (
        f"SIP/2.0 {status_code} {status_text}\r\n"
        f"Via: {via}\r\n"
        f"From: {from_hdr}\r\n"
        f"To: {to_hdr}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq}\r\n"
        f"Server: MegATS-GUI/5.1\r\n"
        f"{extra_headers}"
        f"Content-Length: 0\r\n\r\n"
    )
    return response.encode("utf-8")


def format_preset_fields(preset, number, password, ip):
    if preset == "MicroSIP / PortGo (стандарт)":
        return [
            ("Имя аккаунта:", f"МегАТС ({number})"),
            ("SIP-сервер:", f"{ip}:{SERVER_PORT}"),
            ("SIP-прокси:", f"{ip}:{SERVER_PORT}"),
            ("Имя пользователя:", number),
            ("Домен:", ip),
            ("Логин:", number),
            ("Пароль:", password),
            ("Транспорт:", "UDP"),
        ]
    elif preset == "Zoiper (ПК и смартфон)":
        return [
            ("Username / Login:", number),
            ("Password:", password),
            ("Domain / Host:", f"{ip}:{SERVER_PORT}"),
            ("Outbound Proxy:", f"{ip}:{SERVER_PORT}"),
            ("Auth Username:", number),
            ("Caller ID Name:", number),
            ("Строка быстрого входа:", f"{number}@{ip}:{SERVER_PORT}"),
            ("Transport:", "UDP"),
        ]
    elif preset == "Linphone (формат SIP URI)":
        return [
            ("Username:", number),
            ("SIP Domain:", f"{ip}:{SERVER_PORT}"),
            ("Password:", password),
            ("Display Name:", f"МегАТС {number}"),
            ("Ваш SIP-адрес (URI):", f"sip:{number}@{ip}:{SERVER_PORT}"),
            ("Server / Proxy URI:", f"sip:{ip}:{SERVER_PORT};transport=udp"),
            ("Порт сервера:", str(SERVER_PORT)),
            ("Transport:", "UDP"),
        ]
    else:
        return [
            ("Номер / Username:", number),
            ("Пароль / Password:", password),
            ("Хост / Server IP:", ip),
            ("Порт / Port:", str(SERVER_PORT)),
            ("Сервер с портом:", f"{ip}:{SERVER_PORT}"),
            ("SIP URI:", f"sip:{number}@{ip}:{SERVER_PORT}"),
            ("STUN (для интернета):", "stun.l.google.com:19302"),
            ("Протокол / Transport:", "UDP"),
        ]


class StartupSelectorDialog:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("МегАТС — Настройка подключения")
        self.top.geometry("500x490")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self.on_close)

        self.selected_preset = None
        self.friend_preset = CLIENT_PRESETS[0]
        self.selected_role = "host"
        self.host_ip = get_local_ip()

        frame = ttk.Frame(self.top, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="МегАТС (Голос, Видео и СМС)", font=("Segoe UI", 13, "bold")).pack(pady=(0, 4))

        ttk.Label(frame, text="1. Ваша роль:", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(2, 2))
        self.role_var = tk.StringVar(value="host")
        ttk.Radiobutton(frame, text="Я создаю АТС (Хост)", value="host", variable=self.role_var, command=self.toggle_ip_input).pack(anchor="w", padx=20)
        ttk.Radiobutton(frame, text="Я друг (Клиент)", value="client", variable=self.role_var, command=self.toggle_ip_input).pack(anchor="w", padx=20, pady=(2, 4))

        self.ip_box = ttk.Frame(frame)
        self.ip_box.pack(fill="x", padx=20, pady=2)
        ttk.Label(self.ip_box, text="IP-адрес Хоста:").pack(side="left")
        self.ip_var = tk.StringVar(value=self.host_ip)
        self.ip_entry = ttk.Entry(self.ip_box, textvariable=self.ip_var, width=20, state="disabled")
        self.ip_entry.pack(side="left", padx=6)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=8)

        ttk.Label(frame, text="2. Какая программа у ВАС?", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(2, 2))
        self.preset_var = tk.StringVar(value=CLIENT_PRESETS[0])
        for p in CLIENT_PRESETS:
            ttk.Radiobutton(frame, text=p, value=p, variable=self.preset_var).pack(anchor="w", padx=20, pady=1)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=8)

        ttk.Label(frame, text="3. Программа у ДРУГА (для карточки)?", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(2, 2))
        self.friend_preset_var = tk.StringVar(value=CLIENT_PRESETS[0])
        for p in CLIENT_PRESETS:
            ttk.Radiobutton(frame, text=p, value=p, variable=self.friend_preset_var).pack(anchor="w", padx=20, pady=1)

        ttk.Button(frame, text="Запустить МегАТС →", command=self.confirm).pack(fill="x", ipady=4, pady=(10, 0))

    def toggle_ip_input(self):
        if self.role_var.get() == "client":
            self.ip_entry.configure(state="normal")
        else:
            self.ip_entry.configure(state="disabled")

    def confirm(self):
        self.selected_preset = self.preset_var.get()
        self.friend_preset = self.friend_preset_var.get()
        self.selected_role = self.role_var.get()
        self.host_ip = self.ip_var.get().strip() or get_local_ip()
        self.top.destroy()

    def on_close(self):
        self.selected_preset = None
        self.top.destroy()


class FriendCardDialog:
    def __init__(self, parent, friend_num, friend_pass, server_ip, initial_friend_preset):
        self.top = tk.Toplevel(parent)
        self.top.title(f"Данные для друга: {friend_num}")
        self.top.geometry("560x470")
        self.top.resizable(False, False)
        self.top.grab_set()

        self.friend_num = friend_num
        self.friend_pass = friend_pass
        self.server_ip = server_ip

        frame = ttk.Frame(self.top, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Выдан номер другу: {friend_num}", font=("Segoe UI", 11, "bold"), foreground="#0066cc").pack(anchor="w", pady=(0, 4))
        ttk.Label(frame, text="Какая программа установлена у друга?").pack(anchor="w", pady=(2, 2))
        
        self.preset_var = tk.StringVar(value=initial_friend_preset)
        self.combo = ttk.Combobox(frame, textvariable=self.preset_var, state="readonly", width=45, values=CLIENT_PRESETS)
        self.combo.pack(fill="x", pady=(0, 8))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.update_view())

        self.card_frame = ttk.LabelFrame(frame, text="Параметры для вставки в программу друга", padding=10)
        self.card_frame.pack(fill="both", expand=True, pady=4)

        self.update_view()
        ttk.Button(frame, text="Скопировать всю карточку для друга", command=self.copy_card).pack(fill="x", ipady=5, pady=(8, 0))

    def update_view(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        preset = self.preset_var.get()
        mapping = format_preset_fields(preset, self.friend_num, self.friend_pass, self.server_ip)
        self.current_lines = [f"=== Настройки МегАТС для друга ({preset}) ==="]

        for label_text, val in mapping:
            row = ttk.Frame(self.card_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label_text, width=22).pack(side="left")
            var = tk.StringVar(value=val)
            ttk.Entry(row, textvariable=var, state="readonly", font=("Consolas", 9)).pack(side="left", fill="x", expand=True, padx=4)
            self.current_lines.append(f"{label_text} {val}")

    def copy_card(self):
        self.top.clipboard_clear()
        self.top.clipboard_append("\n".join(self.current_lines))
        self.top.update()
        messagebox.showinfo("Готово", "Карточка настроек для друга скопирована в буфер обмена!", parent=self.top)


class MegATSApp:
    def __init__(self, root, initial_preset, friend_preset, initial_role, host_ip):
        self.root = root
        self.root.title("МегАТС — Виртуальная АТС (Голос, Видео, СМС)")
        self.root.geometry("690x900")
        self.root.resizable(False, False)

        self.local_ip = get_local_ip()
        self.role = initial_role
        self.friend_preset = friend_preset
        self.server_running = False
        self.sock = None

        self.issued_numbers = set()
        self.registered_users = {}
        self.active_calls = {}

        if initial_role == "host":
            self.my_number, self.my_password = generate_unique_credentials(self.issued_numbers)
            self.issued_numbers.add(self.my_number)
            self.current_ip = self.local_ip
            self.got_from_server = True
        else:
            self.current_ip = host_ip
            self.my_number, self.my_password, self.got_from_server = request_number_from_host(host_ip)
            self.issued_numbers.add(self.my_number)

        self.setup_ui(initial_preset)
        self.update_fields()

        if initial_role == "host":
            self.start_server()
        else:
            if self.got_from_server:
                self.log(f"Сервер Хоста ({host_ip}) выдал вам номер: {self.my_number}")
            else:
                self.log(f"Сервер недоступен. Сгенерирован локальный номер: {self.my_number}")

    def setup_ui(self, initial_preset):
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))

        header_frame = ttk.Frame(self.root, padding=(15, 8))
        header_frame.pack(fill="x")
        role_title = "ХОСТ (Сервер АТС)" if self.role == "host" else "КЛИЕНТ (Друг)"
        ttk.Label(header_frame, text=f"МегАТС — {role_title}", style="Header.TLabel").pack()
        ttk.Label(
            header_frame,
            text=f"Ваш номер: {self.my_number} | Поддерживаются аудио, видеозвонки и СМС.",
            foreground="#0066cc",
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(2, 0))

        mode_frame = ttk.LabelFrame(self.root, text="1. Управление сервером и номерами", padding=10)
        mode_frame.pack(fill="x", padx=15, pady=4)

        ip_row = ttk.Frame(mode_frame)
        ip_row.pack(fill="x", pady=3)
        ttk.Label(ip_row, text="IP-адрес сервера:").pack(side="left")
        self.ip_var = tk.StringVar(value=self.current_ip)
        self.ip_entry = ttk.Entry(ip_row, textvariable=self.ip_var, width=18)
        self.ip_entry.pack(side="left", padx=6)
        self.ip_entry.bind("<KeyRelease>", lambda e: self.update_fields())

        ttk.Button(ip_row, text="Мой IP", command=self.set_local_ip).pack(side="left", padx=2)
        ttk.Button(ip_row, text="+ Номер для друга", command=self.create_friend_number).pack(side="right", padx=2)
        ttk.Button(ip_row, text="Сменить номер", command=self.regenerate_number).pack(side="right", padx=2)

        client_row = ttk.Frame(mode_frame)
        client_row.pack(fill="x", pady=4)
        ttk.Label(client_row, text="Ваша программа:").pack(side="left")
        self.client_preset = tk.StringVar(value=initial_preset)
        preset_combo = ttk.Combobox(client_row, textvariable=self.client_preset, state="readonly", width=38, values=CLIENT_PRESETS)
        preset_combo.pack(side="left", padx=8)
        preset_combo.bind("<<ComboboxSelected>>", lambda e: self.update_fields())

        btn_row = ttk.Frame(mode_frame)
        btn_row.pack(fill="x", pady=(6, 2))
        self.start_btn = ttk.Button(btn_row, text="▶ Запустить сервер АТС (для Хоста)", command=self.toggle_server)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.status_lbl = ttk.Label(btn_row, text="Статус: Сервер выкл.", foreground="#666666")
        self.status_lbl.pack(side="right", padx=5)

        card_frame = ttk.LabelFrame(self.root, text="2. Ваши данные для входа", padding=10)
        card_frame.pack(fill="x", padx=15, pady=4)

        self.field_labels = {}
        self.fields = {}
        keys = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]

        for key in keys:
            row = ttk.Frame(card_frame)
            row.pack(fill="x", pady=2)
            lbl = ttk.Label(row, text="", width=24)
            lbl.pack(side="left")
            var = tk.StringVar()
            entry = ttk.Entry(row, textvariable=var, state="readonly", font=("Consolas", 10))
            entry.pack(side="left", fill="x", expand=True, padx=5)
            btn = ttk.Button(row, text="Копировать", width=11, command=lambda v=var: self.copy_to_clipboard(v.get()))
            btn.pack(side="right")
            self.field_labels[key] = lbl
            self.fields[key] = var

        copy_all_row = ttk.Frame(card_frame)
        copy_all_row.pack(fill="x", pady=(6, 0))
        ttk.Button(copy_all_row, text="Скопировать мои данные текстом", command=self.copy_all_card).pack(side="left")

        users_frame = ttk.LabelFrame(self.root, text="3. Абоненты в сети (кликните, чтобы скопировать номер для звонка/СМС)", padding=10)
        users_frame.pack(fill="x", padx=15, pady=4)

        columns = ("number", "role", "ip", "time")
        self.users_tree = ttk.Treeview(users_frame, columns=columns, show="headings", height=4)
        self.users_tree.heading("number", text="Номер абонента")
        self.users_tree.heading("role", text="Кто это")
        self.users_tree.heading("ip", text="IP-адрес")
        self.users_tree.heading("time", text="В сети с")

        self.users_tree.column("number", width=170, anchor="center")
        self.users_tree.column("role", width=150, anchor="center")
        self.users_tree.column("ip", width=180, anchor="center")
        self.users_tree.column("time", width=110, anchor="center")
        self.users_tree.pack(fill="x")

        self.users_tree.bind("<<TreeviewSelect>>", self.on_user_select)

        users_btn_row = ttk.Frame(users_frame)
        users_btn_row.pack(fill="x", pady=(5, 0))
        ttk.Button(users_btn_row, text="Копировать выбранный номер", command=self.copy_selected_user).pack(side="left")
        self.copied_hint = ttk.Label(users_btn_row, text="", foreground="green")
        self.copied_hint.pack(side="left", padx=10)

        log_frame = ttk.LabelFrame(self.root, text="4. Журнал (голосовые вызовы, видео, СМС)", padding=10)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(4, 10))

        self.log_area = scrolledtext.ScrolledText(log_frame, height=6, state="disabled", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True)

    def set_local_ip(self):
        self.ip_var.set(self.local_ip)
        self.update_fields()

    def regenerate_number(self):
        if self.role == "client" and not self.server_running:
            ip = self.ip_var.get().strip() or PUBLIC_SERVER_IP
            self.my_number, self.my_password, _ = request_number_from_host(ip)
            self.issued_numbers.add(self.my_number)
        else:
            self.my_number, self.my_password = generate_unique_credentials(self.issued_numbers)
            self.issued_numbers.add(self.my_number)
        self.update_fields()
        self.log(f"Новый номер: {self.my_number}")

    def create_friend_number(self):
        ip = self.ip_var.get().strip() or PUBLIC_SERVER_IP
        if self.role == "client" and not self.server_running:
            f_num, f_pass, _ = request_number_from_host(ip)
        else:
            f_num, f_pass = generate_unique_credentials(self.issued_numbers)
        self.issued_numbers.add(f_num)
        self.log(f"Создан номер для друга: {f_num}")
        FriendCardDialog(self.root, f_num, f_pass, ip, self.friend_preset)

    def update_fields(self):
        ip = self.ip_var.get().strip() or PUBLIC_SERVER_IP
        preset = self.client_preset.get()
        mapping = format_preset_fields(preset, self.my_number, self.my_password, ip)

        for idx, (label_text, val) in enumerate(mapping, start=1):
            key = f"f{idx}"
            self.field_labels[key].configure(text=label_text)
            self.fields[key].set(val)

    def copy_to_clipboard(self, text):
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.copied_hint.configure(text=f"Скопировано: {text}")
        self.root.after(2500, lambda: self.copied_hint.configure(text=""))

    def copy_all_card(self):
        lines = [f"=== Настройки МегАТС ({self.client_preset.get()}) ==="]
        for idx in range(1, 9):
            key = f"f{idx}"
            lbl = self.field_labels[key].cget("text")
            val = self.fields[key].get()
            lines.append(f"{lbl} {val}")
        self.copy_to_clipboard("\n".join(lines))
        self.copied_hint.configure(text="Карточка скопирована!")

    def on_user_select(self, event):
        selected = self.users_tree.selection()
        if selected:
            num = self.users_tree.item(selected[0], "values")[0]
            self.copy_to_clipboard(num)

    def copy_selected_user(self):
        selected = self.users_tree.selection()
        if selected:
            num = self.users_tree.item(selected[0], "values")[0]
            self.copy_to_clipboard(num)
        else:
            messagebox.showinfo("Выбор номера", "Нажмите на номер абонента в таблице.")

    def refresh_users_table(self):
        selected_num = None
        selected = self.users_tree.selection()
        if selected:
            selected_num = self.users_tree.item(selected[0], "values")[0]

        for item in self.users_tree.get_children():
            self.users_tree.delete(item)

        for num, info in self.registered_users.items():
            who = "Вы (Хост)" if num == self.my_number else "Друг (Абонент)"
            addr_str = f"{info['addr'][0]}:{info['addr'][1]}"
            item_id = self.users_tree.insert("", "end", values=(num, who, addr_str, info["last_seen"]))
            if num == selected_num:
                self.users_tree.selection_set(item_id)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"[{timestamp}] {message}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def toggle_server(self):
        if not self.server_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", SERVER_PORT))
            self.sock.settimeout(1.0)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Порт {SERVER_PORT} занят:\n{e}")
            return

        self.server_running = True
        self.start_btn.configure(text="■ Остановить сервер АТС")
        self.status_lbl.configure(text=f"Сервер ВКЛ ({SERVER_PORT})", foreground="green")
        self.log(f"Сервер запущен! Поддерживаются звонки, видео и СМС.")

        threading.Thread(target=self.server_loop, daemon=True).start()

    def stop_server(self):
        self.server_running = False
        if self.sock:
            self.sock.close()
            self.sock = None
        self.registered_users.clear()
        self.refresh_users_table()
        self.start_btn.configure(text="▶ Запустить сервер АТС (для Хоста)")
        self.status_lbl.configure(text="Статус: Сервер выкл.", foreground="#666666")
        self.log("Сервер остановлен.")

    def server_loop(self):
        while self.server_running:
            try:
                data, addr = self.sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                msg = data.decode("utf-8", errors="ignore")
                first_line = msg.splitlines()[0] if msg else ""

                if first_line == "MEGATS_ALLOC_NUMBER":
                    new_num, new_pass = generate_unique_credentials(self.issued_numbers)
                    self.issued_numbers.add(new_num)
                    reply = f"ASSIGNED:{new_num}:{new_pass}".encode("utf-8")
                    self.sock.sendto(reply, addr)
                    self.root.after(0, self.log, f"Выдан номер другу ({addr[0]}): {new_num}")
                    continue

                if first_line.startswith("REGISTER"):
                    from_hdr = get_header(msg, "From")
                    user_num = extract_user(from_hdr)

                    if re.match(r"^\+0\d{10}$", user_num):
                        expires_hdr = get_header(msg, "Expires")
                        if expires_hdr == "0":
                            self.registered_users.pop(user_num, None)
                            self.sock.sendto(build_response(200, "OK", msg), addr)
                            self.root.after(0, self.refresh_users_table)
                            self.root.after(0, self.log, f"Отключился: {user_num}")
                        else:
                            is_new = user_num not in self.registered_users
                            self.issued_numbers.add(user_num)
                            self.registered_users[user_num] = {
                                "addr": addr,
                                "last_seen": time.strftime("%H:%M:%S"),
                            }
                            contact = get_header(msg, "Contact")
                            extra = f"Contact: {contact}\r\nExpires: 3600\r\n"
                            self.sock.sendto(build_response(200, "OK", msg, extra), addr)
                            self.root.after(0, self.refresh_users_table)
                            if is_new:
                                self.root.after(0, self.log, f"В сети: {user_num} ({addr[0]}:{addr[1]})")
                    else:
                        self.sock.sendto(build_response(403, "Forbidden", msg), addr)

                elif first_line.startswith("MESSAGE"):
                    to_hdr = get_header(msg, "To")
                    from_hdr = get_header(msg, "From")
                    caller_num = extract_user(from_hdr)
                    callee_num = extract_user(to_hdr)

                    self.root.after(0, self.log, f"СМС от {caller_num} для {callee_num}")
                    self.sock.sendto(build_response(200, "OK", msg), addr)

                    if callee_num in self.registered_users:
                        target_addr = self.registered_users[callee_num]["addr"]
                        self.sock.sendto(data, target_addr)

                elif first_line.startswith("INVITE"):
                    from_hdr = get_header(msg, "From")
                    to_hdr = get_header(msg, "To")
                    call_id = get_header(msg, "Call-ID")

                    caller_num = extract_user(from_hdr)
                    callee_num = extract_user(to_hdr)

                    call_type = "Видеозвонок" if "m=video" in msg else "Аудиозвонок"
                    self.root.after(0, self.log, f"{call_type}: {caller_num} ---> {callee_num}")
                    
                    self.sock.sendto(build_response(100, "Trying", msg), addr)

                    if callee_num in self.registered_users:
                        target_addr = self.registered_users[callee_num]["addr"]
                        self.active_calls[call_id] = (addr, target_addr)
                        self.sock.sendto(data, target_addr)
                    else:
                        self.sock.sendto(build_response(404, "Not Found", msg), addr)
                        self.root.after(0, self.log, f"Ошибка 404: номер {callee_num} не в сети")

                elif first_line.startswith("SIP/2.0"):
                    call_id = get_header(msg, "Call-ID")
                    if call_id in self.active_calls:
                        caller_addr, callee_addr = self.active_calls[call_id]
                        dest_addr = caller_addr if addr == callee_addr else callee_addr
                        self.sock.sendto(data, dest_addr)

                elif first_line.startswith(("ACK", "CANCEL", "BYE")):
                    call_id = get_header(msg, "Call-ID")
                    if call_id in self.active_calls:
                        caller_addr, callee_addr = self.active_calls[call_id]
                        dest_addr = callee_addr if addr == caller_addr else caller_addr
                        self.sock.sendto(data, dest_addr)
                        if first_line.startswith(("BYE", "CANCEL")):
                            self.root.after(0, self.log, "Вызов/разговор завершен")

                elif first_line.startswith("OPTIONS"):
                    self.sock.sendto(build_response(200, "OK", msg), addr)

            except Exception as e:
                self.root.after(0, self.log, f"Ошибка пакета: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    dialog = StartupSelectorDialog(root)
    root.wait_window(dialog.top)

    if dialog.selected_preset:
        root.deiconify()
        app = MegATSApp(root, dialog.selected_preset, dialog.friend_preset, dialog.selected_role, dialog.host_ip)
        root.mainloop()
    else:
        root.destroy()
