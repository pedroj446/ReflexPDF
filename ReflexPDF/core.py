# -*- coding: utf-8 -*-
"""
Created on Sat Nov 29 13:44:36 2025

@author: pjuli
"""

import os
import sys
import importlib
import inspect
import threading
import queue
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# Optional: watchdog for hot reload
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False

PLUGINS_DIR = "plugins"  # pasta onde ficam os plugins

# -------------------------
# PluginManager: carrega/recarrega plugins
# -------------------------
class PluginManager:
    def __init__(self, plugins_dir=PLUGINS_DIR, log_fn=print):
        self.plugins_dir = plugins_dir
        self.log = log_fn
        self._lock = threading.RLock()
        self.modules = {}   # chave: id (nome da pasta) -> módulo
        self.meta = {}      # chave: id -> metadata dict

    def discover(self):
        """Descobre subpastas válidas em plugins_dir."""
        if not os.path.isdir(self.plugins_dir):
            os.makedirs(self.plugins_dir, exist_ok=True)
            return []
        items = []
        for name in os.listdir(self.plugins_dir):
            sub = os.path.join(self.plugins_dir, name)
            module_file = os.path.join(sub, f"{name}.py")
            if os.path.isdir(sub) and os.path.isfile(module_file):
                items.append(name)
        return sorted(items)

    def load_all(self):
        """Carrega ou recarrega todos os plugins encontrados."""
        with self._lock:
            found = self.discover()
            new_meta = {}
            for name in found:
                try:
                    mod_name = f"{self.plugins_dir}.{name}.{name}"
                    if mod_name in sys.modules:
                        module = importlib.reload(sys.modules[mod_name])
                    else:
                        module = importlib.import_module(mod_name)
                    if hasattr(module, "main") and callable(module.main):
                        meta = {
                            "id": name,
                            "name": getattr(module, "PLUGIN_NAME", name),
                            "category": getattr(module, "PLUGIN_CATEGORY", "Geral"),
                            "description": getattr(module, "PLUGIN_DESCRIPTION", module.__doc__ or ""),
                            "icon": getattr(module, "PLUGIN_ICON", None),
                            "module": module,
                            "func": module.main
                        }
                        new_meta[name] = meta
                        self.modules[name] = module
                        self.log(f"[PluginManager] Carregado: {name}")
                    else:
                        self.log(f"[PluginManager] Ignorado (sem main): {name}")
                except Exception as e:
                    self.log(f"[PluginManager] Erro ao carregar {name}: {e}")
                    traceback.print_exc()
            # Remover módulos que não existem mais
            removed = set(self.meta.keys()) - set(new_meta.keys())
            for r in removed:
                self.log(f"[PluginManager] Removendo plugin ausente: {r}")
                self.modules.pop(r, None)
            self.meta = new_meta
            return self.meta.copy()

    def get_meta(self):
        with self._lock:
            return self.meta.copy()

# -------------------------
# Watcher (opcional) para hot reload
# -------------------------
class _WatcherHandler(FileSystemEventHandler):
    def __init__(self, event_queue, plugins_dir):
        super().__init__()
        self.q = event_queue
        self.plugins_dir = os.path.abspath(plugins_dir)

    def _is_plugin_py(self, path):
        path = os.path.abspath(path)
        return path.endswith(".py") and self.plugins_dir in path

    def on_created(self, event):
        if self._is_plugin_py(event.src_path):
            self.q.put(("fs_change", event.src_path))

    def on_modified(self, event):
        if self._is_plugin_py(event.src_path):
            self.q.put(("fs_change", event.src_path))

    def on_deleted(self, event):
        if self._is_plugin_py(event.src_path):
            self.q.put(("fs_change", event.src_path))

