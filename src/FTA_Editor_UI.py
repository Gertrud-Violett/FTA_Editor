"""
FTA Editor UI Layer
Copyright (c) makkiblog.com - BSD-2 License

This module contains the UI components for the FTA Editor:
- Tkinter-based graphical interface
- Tree visualization
- Diagram preview
- Node editing dialogs
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import subprocess
import sys
import tempfile
from pathlib import Path
import json

from FTA_Editor_core import FTACore, sanitize_name


class FTAEditorUI:
    """UI layer for FTA Editor application"""
    
    def __init__(self, root):
        """Initialize the UI components"""
        self.root = root
        self.root.title("FTA Editor with Risk Calculation")
        
        # Initialize core logic
        self.core = FTACore()
        
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
        
        # Main vertical paned window (top: tree+diagram, bottom: details+buttons)
        main_vertical_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL)
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
        
        # Build button bar
        self._build_button_bar()
    
    def _build_top_bar(self):
        """Build the top bar with mode selector, title, and date"""
        top_frame = tk.Frame(self.root, relief=tk.RAISED, borderwidth=2, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        # Mode selector
        tk.Label(top_frame, text="Mode:", font=("Arial", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.mode_var = tk.StringVar(value=self.core.mode)
        mode_combo = ttk.Combobox(top_frame, textvariable=self.mode_var, 
                                  values=["FTA", "ETA"], state="readonly", width=10)
        mode_combo.pack(side=tk.LEFT, padx=(0, 20))
        mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
        
        # Title field
        tk.Label(top_frame, text="Title:", font=("Arial", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.title_var = tk.StringVar(value=self.core.title)
        title_entry = tk.Entry(top_frame, textvariable=self.title_var, width=30, font=("Arial", 10))
        title_entry.pack(side=tk.LEFT, padx=(0, 20))
        title_entry.bind("<FocusOut>", self._on_title_changed)
        title_entry.bind("<Return>", self._on_title_changed)
        
        # Date field
        tk.Label(top_frame, text="Date:", font=("Arial", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=(10, 5))
        self.date_var = tk.StringVar(value=self.core.date)
        date_entry = tk.Entry(top_frame, textvariable=self.date_var, width=15, font=("Arial", 10))
        date_entry.pack(side=tk.LEFT, padx=(0, 20))
        date_entry.bind("<FocusOut>", self._on_date_changed)
        date_entry.bind("<Return>", self._on_date_changed)
        
        # Hide zero probability nodes option
        self.hide_zero_var = tk.BooleanVar(value=False)
        hide_zero_cb = tk.Checkbutton(top_frame, text="Hide Zero P_calc", variable=self.hide_zero_var, 
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
        label_text = "Event Tree" if new_mode == "ETA" else "Fault Tree"
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
        
        tk.Label(tree_frame, text="Fault Tree", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.fta_tree = ttk.Treeview(tree_frame, columns=("mark",), show="tree headings")
        self.fta_tree.heading("mark", text="")
        self.fta_tree.column("mark", width=20, anchor="center", stretch=False)
        self.fta_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.fta_tree.bind("<<TreeviewSelect>>", self.show_selected_details)
        
        # Configure visual tags
        for i, color in enumerate(["#d0f0e0", "#ffe4b5", "#e6e6fa", "#c8d6e5"]):
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
        
        tk.Label(diagram_frame, text="Live Diagram Preview", font=("Arial", 12, "bold")).pack(pady=5)
        
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
        
        tk.Label(self.details_frame, text="Node Details", font=("Arial", 12, "bold")).pack(pady=5)
        self.details_text = tk.Text(self.details_frame, height=8, width=80)
        self.details_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
    
    def _build_button_bar(self):
        """Build the button bar at the bottom"""
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X)
        
        buttons = [
            ("New Analysis", "#90EE90", self.new_analysis),
            ("(A)dd Node", "#20b2aa", self.add_node),
            ("(E)dit Node", "#66cdaa", self.edit_node),
            ("(D)elete Node", "#8fbc8f", self.delete_node),
            ("Load JSON", "#b0c4de", self.load_json),
            ("(S)ave JSON As", "#b0e0e6", self.save_json_as),
            ("Export XML", "#dda0dd", self.export_to_xml),
            ("Export Excel", "#f0e68c", self.export_to_excel),
            ("(R)ender Img", "#87CEEB", self.render_img)
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
            "Unsaved Changes",
            "You have unsaved changes. Would you like to save before continuing?\n\n"
            "Yes - Save and continue\n"
            "No - Discard changes and continue\n"
            "Cancel - Stay in current analysis"
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
            title="Save current analysis before continuing"
        )
        if file_path:
            success, error = self.core.save_to_json(file_path)
            if success:
                self._mark_as_saved()
                return True
            else:
                messagebox.showerror("Save Error", error)
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
        self.root.title("FTA Editor with Risk Calculation")
        
        # Update tree label
        label_text = "Event Tree" if self.core.mode == "ETA" else "Fault Tree"
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
            self._show_preview_error("json_viewer.py not found")
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
                    self._show_preview_error(f"Image loading failed: {e}")
            else:
                error_msg = f"Renderer failed (exit {proc.returncode})"
                if proc.stderr:
                    error_msg += f"\nStderr: {proc.stderr.strip()}"
                if proc.stdout:
                    error_msg += f"\nStdout: {proc.stdout.strip()}"
                self._show_preview_error(error_msg)
        except Exception as e:
            import traceback
            self._show_preview_error(f"Preview update failed: {e}\nTraceback: {traceback.format_exc()}")
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
            10, 10, text=f"Preview Error:\n{error_msg}", 
            anchor=tk.NW, fill="red", font=("Arial", 10), width=400
        )
        
        # Add helpful message if Graphviz is not installed
        if "dot" in error_msg.lower() or "graphviz" in error_msg.lower():
            help_text = ("\n\nTo fix this:\n"
                        "1. Install Graphviz from https://graphviz.org/download/\n"
                        "2. Add Graphviz to your system PATH\n"
                        "3. Restart the application")
            self.preview_canvas.create_text(
                10, 120, text=help_text, 
                anchor=tk.NW, fill="blue", font=("Arial", 9), width=400
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
            ("Name:", tk.Entry, node.get("name", "") if node else ""),
            ("Type:", tk.Entry, node.get("type", "Event") if node else "Event"),
            ("Probability:", tk.Entry, str(node.get("probability", 1.0)) if node else "1.0"),
        ]
        entries = {}
        for i, (label, widget_type, default) in enumerate(fields):
            tk.Label(dialog, text=label).grid(row=i, column=0, sticky="w", padx=4, pady=2)
            entry = widget_type(dialog)
            entry.insert(0, default)
            # Make Name field wider
            if label == "Name:":
                entry.config(width=70)
            entry.grid(row=i, column=1, padx=4, pady=2, sticky="ew")
            entries[label] = entry
        
        # Logic Gate
        tk.Label(dialog, text="Logic Gate:").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        logic_combo = ttk.Combobox(dialog, values=["AND", "OR"], state="readonly", width=17)
        logic_combo.set((node.get("logicGate", "OR") if node else "OR").upper())
        logic_combo.grid(row=3, column=1, padx=4, pady=2)
        
        # Notes
        tk.Label(dialog, text="Notes:").grid(row=4, column=0, sticky="nw", padx=4, pady=2)
        notes_text = tk.Text(dialog, height=6, width=80)
        if node:
            notes_text.insert("1.0", node.get("notes", ""))
        notes_text.grid(row=4, column=1, padx=4, pady=2)
        
        # Links UI
        tk.Label(dialog, text="Search Events:").grid(row=5, column=0, sticky="w", padx=4, pady=2)
        search_entry = tk.Entry(dialog, width=75)
        search_entry.grid(row=5, column=1, padx=4, pady=2, sticky="ew")
        
        matches_listbox = tk.Listbox(dialog, height=8, width=80, selectmode=tk.EXTENDED)
        matches_listbox.grid(row=6, column=0, columnspan=2, padx=4, pady=2, sticky="ew")
        
        # AND/OR links sections
        link_sections = []
        for idx, link_type in enumerate(["AND", "OR"], start=7):
            tk.Label(dialog, text=f"{link_type} Links:").grid(
                row=idx, column=0, sticky="nw", padx=4, pady=2
            )
            frame = tk.Frame(dialog)
            frame.grid(row=idx, column=1, padx=4, pady=2, sticky="w")
            listbox = tk.Listbox(frame, height=6, width=80)
            listbox.grid(row=0, column=0, padx=0, pady=0)
            btn_frame = tk.Frame(frame)
            btn_frame.grid(row=0, column=1, padx=4)
            add_btn = tk.Button(btn_frame, text="Add →", width=8)
            remove_btn = tk.Button(btn_frame, text="← Remove", width=8)
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
                messagebox.showinfo("Link Added", f"Added {selected_count} {relation} link(s)")
            elif matches_listbox.curselection():
                messagebox.showwarning("Link Not Added", "Selected node is already linked or is the same as current node")
        
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
                messagebox.showinfo("Link Removed", f"Removed {removed_count} {relation} link(s)")
        
        # Wire events
        search_entry.bind("<KeyRelease>", update_matches)
        for link_type, listbox, add_btn, remove_btn in link_sections:
            add_btn.config(command=lambda r=link_type: add_selected(r))
            remove_btn.config(command=lambda lb=listbox, r=link_type: remove_selected_from(lb, r))
        
        update_matches()
        refresh_link_listboxes()
        
        dialog.focus_force()
        dialog.after(10, lambda: (entries["Name:"].focus_set(), entries["Name:"].select_range(0, tk.END)))
        
        def confirm():
            try:
                probability = float(entries["Probability:"].get())
                if not 0 <= probability <= 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Probability must be between 0 and 1.")
                return
            
            logic_val = (logic_combo.get() or "OR").upper()
            if logic_val not in ("AND", "OR"):
                messagebox.showerror("Error", "Logic Gate must be AND or OR.")
                return
            
            result.update({
                "name": entries["Name:"].get(),
                "type": entries["Type:"].get(),
                "probability": probability,
                "logicGate": logic_val,
                "notes": notes_text.get("1.0", tk.END).strip(),
                "links": [{"target_id": l["target_id"], "relation": l["relation"]} for l in links_internal]
            })
            dialog.destroy()
        
        tk.Button(dialog, text="OK", command=confirm).grid(row=9, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
        tk.Button(dialog, text="Cancel", command=dialog.destroy).grid(row=10, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
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
        
        data = self.node_dialog("Add Node")
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
            messagebox.showerror("Edit Error", "Selected node not found in loaded data.")
            return
        
        data = self.node_dialog("Edit Node", node)
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
                    tag = f"level{min(depth+1, 3)}"
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
            tag = f"level{min(depth+1, 3)}"
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
                f"Name: {node.get('name','')}\n"
                f"Type: {node.get('type','')}\n"
                f"Base Probability: {node.get('probability', 0.0)}\n"
                f"Logic Gate: {node.get('logicGate','')}\n"
                f"Calculated Probability: {calc_prob}\n"
                f"Node ID: {node.get('id','')}\n\n"
                f"Notes:\n{node.get('notes','')}\n\n"
                f"Links:\n{links_display}"
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
    
    # ========== File Operations ==========
    
    def load_json(self):
        """Load FTA data from a JSON file"""
        if not self._check_unsaved_changes():
            return
            
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not file_path:
            return
        
        success, error = self.core.load_from_json(file_path)
        if not success:
            messagebox.showerror("Load Error", error)
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
        label_text = "Event Tree" if self.core.mode == "ETA" else "Fault Tree"
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
                filetypes=[("JSON Files", "*.json")]
            )
            if not file_path:
                return
        
        success, error = self.core.save_to_json(file_path)
        if success:
            messagebox.showinfo("Save Complete", f"Saved to {self.core.last_saved_file}")
            self._mark_as_saved()
        else:
            messagebox.showerror("Save Error", error)
    
    def save_json_as(self):
        """Save FTA data to a new JSON file"""
        self.save_json(overwrite=False)
    
    def export_to_xml(self):
        """Export FTA data to XML format"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML Files", "*.xml")]
        )
        if not file_path:
            return
        
        success, error = self.core.export_to_xml(file_path)
        if success:
            messagebox.showinfo("Export Complete", f"Exported to {file_path}")
        else:
            messagebox.showerror("Export Error", error)
    
    def export_to_excel(self):
        """Export FTA data to Excel format"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")]
        )
        if not file_path:
            return
        
        success, error = self.core.export_to_excel(file_path)
        if success:
            messagebox.showinfo("Export Complete", f"Exported Excel to {file_path}")
        else:
            messagebox.showerror("Export Error", error)
    
    def render_img(self):
        """Render and display the FTA diagram in a new window, and update live preview with HQ"""
        viewer_path = Path(__file__).parent / "json_viewer.py"
        if not viewer_path.exists():
            messagebox.showerror("Render Error", f"json_viewer.py not found at:\n{viewer_path}")
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
                    f"Renderer failed (exit {proc.returncode}).\n{proc.stdout}\n{proc.stderr}"
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
            messagebox.showerror("Render Error", f"{e}")
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
            self._show_preview_error(f"Image loading failed: {e}")
    
    def _create_diagram_viewer_window(self, tmp_png, tmp_json):
        """Create a window to view the rendered diagram"""
        win = tk.Toplevel(self.root)
        win.title("FTA Diagram")
        
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
            raise RuntimeError(f"Failed to load rendered image: {e}")
        
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
                filetypes=[("PNG files", "*.png")]
            )
            if save_path:
                try:
                    import shutil
                    shutil.copy2(str(tmp_png), save_path)
                    messagebox.showinfo("Success", f"Diagram saved to: {save_path}")
                except Exception as e:
                    messagebox.showerror("Save Error", f"Failed to save diagram: {e}")
        
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="Save As PNG", command=save_diagram).pack(pady=5)
        
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
