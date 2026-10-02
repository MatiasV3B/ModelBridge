"""Main GUI Application for Antigravity Bridge using CustomTkinter."""

import os
import sys

# Protect against pythonw None stdout/stderr
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
import time
import json
import threading
import subprocess
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw

from core.config import bridge_config, FILES_DIR, set_windows_startup, is_windows_startup_enabled
from core.bridge_engine import metrics
from core.model_registry import model_registry
from core.file_store import file_store
from server.app import server_manager

# Appearance configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AntigravityBridgeGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Antigravity Bridge — OpenAI Localhost Gateway")
        self.geometry("980x680")
        self.minsize(880, 620)

        # Handle window close (minimize to tray if enabled)
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Main Layout: Top Header + Tabview
        self._create_header()
        self._create_tabs()

        # System tray icon
        self._create_tray_icon()

        # Auto-start bridge if configured
        if bridge_config.auto_start_bridge:
            self.after(400, self._auto_start_bridge)

        # Background updater
        self.after(1000, self._periodic_update)

    def _create_header(self):
        """Top bar with title, status badge and One-Click Start/Stop Button."""
        self.header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("#2b2b2b", "#1e1e1e"))
        self.header_frame.pack(fill="x", padx=16, pady=(14, 8))

        # Title & Subtitle
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=12)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="⚡ Antigravity Bridge",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="OpenAI API Gateway compatible con Agentes Antigravity",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        sub_lbl.pack(anchor="w")

        # Right Action Area: Status Pill + ONE-CLICK TOGGLE BUTTON
        action_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        action_box.pack(side="right", padx=16, pady=12)

        self.status_pill = ctk.CTkLabel(
            action_box,
            text="🔴 DETENIDO",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#ff4444", "#ff6b6b"),
            fg_color=("#3a2020", "#2d1616"),
            corner_radius=8,
            padx=14,
            pady=6,
        )
        self.status_pill.pack(side="left", padx=(0, 16))

        self.btn_auth = ctk.CTkButton(
            action_box,
            text="🔑 Iniciar Sesión",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#373b3e", "#2c3034"),
            hover_color=("#495057", "#3d4246"),
            width=110,
            height=42,
            corner_radius=8,
            command=self._launch_login_window
        )
        self.btn_auth.pack(side="left", padx=(0, 8))

        self.btn_claude_cli = ctk.CTkButton(
            action_box,
            text="💻 Claude Code",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#495057", "#343a40"),
            hover_color=("#6c757d", "#495057"),
            width=120,
            height=42,
            corner_radius=8,
            command=self._launch_claude_code_terminal
        )
        self.btn_claude_cli.pack(side="left", padx=(0, 10))

        self.btn_toggle_bridge = ctk.CTkButton(
            action_box,
            text="▶ INICIAR BRIDGE",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#198754", "#28a745"),
            hover_color=("#157347", "#218838"),
            width=165,
            height=42,
            corner_radius=8,
            command=self.toggle_bridge
        )
        self.btn_toggle_bridge.pack(side="left")

    def _create_tabs(self):
        """Tab navigation container."""
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self.tab_dashboard = self.tabview.add("🚀 Dashboard")
        self.tab_models = self.tabview.add("🧠 Modelos")
        self.tab_files = self.tabview.add("📁 Archivos")
        self.tab_playground = self.tabview.add("💬 Playground")
        self.tab_logs = self.tabview.add("📊 Tráfico y Logs")
        self.tab_settings = self.tabview.add("⚙ Configuración")

        self._build_dashboard_tab()
        self._build_models_tab()
        self._build_files_tab()
        self._build_playground_tab()
        self._build_logs_tab()
        self._build_settings_tab()

    # -------------------------------------------------------------
    # 1. DASHBOARD TAB
    # -------------------------------------------------------------
    def _build_dashboard_tab(self):
        # Quick Connect Cards Box
        cards_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        cards_frame.pack(fill="x", padx=10, pady=10)

        # URL Card
        url_card = ctk.CTkFrame(cards_frame, corner_radius=8)
        url_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkLabel(url_card, text="URL Base OpenAI", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self.lbl_base_url = ctk.CTkLabel(
            url_card,
            text=f"http://{bridge_config.host}:{bridge_config.port}/v1",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color="#4dabf7"
        )
        self.lbl_base_url.pack(anchor="w", padx=12, pady=(0, 8))

        btn_copy_url = ctk.CTkButton(
            url_card,
            text="Copiar URL",
            height=28,
            width=100,
            command=lambda: self._copy_to_clipboard(f"http://{bridge_config.host}:{bridge_config.port}/v1")
        )
        btn_copy_url.pack(anchor="w", padx=12, pady=(0, 10))

        # API Key Card
        key_card = ctk.CTkFrame(cards_frame, corner_radius=8)
        key_card.pack(side="left", fill="both", expand=True, padx=4)

        ctk.CTkLabel(key_card, text="API Key (Cualquiera)", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        lbl_key = ctk.CTkLabel(
            key_card,
            text="sk-antigravity",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color="#69db7c"
        )
        lbl_key.pack(anchor="w", padx=12, pady=(0, 8))

        btn_copy_key = ctk.CTkButton(
            key_card,
            text="Copiar Clave",
            height=28,
            width=100,
            command=lambda: self._copy_to_clipboard("sk-antigravity")
        )
        btn_copy_key.pack(anchor="w", padx=12, pady=(0, 10))

        # Claude Code Terminal Card
        claude_card = ctk.CTkFrame(cards_frame, corner_radius=8)
        claude_card.pack(side="left", fill="both", expand=True, padx=(6, 0))

        ctk.CTkLabel(claude_card, text="✳️ Claude Code (Terminal)", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        lbl_claude_info = ctk.CTkLabel(
            claude_card,
            text=f"Base: :{bridge_config.port} (CLI)",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color="#da77f2"
        )
        lbl_claude_info.pack(anchor="w", padx=12, pady=(0, 8))

        btn_open_claude = ctk.CTkButton(
            claude_card,
            text="💻 Abrir Terminal",
            height=28,
            width=120,
            fg_color=("#845ef7", "#7048e8"),
            hover_color=("#7048e8", "#5f3dc4"),
            command=self._launch_claude_code_terminal
        )
        btn_open_claude.pack(anchor="w", padx=12, pady=(0, 10))

        # Metrics Overview Frame
        metrics_frame = ctk.CTkFrame(self.tab_dashboard, corner_radius=8)
        metrics_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(metrics_frame, text="Métricas en Tiempo Real", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(10, 8))

        stats_box = ctk.CTkFrame(metrics_frame, fg_color="transparent")
        stats_box.pack(fill="x", padx=14, pady=(0, 14))

        self.stat_requests = self._create_stat_badge(stats_box, "Total Peticiones", "0")
        self.stat_in_tokens = self._create_stat_badge(stats_box, "Tokens Entrada", "0")
        self.stat_out_tokens = self._create_stat_badge(stats_box, "Tokens Salida", "0")
        self.stat_active = self._create_stat_badge(stats_box, "En Curso", "0")

        # Instructions / Client Guide
        guide_frame = ctk.CTkFrame(self.tab_dashboard, corner_radius=8)
        guide_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(guide_frame, text="💡 Integración Rápida con Clientes OpenAI & Claude Code", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(12, 6))

        guide_text = (
            "• Claude Code CLI (Terminal):\n"
            "   Haz clic en '💻 Claude Code' arriba o en '💻 Abrir Terminal' para iniciar Claude Code conectado al Bridge.\n"
            "   Variables: ANTHROPIC_BASE_URL=http://localhost:8000 | ANTHROPIC_API_KEY=sk-antigravity\n\n"
            "• Cursor / VS Code (Continue.dev):\n"
            "   Añade proveedor OpenAI compatible con Base URL: http://localhost:8000/v1 y API Key: sk-antigravity\n\n"
            "• LibreChat / Open WebUI / AnythingLLM:\n"
            "   Configura OpenAI API Endpoint como http://host.docker.internal:8000/v1 o http://localhost:8000/v1\n\n"
            "• Python OpenAI SDK:\n"
            "   client = OpenAI(base_url='http://localhost:8000/v1', api_key='sk-antigravity')\n"
            "   response = client.chat.completions.create(model='claude-sonnet-4-6', messages=[...])"
        )
        lbl_guide = ctk.CTkLabel(guide_frame, text=guide_text, justify="left", font=ctk.CTkFont(family="Consolas", size=12))
        lbl_guide.pack(anchor="w", padx=14, pady=(0, 12))

    def _create_stat_badge(self, parent, label, initial_val):
        box = ctk.CTkFrame(parent, corner_radius=6, fg_color=("#333333", "#242424"))
        box.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(box, text=label, font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(6, 0))
        val_lbl = ctk.CTkLabel(box, text=initial_val, font=ctk.CTkFont(size=18, weight="bold"))
        val_lbl.pack(pady=(0, 6))
        return val_lbl

    # -------------------------------------------------------------
    # 2. MODELS TAB
    # -------------------------------------------------------------
    def _build_models_tab(self):
        ctrl_box = ctk.CTkFrame(self.tab_models, fg_color="transparent")
        ctrl_box.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(ctrl_box, text="Modelos de Antigravity Disponibles", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        btn_refresh = ctk.CTkButton(
            ctrl_box,
            text="🔄 Actualizar Modelos (CLI)",
            width=170,
            height=30,
            command=self._refresh_models_list
        )
        btn_refresh.pack(side="right")

        # Active Model Selector
        sel_box = ctk.CTkFrame(self.tab_models, corner_radius=8)
        sel_box.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(sel_box, text="Modelo Activo por Defecto:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=12, pady=10)

        models_list = [m["id"] for m in model_registry.get_models()]
        self.model_dropdown = ctk.CTkComboBox(
            sel_box,
            values=models_list,
            width=280,
            command=self._on_model_selected
        )
        self.model_dropdown.set(bridge_config.default_model)
        self.model_dropdown.pack(side="left", padx=6, pady=10)

        self.lbl_model_status = ctk.CTkLabel(sel_box, text="✓ Guardado", text_color="#69db7c", font=ctk.CTkFont(size=12))
        # 2 Tabs: Antigravity vs Claude Code
        self.active_models_category = "⚡ Antigravity"
        self.models_category_segmented = ctk.CTkSegmentedButton(
            self.tab_models,
            values=["⚡ Antigravity", "✳️ Claude Code"],
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            command=self._on_model_category_changed
        )
        self.models_category_segmented.set("⚡ Antigravity")
        self.models_category_segmented.pack(fill="x", padx=10, pady=(0, 10))

        # Scrollable list of models
        self.models_scroll = ctk.CTkScrollableFrame(self.tab_models, corner_radius=8)
        self.models_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._populate_models_scroll()

    def _on_model_category_changed(self, value):
        self.active_models_category = value
        self._populate_models_scroll()

    def _populate_models_scroll(self):
        for widget in self.models_scroll.winfo_children():
            widget.destroy()

        all_models = model_registry.get_models()
        is_claude_tab = "Claude" in getattr(self, "active_models_category", "")

        if is_claude_tab:
            # Claude Code tab: only the new generation models
            models = [
                m for m in all_models
                if any(k in m["id"].lower() for k in ["5-5", "5.5", "fable", "haiku-4-5", "haiku-4.5"])
            ]
        else:
            # Antigravity tab: Gemini, older Claude models (Sonnet 4.6, Opus 4.6), GPT-OSS
            models = [
                m for m in all_models
                if not any(k in m["id"].lower() for k in ["5-5", "5.5", "fable", "haiku-4-5", "haiku-4.5"])
            ]

        for idx, m in enumerate(models):
            item = ctk.CTkFrame(self.models_scroll, corner_radius=6, fg_color=("#333333", "#252525"))
            item.pack(fill="x", padx=4, pady=4)

            name_box = ctk.CTkFrame(item, fg_color="transparent")
            name_box.pack(side="left", padx=12, pady=8)

            ctk.CTkLabel(name_box, text=m["name"], font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(name_box, text=f"ID: {m['id']}", font=ctk.CTkFont(family="Consolas", size=11), text_color="gray").pack(anchor="w")

            btn_set = ctk.CTkButton(
                item,
                text="Usar por Defecto",
                width=130,
                height=26,
                command=lambda mid=m["id"]: self._set_default_model(mid)
            )
            btn_set.pack(side="right", padx=12)

    def _on_model_selected(self, chosen_model):
        self._set_default_model(chosen_model)

    def _set_default_model(self, model_id):
        bridge_config.default_model = model_id
        bridge_config.save()
        self.model_dropdown.set(model_id)
        self.lbl_model_status.configure(text=f"✓ Modelo activo: {model_id}")

    def _refresh_models_list(self):
        models = model_registry.refresh_models()
        m_ids = [m["id"] for m in models]
        self.model_dropdown.configure(values=m_ids)
        self._populate_models_scroll()
        messagebox.showinfo("Modelos", f"Se actualizaron {len(models)} modelos disponibles desde Antigravity.")

    # -------------------------------------------------------------
    # 3. FILES TAB
    # -------------------------------------------------------------
    def _build_files_tab(self):
        ctrl_box = ctk.CTkFrame(self.tab_files, fg_color="transparent")
        ctrl_box.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(ctrl_box, text="Archivos del Bridge (/v1/files)", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        btn_open_folder = ctk.CTkButton(
            ctrl_box,
            text="📂 Abrir Carpeta",
            width=120,
            height=30,
            fg_color="#495057",
            command=lambda: os.startfile(str(FILES_DIR))
        )
        btn_open_folder.pack(side="right", padx=(8, 0))

        btn_upload = ctk.CTkButton(
            ctrl_box,
            text="➕ Subir Archivo...",
            width=140,
            height=30,
            command=self._upload_file_dialog
        )
        btn_upload.pack(side="right")

        # Scrollable list of uploaded files
        self.files_scroll = ctk.CTkScrollableFrame(self.tab_files, corner_radius=8)
        self.files_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._populate_files_scroll()

    def _upload_file_dialog(self):
        path = filedialog.askopenfilename(title="Seleccionar archivo para subir al Bridge")
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                content = f.read()
            filename = Path(path).name
            file_store.save_file(filename=filename, content_bytes=content)
            self._populate_files_scroll()

    def _populate_files_scroll(self):
        for widget in self.files_scroll.winfo_children():
            widget.destroy()

        files = file_store.list_files()
        if not files:
            empty_lbl = ctk.CTkLabel(
                self.files_scroll,
                text="No hay archivos subidos aún. Puedes subirlos aquí o mediante la API POST /v1/files.",
                text_color="gray",
                font=ctk.CTkFont(size=12)
            )
            empty_lbl.pack(pady=40)
            return

        for f in files:
            row = ctk.CTkFrame(self.files_scroll, corner_radius=6, fg_color=("#333333", "#252525"))
            row.pack(fill="x", padx=4, pady=4)

            info_box = ctk.CTkFrame(row, fg_color="transparent")
            info_box.pack(side="left", padx=12, pady=8)

            ctk.CTkLabel(info_box, text=f["filename"], font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(
                info_box,
                text=f"ID: {f['id']}  •  Tamaño: {round(f['bytes']/1024, 1)} KB  •  Propósito: {f.get('purpose', 'assistants')}",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color="gray"
            ).pack(anchor="w")

            btn_del = ctk.CTkButton(
                row,
                text="Eliminar",
                width=80,
                height=26,
                fg_color="#c92a2a",
                hover_color="#a61e1e",
                command=lambda fid=f["id"]: self._delete_file(fid)
            )
            btn_del.pack(side="right", padx=10)

            btn_copy_fid = ctk.CTkButton(
                row,
                text="Copiar ID",
                width=90,
                height=26,
                command=lambda fid=f["id"]: self._copy_to_clipboard(fid)
            )
            btn_copy_fid.pack(side="right", padx=4)

    def _delete_file(self, file_id):
        file_store.delete_file(file_id)
        self._populate_files_scroll()

    # -------------------------------------------------------------
    # 4. PLAYGROUND TAB
    # -------------------------------------------------------------
    def _build_playground_tab(self):
        pg_frame = ctk.CTkFrame(self.tab_playground, fg_color="transparent")
        pg_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Chat history display
        self.txt_chat_history = ctk.CTkTextbox(pg_frame, font=ctk.CTkFont(size=13), corner_radius=8)
        self.txt_chat_history.pack(fill="both", expand=True, pady=(0, 10))
        self.txt_chat_history.insert("end", "=== Chat Playground con Antigravity Bridge ===\nEscribe un mensaje para probar el modelo en localhost.\n\n")

        # Bottom Input Area
        input_bar = ctk.CTkFrame(pg_frame, fg_color="transparent")
        input_bar.pack(fill="x")

        self.entry_user_msg = ctk.CTkEntry(
            input_bar,
            placeholder_text="Escribe tu mensaje para el agente...",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.entry_user_msg.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_user_msg.bind("<Return>", lambda e: self._send_playground_message())

        self.btn_send_msg = ctk.CTkButton(
            input_bar,
            text="Enviar",
            width=100,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._send_playground_message
        )
        self.btn_send_msg.pack(side="right")

    def _send_playground_message(self):
        msg = self.entry_user_msg.get().strip()
        if not msg:
            return

        self.entry_user_msg.delete(0, "end")
        self.txt_chat_history.insert("end", f"\n[Tú]: {msg}\n[Agente]: ")
        self.txt_chat_history.see("end")

        self.btn_send_msg.configure(state="disabled")

        # Run streaming in background thread
        threading.Thread(target=self._run_playground_stream, args=(msg,), daemon=True).start()

    def _run_playground_stream(self, prompt: str):
        try:
            import requests
            url = f"http://127.0.0.1:{bridge_config.port}/v1/chat/completions"
            payload = {
                "model": bridge_config.default_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            }
            resp = requests.post(url, json=payload, stream=True, timeout=60)
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        raw_data = decoded[6:]
                        if raw_data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                self.after(0, lambda d=delta: self._append_chat(d))
                        except Exception:
                            pass
            self.after(0, lambda: self._append_chat("\n"))
        except Exception as e:
            self.after(0, lambda: self._append_chat(f"\n[Error: {e}. ¿Está el Bridge iniciado?]\n"))
        finally:
            self.after(0, lambda: self.btn_send_msg.configure(state="normal"))

    def _append_chat(self, text: str):
        self.txt_chat_history.insert("end", text)
        self.txt_chat_history.see("end")

    # -------------------------------------------------------------
    # 5. LOGS TAB
    # -------------------------------------------------------------
    def _build_logs_tab(self):
        ctrl_box = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        ctrl_box.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(ctrl_box, text="Registro de Peticiones y Tráfico", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        btn_clear_logs = ctk.CTkButton(
            ctrl_box,
            text="Limpiar Registro",
            width=130,
            height=28,
            command=self._clear_logs
        )
        btn_clear_logs.pack(side="right")

        self.txt_logs = ctk.CTkTextbox(self.tab_logs, font=ctk.CTkFont(family="Consolas", size=12), corner_radius=8)
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _clear_logs(self):
        metrics.recent_logs.clear()
        self.txt_logs.delete("1.0", "end")

    # -------------------------------------------------------------
    # 6. SETTINGS TAB
    # -------------------------------------------------------------
    def _build_settings_tab(self):
        box = ctk.CTkScrollableFrame(self.tab_settings, corner_radius=8)
        box.pack(fill="both", expand=True, padx=10, pady=10)

        # Engine Mode
        ctk.CTkLabel(box, text="Motor de Ejecución", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))

        self.var_engine = ctk.StringVar(value=bridge_config.engine_mode)
        radio_cli = ctk.CTkRadioButton(
            box,
            text="Antigravity CLI (Recomendado: Autenticación automática de Google, soporte completo de agentes)",
            variable=self.var_engine,
            value="cli",
            command=self._save_settings
        )
        radio_cli.pack(anchor="w", padx=16, pady=4)

        radio_sdk = ctk.CTkRadioButton(
            box,
            text="Python SDK Directo (Requiere GEMINI_API_KEY en ajustes o entorno)",
            variable=self.var_engine,
            value="sdk",
            command=self._save_settings
        )
        radio_sdk.pack(anchor="w", padx=16, pady=4)

        # Host and Port
        ctk.CTkLabel(box, text="Red y Conexión", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(16, 4))

        net_frame = ctk.CTkFrame(box, fg_color="transparent")
        net_frame.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(net_frame, text="Host:").pack(side="left", padx=(0, 6))
        self.entry_host = ctk.CTkEntry(net_frame, width=120)
        self.entry_host.insert(0, bridge_config.host)
        self.entry_host.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(net_frame, text="Puerto:").pack(side="left", padx=(0, 6))
        self.entry_port = ctk.CTkEntry(net_frame, width=90)
        self.entry_port.insert(0, str(bridge_config.port))
        self.entry_port.pack(side="left")

        # CLI Path
        ctk.CTkLabel(box, text="Ruta de Antigravity CLI (agy.exe)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(16, 4))
        cli_box = ctk.CTkFrame(box, fg_color="transparent")
        cli_box.pack(fill="x", padx=12, pady=4)

        self.entry_cli_path = ctk.CTkEntry(cli_box, width=450)
        self.entry_cli_path.insert(0, bridge_config.agy_binary_path)
        self.entry_cli_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse_cli = ctk.CTkButton(cli_box, text="Examinar...", width=100, command=self._browse_cli_path)
        btn_browse_cli.pack(side="right")

        # Antigravity Authentication Section
        ctk.CTkLabel(box, text="Cuenta y Autenticación de Antigravity", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(16, 4))
        auth_card = ctk.CTkFrame(box, corner_radius=8, fg_color=("#333333", "#242424"))
        auth_card.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            auth_card,
            text="Antigravity utiliza tu cuenta de Google. Si aún no has iniciado sesión o deseas cambiar de cuenta, haz clic abajo para autenticarte:",
            font=ctk.CTkFont(size=12),
            wraplength=600,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 6))

        btn_auth_action = ctk.CTkButton(
            auth_card,
            text="🔑 Iniciar / Cambiar Sesión de Google Antigravity",
            height=32,
            width=300,
            command=self._launch_login_window
        )
        btn_auth_action.pack(anchor="w", padx=14, pady=(0, 10))

        # Anthropic Claude Agent SDK Section
        ctk.CTkLabel(box, text="Anthropic Claude Agent SDK", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(16, 4))
        anthropic_card = ctk.CTkFrame(box, corner_radius=8, fg_color=("#333333", "#242424"))
        anthropic_card.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            anthropic_card,
            text="API Key de Anthropic para ejecutar los agentes Claude Sonnet 5.5, Opus 5.5, Fable 5.1 y Haiku 4.5:",
            font=ctk.CTkFont(size=12),
            wraplength=600,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        anthropic_input_box = ctk.CTkFrame(anthropic_card, fg_color="transparent")
        anthropic_input_box.pack(fill="x", padx=14, pady=(0, 10))

        self.entry_anthropic_key = ctk.CTkEntry(anthropic_input_box, placeholder_text="sk-ant-api03-...", show="*", width=420)
        if bridge_config.anthropic_api_key:
            self.entry_anthropic_key.insert(0, bridge_config.anthropic_api_key)
        self.entry_anthropic_key.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Opciones de Segundo Plano y Auto-Arranque
        ctk.CTkLabel(box, text="Segundo Plano y Arranque Automático", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(16, 4))
        bg_card = ctk.CTkFrame(box, corner_radius=8, fg_color=("#333333", "#242424"))
        bg_card.pack(fill="x", padx=12, pady=4)

        self.var_auto_start = ctk.BooleanVar(value=bridge_config.auto_start_bridge)
        chk_auto = ctk.CTkCheckBox(
            bg_card,
            text="Activar Bridge automáticamente al abrir la aplicación (Siempre en localhost:8000)",
            variable=self.var_auto_start,
            command=self._save_settings
        )
        chk_auto.pack(anchor="w", padx=14, pady=(10, 6))

        self.var_tray = ctk.BooleanVar(value=bridge_config.minimize_to_tray)
        chk_tray = ctk.CTkCheckBox(
            bg_card,
            text="Mantener el bridge activo en segundo plano al cerrar la ventana (Bandeja del sistema)",
            variable=self.var_tray,
            command=self._save_settings
        )
        chk_tray.pack(anchor="w", padx=14, pady=6)

        self.var_startup = ctk.BooleanVar(value=is_windows_startup_enabled())
        chk_startup = ctk.CTkCheckBox(
            bg_card,
            text="Iniciar automáticamente con Windows al encender el equipo (Servicio 24/7)",
            variable=self.var_startup,
            command=self._on_toggle_startup
        )
        chk_startup.pack(anchor="w", padx=14, pady=(6, 12))

        # Save Button
        btn_save_all = ctk.CTkButton(
            box,
            text="💾 Guardar Cambios de Configuración",
            height=36,
            command=self._save_settings_full
        )
        btn_save_all.pack(anchor="w", padx=12, pady=(24, 10))

    def _launch_login_window(self):
        """Open an interactive console only for the user to login with Antigravity."""
        agy_path = bridge_config.agy_binary_path
        if not agy_path or not os.path.exists(agy_path):
            messagebox.showerror("Error", "No se encontró el ejecutable de Antigravity CLI.")
            return

        cmd = f'start "Inicio de Sesión - Google Antigravity" cmd /k "\"{agy_path}\" && echo. && echo Sesión lista. Puedes cerrar esta ventana. && pause"'
        subprocess.Popen(cmd, shell=True)

    def _browse_cli_path(self):
        f = filedialog.askopenfilename(title="Seleccionar ejecutable agy.exe", filetypes=[("Executable", "*.exe")])
        if f:
            self.entry_cli_path.delete(0, "end")
            self.entry_cli_path.insert(0, f)

    def _on_toggle_startup(self):
        enabled = self.var_startup.get()
        bridge_config.start_with_windows = enabled
        bridge_config.save()
        set_windows_startup(enabled)

    def _auto_start_bridge(self):
        """Auto-activate bridge server upon startup so localhost is always ready."""
        if not server_manager.is_running:
            self.toggle_bridge()

    def _create_tray_icon(self):
        """Create and run the system tray icon for background operation."""
        try:
            import pystray
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((4, 4, 60, 60), fill='#1098ad')
            draw.polygon([(34, 10), (18, 34), (32, 34), (28, 54), (46, 28), (32, 28)], fill='#ffffff')

            menu = pystray.Menu(
                pystray.MenuItem("Abrir Antigravity Bridge", self._restore_from_tray, default=True),
                pystray.MenuItem(lambda text: f"Estado: {'🟢 Activo (8000)' if server_manager.is_running else '🔴 Detenido'}", lambda: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir por Completo", self._quit_app)
            )
            self.tray_icon = pystray.Icon("AntigravityBridge", img, "Antigravity Bridge (Localhost Activo)", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            self.tray_icon = None

    def _on_close_window(self):
        """Minimize to system tray on window close, keeping localhost server alive."""
        if bridge_config.minimize_to_tray and getattr(self, "tray_icon", None):
            self.withdraw()
        else:
            self._quit_app()

    def _restore_from_tray(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self, icon=None, item=None):
        try:
            server_manager.stop()
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(0, self.destroy)

    def _save_settings(self):
        bridge_config.engine_mode = self.var_engine.get()
        if hasattr(self, "var_auto_start"):
            bridge_config.auto_start_bridge = self.var_auto_start.get()
        if hasattr(self, "var_tray"):
            bridge_config.minimize_to_tray = self.var_tray.get()
        bridge_config.save()

    def _save_settings_full(self):
        bridge_config.engine_mode = self.var_engine.get()
        if hasattr(self, "var_auto_start"):
            bridge_config.auto_start_bridge = self.var_auto_start.get()
        if hasattr(self, "var_tray"):
            bridge_config.minimize_to_tray = self.var_tray.get()
        bridge_config.host = self.entry_host.get().strip() or "127.0.0.1"
        try:
            bridge_config.port = int(self.entry_port.get().strip())
        except ValueError:
            bridge_config.port = 8000
        bridge_config.agy_binary_path = self.entry_cli_path.get().strip()
        if hasattr(self, "entry_anthropic_key"):
            bridge_config.anthropic_api_key = self.entry_anthropic_key.get().strip() or None
        bridge_config.save()
        self.lbl_base_url.configure(text=f"http://{bridge_config.host}:{bridge_config.port}/v1")
        messagebox.showinfo("Configuración", "Configuración guardada correctamente.")

    # -------------------------------------------------------------
    # BRIDGE CONTROL
    # -------------------------------------------------------------
    def toggle_bridge(self):
        if server_manager.is_running:
            server_manager.stop()
            self._update_status_ui(False)
        else:
            try:
                server_manager.start(host=bridge_config.host, port=bridge_config.port)
                self._update_status_ui(True)
            except Exception as e:
                messagebox.showerror("Error al iniciar Bridge", f"No se pudo iniciar el servidor:\n{e}")

    def _update_status_ui(self, is_running: bool):
        if is_running:
            self.status_pill.configure(
                text=f"🟢 ACTIVO : {bridge_config.port}",
                text_color=("#38d9a9", "#51cf66"),
                fg_color=("#183d2a", "#1b3323")
            )
            self.btn_toggle_bridge.configure(
                text="⏹ DETENER BRIDGE",
                fg_color=("#dc3545", "#c92a2a"),
                hover_color=("#bd2130", "#a61e1e")
            )
        else:
            self.status_pill.configure(
                text="🔴 DETENIDO",
                text_color=("#ff4444", "#ff6b6b"),
                fg_color=("#3a2020", "#2d1616")
            )
            self.btn_toggle_bridge.configure(
                text="▶ INICIAR BRIDGE",
                fg_color=("#198754", "#28a745"),
                hover_color=("#157347", "#218838")
            )

    def _periodic_update(self):
        """Update metrics and logs regularly."""
        # Update server button state if changed outside
        if server_manager.is_running != (self.btn_toggle_bridge.cget("text") == "⏹ DETENER BRIDGE"):
            self._update_status_ui(server_manager.is_running)

        # Update stats
        self.stat_requests.configure(text=str(metrics.total_requests))
        self.stat_in_tokens.configure(text=str(metrics.total_input_tokens))
        self.stat_out_tokens.configure(text=str(metrics.total_output_tokens))
        self.stat_active.configure(text=str(metrics.active_requests))

        # Update logs view
        if metrics.recent_logs:
            lines = []
            for l in metrics.recent_logs[-30:]:
                line = f"[{l.get('timestamp')}] {l.get('id')} | Model: {l.get('model')} | Status: {l.get('status')} | Duration: {l.get('duration', '...')} | Tokens: {l.get('tokens', '')}"
                lines.append(line)
            content = "\n".join(lines)
            self.txt_logs.delete("1.0", "end")
            self.txt_logs.insert("end", content)
            self.txt_logs.see("end")

        self.after(1000, self._periodic_update)

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _launch_claude_code_terminal(self):
        """Launch Claude Code CLI in a new interactive Windows terminal configured with the Bridge."""
        # Ensure server is running
        if not server_manager.is_running:
            self.toggle_bridge()

        bat_path = Path(__file__).resolve().parent.parent / "Iniciar-ClaudeCode.bat"
        if bat_path.exists():
            subprocess.Popen(f'start "" "{bat_path}"', shell=True)
        else:
            cmd = f'start cmd /k "set ANTHROPIC_BASE_URL=http://{bridge_config.host}:{bridge_config.port} && set ANTHROPIC_API_KEY=sk-antigravity && claude"'
            subprocess.Popen(cmd, shell=True)


def run_gui():
    app = AntigravityBridgeGUI()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
