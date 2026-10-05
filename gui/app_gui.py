"""Modern Centered GUI Application for Model Bridge using CustomTkinter.

Features:
- Focused, centered dashboard with minimal text and modern blue palette.
- Real application logos: Flow logo (Antigravity CLI), Tiger mascot (Claude Code), and Cloud terminal logo (Codex CLI).
- Auto-confirming login flow: launches login and automatically verifies active status, closing the window on completion.
- Models tab structured into 3 distinct places: Antigravity CLI, Claude Code, and Codex CLI.
- Activity tab and counters removed for maximum clarity and speed.
"""

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
from core.auth_status import check_all, login_command, ProviderStatus, find_codex_binary
from server.app import server_manager

try:
    import pystray
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

# Paths & Real App Logos
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
claude_logo_path = ASSETS_DIR / "logo_claude_code.png"
if not claude_logo_path.exists():
    claude_logo_path = ASSETS_DIR / "logo_tiktok_code.png"

PROVIDER_LOGOS = {
    "antigravity": ASSETS_DIR / "logo_flow_antigravity.png",
    "claude": claude_logo_path,
    "codex": ASSETS_DIR / "logo_codex.png",
}

# Modern Blue & Obsidian Theme Palette
PALETTE = {
    "bg": "#090d16",
    "card": "#111827",
    "card_border": "#1e293b",
    "card_active_border": "#3b82f6",
    "header_bg": "#0f172a",
    "accent_blue": "#3b82f6",
    "accent_blue_hover": "#2563eb",
    "accent_cyan": "#38bdf8",
    "accent_green": "#10b981",
    "accent_green_dark": "#064e3b",
    "accent_red": "#ef4444",
    "accent_red_dark": "#451a1a",
    "text_main": "#f8fafc",
    "text_muted": "#94a3b8",
    "text_sub": "#64748b",
}

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def load_provider_icon(key: str, size: tuple = (38, 38)):
    """Load real provider logo as a CTkImage."""
    path = PROVIDER_LOGOS.get(key)
    if path and path.exists():
        try:
            im = Image.open(path)
            return ctk.CTkImage(light_image=im, dark_image=im, size=size)
        except Exception:
            return None
    return None