# -------------------------
# CoreApp: GUI e integração
# -------------------------
class CoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Plugin Core")
        self.root.geometry("900x600")
        self.event_q = queue.Queue()
        self.pm = PluginManager(log_fn=self._log)

        self._build_ui()
        self._bind_events()

        # Carrega plugins iniciais
        self.reload_plugins()

        # Inicia watcher se disponível
        if WATCHDOG_AVAILABLE:
            self._start_watcher()

        # Processa fila periodicamente (thread-safe)
        self.root.after(200, self._process_event_queue)

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self):
        # Layout: left = lista, right = detalhes/params, bottom = log
        self.main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True)

        # Left frame: Treeview de plugins
        left = ttk.Frame(self.main_pane, padding=6)
        self.tree = ttk.Treeview(left, columns=("category", "description"), show="headings", selectmode="browse")
        self.tree.heading("category", text="Categoria")
        self.tree.heading("description", text="Descrição")
        self.tree.column("category", width=120, anchor="w")
        self.tree.column("description", width=300, anchor="w")
        self.tree.pack(fill="both", expand=True, side="top")
        # Buttons under tree
        btn_frame = ttk.Frame(left)
        ttk.Button(btn_frame, text="Recarregar", command=self.reload_plugins).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Executar", command=self._on_execute_clicked).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Executar em pasta", command=self._on_execute_folder_clicked).pack(side="left", padx=4)
        btn_frame.pack(fill="x", pady=6)
        self.main_pane.add(left, weight=1)

        # Right frame: detalhes e formulário dinâmico
        right = ttk.Frame(self.main_pane, padding=6)
        self.meta_title = ttk.Label(right, text="Selecione um plugin", font=("Segoe UI", 12, "bold"))
        self.meta_title.pack(anchor="w")
        self.meta_desc = ttk.Label(right, text="", wraplength=420, justify="left")
        self.meta_desc.pack(anchor="w", pady=(4,10))
        self.form_frame = ttk.Frame(right)
        self.form_frame.pack(fill="both", expand=True)
        self.main_pane.add(right, weight=1)

        # Bottom: log
        bottom = ttk.Frame(self.root, padding=6)
        ttk.Label(bottom, text="Log:").pack(anchor="w")
        self.log_text = tk.Text(bottom, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        bottom.pack(fill="both", side="bottom")

    def _bind_events(self):
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    # -------------------------
    # Plugin loading / UI update
    # -------------------------
    def reload_plugins(self):
        self._log("Recarregando plugins...")
        meta = self.pm.load_all()
        self._refresh_tree(meta)

    def _refresh_tree(self, meta):
        # Atualiza Treeview com metadados
        self.tree.delete(*self.tree.get_children())
        for pid, m in sorted(meta.items()):
            name = m.get("name", pid)
            cat = m.get("category", "Geral")
            desc = (m.get("description") or "").strip().splitlines()[0]
            self.tree.insert("", "end", iid=pid, values=(cat, desc))
        self._log(f"{len(meta)} plugin(s) carregado(s).")

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        pid = sel[0]
        meta = self.pm.get_meta().get(pid)
        if not meta:
            return
        # Atualiza painel direito
        self.meta_title.config(text=meta.get("name", pid))
        self.meta_desc.config(text=meta.get("description", ""))
        # Gera formulário dinâmico
        self._build_form_for(meta["func"])

    def _clear_form(self):
        for w in self.form_frame.winfo_children():
            w.destroy()

    def _build_form_for(self, func):
        self._clear_form()
        sig = inspect.signature(func)
        self.form_widgets = {}
        row = 0
        for pname, param in sig.parameters.items():
            lbl = ttk.Label(self.form_frame, text=f"{pname}:")
            lbl.grid(row=row, column=0, sticky="w", padx=2, pady=4)
            default = param.default if param.default is not inspect._empty else ""
            # Heurística simples para tipos de entrada
            if "file" in pname.lower():
                ent = ttk.Entry(self.form_frame, width=40)
                ent.insert(0, default)
                ent.grid(row=row, column=1, sticky="w", padx=2)
                btn = ttk.Button(self.form_frame, text="Selecionar", command=lambda e=ent: self._choose_file(e))
                btn.grid(row=row, column=2, sticky="w", padx=2)
                self.form_widgets[pname] = ent
            elif "dir" in pname.lower() or "output" in pname.lower():
                ent = ttk.Entry(self.form_frame, width=40)
                ent.insert(0, default)
                ent.grid(row=row, column=1, sticky="w", padx=2)
                btn = ttk.Button(self.form_frame, text="Selecionar", command=lambda e=ent: self._choose_dir(e))
                btn.grid(row=row, column=2, sticky="w", padx=2)
                self.form_widgets[pname] = ent
            else:
                ent = ttk.Entry(self.form_frame, width=40)
                ent.insert(0, str(default))
                ent.grid(row=row, column=1, columnspan=2, sticky="w", padx=2)
                self.form_widgets[pname] = ent
            row += 1
        if row == 0:
            ttk.Label(self.form_frame, text="(Sem parâmetros)").grid(row=0, column=0, sticky="w")

    def _choose_file(self, entry_widget):
        path = filedialog.askopenfilename()
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

    def _choose_dir(self, entry_widget):
        path = filedialog.askdirectory()
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

    # -------------------------
    # Execução de plugins (em thread)
    # -------------------------
    def _on_execute_clicked(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um plugin para executar.")
            return
        pid = sel[0]
        meta = self.pm.get_meta().get(pid)
        if not meta:
            messagebox.showerror("Erro", "Meta do plugin não encontrada.")
            return
        args = self._collect_form_args()
        # Executa em thread para não travar GUI
        threading.Thread(target=self._run_plugin_thread, args=(pid, meta, args), daemon=True).start()

    def _on_execute_folder_clicked(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um plugin para executar em pasta.")
            return
        pid = sel[0]
        meta = self.pm.get_meta().get(pid)
        if not meta:
            messagebox.showerror("Erro", "Meta do plugin não encontrada.")
            return
        folder = filedialog.askdirectory(title="Selecione pasta de entrada")
        if not folder:
            return
        outdir = filedialog.askdirectory(title="Selecione pasta de saída (opcional)")
        # Decide comportamento: se plugin aceita input_file, chamamos repetidamente
        func = meta["func"]
        sig = inspect.signature(func)
        # Heurística: se existe parâmetro com 'file' no nome -> batch
        file_params = [p for p in sig.parameters if "file" in p.lower()]
        if not file_params:
            messagebox.showinfo("Info", "Plugin não parece aceitar arquivos individuais; execução em pasta pode não ser aplicável.")
        # Prepara args base (outdir para params com 'dir' ou 'output')
        base_args = {}
        for pname in sig.parameters:
            if "dir" in pname.lower() or "output" in pname.lower():
                base_args[pname] = outdir or ""
        # Executa em thread
        threading.Thread(target=self._run_plugin_on_folder, args=(pid, meta, folder, base_args), daemon=True).start()

    def _collect_form_args(self):
        args = {}
        for name, widget in getattr(self, "form_widgets", {}).items():
            val = widget.get()
            # tenta converter para int se for dígito
            if val.isdigit():
                val = int(val)
            args[name] = val
        return args

    def _run_plugin_thread(self, pid, meta, args):
        func = meta["func"]
        self.event_q.put(("log", f"Iniciando plugin {pid} ..."))
        try:
            func(**args)
            self.event_q.put(("log", f"Plugin {pid} executado com sucesso."))
        except Exception as e:
            tb = traceback.format_exc()
            self.event_q.put(("log", f"Erro ao executar {pid}: {e}\n{tb}"))
            self.event_q.put(("error", f"Erro ao executar {pid}: {e}"))

    def _run_plugin_on_folder(self, pid, meta, folder, base_args):
        func = meta["func"]
        self.event_q.put(("log", f"Iniciando execução em pasta: {folder} para plugin {pid}"))
        files = sorted(os.listdir(folder))
        total = len(files)
        processed = 0
        for fname in files:
            fpath = os.path.join(folder, fname)
            if not os.path.isfile(fpath):
                continue
            # monta args: coloca o primeiro parâmetro com 'file' como fpath
            sig = inspect.signature(func)
            call_args = base_args.copy()
            for pname in sig.parameters:
                if "file" in pname.lower() and pname not in call_args:
                    call_args[pname] = fpath
                    break
            try:
                func(**call_args)
                processed += 1
                self.event_q.put(("log", f"[{processed}/{total}] {fname} processado."))
            except Exception as e:
                tb = traceback.format_exc()
                self.event_q.put(("log", f"Erro em {fname}: {e}\n{tb}"))
        self.event_q.put(("log", f"Execução em pasta finalizada. {processed}/{total} arquivos processados."))

    # -------------------------
    # Watcher thread
    # -------------------------
    def _start_watcher(self):
        self._log("Iniciando watcher de plugins (hot reload)...")
        self._observer = Observer()
        handler = _WatcherHandler(self.event_q, PLUGINS_DIR)
        self._observer.schedule(handler, PLUGINS_DIR, recursive=True)
        t = threading.Thread(target=self._observer.start, daemon=True)
        t.start()

    # -------------------------
    # Event queue processing (GUI thread)
    # -------------------------
    def _process_event_queue(self):
        try:
            while True:
                item = self.event_q.get_nowait()
                typ, payload = item
                if typ == "fs_change":
                    # arquivo modificado: recarrega plugins
                    self._log(f"Alteração detectada: {payload}. Recarregando plugins...")
                    self.reload_plugins()
                elif typ == "log":
                    self._log(payload)
                elif typ == "error":
                    messagebox.showerror("Erro", payload)
                else:
                    self._log(f"Evento desconhecido: {typ} -> {payload}")
        except queue.Empty:
            pass
        finally:
            self.root.after(200, self._process_event_queue)

    # -------------------------
    # Logging
    # -------------------------
    def _log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        # escreve no Text widget (thread-safe via event queue)
        def write():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        # Se estamos na thread da GUI, escreve direto
        if threading.current_thread() is threading.main_thread():
            write()
        else:
            # enfileira para execução na thread principal
            self.event_q.put(("log", msg))

# -------------------------
# Execução principal
# -------------------------
def main():
    root = tk.Tk()
    app = CoreApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

