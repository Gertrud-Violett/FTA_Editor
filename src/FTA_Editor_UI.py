"""
FTA Editor UI Layer
Copyright (c) makkiblog.com - BSD-2 License

This module contains the UI components for the FTA Editor:
- Tkinter-based graphical interface
- Tree visualization
- Diagram preview
- Node editing dialogs
- AI Agent chat interface
- Multi-provider AI support (OpenAI, Claude, Gemini)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import subprocess
import sys
import tempfile
from pathlib import Path
import json
import threading
import re

from FTA_Editor_core import FTACore, sanitize_name
from AI_agent_handler import AIAgentHandler, AICredentialManager, test_connection, AIProposedChange
from ai_providers import AIProviderFactory


# UI 字体常量（微软雅黑，Windows 自带，可正常显示中文）
UI_FONT = "Microsoft YaHei"


class FTAEditorUI:
    """UI layer for FTA Editor application"""
    
    def __init__(self, root):
        """Initialize the UI components"""
        self.root = root
        self.root.title("FTA/ETA 事故树编辑器")
        
        # Initialize core logic
        self.core = FTACore()
        
        # Initialize AI agent
        self.ai_agent = AIAgentHandler()
        self.ai_processing = False  # Track if AI is processing
        
        # UI state
        self.preview_image = None
        self.preview_img_id = None
        self.preview_original_img = None
        self.preview_scale = 1.0
        self.has_unsaved_changes = False  # Track unsaved changes
        
        # Build UI
        self._build_ui()
        
        # Initialize tree with root node
        self._initialize_tree()
        
        # Bind keyboard shortcuts
        self._bind_shortcuts()
        
        # Initial preview update
        self.update_preview()
    
    def _build_ui(self):
        """Build the main UI layout"""
        # Build top bar with metadata fields
        self._build_top_bar()
        
        # Main horizontal paned window (left: tree+diagram+details, right: AI chat)
        main_horizontal_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_horizontal_paned.pack(fill=tk.BOTH, expand=True)
        
        # Left section container
        left_container = tk.Frame(main_horizontal_paned)
        main_horizontal_paned.add(left_container, stretch="always", minsize=600)
        
        # Main vertical paned window (top: tree+diagram, bottom: details+buttons)
        main_vertical_paned = tk.PanedWindow(left_container, orient=tk.VERTICAL)
        main_vertical_paned.pack(fill=tk.BOTH, expand=True)
        
        # Top section: horizontal paned (tree | diagram)
        top_paned = tk.PanedWindow(main_vertical_paned, orient=tk.HORIZONTAL)
        main_vertical_paned.add(top_paned, stretch="always")
        
        # Build left panel (tree)
        self._build_tree_panel(top_paned)
        
        # Build right panel (diagram preview)
        self._build_diagram_panel(top_paned)
        
        # Build bottom panel (details)
        self._build_details_panel(main_vertical_paned)
        
        # Build AI chat panel (right side)
        self._build_ai_chat_panel(main_horizontal_paned)
        
        # Build button bar
        self._build_button_bar()
    
    def _build_top_bar(self):
        """Build the top bar with mode selector, title, and date"""
        top_frame = tk.Frame(self.root, relief=tk.RAISED, borderwidth=2, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        # Mode selector
        tk.Label(top_frame, text="模式:", font=(UI_FONT, 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.mode_var = tk.StringVar(value=self.core.mode)
        mode_combo = ttk.Combobox(top_frame, textvariable=self.mode_var, 
                                  values=["FTA", "ETA"], state="readonly", width=10)
        mode_combo.pack(side=tk.LEFT, padx=(0, 20))
        mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
        
        # Title field
        tk.Label(top_frame, text="标题:", font=(UI_FONT, 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.title_var = tk.StringVar(value=self.core.title)
        title_entry = tk.Entry(top_frame, textvariable=self.title_var, width=30, font=(UI_FONT, 10))
        title_entry.pack(side=tk.LEFT, padx=(0, 20))
        title_entry.bind("<FocusOut>", self._on_title_changed)
        title_entry.bind("<Return>", self._on_title_changed)
        
        # Date field
        tk.Label(top_frame, text="日期:", font=(UI_FONT, 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.date_var = tk.StringVar(value=self.core.date)
        date_entry = tk.Entry(top_frame, textvariable=self.date_var, width=15, font=(UI_FONT, 10))
        date_entry.pack(side=tk.LEFT, padx=(0, 20))
        date_entry.bind("<FocusOut>", self._on_date_changed)
        date_entry.bind("<Return>", self._on_date_changed)
        
        # Hide zero probability nodes option
        self.hide_zero_var = tk.BooleanVar(value=False)
        hide_zero_cb = tk.Checkbutton(top_frame, text="隐藏零概率节点", variable=self.hide_zero_var, 
                                      bg="#f0f0f0", command=self._on_hide_zero_changed)
        hide_zero_cb.pack(side=tk.LEFT, padx=(10, 10))
    
    def _on_mode_changed(self, event=None):
        """Handle mode change"""
        new_mode = self.mode_var.get()
        self.core.set_metadata(mode=new_mode)
        self.core.recalculate_probabilities()
        self._apply_zero_marks()
        self.update_preview()
        self._mark_as_changed()
        # Update tree label
        label_text = "事件树" if new_mode == "ETA" else "故障树"
        for widget in self.fta_tree.master.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(text=label_text)
                break
    
    def _on_title_changed(self, event=None):
        """Handle title change"""
        self.core.set_metadata(title=self.title_var.get())
        self._mark_as_changed()
    
    def _on_date_changed(self, event=None):
        """Handle date change"""
        self.core.set_metadata(date=self.date_var.get())
        self._mark_as_changed()
    
    def _on_hide_zero_changed(self):
        """Handle hide zero probability nodes option change"""
        self.update_preview()
        # Note: This doesn't mark as changed since it's just a display option
    
    def _build_tree_panel(self, parent):
        """Build the fault tree panel"""
        tree_frame = tk.Frame(parent, relief=tk.SUNKEN, borderwidth=2)
        parent.add(tree_frame, stretch="always")
        
        tk.Label(tree_frame, text="故障树", font=(UI_FONT, 12, "bold")).pack(pady=5)
        
        self.fta_tree = ttk.Treeview(tree_frame, columns=("mark",), show="tree headings")
        self.fta_tree.heading("mark", text="")
        self.fta_tree.column("mark", width=20, anchor="center", stretch=False)
        self.fta_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.fta_tree.bind("<<TreeviewSelect>>", self.show_selected_details)
        
        # Configure visual tags - support arbitrary depths
        colors = ["#d0f0e0", "#ffe4b5", "#e6e6fa", "#c8d6e5", "#f5f5dc", "#e0ffff", "#ffe4e1", "#f0f8ff"]
        for i in range(20):  # Support up to 20 levels
            color = colors[i % len(colors)]
            self.fta_tree.tag_configure(f"level{i}", background=color)
        
        base_font = tkfont.nametofont("TkDefaultFont")
        marked_font = tkfont.Font(
            root=self.root,
            family=base_font.actual("family"),
            size=base_font.actual("size") + 1,
            weight="bold"
        )
        
        # Blue highlight for zero probability nodes
        self.fta_tree.tag_configure("zero_prob", foreground="blue")
        
        # Bold red highlight for probability 1.0 nodes
        self.fta_tree.tag_configure("full_prob", foreground="red", font=marked_font)
    
    def _build_diagram_panel(self, parent):
        """Build the live diagram preview panel"""
        diagram_frame = tk.Frame(parent, relief=tk.SUNKEN, borderwidth=2)
        parent.add(diagram_frame, stretch="always")
        
        tk.Label(diagram_frame, text="实时图形预览", font=(UI_FONT, 12, "bold")).pack(pady=5)
        
        canvas_frame = tk.Frame(diagram_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        v_scroll = tk.Scrollbar(canvas_frame)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.preview_canvas = tk.Canvas(
            canvas_frame,
            xscrollcommand=h_scroll.set,
            yscrollcommand=v_scroll.set,
            bg="white"
        )
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        h_scroll.config(command=self.preview_canvas.xview)
        v_scroll.config(command=self.preview_canvas.yview)
        
        # Bind pan and zoom events
        self.preview_canvas.bind("<Control-MouseWheel>", self._preview_zoom)
        self.preview_canvas.bind("<Control-Button-4>", self._preview_zoom)
        self.preview_canvas.bind("<Control-Button-5>", self._preview_zoom)
        self.preview_canvas.bind("<ButtonPress-1>", self._preview_start_pan)
        self.preview_canvas.bind("<B1-Motion>", self._preview_pan)
        self.preview_canvas.bind("<ButtonRelease-1>", self._preview_end_pan)
    
    def _build_details_panel(self, parent):
        """Build the node details panel"""
        bottom_frame = tk.Frame(parent)
        parent.add(bottom_frame, height=150)
        
        self.details_frame = tk.Frame(bottom_frame, relief=tk.SUNKEN, borderwidth=2)
        self.details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tk.Label(self.details_frame, text="节点详情", font=(UI_FONT, 12, "bold")).pack(pady=5)
        self.details_text = tk.Text(self.details_frame, height=8, width=80)
        self.details_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
    
    def _build_ai_chat_panel(self, parent):
        """Build the AI chat panel on the right side"""
        chat_frame = tk.Frame(parent, relief=tk.SUNKEN, borderwidth=2)
        parent.add(chat_frame, minsize=300, stretch="never")
        
        # Title and settings
        title_frame = tk.Frame(chat_frame, bg="#e6f3ff")
        title_frame.pack(fill=tk.X, padx=2, pady=2)
        
        tk.Label(title_frame, text="AI 助手", font=(UI_FONT, 12, "bold"), 
                bg="#e6f3ff").pack(side=tk.LEFT, padx=5, pady=5)
        
        # Settings button
        settings_btn = tk.Button(title_frame, text="⚙", font=(UI_FONT, 10),
                                command=self._show_ai_settings, width=3)
        settings_btn.pack(side=tk.RIGHT, padx=5, pady=2)
        
        # Status indicator
        self.ai_status_label = tk.Label(title_frame, text="●", font=(UI_FONT, 10),
                                        fg="gray", bg="#e6f3ff")
        self.ai_status_label.pack(side=tk.RIGHT, padx=2)
        self._update_ai_status()
        
        # Chat history display
        chat_history_frame = tk.Frame(chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar for chat history
        chat_scroll = tk.Scrollbar(chat_history_frame)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.chat_display = tk.Text(chat_history_frame, wrap=tk.WORD, 
                                    state=tk.DISABLED, bg="#fafafa",
                                    yscrollcommand=chat_scroll.set)
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        chat_scroll.config(command=self.chat_display.yview)
        
        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground="#0066cc", font=(UI_FONT, 10, "bold"))
        self.chat_display.tag_configure("assistant", foreground="#006600", font=(UI_FONT, 10))
        self.chat_display.tag_configure("system", foreground="#666666", font=(UI_FONT, 9, "italic"))
        self.chat_display.tag_configure("error", foreground="#cc0000", font=(UI_FONT, 10))
        self.chat_display.tag_configure("suggestion", foreground="#996600", 
                                        font=(UI_FONT, 10, "bold"), background="#fff3cd")
        
        # Quick action buttons
        quick_actions_frame = tk.Frame(chat_frame)
        quick_actions_frame.pack(fill=tk.X, padx=5, pady=2)
        
        tk.Button(quick_actions_frame, text="分析故障树", 
                 command=self._ai_quick_analysis, bg="#d4edda").pack(side=tk.LEFT, padx=2)
        tk.Button(quick_actions_frame, text="更新故障树", 
                 command=self._ai_update_fta, bg="#d4edda").pack(side=tk.LEFT, padx=2)
        tk.Button(quick_actions_frame, text="清空对话", 
                 command=self._clear_chat, bg="#f8d7da").pack(side=tk.RIGHT, padx=2)
        
        # Message input area
        input_frame = tk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.chat_input = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.chat_input.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.chat_input.bind("<Return>", self._on_chat_enter)
        self.chat_input.bind("<Shift-Return>", lambda e: None)  # Allow Shift+Enter for newline
        
        send_btn = tk.Button(input_frame, text="发送", command=self._send_chat_message,
                            bg="#007bff", fg="white", width=8)
        send_btn.pack(side=tk.RIGHT)
        
        # Add welcome message
        self._add_chat_message("system", "欢迎使用 AI 助手！请在设置(⚙)中配置 API 密钥。你可以询问关于故障树的问题或请求建议。")
    
    def _update_ai_status(self):
        """Update the AI status indicator"""
        if self.ai_agent.is_configured():
            self.ai_status_label.config(fg="green", text="●")
        else:
            self.ai_status_label.config(fg="gray", text="○")
    
    def _show_ai_settings(self):
        """Show AI settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("AI 设置")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("550x480")
        
        tk.Label(dialog, text="AI API 配置", font=(UI_FONT, 12, "bold")).pack(pady=10)
        
        # Load existing credentials if available
        cred_manager = AICredentialManager()
        existing_creds, _ = cred_manager.load_credentials()
        
        # Provider selection
        tk.Label(dialog, text="AI 服务商:").pack(anchor="w", padx=20, pady=(10, 0))
        all_providers = AIProviderFactory.get_all_providers()
        provider_names = list(all_providers.keys())
        provider_combo = ttk.Combobox(dialog, values=provider_names, width=57, state="readonly")
        provider_combo.pack(padx=20, pady=2)
        provider_combo.set(existing_creds.get("provider", "OpenAI") if existing_creds else "OpenAI")
        
        # API Key
        tk.Label(dialog, text="API 密钥:").pack(anchor="w", padx=20, pady=(10, 0))
        api_key_entry = tk.Entry(dialog, width=60, show="*")
        api_key_entry.pack(padx=20, pady=2)
        if existing_creds:
            api_key_entry.insert(0, existing_creds.get("api_key", ""))
        
        # Show/Hide API key checkbox
        show_key_var = tk.BooleanVar(value=False)
        def toggle_show_key():
            api_key_entry.config(show="" if show_key_var.get() else "*")
        tk.Checkbutton(dialog, text="显示 API 密钥", variable=show_key_var, 
                      command=toggle_show_key).pack(anchor="w", padx=20)
        
        # API Endpoint
        tk.Label(dialog, text="API 端点:").pack(anchor="w", padx=20, pady=(10, 0))
        endpoint_entry = tk.Entry(dialog, width=60)
        endpoint_entry.pack(padx=20, pady=2)
        
        # Status label - MUST be defined before functions that use it
        status_label = tk.Label(dialog, text="", font=(UI_FONT, 9))
        status_label.pack(pady=10)
        
        # Model dropdown with refresh button
        model_frame = tk.Frame(dialog)
        model_frame.pack(padx=20, pady=2, fill="x")
        model_combo = ttk.Combobox(model_frame, width=50)
        model_combo.pack(side="left", fill="x", expand=True)
        
        def refresh_models():
            """Fetch available models for the selected provider"""
            selected_provider = provider_combo.get()
            api_key = api_key_entry.get().strip()
            
            if not selected_provider:
                status_label.config(text="请先选择服务商", fg="red")
                return
            
            if not api_key:
                status_label.config(text="请先输入 API 密钥", fg="red")
                return
            
            provider = all_providers.get(selected_provider)
            if not provider:
                status_label.config(text="未找到该服务商", fg="red")
                return
            
            status_label.config(text="正在获取可用模型...", fg="blue")
            dialog.update()
            
            endpoint = endpoint_entry.get().strip()
            available_models, fetch_error = provider.get_available_models(api_key, endpoint)
            
            if fetch_error:
                status_label.config(text=f"注意: {fetch_error}", fg="orange")
            else:
                status_label.config(text="模型加载成功", fg="green")
            
            model_combo['values'] = available_models
            if available_models:
                model_combo.set(available_models[0])
        
        refresh_btn = tk.Button(model_frame, text="↻", command=refresh_models, width=3)
        refresh_btn.pack(side="right", padx=(5, 0))
        
        tk.Label(dialog, text="模型:").pack(anchor="w", padx=20, pady=(10, 0))
        
        # Function to update endpoint and models when provider changes
        def update_provider_options(*args):
            selected_provider = provider_combo.get()
            provider = all_providers.get(selected_provider)
            if provider:
                endpoint_entry.delete(0, tk.END)
                endpoint_entry.insert(0, provider.get_default_endpoint())
                
                api_key = api_key_entry.get().strip()
                endpoint = provider.get_default_endpoint()
                
                # Try to fetch available models dynamically
                if api_key:
                    status_label.config(text="正在获取可用模型...", fg="blue")
                    dialog.update()
                    
                    available_models, fetch_error = provider.get_available_models(api_key, endpoint)
                    
                    if fetch_error:
                        status_label.config(text=f"使用默认模型: {fetch_error}", fg="orange")
                    else:
                        status_label.config(text="", fg="black")
                    
                    model_combo['values'] = available_models
                    if available_models:
                        model_combo.set(available_models[0])
                else:
                    # No API key yet, use defaults
                    model_options = provider.get_default_models()
                    model_combo['values'] = model_options
                    if model_options:
                        model_combo.set(model_options[0])
        
        # Set initial values and bind change event
        provider_combo.bind('<<ComboboxSelected>>', update_provider_options)
        update_provider_options()
        
        # Set existing values if available
        if existing_creds:
            endpoint_entry.insert(0, existing_creds.get("api_endpoint", ""))
            model_combo.set(existing_creds.get("model", ""))
        
        def test_and_save():
            provider_name = provider_combo.get().strip()
            api_key = api_key_entry.get().strip()
            endpoint = endpoint_entry.get().strip()
            model = model_combo.get().strip()
            
            if not provider_name:
                status_label.config(text="请选择 AI 服务商", fg="red")
                return
            
            if not api_key:
                status_label.config(text="请输入 API 密钥", fg="red")
                return
            
            if not endpoint:
                status_label.config(text="请输入 API 端点", fg="red")
                return
            
            if not model:
                status_label.config(text="请选择模型", fg="red")
                return
            
            status_label.config(text="正在测试连接...", fg="blue")
            dialog.update()
            
            success, message = test_connection(api_key, endpoint, model, provider_name)
            
            if success:
                # Save credentials
                save_success, save_error = self.ai_agent.configure(api_key, endpoint, model, provider_name)
                if save_success:
                    status_label.config(text="✓ 配置保存成功！", fg="green")
                    self._update_ai_status()
                    self._add_chat_message("system", f"✓ {provider_name} AI 配置成功！你现在可以询问关于故障树的问题。")
                    dialog.after(1500, dialog.destroy)
                else:
                    status_label.config(text=f"保存失败: {save_error}", fg="red")
            else:
                status_label.config(text=f"✗ {message}", fg="red")
        
        def clear_credentials():
            success, error = cred_manager.delete_credentials()
            if success:
                api_key_entry.delete(0, tk.END)
                status_label.config(text="凭据已清除", fg="blue")
                self._update_ai_status()
            else:
                status_label.config(text=f"错误: {error}", fg="red")
        
        # Buttons
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="测试并保存", command=test_and_save, 
                 bg="#28a745", fg="white", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="清除", command=clear_credentials,
                 bg="#dc3545", fg="white", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy,
                 width=15).pack(side=tk.LEFT, padx=5)
        
        # Info text
        info_text = ("提示：您的 API 密钥仅保存在本地，位于：\n"
                    f"{cred_manager.CREDENTIALS_FILE}\n"
                    "它永远不会被上传或共享。")
        tk.Label(dialog, text=info_text, font=(UI_FONT, 8), fg="gray").pack(pady=5)
    
    def _add_chat_message(self, role: str, message: str):
        """Add a message to the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Add timestamp and role prefix
        if role == "user":
            prefix = "\n🧑 你:\n"
            tag = "user"
        elif role == "assistant":
            prefix = "\n🤖 AI:\n"
            tag = "assistant"
        elif role == "error":
            prefix = "\n❌ 错误:\n"
            tag = "error"
        else:
            prefix = "\nℹ️ "
            tag = "system"
        
        self.chat_display.insert(tk.END, prefix, tag)
        self.chat_display.insert(tk.END, message + "\n", tag)
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
    
    def _on_chat_enter(self, event):
        """Handle Enter key in chat input"""
        if not event.state & 0x1:  # Not Shift+Enter
            self._send_chat_message()
            return "break"
        return None
    
    def _send_chat_message(self):
        """Send a chat message to the AI"""
        if self.ai_processing:
            return
        
        message = self.chat_input.get("1.0", tk.END).strip()
        if not message:
            return
        
        if not self.ai_agent.is_configured():
            self._add_chat_message("error", "AI 未配置。请点击 ⚙ 按钮设置你的 API 密钥。")
            return
        
        # Clear input
        self.chat_input.delete("1.0", tk.END)
        
        # Add user message to display
        self._add_chat_message("user", message)
        
        # Update FTA context
        self.ai_agent.set_fta_context(
            self.core.get_data(),
            self.core.mode,
            self.core.title
        )
        
        # Process in thread to avoid blocking UI
        self.ai_processing = True
        self._add_chat_message("system", "思考中...")
        
        def process():
            try:
                response, changes = self.ai_agent.send_message(message)
                self.root.after(0, lambda: self._handle_ai_response(response, changes))
            except Exception as e:
                self.root.after(0, lambda: self._add_chat_message("error", str(e)))
            finally:
                self.ai_processing = False
        
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()
    
    def _handle_ai_response(self, response: str, changes: list):
        """Handle AI response in main thread"""
        # Remove "思考中..." message
        self.chat_display.config(state=tk.NORMAL)
        
        # Find and remove the last "思考中..." line
        content = self.chat_display.get("1.0", tk.END)
        lines = content.split("\n")
        new_lines = []
        skip_next = False
        for i, line in enumerate(lines):
            if "思考中..." in line:
                # Skip this line and the ℹ️ prefix before it
                if new_lines and new_lines[-1].strip() == "ℹ️":
                    new_lines.pop()
                continue
            new_lines.append(line)
        
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.insert("1.0", "\n".join(new_lines))
        self.chat_display.config(state=tk.DISABLED)
        
        # Add AI response
        self._add_chat_message("assistant", response)
        
        # If there are proposed changes, show confirmation dialog
        if changes:
            self._show_change_proposals(changes)
    
    def _show_change_proposals(self, changes: list):
        """Show dialog for proposed FTA changes"""
        dialog = tk.Toplevel(self.root)
        dialog.title("AI 建议的更改")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("600x400")
        
        tk.Label(dialog, text="AI 提出了以下更改建议:", 
                font=(UI_FONT, 11, "bold")).pack(pady=10)
        
        # List of changes
        changes_frame = tk.Frame(dialog)
        changes_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scroll = tk.Scrollbar(changes_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        changes_list = tk.Listbox(changes_frame, height=10, yscrollcommand=scroll.set,
                                  selectmode=tk.MULTIPLE)
        changes_list.pack(fill=tk.BOTH, expand=True)
        scroll.config(command=changes_list.yview)
        
        for i, change in enumerate(changes):
            change_text = f"[{change.change_type.upper()}] {change.description[:80]}"
            if change.target_id:
                change_text += f" (目标: {change.target_id})"
            changes_list.insert(tk.END, change_text)
            changes_list.selection_set(i)  # Select all by default
        
        # Details text
        tk.Label(dialog, text="更改详情:", font=(UI_FONT, 10, "bold")).pack(anchor="w", padx=10)
        details_text = tk.Text(dialog, height=6, wrap=tk.WORD)
        details_text.pack(fill=tk.X, padx=10, pady=5)
        
        def show_details(event):
            selection = changes_list.curselection()
            if selection:
                idx = selection[0]
                change = changes[idx]
                details_text.delete("1.0", tk.END)
                details_text.insert("1.0", f"类型: {change.change_type}\n")
                details_text.insert(tk.END, f"目标: {change.target_id}\n")
                details_text.insert(tk.END, f"描述: {change.description}\n")
                if change.data:
                    details_text.insert(tk.END, f"数据: {json.dumps(change.data, indent=2)}")
        
        changes_list.bind("<<ListboxSelect>>", show_details)
        
        def apply_selected():
            selected = changes_list.curselection()
            if not selected:
                messagebox.showinfo("未选择", "请选择要应用的更改。")
                return
            
            applied = 0
            for idx in selected:
                change = changes[idx]
                if self._apply_change(change):
                    applied += 1
            
            if applied > 0:
                self.core.recalculate_probabilities()
                self._refresh_tree('root', self.core.get_data().get("children", []))
                self._apply_zero_marks()
                self.update_preview()
                self._mark_as_changed()
                self._add_chat_message("system", f"已对故障树应用 {applied} 项更改。")
            
            dialog.destroy()
        
        # Buttons
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="应用所选", command=apply_selected,
                 bg="#28a745", fg="white", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy,
                 width=15).pack(side=tk.LEFT, padx=5)
        
        tk.Label(dialog, text="⚠️ 请谨慎审查更改后再应用。", 
                font=(UI_FONT, 9), fg="orange").pack(pady=5)
    
    def _apply_change(self, change: 'AIProposedChange') -> bool:
        """Apply a single proposed change to the FTA"""
        try:
            if change.change_type == "add":
                # Add a new node
                parent_id = change.target_id or "root"

                # Respect the AI-provided ID so grandchildren can target it
                new_id = change.data.get("id") or f"{parent_id}_new"
                if self.fta_tree.exists(new_id):
                    self._add_chat_message("error", f"节点 ID '{new_id}' 已存在；跳过添加。")
                    return False
                if not self.fta_tree.exists(parent_id):
                    self._add_chat_message("error", f"树中未找到父节点 '{parent_id}'；跳过添加。")
                    return False
                
                # Use parent probability as default if AI doesn't specify one
                default_prob = self._get_parent_probability(parent_id)
                node_prob = change.data.get("probability")
                if node_prob is None:
                    node_prob = default_prob
                else:
                    node_prob = float(node_prob)
                
                new_node = {
                    "id": new_id,
                    "name": sanitize_name(change.data.get("name", "新节点")),
                    "type": change.data.get("type", "Event"),
                    "probability": node_prob,
                    "logicGate": change.data.get("logicGate", "OR"),
                    "notes": change.data.get("notes", change.description),
                    "links": [],
                    "children": []
                }
                
                self.core.add_node_to_data(parent_id, new_node)
                
                depth = self._get_depth(parent_id)
                tag = f"level{depth+1}"  # Support arbitrary depths
                self.fta_tree.insert(parent_id, 'end', iid=new_id, 
                                    text=new_node["name"], tags=(tag,))
                return True
                
            elif change.change_type == "edit":
                # Edit existing node
                node = self.core.find_node_by_id(change.target_id)
                if node:
                    updates = {}
                    if "name" in change.data:
                        updates["name"] = sanitize_name(change.data["name"])
                    if "probability" in change.data:
                        updates["probability"] = float(change.data["probability"])
                    if "type" in change.data:
                        updates["type"] = change.data["type"]
                    if "logicGate" in change.data:
                        updates["logicGate"] = change.data["logicGate"]
                    if "notes" in change.data:
                        updates["notes"] = change.data["notes"]
                    
                    if updates:
                        self.core.update_node(change.target_id, updates)
                        if "name" in updates:
                            self.fta_tree.item(change.target_id, text=updates["name"])
                        return True
                        
            elif change.change_type == "delete":
                # Delete node
                if change.target_id and change.target_id != "root":
                    self.fta_tree.delete(change.target_id)
                    self.core.delete_node_from_data(change.target_id)
                    return True
                    
        except Exception as e:
            self._add_chat_message("error", f"应用更改失败: {e}")
        
        return False
    
    def _ai_quick_analysis(self):
        """Run quick AI analysis of current FTA - analysis only, no popup"""
        if not self.ai_agent.is_configured():
            self._add_chat_message("error", "AI 未配置。请点击 ⚙ 按钮设置你的 API 密钥。")
            return
        
        if self.ai_processing:
            return
        
        self._add_chat_message("user", "分析此故障树并提供建议。")
        self.ai_processing = True
        self._add_chat_message("system", "正在分析故障树...")
        
        def process():
            try:
                response, changes = self.ai_agent.get_quick_analysis(
                    self.core.get_data(),
                    self.core.mode,
                    self.core.title
                )
                # For quick analysis, show response text only (no popup)
                self.root.after(0, lambda: self._add_chat_message("assistant", response))
            except Exception as e:
                self.root.after(0, lambda: self._add_chat_message("error", str(e)))
            finally:
                self.ai_processing = False
        
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()
    
    def _ai_update_fta(self):
        """Update FTA with AI suggestions by replacing the entire JSON (after validation)."""
        if not self.ai_agent.is_configured():
            self._add_chat_message("error", "AI 未配置。请点击 ⚙ 按钮设置你的 API 密钥。")
            return
        
        if self.ai_processing:
            return
        
        # Check if a node is selected
        selected = self.fta_tree.selection()
        node_id = selected[0] if selected else None
        node_name = ""
        if node_id:
            node = self.core.find_node_by_id(node_id)
            node_name = node.get("name", node_id) if node else node_id
        
        if node_id:
            self._add_chat_message("user", f"使用针对以下节点的建议更新故障树: {node_name}")
        else:
            self._add_chat_message("user", "使用你的建议更新故障树。请确保保留原始的 json 结构。")
        
        self.ai_processing = True
        self._add_chat_message("system", "正在生成更新的完整 JSON...")
        
        def _find_node_in_dict(root_node: dict, nid: str):
            if not isinstance(root_node, dict):
                return None
            if root_node.get("id") == nid:
                return root_node
            for child in root_node.get("children", []) or []:
                res = _find_node_in_dict(child, nid)
                if res is not None:
                    return res
            return None

        def process():
            try:
                assistant_text, updated = self.ai_agent.generate_full_fta_update(
                    self.core.get_data(), self.core.mode, self.core.title
                )
                def finalize():
                    # Show assistant rationale
                    self._add_chat_message("assistant", assistant_text)
                    if updated is None:
                        # Provide detailed parse error context
                        excerpt = assistant_text.strip().replace("\n", " ")[:500]
                        err_msg = "AI 未返回有效的 JSON。未应用任何更改。"
                        self._add_chat_message("error", err_msg)
                        self._add_chat_message("system", f"AI 输出的前 500 个字符: {excerpt}")
                        print("AI JSON Parse Error - output excerpt:\n" + excerpt, file=sys.stderr)
                        return
                    ok, err = self.ai_agent.verify_updated_fta_json(updated)
                    if not ok:
                        # Try to extract node id from error to show failing section
                        nid = None
                        m = re.search(r"node\s+([A-Za-z0-9_]+)", err or "")
                        if m:
                            nid = m.group(1)
                        section_snippet = None
                        if nid:
                            failing = _find_node_in_dict(updated, nid)
                            if failing is not None:
                                try:
                                    section_snippet = json.dumps(failing, indent=2)
                                except Exception:
                                    section_snippet = str(failing)
                        # Root-level diagnostics if missing root fields
                        if not section_snippet and isinstance(updated, dict):
                            try:
                                keys = list(updated.keys())
                                section_snippet = "顶层键: " + ", ".join(keys)
                            except Exception:
                                section_snippet = None

                        self._add_chat_message("error", f"已拒绝更新的 JSON: {err}")
                        if section_snippet:
                            self._add_chat_message("system", f"问题部分:\n{section_snippet[:1500]}")
                            print("AI JSON Validation Error: " + err + "\nProblematic section:\n" + section_snippet, file=sys.stderr)
                        else:
                            print("AI JSON Validation Error: " + (err or "unknown"), file=sys.stderr)
                        return
                    # Apply full replacement safely
                    self.core.set_data(updated)
                    # Rebuild entire tree view
                    for child_id in list(self.fta_tree.get_children('root')):
                        self.fta_tree.delete(child_id)
                    for child in updated.get('children', []):
                        tag = f"level1"
                        cid = child.get('id')
                        cname = sanitize_name(child.get('name', cid))
                        self.fta_tree.insert('root', 'end', iid=cid, text=cname, tags=(tag,))
                        self._rebuild_subtree(cid, child)
                    # Refresh visuals
                    self.core.recalculate_probabilities()
                    self._apply_zero_marks()
                    self.update_preview()
                    self._mark_as_changed()
                    self._add_chat_message("system", "故障树已根据 AI 生成的 JSON 更新。")
                self.root.after(0, finalize)
            except Exception as e:
                self.root.after(0, lambda: self._add_chat_message("error", str(e)))
            finally:
                self.ai_processing = False
        
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()
    
    def _apply_all_changes(self, response: str, changes: list):
        """Apply all suggested changes automatically without showing a popup"""
        # Add AI response to chat
        self._add_chat_message("assistant", response)
        
        if not changes:
            self._add_chat_message("system", "未提供任何更改建议。")
            return
        
        # Apply all changes
        applied = 0
        failed = 0
        for change in changes:
            if self._apply_change(change):
                applied += 1
            else:
                failed += 1
        
        # Refresh tree and preview after all changes
        if applied > 0:
            self.core.recalculate_probabilities()
            self._refresh_tree('root', self.core.get_data().get("children", []))
            self._apply_zero_marks()
            self.update_preview()
            self._mark_as_changed()
        
        # Report results
        msg = f"已对故障树应用 {applied} 项更改"
        if failed > 0:
            msg += f"（{failed} 项失败）"
        self._add_chat_message("system", msg + "。")
    
    def _clear_chat(self):
        """Clear chat history"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.ai_agent.clear_conversation()
        self._add_chat_message("system", "对话已清空。开始新的对话！")

    def _build_button_bar(self):
        """Build the button bar at the bottom"""
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X)
        
        buttons = [
            ("新建分析", "#90EE90", self.new_analysis),
            ("(A)添加节点", "#20b2aa", self.add_node),
            ("(E)编辑节点", "#66cdaa", self.edit_node),
            ("(D)删除节点", "#8fbc8f", self.delete_node),
            ("载入JSON", "#b0c4de", self.load_json),
            ("(S)另存JSON", "#b0e0e6", self.save_json_as),
            ("导出XML", "#dda0dd", self.export_to_xml),
            ("导出Excel", "#f0e68c", self.export_to_excel),
            ("(R)渲染图形", "#87CEEB", self.render_img)
        ]
        
        for text, color, cmd in buttons:
            tk.Button(button_frame, text=text, bg=color, command=cmd).pack(
                side=tk.LEFT, padx=2, pady=2
            )
    
    def _initialize_tree(self):
        """Initialize the tree with the root node"""
        data = self.core.get_data()
        self.fta_tree.insert('', 'end', iid='root', text='RootEvent', tags=("level0",), open=True)
    
    def _bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        shortcuts = [
            ("<Control-n>", self.new_analysis),
            ("<Control-a>", self.add_node),
            ("<Control-e>", self.edit_node),
            ("<Control-d>", self.delete_node),
            ("<Control-s>", lambda: self.save_json(overwrite=True)),
            ("<Control-Shift-S>", self.save_json_as),
            ("<Control-r>", self.render_img)
        ]
        for key, cmd in shortcuts:
            self.root.bind_all(key, lambda e, c=cmd: c())
    
    # ========== Unsaved Changes Tracking ==========
    
    def _mark_as_changed(self):
        """Mark the analysis as having unsaved changes"""
        self.has_unsaved_changes = True
        if not self.root.title().endswith("*"):
            self.root.title(self.root.title() + "*")
    
    def _mark_as_saved(self):
        """Mark the analysis as saved"""
        self.has_unsaved_changes = False
        if self.root.title().endswith("*"):
            self.root.title(self.root.title()[:-1])
    
    def _check_unsaved_changes(self):
        """Check for unsaved changes and prompt user to save"""
        if not self.has_unsaved_changes:
            return True
        
        result = messagebox.askyesnocancel(
            "未保存的更改",
            "您有未保存的更改。是否在继续之前保存？\n\n"
            "是 - 保存并继续\n"
            "否 - 放弃更改并继续\n"
            "取消 - 停留在当前分析"
        )
        
        if result is True:  # Yes - save
            success, _ = self.core.save_to_json()
            if success:
                self._mark_as_saved()
                return True
            else:
                # Try save as if no file path
                return self._save_as_before_continue()
        elif result is False:  # No - discard
            return True
        else:  # Cancel
            return False
    
    def _save_as_before_continue(self):
        """Show save as dialog before continuing with operation"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="在继续之前保存当前分析"
        )
        if file_path:
            success, error = self.core.save_to_json(file_path)
            if success:
                self._mark_as_saved()
                return True
            else:
                messagebox.showerror("保存错误", error)
                return False
        return False
    
    def new_analysis(self):
        """Create a new FTA analysis"""
        if not self._check_unsaved_changes():
            return
        
        # Reset to new analysis
        self.core = FTACore()
        self.has_unsaved_changes = False
        
        # Update UI fields
        self.title_var.set(self.core.title)
        self.date_var.set(self.core.date)
        self.mode_var.set(self.core.mode)
        
        # Reset tree view
        self.fta_tree.delete(*self.fta_tree.get_children())
        self.fta_tree.insert('', 'end', iid='root', text='RootEvent', tags=("level0",), open=True)
        
        # Clear details
        self.details_text.delete("1.0", tk.END)
        
        # Update preview
        self.update_preview()
        
        # Update window title
        self.root.title("FTA/ETA 事故树编辑器")
        
        # Update tree label
        label_text = "事件树" if self.core.mode == "ETA" else "故障树"
        for widget in self.fta_tree.master.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(text=label_text)
                break
    
    # ========== Preview Panel Methods ==========
    
    def _preview_zoom(self, event):
        """Handle zoom in preview canvas"""
        if self.preview_original_img is None:
            return
        
        factor = 1.1 if (event.delta > 0 or event.num == 4) else 0.9
        self.preview_scale *= factor
        
        try:
            from PIL import Image, ImageTk
            new_width = int(self.preview_original_img.width * self.preview_scale)
            new_height = int(self.preview_original_img.height * self.preview_scale)
            
            if new_width > 0 and new_height > 0:
                resized = self.preview_original_img.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )
                self.preview_image = ImageTk.PhotoImage(resized)
                self.preview_canvas.itemconfig(self.preview_img_id, image=self.preview_image)
                self.preview_canvas.configure(scrollregion=(0, 0, new_width, new_height))
        except Exception:
            pass
    
    def _preview_start_pan(self, event):
        """Start panning in preview canvas"""
        self.preview_canvas.scan_mark(event.x, event.y)
        self.preview_canvas.config(cursor="fleur")
    
    def _preview_pan(self, event):
        """Pan in preview canvas"""
        self.preview_canvas.scan_dragto(event.x, event.y, gain=1)
    
    def _preview_end_pan(self, event):
        """End panning in preview canvas"""
        self.preview_canvas.config(cursor="")
    
    def update_preview(self):
        """Update the live diagram preview panel"""
        viewer_path = Path(__file__).parent / "json_viewer.py"
        if not viewer_path.exists():
            self._show_preview_error("未找到 json_viewer.py")
            return
        
        tmp_json = tmp_png = None
        try:
            tmp_json_f = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json", encoding="utf-8"
            )
            tmp_json = Path(tmp_json_f.name)
            export_data = self.core.prepare_export_data()
            json.dump(export_data, tmp_json_f, indent=2, ensure_ascii=False)
            tmp_json_f.close()
            
            tmp_png_f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_png = Path(tmp_png_f.name)
            tmp_png_f.close()
            
            cmd = [sys.executable, str(viewer_path), "-i", str(tmp_json), "-o", str(tmp_png)]
            if self.hide_zero_var.get():
                cmd.append("--hide-zero")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if proc.returncode == 0 and tmp_png.exists():
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(str(tmp_png))
                    self.preview_original_img = pil_img.copy()
                    
                    # Reset scale on update
                    self.preview_scale = 1.0
                    
                    self.preview_image = ImageTk.PhotoImage(pil_img)
                    
                    if self.preview_img_id:
                        self.preview_canvas.itemconfig(self.preview_img_id, image=self.preview_image)
                    else:
                        self.preview_img_id = self.preview_canvas.create_image(
                            0, 0, image=self.preview_image, anchor=tk.NW
                        )
                    
                    self.preview_canvas.config(scrollregion=self.preview_canvas.bbox(tk.ALL))
                    # Clear any previous error messages
                    self._clear_preview_error()
                except Exception as e:
                    self._show_preview_error(f"图像加载失败: {e}")
            else:
                error_msg = f"渲染器失败（退出码 {proc.returncode}）"
                if proc.stderr:
                    error_msg += f"\n标准错误: {proc.stderr.strip()}"
                if proc.stdout:
                    error_msg += f"\n标准输出: {proc.stdout.strip()}"
                self._show_preview_error(error_msg)
        except Exception as e:
            import traceback
            self._show_preview_error(f"预览更新失败: {e}\n回溯信息: {traceback.format_exc()}")
        finally:
            for path in [tmp_json, tmp_png]:
                try:
                    if path and path.exists():
                        path.unlink()
                except Exception:
                    pass

    def _show_preview_error(self, error_msg):
        """Show error message in preview canvas"""
        self.preview_canvas.delete("all")
        self.preview_image = None
        self.preview_img_id = None
        self.preview_original_img = None
        
        # Show error text
        self.preview_canvas.create_text(
            10, 10, text=f"预览错误:\n{error_msg}", 
            anchor=tk.NW, fill="red", font=(UI_FONT, 10), width=400
        )
        
        # Add helpful message if Graphviz is not installed
        if "dot" in error_msg.lower() or "graphviz" in error_msg.lower():
            help_text = ("\n\n修复方法：\n"
                        "1. 从 https://graphviz.org/download/ 安装 Graphviz\n"
                        "2. 将 Graphviz 添加到系统 PATH\n"
                        "3. 重启应用程序")
            self.preview_canvas.create_text(
                10, 120, text=help_text, 
                anchor=tk.NW, fill="blue", font=(UI_FONT, 9), width=400
            )
    
    def _clear_preview_error(self):
        """Clear any error messages from preview canvas"""
        # This method is called when preview successfully updates
        pass
    
    # ========== Node Dialog ==========
    
    def node_dialog(self, title, node=None):
        """Show dialog for adding or editing a node"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("750x650")  # Set larger default window size (1.5x wider)
        result = {}
        
        # Basic fields
        fields = [
            ("名称:", tk.Entry, node.get("name", "") if node else ""),
            ("类型:", tk.Entry, node.get("type", "Event") if node else "Event"),
            ("概率:", tk.Entry, str(node.get("probability", 1.0)) if node else "1.0"),
        ]
        entries = {}
        for i, (label, widget_type, default) in enumerate(fields):
            tk.Label(dialog, text=label).grid(row=i, column=0, sticky="w", padx=4, pady=2)
            entry = widget_type(dialog)
            entry.insert(0, default)
            # Make Name field wider
            if label == "名称:":
                entry.config(width=70)
            entry.grid(row=i, column=1, padx=4, pady=2, sticky="ew")
            entries[label] = entry
        
        # Logic Gate
        tk.Label(dialog, text="逻辑门:").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        logic_combo = ttk.Combobox(dialog, values=["AND", "OR"], state="readonly", width=17)
        logic_combo.set((node.get("logicGate", "OR") if node else "OR").upper())
        logic_combo.grid(row=3, column=1, padx=4, pady=2)
        
        # Notes
        tk.Label(dialog, text="备注:").grid(row=4, column=0, sticky="nw", padx=4, pady=2)
        notes_text = tk.Text(dialog, height=6, width=80)
        if node:
            notes_text.insert("1.0", node.get("notes", ""))
        notes_text.grid(row=4, column=1, padx=4, pady=2)
        
        # Links UI
        tk.Label(dialog, text="搜索事件:").grid(row=5, column=0, sticky="w", padx=4, pady=2)
        search_entry = tk.Entry(dialog, width=75)
        search_entry.grid(row=5, column=1, padx=4, pady=2, sticky="ew")
        
        matches_listbox = tk.Listbox(dialog, height=8, width=80, selectmode=tk.EXTENDED)
        matches_listbox.grid(row=6, column=0, columnspan=2, padx=4, pady=2, sticky="ew")
        
        # AND/OR links sections
        link_sections = []
        for idx, link_type in enumerate(["AND", "OR"], start=7):
            tk.Label(dialog, text=f"{link_type} 链接:").grid(
                row=idx, column=0, sticky="nw", padx=4, pady=2
            )
            frame = tk.Frame(dialog)
            frame.grid(row=idx, column=1, padx=4, pady=2, sticky="w")
            listbox = tk.Listbox(frame, height=6, width=80)
            listbox.grid(row=0, column=0, padx=0, pady=0)
            btn_frame = tk.Frame(frame)
            btn_frame.grid(row=0, column=1, padx=4)
            add_btn = tk.Button(btn_frame, text="添加 →", width=8)
            remove_btn = tk.Button(btn_frame, text="← 移除", width=8)
            add_btn.grid(row=0, column=0, pady=2)
            remove_btn.grid(row=1, column=0, pady=2)
            link_sections.append((link_type, listbox, add_btn, remove_btn))
        
        # Collect available nodes
        choices = self.core.get_all_nodes_flat()
        id_to_name = {cid: cname for cid, cname in choices if cid is not None}
        make_display = lambda cid: f"{id_to_name.get(cid, cid)} ({cid})"
        
        # Track links
        links_internal = []
        if node:
            for l in node.get("links", []):
                tid = l.get("target_id")
                rel = (l.get("relation") or "OR").upper()
                links_internal.append({"target_id": tid, "relation": rel})
        
        def refresh_link_listboxes():
            for link_type, listbox, _, _ in link_sections:
                listbox.delete(0, tk.END)
                for l in links_internal:
                    if l["relation"] == link_type:
                        listbox.insert(tk.END, make_display(l["target_id"]))
        
        def update_matches(event=None):
            q = search_entry.get().strip().lower()
            matches_listbox.delete(0, tk.END)
            for cid, cname in choices:
                if cid is None:
                    continue
                if not q or q in f"{cname} ({cid})".lower():
                    matches_listbox.insert(tk.END, f"{cname} ({cid})")
        
        def add_selected(relation):
            selected_count = 0
            for i in matches_listbox.curselection():
                disp = matches_listbox.get(i)
                tid = disp.split("(")[-1].rstrip(")")
                if node and tid == node.get("id"):
                    continue
                if not any(l["target_id"] == tid and l["relation"] == relation for l in links_internal):
                    links_internal.append({"target_id": tid, "relation": relation})
                    selected_count += 1
            refresh_link_listboxes()
            # Clear selection and show feedback
            matches_listbox.selection_clear(0, tk.END)
            if selected_count > 0:
                messagebox.showinfo("链接已添加", f"已添加 {selected_count} 条 {relation} 链接")
            elif matches_listbox.curselection():
                messagebox.showwarning("链接未添加", "所选节点已链接，或是当前节点本身")
        
        def remove_selected_from(listbox, relation):
            removed_count = 0
            for idx in reversed(listbox.curselection()):
                disp = listbox.get(idx)
                tid = disp.split("(")[-1].rstrip(")")
                removed_count += 1
                links_internal[:] = [
                    l for l in links_internal
                    if not (l["target_id"] == tid and l["relation"] == relation)
                ]
            refresh_link_listboxes()
            # Show feedback
            if removed_count > 0:
                messagebox.showinfo("链接已移除", f"已移除 {removed_count} 条 {relation} 链接")
        
        # Wire events
        search_entry.bind("<KeyRelease>", update_matches)
        for link_type, listbox, add_btn, remove_btn in link_sections:
            add_btn.config(command=lambda r=link_type: add_selected(r))
            remove_btn.config(command=lambda lb=listbox, r=link_type: remove_selected_from(lb, r))
        
        update_matches()
        refresh_link_listboxes()
        
        dialog.focus_force()
        dialog.after(10, lambda: (entries["名称:"].focus_set(), entries["名称:"].select_range(0, tk.END)))
        
        def confirm():
            try:
                probability = float(entries["概率:"].get())
                if not 0 <= probability <= 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("错误", "概率必须在 0 到 1 之间。")
                return
            
            logic_val = (logic_combo.get() or "OR").upper()
            if logic_val not in ("AND", "OR"):
                messagebox.showerror("错误", "逻辑门必须是 AND 或 OR。")
                return
            
            result.update({
                "name": entries["名称:"].get(),
                "type": entries["类型:"].get(),
                "probability": probability,
                "logicGate": logic_val,
                "notes": notes_text.get("1.0", tk.END).strip(),
                "links": [{"target_id": l["target_id"], "relation": l["relation"]} for l in links_internal]
            })
            dialog.destroy()
        
        tk.Button(dialog, text="确定", command=confirm).grid(row=9, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
        tk.Button(dialog, text="取消", command=dialog.destroy).grid(row=10, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.wait_window()
        return result if result else None
    
    # ========== Node Operations ==========
    
    def add_node(self):
        """Add a new node to the tree"""
        selected = self.fta_tree.selection()
        if not selected:
            return
        
        data = self.node_dialog("添加节点")
        if data:
            parent_id = selected[0]
            depth = self._get_depth(parent_id)
            
            # Generate unique ID by checking existing children
            existing_children = self.fta_tree.get_children(parent_id)
            max_index = -1
            for child_id in existing_children:
                if child_id.startswith(f"{parent_id}_"):
                    try:
                        index = int(child_id.split("_")[-1])
                        max_index = max(max_index, index)
                    except ValueError:
                        continue
            new_id = f"{parent_id}_{max_index + 1}"
            
            tag = f"level{min(depth+1, 3)}"
            display_name = sanitize_name(data.get("name", ""))
            self.fta_tree.insert(parent_id, 'end', iid=new_id, text=display_name, tags=(tag,))
            
            new_node = {
                "id": new_id,
                "name": sanitize_name(data.get("name", "")),
                "type": data.get("type", "Event"),
                "probability": float(data.get("probability", 1.0)),
                "logicGate": data.get("logicGate", "OR"),
                "notes": data.get("notes", ""),
                "links": data.get("links", []),
                "children": []
            }
            self.core.add_node_to_data(parent_id, new_node)
            self.core.recalculate_probabilities()
            self._apply_zero_marks()
            self.update_preview()
            self._mark_as_changed()
    
    def edit_node(self):
        """Edit the selected node"""
        selected = self.fta_tree.selection()
        if not selected:
            return
        
        node_id = selected[0]
        node = self.core.find_node_by_id(node_id)
        if not node:
            messagebox.showerror("编辑错误", "在已加载的数据中未找到所选节点。")
            return
        
        data = self.node_dialog("编辑节点", node)
        if data:
            self.core.update_node(node_id, {
                "name": sanitize_name(data.get("name", node.get("name", ""))),
                "type": data.get("type", node.get("type", "Event")),
                "probability": float(data.get("probability", node.get("probability", 1.0))),
                "logicGate": data.get("logicGate", node.get("logicGate", "OR")),
                "notes": data.get("notes", node.get("notes", "")),
                "links": data.get("links", node.get("links", []))
            })
            self.fta_tree.item(node_id, text=sanitize_name(node.get("name", node_id)))
            self.core.recalculate_probabilities()
            self._apply_zero_marks()
            self.update_preview()
            self._mark_as_changed()
    
    def delete_node(self):
        """Delete the selected node"""
        selected = self.fta_tree.selection()
        if not selected or selected[0] == 'root':
            return
        
        node_id = selected[0]
        parent_id = self.fta_tree.parent(node_id)
        
        # Delete from tree view
        self.fta_tree.delete(node_id)
        
        # Delete from data
        self.core.delete_node_from_data(node_id)
        self.core.recalculate_probabilities()
        
        # Refresh the parent's children to ensure consistent state
        if parent_id:
            parent_node = self.core.find_node_by_id(parent_id)
            if parent_node:
                # Clear and rebuild children for this parent
                current_children = list(self.fta_tree.get_children(parent_id))
                for child_id in current_children:
                    self.fta_tree.delete(child_id)
                
                # Rebuild from data
                for i, child in enumerate(parent_node.get("children", [])):
                    depth = self._get_depth(parent_id)
                    tag = f"level{depth+1}"  # Support arbitrary depths
                    child_id = child.get("id")
                    child_name = sanitize_name(child.get("name", child_id))
                    self.fta_tree.insert(parent_id, 'end', iid=child_id, text=child_name, tags=(tag,))
                    # Recursively rebuild subtree
                    self._rebuild_subtree(child_id, child)
        
        self._apply_zero_marks()
        self.update_preview()
        self._mark_as_changed()
    
    def _rebuild_subtree(self, parent_id, parent_node):
        """Recursively rebuild subtree from data"""
        for child in parent_node.get("children", []):
            depth = self._get_depth(parent_id)
            tag = f"level{depth+1}"  # Support arbitrary depths
            child_id = child.get("id")
            child_name = sanitize_name(child.get("name", child_id))
            self.fta_tree.insert(parent_id, 'end', iid=child_id, text=child_name, tags=(tag,))
            self._rebuild_subtree(child_id, child)
    
    # ========== Display Methods ==========
    
    def show_selected_details(self, event):
        """Show details of the selected node"""
        selected = self.fta_tree.selection()
        if not selected:
            return
        
        node = self.core.find_node_by_id(selected[0])
        if node:
            calc_prob = node.get("calculatedProbability", node.get("probability", 0.0))
            links_display = ""
            for l in node.get("links", []):
                tid = l.get("target_id")
                rel = l.get("relation", "OR")
                target_node = self.core.find_node_by_id(tid) if tid else None
                target_name = target_node.get("name") if target_node else tid
                links_display += f"{rel} -> {target_name} ({tid})\n"
            
            details = (
                f"名称: {node.get('name','')}\n"
                f"类型: {node.get('type','')}\n"
                f"基础概率: {node.get('probability', 0.0)}\n"
                f"逻辑门: {node.get('logicGate','')}\n"
                f"计算概率: {calc_prob}\n"
                f"节点 ID: {node.get('id','')}\n\n"
                f"备注:\n{node.get('notes','')}\n\n"
                f"链接:\n{links_display}"
            )
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert(tk.END, details)
    
    def _apply_zero_marks(self):
        """Apply visual marks to nodes with zero probability"""
        zero_nodes = self.core.get_zero_probability_nodes()
        
        def walk(node):
            nid = str(node.get("id"))
            is_zero = nid in zero_nodes
            prob = node.get("probability")
            is_full_prob = prob == 1.0
            
            try:
                self.fta_tree.set(nid, "mark", "✖" if is_zero else "")
                depth = self._get_depth(nid)
                level_tag = f"level{min(depth,3)}"
                
                # Apply appropriate tags based on probability
                if is_full_prob:
                    tags = (level_tag, "full_prob")
                elif is_zero:
                    tags = (level_tag, "zero_prob")
                else:
                    tags = (level_tag,)
                
                self.fta_tree.item(nid, text=sanitize_name(node.get("name", "")), tags=tags)
            except Exception:
                pass
            
            for c in node.get("children", []):
                walk(c)
        
        data = self.core.get_data()
        if isinstance(data, dict):
            walk(data)
    
    def _refresh_tree(self, parent_id, children):
        """Refresh the tree view from data"""
        self.fta_tree.delete(*self.fta_tree.get_children(parent_id))
        for child in children:
            depth = self._get_depth(parent_id)
            level_tag = f"level{min(depth+1, 3)}"
            cid = str(child.get("id"))
            name = sanitize_name(child.get("name", cid))
            
            try:
                self.fta_tree.insert(
                    parent_id, 'end', iid=cid, text=name,
                    values=("",), tags=(level_tag,)
                )
            except Exception:
                fallback = f"{parent_id}_{self.fta_tree.index(parent_id)}"
                self.fta_tree.insert(
                    parent_id, 'end', iid=fallback, text=name,
                    values=("",), tags=(level_tag,)
                )
                child["id"] = fallback
            
            self._refresh_tree(cid, child.get("children", []))
    
    def _get_depth(self, node_id):
        """Get the depth of a node in the tree"""
        depth = 0
        while node_id != 'root':
            node_id = self.fta_tree.parent(node_id)
            depth += 1
        return depth
    
    def _get_parent_probability(self, parent_id: str) -> float:
        """Get the parent node's probability for use as default for new children"""
        if parent_id == 'root':
            return 0.5  # Default for root's children
        parent = self.core.find_node_by_id(parent_id)
        if parent:
            return float(parent.get('probability', 0.5))
        return 0.5
    
    # ========== File Operations ==========
    
    def load_json(self):
        """Load FTA data from a JSON file"""
        if not self._check_unsaved_changes():
            return
            
        file_path = filedialog.askopenfilename(filetypes=[("JSON 文件", "*.json")])
        if not file_path:
            return
        
        success, error = self.core.load_from_json(file_path)
        if not success:
            messagebox.showerror("加载错误", error)
            return
        
        # Update UI with loaded data
        data = self.core.get_data()
        self.fta_tree.item('root', text=data.get("name", "RootEvent"))
        self._refresh_tree('root', data.get("children", []))
        self._apply_zero_marks()
        self.update_preview()
        
        # Update metadata fields in UI
        self.title_var.set(self.core.title)
        self.date_var.set(self.core.date)
        self.mode_var.set(self.core.mode)
        
        # Update tree label based on mode
        label_text = "事件树" if self.core.mode == "ETA" else "故障树"
        for widget in self.fta_tree.master.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(text=label_text)
                break
        
        # Mark as saved since we just loaded
        self._mark_as_saved()
    
    def save_json(self, overwrite=False):
        """Save FTA data to a JSON file"""
        file_path = None
        if not overwrite or not self.core.last_saved_file:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON 文件", "*.json")]
            )
            if not file_path:
                return
        
        success, error = self.core.save_to_json(file_path)
        if success:
            messagebox.showinfo("保存完成", f"已保存到 {self.core.last_saved_file}")
            self._mark_as_saved()
        else:
            messagebox.showerror("保存错误", error)
    
    def save_json_as(self):
        """Save FTA data to a new JSON file"""
        self.save_json(overwrite=False)
    
    def export_to_xml(self):
        """Export FTA data to XML format"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML 文件", "*.xml")]
        )
        if not file_path:
            return
        
        success, error = self.core.export_to_xml(file_path)
        if success:
            messagebox.showinfo("导出完成", f"已导出到 {file_path}")
        else:
            messagebox.showerror("导出错误", error)
    
    def export_to_excel(self):
        """Export FTA data to Excel format"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")]
        )
        if not file_path:
            return
        
        success, error = self.core.export_to_excel(file_path)
        if success:
            messagebox.showinfo("导出完成", f"已导出 Excel 到 {file_path}")
        else:
            messagebox.showerror("导出错误", error)
    
    def render_img(self):
        """Render and display the FTA diagram in a new window, and update live preview with HQ"""
        viewer_path = Path(__file__).parent / "json_viewer.py"
        if not viewer_path.exists():
            messagebox.showerror("渲染错误", f"未找到 json_viewer.py:\n{viewer_path}")
            return
        
        tmp_json = tmp_png = tmp_preview_png = None
        try:
            tmp_json_f = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json", encoding="utf-8"
            )
            tmp_json = Path(tmp_json_f.name)
            json.dump(self.core.prepare_export_data(), tmp_json_f, indent=2, ensure_ascii=False)
            tmp_json_f.close()
            
            tmp_png_f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_png = Path(tmp_png_f.name)
            tmp_png_f.close()
            
            tmp_preview_png_f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_preview_png = Path(tmp_preview_png_f.name)
            tmp_preview_png_f.close()
            
            # Render high-quality image for display window
            cmd = [sys.executable, str(viewer_path), "-i", str(tmp_json), "-o", str(tmp_png)]
            if self.hide_zero_var.get():
                cmd.append("--hide-zero")
            cmd.append("--high-quality")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            
            if proc.returncode != 0 or not tmp_png.exists():
                raise RuntimeError(
                    f"渲染器失败（退出码 {proc.returncode}）。\n{proc.stdout}\n{proc.stderr}"
                )
            
            # Also update live preview with high-quality image
            cmd_preview = [sys.executable, str(viewer_path), "-i", str(tmp_json), "-o", str(tmp_preview_png)]
            if self.hide_zero_var.get():
                cmd_preview.append("--hide-zero")
            cmd_preview.append("--high-quality")
            proc_preview = subprocess.run(cmd_preview, capture_output=True, text=True)
            
            if proc_preview.returncode == 0 and tmp_preview_png.exists():
                self._update_preview_with_image(tmp_preview_png)
            
            # Create viewer window - passes ownership of tmp files to the window
            self._create_diagram_viewer_window(tmp_png, tmp_json)
            # Note: tmp_preview_png is no longer needed after preview update
            try:
                if tmp_preview_png and tmp_preview_png.exists():
                    tmp_preview_png.unlink()
            except Exception:
                pass
            
        except Exception as e:
            messagebox.showerror("渲染错误", f"{e}")
            # Clean up on error
            for path in [tmp_json, tmp_png, tmp_preview_png]:
                try:
                    if path and path.exists():
                        path.unlink()
                except Exception:
                    pass
    
    def _update_preview_with_image(self, image_path):
        """Update the live preview with a specific image file"""
        try:
            from PIL import Image, ImageTk
            pil_img = Image.open(str(image_path))
            self.preview_original_img = pil_img.copy()
            
            # Reset scale on update
            self.preview_scale = 1.0
            
            self.preview_image = ImageTk.PhotoImage(pil_img)
            
            if self.preview_img_id:
                self.preview_canvas.itemconfig(self.preview_img_id, image=self.preview_image)
            else:
                self.preview_img_id = self.preview_canvas.create_image(
                    0, 0, image=self.preview_image, anchor=tk.NW
                )
            
            self.preview_canvas.config(scrollregion=self.preview_canvas.bbox(tk.ALL))
            self._clear_preview_error()
        except Exception as e:
            self._show_preview_error(f"图像加载失败: {e}")
    
    def _create_diagram_viewer_window(self, tmp_png, tmp_json):
        """Create a window to view the rendered diagram"""
        win = tk.Toplevel(self.root)
        win.title("FTA 图形")
        
        frame = tk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True)
        
        h_scroll = tk.Scrollbar(frame, orient=tk.HORIZONTAL)
        v_scroll = tk.Scrollbar(frame)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas = tk.Canvas(frame, xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        h_scroll.config(command=canvas.xview)
        v_scroll.config(command=canvas.yview)
        
        try:
            from PIL import Image, ImageTk
            pil_img = Image.open(str(tmp_png))
            original_img = pil_img.copy()
        except Exception as e:
            win.destroy()
            raise RuntimeError(f"加载渲染图像失败: {e}")
        
        img = ImageTk.PhotoImage(pil_img)
        img_id = canvas.create_image(0, 0, image=img, anchor=tk.NW)
        canvas.image = img
        canvas.config(scrollregion=canvas.bbox(tk.ALL))
        
        # Zoom and pan
        current_scale = [1.0]
        
        def zoom(event):
            factor = 1.1 if (event.delta > 0 or event.num == 4) else 0.9
            current_scale[0] *= factor
            
            new_width = int(original_img.width * current_scale[0])
            new_height = int(original_img.height * current_scale[0])
            
            if new_width > 0 and new_height > 0:
                resized = original_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                new_img = ImageTk.PhotoImage(resized)
                canvas.itemconfig(img_id, image=new_img)
                canvas.image = new_img
                canvas.configure(scrollregion=(0, 0, new_width, new_height))
        
        canvas.bind("<Control-MouseWheel>", zoom)
        canvas.bind("<Control-Button-4>", zoom)
        canvas.bind("<Control-Button-5>", zoom)
        
        canvas.bind("<ButtonPress-1>", lambda e: (canvas.scan_mark(e.x, e.y), canvas.config(cursor="fleur")))
        canvas.bind("<B1-Motion>", lambda e: canvas.scan_dragto(e.x, e.y, gain=1))
        canvas.bind("<ButtonRelease-1>", lambda e: canvas.config(cursor=""))
        
        def save_diagram():
            save_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG 文件", "*.png")]
            )
            if save_path:
                try:
                    import shutil
                    shutil.copy2(str(tmp_png), save_path)
                    messagebox.showinfo("成功", f"图形已保存到: {save_path}")
                except Exception as e:
                    messagebox.showerror("保存错误", f"保存图形失败: {e}")
        
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="另存为 PNG", command=save_diagram).pack(pady=5)
        
        def on_close():
            # Clean up temporary files when window closes
            for path in [tmp_json, tmp_png]:
                try:
                    if path and isinstance(path, Path) and path.exists():
                        path.unlink()
                except Exception:
                    pass
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", on_close)


def main():
    """Main entry point for the application"""
    root = tk.Tk()
    app = FTAEditorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
