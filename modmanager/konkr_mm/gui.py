"""Interfaz GTK3 (táctil) del gestor de mods."""
import os
import subprocess
import sys
import threading
import traceback

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GLib, Gio, Gdk, GdkPixbuf, Pango  # noqa: E402

from . import __version__, core, i18n, nexus, server  # noqa: E402
from .i18n import _  # noqa: E402
from .qrcodegen import QrCode  # noqa: E402
from .games import GAMES, NEXUS_TO_GAME  # noqa: E402

CSS = b"""
* { font-size: 15px; }
button { min-height: 42px; padding: 4px 14px; }
treeview.view { padding: 6px 4px; }
.title-big { font-size: 20px; font-weight: bold; }
.dim { opacity: 0.7; }
.statusbar { padding: 6px 12px; }
"""

OK = "<span foreground='#6fcf73'>{}</span>"
WARN = "<span foreground='#f0b34a'>{}</span>"
BAD = "<span foreground='#ef6b6b'>{}</span>"
DIM = "<span alpha='70%'>{}</span>"


def esc(s):
    return GLib.markup_escape_text(str(s))


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Konkr Mod Manager")
        self.set_default_size(1280, 760)
        self.busy = False
        self.cancel_flag = False
        self.mgr = core.Manager(log=self.log_threadsafe)
        i18n.set_language(self.mgr.config.get("language", "auto"))
        self.game_key = self.mgr.config.get("last_game", "skyrimse")
        if self.game_key not in GAMES:
            self.game_key = "skyrimse"
        self.ctx = None
        self.nexus_files = []
        self.nexus_target = {}

        # ---- cabecera
        hb = Gtk.HeaderBar(show_close_button=True)
        hb.props.title = "Konkr Mod Manager"
        self.set_titlebar(hb)
        self.game_combo = Gtk.ComboBoxText()
        for k, g in GAMES.items():
            self.game_combo.append(k, g["name"])
        self.game_combo.set_active_id(self.game_key)
        self.game_combo.connect("changed", self.on_game_changed)
        hb.pack_start(self.game_combo)
        self.apply_btn = Gtk.Button(label=_("Aplicar al juego"))
        self.apply_btn.get_style_context().add_class("suggested-action")
        self.apply_btn.connect("clicked", lambda *a: self.do_apply())
        hb.pack_end(self.apply_btn)

        # ---- páginas
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER, margin=6)
        outer.pack_start(switcher, False, False, 0)
        outer.pack_start(self.stack, True, True, 0)
        self.stack.add_titled(self.build_mods_page(), "mods", _("Mods"))
        self.stack.add_titled(self.build_plugins_page(), "plugins", _("Orden de plugins"))
        self.stack.add_titled(self.build_nexus_page(), "nexus", "Nexus")
        self.stack.add_titled(self.build_game_page(), "game", _("Juego"))
        self.stack.add_titled(self.build_phone_page(), "phone", _("Móvil"))
        self.stack.add_titled(self.build_log_page(), "log", _("Registro"))

        # ---- barra de estado
        sb = Gtk.Box(spacing=12)
        sb.get_style_context().add_class("statusbar")
        self.status_lbl = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.progress.set_size_request(260, -1)
        self.cancel_btn = Gtk.Button(label=_("Cancelar"))
        self.cancel_btn.connect("clicked", self.on_cancel)
        self.cancel_btn.set_no_show_all(True)
        sb.pack_start(self.status_lbl, True, True, 0)
        sb.pack_end(self.cancel_btn, False, False, 0)
        sb.pack_end(self.progress, False, False, 0)
        outer.pack_end(sb, False, False, 0)
        outer.pack_end(Gtk.Separator(), False, False, 0)

        self.switch_game(self.game_key)

        # ---- companion móvil
        self.companion = None
        self.companion_error = ""
        self.mgr.listeners.append(lambda key: GLib.idle_add(self.on_external_change))
        if self.mgr.config.get("companion", {}).get("enabled", True):
            self.start_companion()
        self.refresh_phone()

    # =========================================================== utilidades
    def log_threadsafe(self, msg):
        GLib.idle_add(self._log, msg)

    def _log(self, msg):
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), msg + "\n")
        self.log_view.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)
        return False

    def set_status(self, text, frac=None):
        self.status_lbl.set_text(text or "")
        if frac is None:
            self.progress.pulse()
        else:
            self.progress.set_fraction(max(0.0, min(1.0, frac)))

    def _dialog(self, kind, buttons, title, detail):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind, buttons=buttons, text=title)
        if detail:
            d.format_secondary_text(detail)
        r = d.run()
        d.destroy()
        return r

    def error(self, title, detail=""):
        self._dialog(Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, title, detail)

    def info(self, title, detail=""):
        self._dialog(Gtk.MessageType.INFO, Gtk.ButtonsType.OK, title, detail)

    def confirm(self, title, detail=""):
        return self._dialog(Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, title, detail) == Gtk.ResponseType.YES

    def run_bg(self, label, func, done=None, cancellable=False):
        """Ejecuta func(progress) en otro hilo. done(result) en el hilo de la interfaz."""
        if self.busy:
            self.info(_("Espera a que termine la tarea actual."))
            return
        self.busy = True
        self.cancel_flag = False
        self.stack.set_sensitive(False)
        self.apply_btn.set_sensitive(False)
        self.game_combo.set_sensitive(False)
        if cancellable:
            self.cancel_btn.show()
        self.set_status(label, 0)

        def progress(frac, text):
            GLib.idle_add(self.set_status, text, frac)

        def worker():
            try:
                res = func(progress)
                err = None
            except (core.ModError, nexus.NexusError) as e:
                res, err = None, (str(e), "")
            except Exception as e:  # noqa
                res, err = None, (_("Error inesperado: {error}", error=e), traceback.format_exc())
                self.log_threadsafe(traceback.format_exc())
            GLib.idle_add(finish, res, err)

        def finish(res, err):
            self.busy = False
            self.stack.set_sensitive(True)
            self.apply_btn.set_sensitive(True)
            self.game_combo.set_sensitive(True)
            self.cancel_btn.hide()
            self.refresh_all()
            if err:
                self.set_status(_("Error: {error}", error=err[0]), 0)
                self.error(err[0], err[1][-1500:] if err[1] else "")
            elif done:
                done(res)
            return False

        threading.Thread(target=worker, daemon=True).start()

    def on_cancel(self, *a):
        self.cancel_flag = True

    def ask_in_ui(self, fn, *args):
        """Desde un hilo de trabajo: ejecuta fn en la interfaz y espera su resultado."""
        ev, box = threading.Event(), {}

        def call():
            try:
                box["r"] = fn(*args)
            finally:
                ev.set()
            return False
        GLib.idle_add(call)
        ev.wait()
        return box.get("r")

    # =========================================================== juego
    def on_game_changed(self, combo):
        key = combo.get_active_id()
        if key and key != self.game_key:
            self.switch_game(key)

    def switch_game(self, key):
        self.game_key = key
        self.mgr.config["last_game"] = key
        self.mgr.save_config()
        self.ctx = self.mgr.game(key)
        self.refresh_all()
        if not self.ctx.found:
            self.set_status(_("No encuentro {game}. Ve a la pestaña Juego.", game=GAMES[key]["name"]), 0)
        else:
            self.set_status(_("{game} listo", game=GAMES[key]["name"]), 0)

    def refresh_all(self):
        self.refresh_mods()
        self.refresh_plugins()
        self.refresh_game()
        dirty = self.ctx.state.get("dirty")
        self.apply_btn.set_label(_("Aplicar al juego") + (" •" if dirty else ""))
        self.pending_lbl.set_markup(
            WARN.format(esc(_("Hay cambios sin aplicar: pulsa «Aplicar al juego» (con el juego cerrado).")))
            if dirty else DIM.format(esc(_("El juego está sincronizado con esta lista."))))

    # =========================================================== página Mods
    def build_mods_page(self):
        box = Gtk.Box(spacing=10, margin=10)
        self.mods_store = Gtk.ListStore(bool, int, str, str, str, str, str)
        tv = Gtk.TreeView(model=self.mods_store)
        tv.set_activate_on_single_click(False)
        self.mods_tv = tv
        tog = Gtk.CellRendererToggle()
        tog.connect("toggled", self.on_mod_toggled)
        tv.append_column(Gtk.TreeViewColumn(_("Activo"), tog, active=0))
        tv.append_column(Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=1))
        name_r = Gtk.CellRendererText(editable=True, ellipsize=Pango.EllipsizeMode.END)
        name_r.connect("edited", self.on_mod_renamed)
        c = Gtk.TreeViewColumn(_("Nombre"), name_r, text=2)
        c.set_expand(True)
        tv.append_column(c)
        tv.append_column(Gtk.TreeViewColumn(_("Versión"), Gtk.CellRendererText(), text=3))
        tv.append_column(Gtk.TreeViewColumn(_("Tipo"), Gtk.CellRendererText(), text=4))
        tv.append_column(Gtk.TreeViewColumn(_("Contenido"), Gtk.CellRendererText(), text=5))
        sw = Gtk.ScrolledWindow()
        sw.add(tv)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.pack_start(sw, True, True, 0)
        self.pending_lbl = Gtk.Label(xalign=0)
        left.pack_start(self.pending_lbl, False, False, 0)
        box.pack_start(left, True, True, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.set_size_request(230, -1)
        for label, cb in [(_("Añadir desde archivo…"), self.on_add_file),
                          ("▲ " + _("Subir"), lambda *a: self.on_move_mod(-1)),
                          ("▼ " + _("Bajar"), lambda *a: self.on_move_mod(1)),
                          (_("Activar / desactivar"), self.on_toggle_selected),
                          (_("Abrir carpeta del mod"), self.on_open_mod_dir),
                          (_("Quitar mod"), self.on_remove_mod)]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            col.pack_start(b, False, False, 0)
        hint = Gtk.Label(wrap=True, xalign=0, max_width_chars=26)
        hint.set_markup(DIM.format(esc(_("Si dos mods traen el mismo archivo, gana el que está más abajo. "
                                         "Toca dos veces el nombre para renombrar."))))
        col.pack_end(hint, False, False, 0)
        box.pack_start(col, False, False, 0)
        return box

    def selected_mod_id(self):
        model, it = self.mods_tv.get_selection().get_selected()
        return model[it][6] if it else None

    def refresh_mods(self, select_id=None):
        select_id = select_id or self.selected_mod_id()
        self.mods_store.clear()
        for i, m in enumerate(self.ctx.mods):
            info = []
            n = len(m.get("plugins") or [])
            if n:
                info.append(_("{n} plugins", n=n) if n > 1 else _("1 plugin"))
            info.append(_("{n} archivos", n=m.get("files", 0)))
            info.append(core.human_size(m.get("size", 0)))
            kind = "Data" if m["kind"] == "data" else _("Raíz del juego")
            it = self.mods_store.append([m["enabled"], i + 1, m["name"], m.get("version", ""), kind,
                                         ", ".join(info), m["id"]])
            if m["id"] == select_id:
                self.mods_tv.get_selection().select_iter(it)

    def on_mod_toggled(self, _r, path):
        row = self.mods_store[path]
        self.ctx.set_enabled(row[6], not row[0])
        self.refresh_all()

    def on_toggle_selected(self, *a):
        mid = self.selected_mod_id()
        if mid:
            m = self.ctx.get_mod(mid)
            self.ctx.set_enabled(mid, not m["enabled"])
            self.refresh_all()

    def on_mod_renamed(self, _r, path, text):
        if text.strip():
            self.ctx.rename_mod(self.mods_store[path][6], text.strip())
            self.refresh_mods()

    def on_move_mod(self, delta):
        mid = self.selected_mod_id()
        if mid:
            self.ctx.move_mod(mid, delta)
            self.refresh_all()

    def on_remove_mod(self, *a):
        mid = self.selected_mod_id()
        if not mid:
            return
        m = self.ctx.get_mod(mid)
        if self.confirm(_("¿Quitar «{name}»?", name=m["name"]),
                        _("Se borran sus archivos del gestor. Del juego se quitará al pulsar «Aplicar al juego».")):
            self.ctx.remove_mod(mid)
            self.refresh_all()

    def on_open_mod_dir(self, *a):
        mid = self.selected_mod_id()
        if mid:
            subprocess.Popen(["xdg-open", self.ctx.mod_dir(self.ctx.get_mod(mid))])

    def on_add_file(self, *a):
        if not self.ctx.found:
            self.error(_("Primero hay que localizar el juego (pestaña Juego)."))
            return
        d = Gtk.FileChooserDialog(title=_("Elige uno o varios mods"), transient_for=self,
                                  action=Gtk.FileChooserAction.OPEN)
        d.add_buttons(_("Cancelar"), Gtk.ResponseType.CANCEL, _("Instalar"), Gtk.ResponseType.OK)
        d.set_select_multiple(True)
        f = Gtk.FileFilter()
        f.set_name("Mods (.zip, .7z, .rar)")
        for p in ("*.zip", "*.7z", "*.rar", "*.ZIP", "*.7Z", "*.RAR"):
            f.add_pattern(p)
        d.add_filter(f)
        last = self.mgr.config.get("last_add_dir") or os.path.expanduser("~/Downloads")
        if os.path.isdir(last):
            d.set_current_folder(last)
        files = d.get_filenames() if d.run() == Gtk.ResponseType.OK else []
        d.destroy()
        if not files:
            return
        self.mgr.config["last_add_dir"] = os.path.dirname(files[0])
        self.mgr.save_config()

        def job(progress):
            out = []
            for i, path in enumerate(files):
                progress(i / len(files), _("Instalando {file}…", file=os.path.basename(path)))
                m = self.ctx.install_archive(path, chooser=self.chooser_threadsafe, progress=progress)
                if m:
                    out.append(m["name"])
            return out
        self.run_bg(_("Instalando…"), job, lambda res: self.set_status(
            _("Instalado: {names}. Pulsa «Aplicar al juego».", names=", ".join(res)) if res
            else _("Nada instalado"), 1))

    # ---- selector para FOMOD / estructura desconocida
    def chooser_threadsafe(self, tmp, analysis):
        return self.ask_in_ui(self.chooser_dialog, tmp, analysis)

    def chooser_dialog(self, tmp, an):
        root_label = _("(raíz del archivo)")
        d = Gtk.Dialog(title=_("¿Qué carpeta instalo?"), transient_for=self, modal=True)
        d.set_default_size(820, 560)
        d.add_buttons(_("Cancelar"), Gtk.ResponseType.CANCEL, _("Instalar selección"), Gtk.ResponseType.OK)
        area = d.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        msg = Gtk.Label(wrap=True, xalign=0)
        if an["fomod"]:
            msg.set_text(_("Este mod trae un instalador FOMOD (de los que preguntan opciones). Todavía no lo "
                           "interpreto, así que marca a mano las carpetas que quieras: normalmente la de núcleo "
                           "(Core, 00 …) y la de la opción que prefieras. Su contenido se fusiona en Data."))
        else:
            msg.set_text(_("No reconozco la estructura de este mod. Marca la carpeta (o carpetas) que contienen "
                           "lo que va dentro de Data (meshes, textures, .esp…)."))
        area.pack_start(msg, False, False, 0)
        store = Gtk.ListStore(bool, str, str)
        for rel in an["candidates"]:
            try:
                peek = ", ".join(sorted(os.listdir(os.path.join(tmp, rel)))[:6])
            except OSError:
                peek = ""
            store.append([False, rel or root_label, peek])
        tv = Gtk.TreeView(model=store)
        tog = Gtk.CellRendererToggle()

        def toggled(_r, path):
            store[path][0] = not store[path][0]
        tog.connect("toggled", toggled)
        tv.append_column(Gtk.TreeViewColumn("", tog, active=0))
        tv.append_column(Gtk.TreeViewColumn(_("Carpeta"), Gtk.CellRendererText(), text=1))
        c = Gtk.TreeViewColumn(_("Contiene"), Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=2)
        c.set_expand(True)
        tv.append_column(c)
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.add(tv)
        area.pack_start(sw, True, True, 0)
        r1 = Gtk.RadioButton.new_with_label(None, _("Va dentro de Data (lo normal)"))
        r2 = Gtk.RadioButton.new_with_label_from_widget(r1, _("Va en la raíz del juego (script extender, ENB…)"))
        area.pack_start(r1, False, False, 0)
        area.pack_start(r2, False, False, 0)
        d.show_all()
        result = None
        while d.run() == Gtk.ResponseType.OK:
            roots = [row[1] if row[1] != root_label else "" for row in store if row[0]]
            if not roots:
                self.info(_("Marca al menos una carpeta."))
                continue
            result = {"roots": roots, "kind": "data" if r1.get_active() else "root"}
            break
        d.destroy()
        return result

    # =========================================================== página Plugins
    def build_plugins_page(self):
        box = Gtk.Box(spacing=10, margin=10)
        self.pl_store = Gtk.ListStore(bool, int, str, str, str)
        tv = Gtk.TreeView(model=self.pl_store)
        self.pl_tv = tv
        tog = Gtk.CellRendererToggle()
        tog.connect("toggled", self.on_plugin_toggled)
        tv.append_column(Gtk.TreeViewColumn(_("Activo"), tog, active=0))
        tv.append_column(Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=1))
        c = Gtk.TreeViewColumn("Plugin", Gtk.CellRendererText(), text=2)
        c.set_expand(True)
        tv.append_column(c)
        tv.append_column(Gtk.TreeViewColumn(_("Tipo"), Gtk.CellRendererText(), text=3))
        tv.append_column(Gtk.TreeViewColumn("Mod", Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=4))
        sw = Gtk.ScrolledWindow()
        sw.add(tv)
        box.pack_start(sw, True, True, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.set_size_request(230, -1)
        for label, delta in (("▲ " + _("Subir"), -1), ("▼ " + _("Bajar"), 1)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, d=delta: self.on_move_plugin(d))
            col.pack_start(b, False, False, 0)
        hint = Gtk.Label(wrap=True, xalign=0, max_width_chars=26)
        hint.set_markup(DIM.format(esc(_("Orden de carga de los plugins de tus mods. Los maestros (.esm/.esl) "
                                         "siempre cargan antes que los .esp.") + "\n\n" +
                                       _("Las Creations instaladas desde el menú del juego se respetan y van "
                                         "por delante."))))
        col.pack_end(hint, False, False, 0)
        box.pack_start(col, False, False, 0)
        return box

    def refresh_plugins(self):
        _m, it = self.pl_tv.get_selection().get_selected()
        sel = self.pl_store[it][2] if it else None
        self.pl_store.clear()
        names = {"esm": _("Maestro"), "esl": _("Ligero (ESL)"), "esp": _("Normal")}
        for i, e in enumerate(self.ctx.state["plugins"]):
            it = self.pl_store.append([e["active"], i + 1, e["name"], names.get(e.get("kind"), ""), e.get("mod", "")])
            if e["name"] == sel:
                self.pl_tv.get_selection().select_iter(it)

    def on_plugin_toggled(self, _r, path):
        row = self.pl_store[path]
        self.ctx.set_plugin_active(row[2], not row[0])
        self.refresh_all()

    def on_move_plugin(self, delta):
        _m, it = self.pl_tv.get_selection().get_selected()
        if it:
            self.ctx.move_plugin(self.pl_store[it][2], delta)
            self.refresh_all()

    # =========================================================== página Nexus
    def build_nexus_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label=_("Clave de API:")), False, False, 0)
        self.key_entry = Gtk.Entry(visibility=False, placeholder_text="nexusmods.com → Settings → API Keys")
        self.key_entry.set_text(self.mgr.api_key)
        row.pack_start(self.key_entry, True, True, 0)
        show = Gtk.ToggleButton(label=_("Mostrar"))
        show.connect("toggled", lambda b: self.key_entry.set_visibility(b.get_active()))
        row.pack_start(show, False, False, 0)
        b = Gtk.Button(label=_("Guardar y comprobar"))
        b.connect("clicked", self.on_validate_key)
        row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.account_lbl = Gtk.Label(xalign=0)
        self.account_lbl.set_markup(DIM.format(esc(_("Sin comprobar."))))
        box.pack_start(self.account_lbl, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 4)

        row2 = Gtk.Box(spacing=8)
        self.mod_entry = Gtk.Entry(placeholder_text=_("Pega la URL del mod, su número o un enlace nxm://"))
        self.mod_entry.connect("activate", self.on_nexus_lookup)
        row2.pack_start(self.mod_entry, True, True, 0)
        paste = Gtk.Button(label=_("Pegar"))
        paste.connect("clicked", self.on_paste)
        row2.pack_start(paste, False, False, 0)
        b2 = Gtk.Button(label=_("Buscar archivos"))
        b2.connect("clicked", self.on_nexus_lookup)
        row2.pack_start(b2, False, False, 0)
        box.pack_start(row2, False, False, 0)

        self.mod_title = Gtk.Label(xalign=0, wrap=True)
        self.mod_title.get_style_context().add_class("title-big")
        box.pack_start(self.mod_title, False, False, 0)
        self.mod_summary = Gtk.Label(xalign=0, wrap=True)
        self.mod_summary.get_style_context().add_class("dim")
        box.pack_start(self.mod_summary, False, False, 0)

        self.files_store = Gtk.ListStore(str, str, str, str, int)
        tv = Gtk.TreeView(model=self.files_store)
        self.files_tv = tv
        c = Gtk.TreeViewColumn(_("Archivo"), Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=0)
        c.set_expand(True)
        tv.append_column(c)
        tv.append_column(Gtk.TreeViewColumn(_("Versión"), Gtk.CellRendererText(), text=1))
        tv.append_column(Gtk.TreeViewColumn(_("Categoría"), Gtk.CellRendererText(), text=2))
        tv.append_column(Gtk.TreeViewColumn(_("Tamaño"), Gtk.CellRendererText(), text=3))
        tv.connect("row-activated", lambda *a: self.on_nexus_download())
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.add(tv)
        box.pack_start(sw, True, True, 0)

        row3 = Gtk.Box(spacing=8)
        self.rate_lbl = Gtk.Label(xalign=0)
        self.rate_lbl.get_style_context().add_class("dim")
        row3.pack_start(self.rate_lbl, True, True, 0)
        dl = Gtk.Button(label=_("Descargar e instalar"))
        dl.get_style_context().add_class("suggested-action")
        dl.connect("clicked", lambda *a: self.on_nexus_download())
        row3.pack_end(dl, False, False, 0)
        box.pack_start(row3, False, False, 0)
        return box

    def nx(self):
        return nexus.Nexus(self.key_entry.get_text() or self.mgr.api_key)

    def on_paste(self, *a):
        txt = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        if txt:
            self.mod_entry.set_text(txt.strip())
            self.on_nexus_lookup()

    def on_validate_key(self, *a):
        self.mgr.set_api_key(self.key_entry.get_text().strip())

        def done(d):
            who = _("Conectado como {name}", name=d.get("name", "?"))
            extra = (OK.format(esc(_("Premium: descargas directas activadas"))) if d.get("premium") else
                     WARN.format(esc(_("cuenta gratuita: usa enlaces nxm:// (botón «Mod Manager Download» de la web)"))))
            self.account_lbl.set_markup(f"<b>{esc(who)}</b> — {extra}")
        self.run_bg(_("Comprobando clave…"), lambda p: self.nx().validate(), done)

    def on_nexus_lookup(self, *a):
        q = nexus.parse_input(self.mod_entry.get_text())
        if not q["mod_id"]:
            self.error(_("No reconozco eso."),
                       _("Pega una URL como https://www.nexusmods.com/skyrimspecialedition/mods/12604, "
                         "el número del mod o un enlace nxm://."))
            return
        domain = q["domain"] or GAMES[self.game_key]["nexus"]
        gk = NEXUS_TO_GAME.get(domain)
        if not gk:
            self.error(_("Ese mod es de otro juego ({domain}).", domain=domain))
            return
        if gk != self.game_key:
            self.game_combo.set_active_id(gk)  # cambia de juego automáticamente
        self.nexus_target = dict(q, domain=domain)
        api = self.nx()

        def job(progress):
            return api.mod_info(domain, q["mod_id"]), api.files(domain, q["mod_id"]), api.rate

        def done(res):
            info, files, rate = res
            self.nexus_target["info"] = info
            self.mod_title.set_text(info.get("name", f"Mod {q['mod_id']}"))
            self.mod_summary.set_text((info.get("summary") or "").replace("<br />", " ")[:400])
            self.files_store.clear()
            self.nexus_files = files
            sel_it = None
            for f in files:
                cat = (f.get("category_name") or "").replace("_", " ").title()
                size = core.human_size((f.get("size_kb") or 0) * 1024)
                it = self.files_store.append([f.get("name", ""), f.get("version", ""), cat, size, f["file_id"]])
                if q["file_id"] and f["file_id"] == q["file_id"]:
                    sel_it = it
            if sel_it:
                self.files_tv.get_selection().select_iter(sel_it)
            elif len(self.files_store):
                self.files_tv.get_selection().select_path(Gtk.TreePath(0))
            self.show_rate(rate)
            self.set_status(_("{n} archivos encontrados", n=len(files)), 1)
            if q["key"] and q["file_id"]:
                self.on_nexus_download()
        self.run_bg(_("Consultando Nexus…"), job, done)

    def show_rate(self, rate):
        if rate:
            self.rate_lbl.set_text(_("Peticiones restantes hoy: {day}, esta hora: {hour}",
                                     day=rate.get("x-rl-daily-remaining", "?"),
                                     hour=rate.get("x-rl-hourly-remaining", "?")))

    def on_nexus_download(self):
        _m, it = self.files_tv.get_selection().get_selected()
        if not it or not self.nexus_target.get("mod_id"):
            self.info(_("Busca un mod y elige un archivo de la lista."))
            return
        file_id = self.files_store[it][4]
        f = next(x for x in self.nexus_files if x["file_id"] == file_id)
        t = self.nexus_target
        key = t["key"] if t.get("file_id") == file_id else None
        expires = t["expires"] if key else None
        info = t.get("info", {})
        api = self.nx()
        ctx = self.ctx

        def job(progress):
            url = api.download_url(t["domain"], t["mod_id"], file_id, key, expires)
            total_mb = (f.get("size_kb") or 0) / 1024

            def prog(done, total):
                tot = total or (f.get("size_kb") or 0) * 1024
                progress(done / tot if tot else None,
                         _("Descargando {file}: {done} / {total} MB", file=f.get("file_name", ""),
                           done=f"{done / 1048576:.1f}", total=f"{total_mb:.1f}"))
            path = api.download(url, ctx.downloads, f.get("file_name"), prog, lambda: self.cancel_flag)
            src = {"type": "nexus", "domain": t["domain"], "mod_id": t["mod_id"], "file_id": file_id}
            return ctx.install_archive(path, name=nexus.nice_name(info.get("name"), f), version=f.get("version", ""),
                                       source=src, chooser=self.chooser_threadsafe, progress=progress,
                                       delete_archive=self.mgr.config.get("delete_archives", True))

        def done(mod):
            self.show_rate(api.rate)
            if mod:
                self.set_status(_("Instalado «{name}». Pulsa «Aplicar al juego».", name=mod["name"]), 1)
                self.stack.set_visible_child_name("mods")
        self.run_bg(_("Descargando…"), job, done, cancellable=True)

    def handle_nxm(self, link):
        self.stack.set_visible_child_name("nexus")
        self.mod_entry.set_text(link)
        self.present()
        if not self.busy:
            self.on_nexus_lookup()

    # =========================================================== página Juego
    def build_game_page(self):
        sw = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16)
        sw.add(box)
        self.game_info = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.pack_start(self.game_info, False, False, 0)
        row = Gtk.Box(spacing=8)
        b = Gtk.Button(label=_("Detectar de nuevo"))
        b.connect("clicked", self.on_detect)
        row.pack_start(b, False, False, 0)
        b = Gtk.Button(label=_("Elegir carpeta del juego…"))
        b.connect("clicked", self.on_pick_game_dir)
        row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)

        fr = Gtk.Frame(label=" Script extender ")
        fb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        fr.add(fb)
        self.se_lbl = Gtk.Label(xalign=0, wrap=True)
        fb.pack_start(self.se_lbl, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.se_on = Gtk.Button()
        self.se_on.connect("clicked", self.on_se_enable)
        row.pack_start(self.se_on, False, False, 0)
        self.se_off = Gtk.Button(label=_("Restaurar launcher original"))
        self.se_off.connect("clicked", self.on_se_restore)
        row.pack_start(self.se_off, False, False, 0)
        fb.pack_start(row, False, False, 0)
        box.pack_start(fr, False, False, 0)

        self.fo4_frame = Gtk.Frame(label=" Fallout 4 ")
        fb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.fo4_frame.add(fb)
        lbl = Gtk.Label(xalign=0, wrap=True,
                        label=_("Fallout 4 ignora las texturas/mallas sueltas de los mods y su lista de plugins "
                                "hasta que se cambian dos ajustes en sus INI. Hazlo una vez."))
        fb.pack_start(lbl, False, False, 0)
        b = Gtk.Button(label=_("Activar mods en los INI"), halign=Gtk.Align.START)
        b.connect("clicked", self.on_fo4_ini)
        fb.pack_start(b, False, False, 0)
        box.pack_start(self.fo4_frame, False, False, 0)

        fr = Gtk.Frame(label=" " + _("Opciones") + " ")
        fb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        fr.add(fb)
        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label=_("Idioma:")), False, False, 0)
        self.lang_combo = Gtk.ComboBoxText()
        self.lang_combo.append("auto", _("Automático (el del sistema)"))
        for code, name in i18n.available().items():
            self.lang_combo.append(code, name)
        self.lang_combo.set_active_id(self.mgr.config.get("language", "auto"))
        if self.lang_combo.get_active_id() is None:
            self.lang_combo.set_active_id("auto")
        self.lang_combo.connect("changed", self.on_lang_changed)
        row.pack_start(self.lang_combo, False, False, 0)
        fb.pack_start(row, False, False, 0)
        self.del_chk = Gtk.CheckButton(label=_("Borrar el archivo descargado de Nexus tras instalarlo (ahorra espacio)"))
        self.del_chk.set_active(self.mgr.config.get("delete_archives", True))
        self.del_chk.connect("toggled", self.on_del_toggled)
        fb.pack_start(self.del_chk, False, False, 0)
        b = Gtk.Button(label=_("Quitar TODOS los mods del juego (dejarlo como de fábrica)"), halign=Gtk.Align.START)
        b.get_style_context().add_class("destructive-action")
        b.connect("clicked", self.on_purge)
        fb.pack_start(b, False, False, 0)
        box.pack_start(fr, False, False, 0)
        ver = Gtk.Label(xalign=0, label=f"Konkr Mod Manager {__version__}")
        ver.get_style_context().add_class("dim")
        box.pack_end(ver, False, False, 0)
        return sw

    def refresh_game(self):
        c = self.ctx
        g = GAMES[self.game_key]

        def mark(ok, yes, no):
            return OK.format("✔ " + esc(yes)) if ok else BAD.format("✘ " + esc(no))
        lines = [f"<span size='x-large' weight='bold'>{esc(g['name'])}</span>",
                 mark(c.found, _("Juego encontrado"), _("Juego no encontrado: instálalo en Steam o elige su carpeta"))]
        if c.found:
            lines.append(DIM.format(esc(_("Carpeta:"))) + " " + esc(c.game_dir))
            lines.append(mark(c.prefix_ok, _("Prefijo de Proton listo"),
                              _("Falta el prefijo de Proton: abre el juego una vez desde Steam y ciérralo")))
            lines.append(DIM.format("plugins.txt:") + " " + esc(c.plugins_txt or "-"))
            lines.append(DIM.format(esc(_("Mods guardados en:"))) + " " + esc(c.staging))
        self.game_info.set_markup("\n".join(lines))
        s = c.se_status() if c.found else {}
        se = g["se_name"]
        if not c.found:
            self.se_lbl.set_text("—")
        elif not s.get("loader"):
            self.se_lbl.set_markup(WARN.format(esc(_("{se} no instalado.", se=se))) + " " + esc(
                _("Descárgalo (el archivo que trae {loader}), añádelo como mod y pulsa Aplicar. Su versión "
                  "tiene que coincidir con la del juego.", loader=g["loader"])))
        elif s.get("swapped"):
            self.se_lbl.set_markup(OK.format(esc(_("{se} activo.", se=se))) + " " + esc(
                _("Al darle a Jugar en Steam arranca {loader}. Si Steam actualiza el juego, vuelve aquí.",
                  loader=g["loader"])))
        else:
            self.se_lbl.set_markup(WARN.format(esc(_("{se} instalado pero no activo.", se=se))) + " " + esc(
                _("Pulsa el botón para que Steam lo arranque al darle a Jugar.")))
        self.se_on.set_label(_("Arrancar con {se}", se=se))
        self.se_on.set_sensitive(bool(s.get("loader")) and not s.get("swapped"))
        self.se_off.set_sensitive(bool(s.get("orig")))
        self.fo4_frame.set_visible(self.game_key == "fallout4")

    def on_detect(self, *a):
        d = self.ctx.detect()
        self.refresh_all()
        if not d:
            self.error(_("No lo encuentro en tus bibliotecas de Steam."),
                       _("Si está instalado, usa «Elegir carpeta del juego…»."))

    def on_pick_game_dir(self, *a):
        d = Gtk.FileChooserDialog(title=_("Carpeta del juego (la que contiene Data)"), transient_for=self,
                                  action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons(_("Cancelar"), Gtk.ResponseType.CANCEL, _("Elegir"), Gtk.ResponseType.OK)
        if d.run() == Gtk.ResponseType.OK:
            path = d.get_filename()
            from .games import ci_find
            data = ci_find(path, "Data") if path else None
            if data and os.path.isdir(data):
                self.ctx.set_game_dir(path)
            else:
                self.error(_("Esa carpeta no tiene «Data»."))
        d.destroy()
        self.refresh_all()

    def on_se_enable(self, *a):
        try:
            self.ctx.se_enable()
        except (core.ModError, OSError) as e:
            self.error(str(e))
        self.refresh_all()

    def on_se_restore(self, *a):
        try:
            self.ctx.se_restore()
        except (core.ModError, OSError) as e:
            self.error(str(e))
        self.refresh_all()

    def on_fo4_ini(self, *a):
        try:
            self.ctx.fix_loose_files_ini()
            self.info(_("Listo"), _("Fallout4Custom.ini y Fallout4Prefs.ini ajustados (hay copia .kmm-orig)."))
        except (core.ModError, OSError) as e:
            self.error(str(e))

    def on_del_toggled(self, b):
        self.mgr.config["delete_archives"] = b.get_active()
        self.mgr.save_config()

    def on_lang_changed(self, combo):
        code = combo.get_active_id() or "auto"
        self.mgr.config["language"] = code
        self.mgr.save_config()
        new = i18n.resolve(code)
        old = i18n.current()
        i18n.set_language(code)
        if new != old:
            self.info(_("Idioma cambiado"), _("Cierra y vuelve a abrir el programa para ver el nuevo idioma."))
            i18n.set_language(old)  # la ventana actual sigue en el idioma con el que se creó

    def on_purge(self, *a):
        if self.confirm(_("¿Quitar todos los mods del juego?"),
                        _("Se borran del juego los archivos puestos por el gestor y se restauran los originales. "
                          "Tu lista de mods se conserva: puedes volver a Aplicar cuando quieras.")):
            self.run_bg(_("Restaurando el juego…"), lambda p: self.ctx.purge(p),
                        lambda n: self.set_status(_("Juego restaurado ({n} archivos quitados)", n=n), 1))

    # =========================================================== móvil
    def build_phone_page(self):
        sw = Gtk.ScrolledWindow()
        box = Gtk.Box(spacing=28, margin=20)
        sw.add(box)
        self.qr_img = Gtk.Image(valign=Gtk.Align.START)
        self.qr_img.set_size_request(300, 300)
        box.pack_start(self.qr_img, False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.pack_start(col, True, True, 0)
        row = Gtk.Box(spacing=12)
        t = Gtk.Label(xalign=0)
        t.set_markup(f"<span size='x-large' weight='bold'>{esc(_('App del móvil'))}</span>")
        row.pack_start(t, True, True, 0)
        self.phone_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.phone_switch.set_active(self.mgr.config.get("companion", {}).get("enabled", True))
        self.phone_switch.connect("notify::active", self.on_phone_switch)
        row.pack_end(self.phone_switch, False, False, 0)
        col.pack_start(row, False, False, 0)
        self.phone_info = Gtk.Label(xalign=0, wrap=True, selectable=True)
        col.pack_start(self.phone_info, False, False, 0)
        steps = Gtk.Label(xalign=0, wrap=True)
        steps.set_markup(
            "1. " + esc(_("Conecta el móvil a la misma Wi-Fi que la consola.")) + "\n"
            "2. " + esc(_("Escanea el código con la cámara (o escribe la dirección en el navegador y luego el PIN).")) + "\n"
            "3. " + esc(_("En el navegador del móvil: menú → Añadir a pantalla de inicio, para tenerla como una app.")) +
            "\n\n" + DIM.format(esc(_("Desde el móvil puedes explorar y buscar mods de Nexus, enviarlos a la consola, "
                                      "activarlos, ordenarlos y aplicar. Funciona mientras este programa esté abierto "
                                      "o el servicio en segundo plano esté activado (ver README)."))))
        col.pack_start(steps, False, False, 0)
        b = Gtk.Button(label=_("Cambiar PIN (desconecta los móviles emparejados)"), halign=Gtk.Align.START)
        b.connect("clicked", self.on_new_pin)
        col.pack_start(b, False, False, 0)
        return sw

    def start_companion(self):
        try:
            if self.companion is None:
                self.companion = server.Companion(self.mgr)
            self.companion.start()
            self.companion_error = ""
        except OSError as e:
            self.companion_error = _("No se pudo abrir el puerto {port}: {error}. ¿Hay otra copia del gestor abierta?",
                                     port=self.mgr.config["companion"].get("port", 8765), error=e.strerror or e)
            self.log_threadsafe(self.companion_error)

    def phone_url(self):
        c = self.companion
        return f"{c.url}/#pin={c.pin}" if c and c.running else None

    def qr_pixbuf(self, text, px=300):
        """Código QR como imagen (sin depender de cairo)."""
        qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
        n = qr.get_size()
        mods = n + 8                       # margen blanco de 4 módulos
        cell = max(1, px // mods)
        side = cell * mods
        white, black = b"\xff\xff\xff", b"\x00\x00\x00"
        rows = []
        for y in range(mods):
            line = b"".join((black if 4 <= x < n + 4 and 4 <= y < n + 4 and qr.get_module(x - 4, y - 4)
                             else white) * cell for x in range(mods))
            rows.extend([line] * cell)
        data = GLib.Bytes.new(b"".join(rows))
        return GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, side, side, side * 3)

    def refresh_phone(self):
        c = self.companion
        if c and c.running:
            active = len(c.queue.active())
            self.phone_info.set_markup(
                OK.format("✔ " + esc(_("Activa"))) + "\n" +
                esc(_("Dirección:")) + f" <span size='large' weight='bold'>{esc(c.url)}</span>\n" +
                f"PIN: <span size='xx-large' weight='bold' letter_spacing='4000'>{esc(c.pin)}</span>" +
                ("\n" + WARN.format(esc(_("Tareas del móvil en curso: {n}", n=active))) if active else ""))
        elif self.companion_error:
            self.phone_info.set_markup(BAD.format("✘ " + esc(self.companion_error)))
        else:
            self.phone_info.set_markup(DIM.format(esc(_("Desactivada. El móvil no puede conectarse."))))
        url = self.phone_url()
        if url:
            self.qr_img.set_from_pixbuf(self.qr_pixbuf(url))
        else:
            self.qr_img.clear()

    def on_phone_switch(self, sw, _p):
        on = sw.get_active()
        self.mgr.config.setdefault("companion", {})["enabled"] = on
        self.mgr.save_config()
        if on and not (self.companion and self.companion.running):
            self.start_companion()
        elif not on and self.companion:
            self.companion.stop()
        self.refresh_phone()

    def on_new_pin(self, *a):
        if self.companion:
            self.companion.new_pin()
            self.refresh_phone()

    def on_external_change(self):
        """Cambios hechos desde el móvil (u otro hilo): refresca si los datos no están en uso."""
        if self.mgr.lock.acquire(blocking=False):
            try:
                if not self.busy:
                    self.refresh_all()
                self.refresh_phone()
            finally:
                self.mgr.lock.release()
        else:
            GLib.timeout_add(700, self.on_external_change)
        return False

    # =========================================================== registro
    def build_log_page(self):
        sw = Gtk.ScrolledWindow(margin=10)
        self.log_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw.add(self.log_view)
        return sw

    # =========================================================== aplicar
    def do_apply(self):
        if not self.ctx.found:
            self.error(_("No encuentro la carpeta del juego."))
            return
        self.run_bg(_("Aplicando mods al juego…"), lambda p: self.ctx.apply(p),
                    lambda stats: self.set_status(_("Aplicado.") + " " + core.stats_text(stats), 1))


class App(Gtk.Application):
    SERVICE = "konkr-modmanager-server.service"

    def __init__(self):
        super().__init__(application_id="io.github.konkr_modmanager",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # Si el servicio en segundo plano está activo, se para mientras la ventana está abierta
        # (los dos usarían los mismos datos y el mismo puerto) y se vuelve a arrancar al salir.
        self.restart_service = False
        try:
            r = subprocess.run(["systemctl", "--user", "is-active", "--quiet", self.SERVICE], timeout=5)
            if r.returncode == 0:
                subprocess.run(["systemctl", "--user", "stop", self.SERVICE], timeout=15)
                self.restart_service = True
        except (OSError, subprocess.TimeoutExpired):
            pass
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_shutdown(self):
        if self.win and self.win.companion:
            self.win.companion.stop()
        if getattr(self, "restart_service", False):
            try:
                subprocess.Popen(["systemctl", "--user", "start", self.SERVICE])
            except OSError:
                pass
        Gtk.Application.do_shutdown(self)

    def do_activate(self):
        if not self.win:
            self.win = MainWindow(self)
            self.win.show_all()
            self.win.cancel_btn.hide()
            self.win.refresh_game()
        self.win.present()

    def do_command_line(self, cmdline):
        self.activate()
        for a in cmdline.get_arguments()[1:]:
            if a.lower().startswith("nxm://"):
                self.win.handle_nxm(a)
        return 0


def main():
    return App().run(sys.argv)