class LoginSessionModal(ctk.CTkToplevel):
    """Modal dialog during login that auto-detects authentication and closes."""

    def __init__(self, parent, key: str, title: str, on_success_callback=None):
        super().__init__(parent)
        self.key = key
        self.title_text = title
        self.on_success_callback = on_success_callback
        self.active_confirmed = False
        self._is_closed = False

        self.title(f"Iniciar Sesión — {title}")
        self.geometry("450x320")
        self.resizable(False, False)
        self.configure(fg_color=PALETTE["bg"])
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        try:
            px = parent.winfo_rootx() + (parent.winfo_width() // 2) - 225
            py = parent.winfo_rooty() + (parent.winfo_height() // 2) - 160
            self.geometry(f"+{px}+{py}")
        except Exception:
            pass

        content = ctk.CTkFrame(
            self,
            fg_color=PALETTE["card"],
            corner_radius=12,
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        content.pack(fill="both", expand=True, padx=16, pady=16)

        # Provider Logo
        img = load_provider_icon(key, size=(52, 52))
        if img:
            lbl_logo = ctk.CTkLabel(content, image=img, text="")
        else:
            lbl_logo = ctk.CTkLabel(content, text="🔑", font=ctk.CTkFont(size=36))
        lbl_logo.pack(pady=(16, 6))

        # Title
        ctk.CTkLabel(
            content,
            text=f"Autenticando en {title}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["text_main"]
        ).pack(pady=(0, 4))

        # Description
        self.lbl_status = ctk.CTkLabel(
            content,
            text="Se abrió la terminal para iniciar sesión.\nCompleta la autenticación y esta ventana se cerrará sola.",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"],
            justify="center"
        )
        self.lbl_status.pack(pady=(0, 12), padx=20)

        # Badge
        self.badge_status = ctk.CTkLabel(
            content,
            text="⏳ Esperando inicio de sesión...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#f59e0b",
            fg_color="#451a03",
            corner_radius=8,
            padx=14,
            pady=5
        )
        self.badge_status.pack(pady=(0, 14))

        # Button
        self.btn_cancel = ctk.CTkButton(
            content,
            text="Cancelar / Cerrar",
            width=120,
            height=30,
            fg_color=PALETTE["card_border"],
            hover_color="#334155",
            command=self._on_close
        )
        self.btn_cancel.pack(pady=(0, 10))

        # Start poll
        self._start_poll()

    def _start_poll(self):
        def _check():
            if self._is_closed:
                return
            statuses = check_all()
            st = statuses.get(self.key)
            if st and st.active:
                self.after(0, lambda: self._on_confirmed(st))
            else:
                if not self._is_closed:
                    self.after(1100, self._start_poll)

        threading.Thread(target=_check, daemon=True).start()

    def _on_confirmed(self, st):
        if self.active_confirmed or self._is_closed:
            return
        self.active_confirmed = True

        acc = st.account or "Cuenta activa"
        self.badge_status.configure(
            text="✓ ¡SESIÓN CONFIRMADA!",
            text_color="#10b981",
            fg_color="#064e3b"
        )
        self.lbl_status.configure(
            text=f"¡Sesión confirmada exitosamente!\n{acc}\nCerrando ventana automáticamente...",
            text_color="#38bdf8"
        )
        self.btn_cancel.configure(text="✓ Listo")

        if self.on_success_callback:
            try:
                self.on_success_callback(self.key, st)
            except Exception:
                pass

        # Close automatically after 1.5 seconds
        self.after(1500, self._on_close)

    def _on_close(self):
        self._is_closed = True
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass


class ModelBridgeGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Model Bridge — Universal Local AI Gateway")
        self.geometry("980x670")
        self.minsize(920, 620)
        self.configure(fg_color=PALETTE["bg"])

        # Cache live auth status
        self.auth_statuses = {
            "antigravity": ProviderStatus("antigravity"),
            "claude": ProviderStatus("claude"),
            "codex": ProviderStatus("codex"),
        }
        self.checking_auth = False

        # Window closing handling (minimize to tray or quit)
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Layout: Header + 3 Tabviews
        self._build_header()
        self._build_tabs()

        # System tray setup
        self._setup_tray()

        # Initial provider status check
        self._trigger_auth_check()

        # Auto-start bridge if configured
        if bridge_config.auto_start_bridge:
            self.after(500, self._auto_start_bridge)

        # Periodic updates (polling auth and server status every 2.5s)
        self.after(1000, self._periodic_update)

    # -------------------------------------------------------------
    # TOP HEADER
    # -------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=PALETTE["header_bg"],
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        header.pack(fill="x", padx=20, pady=(16, 10))

        # Brand / Title Block
        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.pack(side="left", padx=18, pady=12)

        title_row = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_row.pack(anchor="w")

        lbl_title = ctk.CTkLabel(
            title_row,
            text="⚡ Model Bridge",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=PALETTE["text_main"]
        )
        lbl_title.pack(side="left")

        badge_local = ctk.CTkLabel(
            title_row,
            text="Local Gateway",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#93c5fd",
            fg_color="#1e3a8a",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge_local.pack(side="left", padx=(10, 0))

        lbl_subtitle = ctk.CTkLabel(
            brand_frame,
            text="Pasarela local compatible con Autono, Antigravity CLI, Claude Code y Codex CLI",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"]
        )
        lbl_subtitle.pack(anchor="w", pady=(2, 0))

        # Status & Quick Controls on Header Right
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.pack(side="right", padx=18, pady=12)

        self.status_pill = ctk.CTkLabel(
            right_frame,
            text="🔴 DETENIDO",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["accent_red"],
            fg_color=PALETTE["accent_red_dark"],
            corner_radius=8,
            padx=12,
            pady=5
        )
        self.status_pill.pack(side="left", padx=(0, 12))

        btn_copy_quick = ctk.CTkButton(
            right_frame,
            text="📋 Copiar Endpoint",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=PALETTE["card_border"],
            hover_color="#334155",
            text_color=PALETTE["text_main"],
            height=32,
            width=130,
            corner_radius=8,
            command=lambda: self._copy_to_clipboard(f"http://{bridge_config.host}:{bridge_config.port}/v1")
        )
        btn_copy_quick.pack(side="left")

    # -------------------------------------------------------------
    # TAB NAVIGATION (3 FOCUSED TABS)
    # -------------------------------------------------------------
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=12,
            fg_color=PALETTE["card"],
            border_width=1,
            border_color=PALETTE["card_border"],
            segmented_button_fg_color=PALETTE["bg"],
            segmented_button_selected_color=PALETTE["accent_blue"],
            segmented_button_selected_hover_color=PALETTE["accent_blue_hover"],
            segmented_button_unselected_color=PALETTE["card"],
            segmented_button_unselected_hover_color="#1e293b",
            text_color=PALETTE["text_main"]
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self.tab_dashboard = self.tabview.add("⚡ Principal")
        self.tab_models = self.tabview.add("🧠 Modelos")
        self.tab_settings = self.tabview.add("⚙ Configuración")

        self._build_dashboard_tab()
        self._build_models_tab()
        self._build_settings_tab()

    # -------------------------------------------------------------
    # TAB 1: PRINCIPAL (CENTERED, 3 REAL LOGO PROVIDERS + PLAY)
    # -------------------------------------------------------------
    def _build_dashboard_tab(self):
        container = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=12)

        # 1. CENTERED HERO: PLAY BUTTON & SERVER STATUS
        hero_card = ctk.CTkFrame(
            container,
            corner_radius=12,
            fg_color="#0f172a",
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        hero_card.pack(fill="x", pady=(0, 16), padx=4)

        hero_content = ctk.CTkFrame(hero_card, fg_color="transparent")
        hero_content.pack(pady=22, padx=20)

        # Large Centered Play / Stop Button
        self.btn_play_bridge = ctk.CTkButton(
            hero_content,
            text="▶  INICIAR BRIDGE",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            height=48,
            width=260,
            corner_radius=10,
            command=self.toggle_bridge
        )
        self.btn_play_bridge.pack(pady=(0, 10))

        # Dynamic Endpoint & Key helper
        self.lbl_hero_endpoint = ctk.CTkLabel(
            hero_content,
            text=f"http://{bridge_config.host}:{bridge_config.port}/v1  •  API Key: sk-antigravity",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=PALETTE["accent_cyan"]
        )
        self.lbl_hero_endpoint.pack()

        # 2. CENTERED SECTION: THE 3 PROVIDERS
        section_lbl = ctk.CTkLabel(
            container,
            text="Proveedores y Sesiones Activas",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["text_main"]
        )
        section_lbl.pack(anchor="w", padx=8, pady=(4, 8))

        # 3 Balanced Provider Columns
        providers_row = ctk.CTkFrame(container, fg_color="transparent")
        providers_row.pack(fill="x", padx=4, pady=(0, 10))
        providers_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="prov_col")

        # Card 1: Antigravity CLI (Flow Logo)
        self.card_antigravity = self._create_provider_card(
            providers_row,
            col=0,
            key="antigravity",
            title="Antigravity CLI",
            subtitle="Google Antigravity & Flow",
            login_hint="Inicia sesión con tu cuenta de Google"
        )

        # Card 2: Claude Code (Tiger Mascot Logo)
        self.card_claude = self._create_provider_card(
            providers_row,
            col=1,
            key="claude",
            title="Claude Code",
            subtitle="Anthropic Claude Code CLI",
            login_hint="Inicia sesión con tu cuenta de Anthropic"
        )

        # Card 3: Codex CLI (Codex Cloud Logo)
        self.card_codex = self._create_provider_card(
            providers_row,
            col=2,
            key="codex",
            title="Codex CLI",
            subtitle="OpenAI ChatGPT & Codex CLI",
            login_hint="Inicia sesión con OpenAI o tu API key"
        )

    def _create_provider_card(self, parent, col, key, title, subtitle, login_hint):
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color="#0f172a",
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        # Logo + Title Header
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 8))

        # Real App Logo
        icon_img = load_provider_icon(key, size=(38, 38))
        if icon_img:
            icon_lbl = ctk.CTkLabel(top_row, image=icon_img, text="")
        else:
            icon_lbl = ctk.CTkLabel(top_row, text="⚡", font=ctk.CTkFont(size=22))
        icon_lbl.pack(side="left", padx=(0, 12))

        title_box = ctk.CTkFrame(top_row, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_box,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["text_main"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color=PALETTE["text_muted"]
        ).pack(anchor="w")

        # Status Pill (Activated vs Not Connected)
        badge_status = ctk.CTkLabel(
            inner,
            text="⚪ No detectado",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            corner_radius=6,
            padx=10,
            pady=4
        )
        badge_status.pack(anchor="w", pady=(4, 6))

        # Account / Detail Label (Email or hint)
        lbl_account = ctk.CTkLabel(
            inner,
            text=login_hint,
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_sub"],
            wraplength=230,
            justify="left"
        )
        lbl_account.pack(anchor="w", pady=(0, 14))

        # Bottom Action Button
        btn_action = ctk.CTkButton(
            inner,
            text="🔑 Iniciar Sesión",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            height=34,
            corner_radius=8,
            command=lambda k=key, t=title: self._on_provider_action_click(k, t)
        )
        btn_action.pack(fill="x", pady=(4, 0))

        # Store references for dynamic updates
        setattr(self, f"ui_card_{key}", card)
        setattr(self, f"ui_badge_{key}", badge_status)
        setattr(self, f"ui_acc_{key}", lbl_account)
        setattr(self, f"ui_btn_{key}", btn_action)
        setattr(self, f"ui_icon_{key}", icon_lbl)
        return card

    # -------------------------------------------------------------
    # PROVIDER AUTH LOGIC & DYNAMIC STATUS
    # -------------------------------------------------------------
    def _trigger_auth_check(self):
        """Run non-blocking check of the 3 providers."""
        if self.checking_auth:
            return
        self.checking_auth = True

        def _worker():
            try:
                res = check_all()
                self.after(0, lambda: self._apply_auth_status(res))
            except Exception:
                pass
            finally:
                self.checking_auth = False

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_auth_status(self, statuses: dict):
        """Update provider cards visually to 'Activated' with bright styling."""
        self.auth_statuses = statuses

        for key, st in statuses.items():
            card = getattr(self, f"ui_card_{key}", None)
            badge = getattr(self, f"ui_badge_{key}", None)
            lbl_acc = getattr(self, f"ui_acc_{key}", None)
            btn = getattr(self, f"ui_btn_{key}", None)

            if not card or not badge or not btn:
                continue

            if st.active:
                # ─── ACTIVATED STATE ───
                card.configure(border_color=PALETTE["card_active_border"])
                badge.configure(
                    text="● ACTIVATED",
                    text_color="#10b981",
                    fg_color="#064e3b"
                )
                acc_display = st.account or "Sesión verificada"
                if len(acc_display) > 28:
                    acc_display = acc_display[:25] + "..."
                lbl_acc.configure(text=f"Cuenta: {acc_display}", text_color="#38bdf8")

                if key == "claude":
                    btn.configure(
                        text="💻 Abrir Terminal",
                        fg_color="#4f46e5",
                        hover_color="#4338ca"
                    )
                else:
                    btn.configure(
                        text="💻 Terminal CLI",
                        fg_color="#334155",
                        hover_color="#475569"
                    )
            elif st.installed:
                # Installed but not logged in
                card.configure(border_color=PALETTE["card_border"])
                badge.configure(
                    text="○ No iniciado",
                    text_color="#f59e0b",
                    fg_color="#451a03"
                )
                lbl_acc.configure(text="CLI detectada. Requiere iniciar sesión.", text_color=PALETTE["text_muted"])
                btn.configure(
                    text="🔑 Iniciar Sesión",
                    fg_color=PALETTE["accent_blue"],
                    hover_color=PALETTE["accent_blue_hover"]
                )
            else:
                # Not installed or not detected
                card.configure(border_color=PALETTE["card_border"])
                badge.configure(
                    text="○ No detectado",
                    text_color="#94a3b8",
                    fg_color="#1e293b"
                )
                lbl_acc.configure(text="Ejecutable no encontrado en PATH", text_color=PALETTE["text_sub"])
                btn.configure(
                    text="🔑 Iniciar Sesión",
                    fg_color=PALETTE["accent_blue"],
                    hover_color=PALETTE["accent_blue_hover"]
                )

        # Refresh model cards status in Models tab
        self._refresh_models_badges()

    def _on_provider_action_click(self, key: str, title: str):
        st = self.auth_statuses.get(key)
        if st and st.active:
            # If already activated, launch terminal directly
            if key == "claude":
                self._launch_claude_code_terminal()
            elif key == "antigravity":
                agy_path = bridge_config.agy_binary_path or "agy"
                cmd = f'start "Antigravity CLI Terminal" cmd /k "\"{agy_path}\""'
                subprocess.Popen(cmd, shell=True)
            elif key == "codex":
                codex_exe = find_codex_binary() or "codex"
                cmd = f'start "Codex CLI Terminal" cmd /k "\"{codex_exe}\""'
                subprocess.Popen(cmd, shell=True)
            return

        # Not logged in: launch login flow and modal
        cmd = login_command(key)
        if not cmd:
            if key == "antigravity":
                messagebox.showerror("Error", "No se encontró el ejecutable de Antigravity CLI (agy.exe). Configura la ruta en Configuración.")
            else:
                messagebox.showerror("Error", f"No se encontró el ejecutable para {title}. Instálalo o agrégalo a tu PATH.")
            return

        # Launch login process in terminal (which auto-closes via cmd /c upon completion)
        subprocess.Popen(cmd, shell=True)

        # Open in-app auto-confirming modal
        LoginSessionModal(
            self,
            key=key,
            title=title,
            on_success_callback=lambda k, s: self._trigger_auth_check()
        )

    # -------------------------------------------------------------
    # TAB 2: MODELOS (TRES LUGARES: ANTIGRAVITY, CLAUDE CODE, CODEX)
    # -------------------------------------------------------------
    def _build_models_tab(self):
        container = ctk.CTkFrame(self.tab_models, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=12)

        # Top Bar with Default Model Selector
        top_bar = ctk.CTkFrame(
            container,
            corner_radius=10,
            fg_color="#0f172a",
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        top_bar.pack(fill="x", pady=(0, 12))

        bar_inner = ctk.CTkFrame(top_bar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            bar_inner,
            text="Modelo por Defecto:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text_main"]
        ).pack(side="left", padx=(0, 10))

        models_list = [m["id"] for m in model_registry.get_models()]
        self.model_dropdown = ctk.CTkComboBox(
            bar_inner,
            values=models_list,
            width=280,
            fg_color="#1e293b",
            border_color="#334155",
            command=self._on_model_selected
        )
        self.model_dropdown.set(bridge_config.default_model)
        self.model_dropdown.pack(side="left", padx=(0, 14))

        self.lbl_model_status = ctk.CTkLabel(
            bar_inner,
            text=f"✓ Activo: {bridge_config.default_model}",
            text_color="#10b981",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_model_status.pack(side="left")

        btn_refresh = ctk.CTkButton(
            bar_inner,
            text="🔄 Actualizar",
            width=110,
            height=30,
            fg_color=PALETTE["card_border"],
            hover_color="#334155",
            command=self._refresh_models_list
        )
        btn_refresh.pack(side="right")

        # Scrollable container containing the 3 Distinct Places
        self.models_scroll = ctk.CTkScrollableFrame(
            container,
            corner_radius=10,
            fg_color="#0f172a",
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        self.models_scroll.pack(fill="both", expand=True)

        self._populate_three_model_places()

    def _populate_three_model_places(self):
        for widget in self.models_scroll.winfo_children():
            widget.destroy()

        all_models = model_registry.get_models()

        # Group models into 3 places
        places = [
            {
                "key": "antigravity",
                "title": "Antigravity CLI (Flow)",
                "subtitle": "Google Gemini 3.8 / 3.7 / 3.6 Flash & Pro",
                "filter": lambda m: m["id"].startswith("gemini-")
            },
            {
                "key": "claude",
                "title": "Claude Code",
                "subtitle": "Anthropic Claude Sonnet & Opus Thinking",
                "filter": lambda m: m["id"].startswith("claude-")
            },
            {
                "key": "codex",
                "title": "Codex CLI",
                "subtitle": "OpenAI GPT-OSS 120B, GPT-4o & Codex Models",
                "filter": lambda m: not m["id"].startswith("gemini-") and not m["id"].startswith("claude-")
            }
        ]

        self.model_row_widgets = {}

        for p in places:
            group_models = [m for m in all_models if p["filter"](m)]

            # Section Container Card
            place_frame = ctk.CTkFrame(
                self.models_scroll,
                corner_radius=10,
                fg_color="#111827",
                border_width=1,
                border_color=PALETTE["card_border"]
            )
            place_frame.pack(fill="x", padx=6, pady=8)

            # Section Header
            hdr = ctk.CTkFrame(place_frame, fg_color="transparent")
            hdr.pack(fill="x", padx=14, pady=10)

            # Real App Logo in Header
            p_img = load_provider_icon(p["key"], size=(30, 30))
            if p_img:
                ctk.CTkLabel(hdr, image=p_img, text="").pack(side="left", padx=(0, 10))

            tbox = ctk.CTkFrame(hdr, fg_color="transparent")
            tbox.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                tbox,
                text=p["title"],
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=PALETTE["text_main"]
            ).pack(anchor="w")

            ctk.CTkLabel(
                tbox,
                text=p["subtitle"],
                font=ctk.CTkFont(size=11),
                text_color=PALETTE["text_muted"]
            ).pack(anchor="w")

            # Provider Status Badge in Header
            st = self.auth_statuses.get(p["key"])
            is_active = st and st.active
            status_lbl = ctk.CTkLabel(
                hdr,
                text="● ACTIVATED" if is_active else "○ Inactivo",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#10b981" if is_active else "#94a3b8",
                fg_color="#064e3b" if is_active else "#1e293b",
                corner_radius=6,
                padx=10,
                pady=4
            )
            status_lbl.pack(side="right", padx=(0, 6))

            count_badge = ctk.CTkLabel(
                hdr,
                text=f"{len(group_models)} modelos",
                font=ctk.CTkFont(size=11),
                text_color="#93c5fd",
                fg_color="#1e3a8a",
                corner_radius=6,
                padx=8,
                pady=4
            )
            count_badge.pack(side="right", padx=(0, 8))

            # Store for dynamic update
            setattr(self, f"ui_place_badge_{p['key']}", status_lbl)

            # Models rows
            models_container = ctk.CTkFrame(place_frame, fg_color="transparent")
            models_container.pack(fill="x", padx=12, pady=(0, 10))

            for m in group_models:
                m_row = ctk.CTkFrame(
                    models_container,
                    corner_radius=8,
                    fg_color="#1e293b",
                    border_width=1,
                    border_color="#334155"
                )
                m_row.pack(fill="x", padx=2, pady=3)

                m_name_box = ctk.CTkFrame(m_row, fg_color="transparent")
                m_name_box.pack(side="left", padx=12, pady=6)

                ctk.CTkLabel(
                    m_name_box,
                    text=m["name"],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=PALETTE["text_main"]
                ).pack(anchor="w")

                ctk.CTkLabel(
                    m_name_box,
                    text=f"ID: {m['id']}",
                    font=ctk.CTkFont(family="Consolas", size=10),
                    text_color=PALETTE["text_muted"]
                ).pack(anchor="w")

                # Action button / badge
                action_box = ctk.CTkFrame(m_row, fg_color="transparent")
                action_box.pack(side="right", padx=10)

                self.model_row_widgets[m["id"]] = action_box
                self._render_model_action_widget(m["id"])

    def _render_model_action_widget(self, model_id: str):
        box = self.model_row_widgets.get(model_id)
        if not box:
            return
        for w in box.winfo_children():
            w.destroy()

        if bridge_config.default_model == model_id:
            ctk.CTkLabel(
                box,
                text="✓ Activo por Defecto",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#10b981",
                fg_color="#064e3b",
                corner_radius=6,
                padx=10,
                pady=4
            ).pack()
        else:
            ctk.CTkButton(
                box,
                text="Usar por Defecto",
                width=120,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color=PALETTE["accent_blue"],
                hover_color=PALETTE["accent_blue_hover"],
                command=lambda mid=model_id: self._set_default_model(mid)
            ).pack()

    def _refresh_models_badges(self):
        for key in ("antigravity", "claude", "codex"):
            badge = getattr(self, f"ui_place_badge_{key}", None)
            st = self.auth_statuses.get(key)
            if badge and st:
                is_active = st.active
                badge.configure(
                    text="● ACTIVATED" if is_active else "○ Inactivo",
                    text_color="#10b981" if is_active else "#94a3b8",
                    fg_color="#064e3b" if is_active else "#1e293b"
                )

    def _on_model_selected(self, chosen_model):
        self._set_default_model(chosen_model)

    def _set_default_model(self, model_id):
        bridge_config.default_model = model_id
        bridge_config.save()
        if hasattr(self, "model_dropdown"):
            self.model_dropdown.set(model_id)
        if hasattr(self, "lbl_model_status"):
            self.lbl_model_status.configure(text=f"✓ Modelo activo: {model_id}")

        # Update all action buttons in the 3 places
        for mid in list(getattr(self, "model_row_widgets", {}).keys()):
            self._render_model_action_widget(mid)

    def _refresh_models_list(self):
        models = model_registry.refresh_models()
        m_ids = [m["id"] for m in models]
        if hasattr(self, "model_dropdown"):
            self.model_dropdown.configure(values=m_ids)
        self._populate_three_model_places()
        messagebox.showinfo("Modelos", f"Se actualizaron {len(models)} modelos en los 3 proveedores.")

    # -------------------------------------------------------------
    # TAB 3: CONFIGURACIÓN
    # -------------------------------------------------------------
    def _build_settings_tab(self):
        scroll = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=12)

        # Card 1: Red y Puerto Local
        c1 = self._create_settings_card(scroll, "🌐 Red y Puerto Local")

        desc_lbl = ctk.CTkLabel(
            c1,
            text="Configura el Host y Puerto de escucha local de Model Bridge. Puedes cambiar el puerto si otro servicio lo está usando en tu equipo (ej. 8765, 8888, 9000, 9090).",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"],
            wraplength=620,
            justify="left"
        )
        desc_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        net_row = ctk.CTkFrame(c1, fg_color="transparent")
        net_row.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkLabel(net_row, text="Host:", text_color=PALETTE["text_main"], font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_host = ctk.CTkEntry(net_row, width=125, fg_color="#1e293b", border_color="#334155")
        self.entry_host.insert(0, bridge_config.host)
        self.entry_host.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(net_row, text="Puerto:", text_color=PALETTE["text_main"], font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_port = ctk.CTkEntry(net_row, width=85, fg_color="#1e293b", border_color="#334155")
        self.entry_port.insert(0, str(bridge_config.port))
        self.entry_port.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(net_row, text="Presets:", text_color=PALETTE["text_muted"], font=ctk.CTkFont(size=11)).pack(side="left", padx=(6, 4))
        for p in [8765, 8888, 9000, 9090]:
            btn_p = ctk.CTkButton(
                net_row,
                text=str(p),
                width=46,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#1e293b",
                hover_color="#334155",
                command=lambda port_val=p: self._set_port_preset(port_val)
            )
            btn_p.pack(side="left", padx=2)

        # Card 2: Rutas de Ejecutables
        c2 = self._create_settings_card(scroll, "⚡ Ruta de Antigravity CLI (agy.exe)")
        cli_row = ctk.CTkFrame(c2, fg_color="transparent")
        cli_row.pack(fill="x", padx=16, pady=(10, 14))

        self.entry_cli_path = ctk.CTkEntry(cli_row, fg_color="#1e293b", border_color="#334155")
        self.entry_cli_path.insert(0, bridge_config.agy_binary_path or "")
        self.entry_cli_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_browse_cli = ctk.CTkButton(
            cli_row,
            text="Examinar...",
            width=100,
            fg_color="#334155",
            hover_color="#475569",
            command=self._browse_cli_path
        )
        btn_browse_cli.pack(side="right")

        # Card 3: Claves de API Opcionales
        c3 = self._create_settings_card(scroll, "🔑 Claves de API para Modo Nube (Opcional)")
        api_inner = ctk.CTkFrame(c3, fg_color="transparent")
        api_inner.pack(fill="x", padx=16, pady=(10, 14))

        # Anthropic
        ctk.CTkLabel(api_inner, text="Anthropic API Key:", text_color=PALETTE["text_muted"]).pack(anchor="w", pady=(0, 2))
        self.entry_anthropic_key = ctk.CTkEntry(api_inner, placeholder_text="sk-ant-api03-...", show="*", fg_color="#1e293b", border_color="#334155")
        if bridge_config.anthropic_api_key:
            self.entry_anthropic_key.insert(0, bridge_config.anthropic_api_key)
        self.entry_anthropic_key.pack(fill="x", pady=(0, 10))

        # OpenAI
        ctk.CTkLabel(api_inner, text="OpenAI API Key:", text_color=PALETTE["text_muted"]).pack(anchor="w", pady=(0, 2))
        self.entry_openai_key = ctk.CTkEntry(api_inner, placeholder_text="sk-proj-...", show="*", fg_color="#1e293b", border_color="#334155")
        if getattr(bridge_config, "openai_api_key", None):
            self.entry_openai_key.insert(0, bridge_config.openai_api_key)
        self.entry_openai_key.pack(fill="x", pady=(0, 10))

        # Gemini
        ctk.CTkLabel(api_inner, text="Google Gemini API Key:", text_color=PALETTE["text_muted"]).pack(anchor="w", pady=(0, 2))
        self.entry_gemini_key = ctk.CTkEntry(api_inner, placeholder_text="AIzaSy...", show="*", fg_color="#1e293b", border_color="#334155")
        if bridge_config.gemini_api_key:
            self.entry_gemini_key.insert(0, bridge_config.gemini_api_key)
        self.entry_gemini_key.pack(fill="x")

        # Card 4: Sistema y Segundo Plano
        c4 = self._create_settings_card(scroll, "🖥️ Segundo Plano y Sistema")
        sys_inner = ctk.CTkFrame(c4, fg_color="transparent")
        sys_inner.pack(fill="x", padx=16, pady=(10, 14))

        self.var_auto_start = ctk.BooleanVar(value=bridge_config.auto_start_bridge)
        ctk.CTkCheckBox(
            sys_inner,
            text="Iniciar Bridge automáticamente al abrir la aplicación",
            variable=self.var_auto_start,
            text_color=PALETTE["text_main"],
            fg_color=PALETTE["accent_blue"]
        ).pack(anchor="w", pady=4)

        self.var_tray = ctk.BooleanVar(value=bridge_config.minimize_to_tray)
        ctk.CTkCheckBox(
            sys_inner,
            text="Minimizar a la bandeja del sistema al cerrar",
            variable=self.var_tray,
            text_color=PALETTE["text_main"],
            fg_color=PALETTE["accent_blue"]
        ).pack(anchor="w", pady=4)

        self.var_startup = ctk.BooleanVar(value=is_windows_startup_enabled())
        ctk.CTkCheckBox(
            sys_inner,
            text="Iniciar con Windows al encender el equipo (24/7)",
            variable=self.var_startup,
            text_color=PALETTE["text_main"],
            fg_color=PALETTE["accent_blue"],
            command=self._on_toggle_startup
        ).pack(anchor="w", pady=4)

        # Save Button
        btn_save = ctk.CTkButton(
            scroll,
            text="💾  Guardar Configuración",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PALETTE["accent_blue"],
            hover_color=PALETTE["accent_blue_hover"],
            height=42,
            corner_radius=8,
            command=self._save_settings_full
        )
        btn_save.pack(anchor="w", padx=4, pady=(16, 20))

    def _create_settings_card(self, parent, title):
        card = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color="#0f172a",
            border_width=1,
            border_color=PALETTE["card_border"]
        )
        card.pack(fill="x", padx=4, pady=6)

        header = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text_main"]
        )
        header.pack(anchor="w", padx=16, pady=(12, 4))
        return card

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

    def _set_port_preset(self, port_val: int):
        self.entry_port.delete(0, "end")
        self.entry_port.insert(0, str(port_val))

    def _save_settings_full(self):
        try:
            new_host = self.entry_host.get().strip() or "127.0.0.1"
            new_port_str = self.entry_port.get().strip() or "8765"
            try:
                new_port = int(new_port_str)
                if not (1 <= new_port <= 65535):
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", "El puerto debe ser un número entero entre 1 y 65535.")
                return

            host_or_port_changed = (new_host != bridge_config.host or new_port != bridge_config.port)
            bridge_config.host = new_host
            bridge_config.port = new_port
            bridge_config.agy_binary_path = self.entry_cli_path.get().strip()
            bridge_config.anthropic_api_key = self.entry_anthropic_key.get().strip()
            if hasattr(self, "entry_openai_key"):
                bridge_config.openai_api_key = self.entry_openai_key.get().strip()
            if hasattr(self, "entry_gemini_key"):
                bridge_config.gemini_api_key = self.entry_gemini_key.get().strip()
            bridge_config.auto_start_bridge = self.var_auto_start.get()
            bridge_config.minimize_to_tray = self.var_tray.get()
            bridge_config.save()

            self.lbl_hero_endpoint.configure(
                text=f"http://{bridge_config.host}:{bridge_config.port}/v1  •  API Key: sk-antigravity"
            )

            # If server is running and host/port changed, smoothly restart on new host/port
            if server_manager.is_running and host_or_port_changed:
                server_manager.restart(host=bridge_config.host, port=bridge_config.port, log_level=bridge_config.log_level)
                self._update_status_ui(True)
                messagebox.showinfo("Configuración", f"✓ Configuración guardada y servidor actualizado en http://{bridge_config.host}:{bridge_config.port}")
            else:
                messagebox.showinfo("Configuración", "✓ Configuración guardada correctamente.")

            self._trigger_auth_check()
        except ValueError:
            messagebox.showerror("Error", "El puerto debe ser un número entero válido.")
        except Exception as e:
            messagebox.showerror("Error", f"Error al guardar configuración: {e}")

    # -------------------------------------------------------------
    # BRIDGE RUNTIME CONTROL (PLAY / STOP)
    # -------------------------------------------------------------
    def toggle_bridge(self):
        if server_manager.is_running:
            server_manager.stop()
            self._update_status_ui(False)
        else:
            try:
                server_manager.start(
                    host=bridge_config.host,
                    port=bridge_config.port,
                    log_level=bridge_config.log_level
                )
                self._update_status_ui(True)
            except Exception as e:
                messagebox.showerror("Error al iniciar Bridge", str(e))
                self._update_status_ui(False)

    def _auto_start_bridge(self):
        if not server_manager.is_running:
            self.toggle_bridge()

    def _update_status_ui(self, is_running: bool):
        if is_running:
            self.status_pill.configure(
                text=f"🟢 ONLINE :{bridge_config.port}",
                text_color=PALETTE["accent_green"],
                fg_color=PALETTE["accent_green_dark"]
            )
            self.btn_play_bridge.configure(
                text="⏹  DETENER BRIDGE",
                fg_color=PALETTE["accent_red"],
                hover_color="#b91c1c"
            )
        else:
            self.status_pill.configure(
                text="🔴 DETENIDO",
                text_color=PALETTE["accent_red"],
                fg_color=PALETTE["accent_red_dark"]
            )
            self.btn_play_bridge.configure(
                text="▶  INICIAR BRIDGE",
                fg_color=PALETTE["accent_blue"],
                hover_color=PALETTE["accent_blue_hover"]
            )

    def _periodic_update(self):
        # Sync server running state
        if server_manager.is_running != (self.btn_play_bridge.cget("text").startswith("⏹")):
            self._update_status_ui(server_manager.is_running)

        # Periodically re-check auth status (every ~2.5s)
        self._trigger_auth_check()

        self.after(2500, self._periodic_update)

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _launch_claude_code_terminal(self):
        if not server_manager.is_running:
            self.toggle_bridge()

        bat_path = Path(__file__).resolve().parent.parent / "Iniciar-ClaudeCode.bat"
        if bat_path.exists():
            subprocess.Popen(f'start "" "{bat_path}"', shell=True)
        else:
            cmd = f'start cmd /k "set ANTHROPIC_BASE_URL=http://{bridge_config.host}:{bridge_config.port} && set ANTHROPIC_API_KEY=sk-antigravity && claude"'
            subprocess.Popen(cmd, shell=True)

    # -------------------------------------------------------------
    # SYSTEM TRAY
    # -------------------------------------------------------------
    def _setup_tray(self):
        self.tray_icon = None
        if not PYSTRAY_AVAILABLE:
            return

        def _create_image():
            img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((8, 8, 56, 56), fill="#2563eb")
            draw.polygon([(26, 16), (44, 32), (26, 48)], fill="white")
            return img

        menu = pystray.Menu(
            pystray.MenuItem("Abrir Model Bridge", self._show_from_tray, default=True),
            pystray.MenuItem(lambda text: f"Estado: {'🟢 Activo' if server_manager.is_running else '🔴 Detenido'}", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Iniciar / Detener Bridge", self._tray_toggle_bridge),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir por Completo", self._tray_quit)
        )
        self.tray_icon = pystray.Icon("model_bridge", _create_image(), "Model Bridge", menu)

    def _show_from_tray(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_toggle_bridge(self, icon=None, item=None):
        self.after(0, self.toggle_bridge)

    def _tray_quit(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self._force_quit)

    def _on_close_window(self):
        if bridge_config.minimize_to_tray and PYSTRAY_AVAILABLE:
            self.withdraw()
            if self.tray_icon and not self.tray_icon.visible:
                threading.Thread(target=self.tray_icon.run, daemon=True).start()
        else:
            self._force_quit()

    def _force_quit(self):
        if server_manager.is_running:
            server_manager.stop()
        self.destroy()
        sys.exit(0)


def run_gui():
    app = ModelBridgeGUI()
    app.mainloop()


def main():
    run_gui()


if __name__ == "__main__":
    main()
