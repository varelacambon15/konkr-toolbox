"""Interfaz GTK3 (táctil) de Konkr Tweaks."""
import os
import sys
import threading
import traceback

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf, Pango  # noqa: E402

from . import __version__, device, i18n, launchopts, optimize, profiles, settings, steam  # noqa: E402
from .i18n import _  # noqa: E402

CSS = b"""
* { font-size: 15px; }
button { min-height: 40px; padding: 4px 14px; }
list row { padding: 6px 8px; }
.title-big { font-size: 22px; font-weight: bold; }
.dim { opacity: 0.7; }
.card { padding: 4px 0; }
"""
OK = "<span foreground='#6fcf73'>{}</span>"
WARN = "<span foreground='#f0b34a'>{}</span>"
DIM = "<span alpha='70%'>{}</span>"
DEFAULTS_ID = 0


def esc(s):
    return GLib.markup_escape_text(str(s))


def preset_label(key):
    return {"lowest": _("Mínimo"), "battery": _("Mínimo"), "balanced": _("Medio"), "quality": _("Alto")}.get(key, key)


def mode_label(key):
    return {"max": _("Máximo rendimiento"), "perf": _("Rendimiento"), "balanced": _("Equilibrado"),
            "quality": _("Calidad"), "battery": _("Batería")}.get(key, key)


def mode_hint(key):
    return {"max": _("Lo más bajo posible y el traductor FEX más rápido. Si el juego se cierra o hace cosas raras, usa Rendimiento."),
            "perf": _("Gráficos al mínimo a 1280 × 720. Lo más fluido sin arriesgar estabilidad."),
            "balanced": _("Gráficos medios a 1280 × 720. Buen aspecto y fps estables."),
            "quality": _("Gráficos altos a 1920 × 1080. Para juegos ligeros o antiguos."),
            "battery": _("Gráficos al mínimo y límite de 30 fps: menos calor y más horas de batería.")}.get(key, "")


class GameRow(Gtk.ListBoxRow):
    def __init__(self, game):
        super().__init__()
        self.game = game
        box = Gtk.Box(spacing=10)
        self.img = Gtk.Image()
        self.img.set_size_request(120, 56)
        box.pack_start(self.img, False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        self.name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=26)
        self.name.set_markup(f"<b>{esc(game['name'])}</b>")
        self.badges = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=30)
        col.pack_start(self.name, False, False, 0)
        col.pack_start(self.badges, False, False, 0)
        box.pack_start(col, True, True, 0)
        self.add(box)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Konkr Tweaks")
        self.set_default_size(1280, 780)
        self.cfg = settings.app_config()
        i18n.set_language(self.cfg.get("language", "auto"))
        self.root = steam.steam_root()
        self.dev = device.info()
        self.profiles = profiles.load_all()
        self.games = []
        self.launch_opts = {}
        self.current = None
        self.loading = False
        self.busy = False

        hb = Gtk.HeaderBar(show_close_button=True)
        hb.props.title = "Konkr Tweaks"
        hb.props.subtitle = _("Optimizaciones por juego")
        self.set_titlebar(hb)
        self.all_btn = Gtk.Button(label=_("Activar en todos los juegos"))
        self.all_btn.connect("clicked", self.on_activate_all)
        hb.pack_end(self.all_btn)
        gear = Gtk.Button(label=_("Opciones"))
        gear.connect("clicked", self.on_about)
        hb.pack_end(gear)
        refresh = Gtk.Button(label=_("Actualizar lista"))
        refresh.connect("clicked", lambda *a: self.reload())
        hb.pack_start(refresh)

        paned = Gtk.Paned()
        self.add(paned)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        left.set_size_request(400, -1)
        self.search = Gtk.SearchEntry(placeholder_text=_("Buscar juego"))
        self.search.connect("search-changed", lambda *a: self.listbox.invalidate_filter())
        left.pack_start(self.search, False, False, 0)
        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        self.listbox.connect("row-selected", self.on_row_selected)
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sw.add(self.listbox)
        left.pack_start(sw, True, True, 0)
        paned.pack1(left, False, False)

        self.detail_sw = Gtk.ScrolledWindow()
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=18)
        self.detail_sw.add(self.detail)
        paned.pack2(self.detail_sw, True, False)

        self.status = Gtk.Label(xalign=0, margin=6)
        self.reload()

    # ================================================================ datos
    def reload(self):
        self.games = steam.installed_games(self.root) if self.root else []
        self.launch_opts = steam.all_launch_options(self.root) if self.root else {}
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        row = GameRow({"appid": DEFAULTS_ID, "name": _("Ajustes por defecto (todos los juegos)")})
        row.img.set_from_icon_name("preferences-system", Gtk.IconSize.DIALOG)
        self.listbox.add(row)
        self.rows = {}
        for g in self.games:
            r = GameRow(g)
            self.rows[g["appid"]] = r
            self.listbox.add(r)
        self.refresh_badges()
        self.listbox.show_all()
        GLib.idle_add(self._load_images, list(self.games))
        sel = self.current["appid"] if self.current else DEFAULTS_ID
        for r in self.listbox.get_children():
            if r.game["appid"] == sel:
                self.listbox.select_row(r)
                break
        if not self.root:
            self.show_message(_("No encuentro Steam"), _("No hay ninguna instalación de Steam en esta cuenta."))
        elif not self.games:
            self.show_message(_("No hay juegos instalados"), _("Instala algún juego en Steam y vuelve a abrir el programa."))

    def _load_images(self, pending):
        for _i in range(6):
            if not pending:
                return False
            g = pending.pop(0)
            r = self.rows.get(g["appid"])
            path = steam.cover_image(g["appid"], self.root)
            if r and path:
                try:
                    r.img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 120, 56, True))
                except GLib.Error:
                    pass
        return True

    def _filter(self, row):
        q = self.search.get_text().strip().lower()
        return not q or row.game["appid"] == DEFAULTS_ID or q in row.game["name"].lower()

    def refresh_badges(self):
        for appid, r in self.rows.items():
            st = settings.game_state(appid)
            marks = []
            if settings.wrapper_active(self.launch_opts.get(appid, "")):
                marks.append(OK.format("● " + esc(_("Activo"))))
            extra = []
            if st.get("custom"):
                extra.append(_("Ajustes propios"))
            if st.get("mode"):
                extra.append(mode_label(st["mode"]))
            elif st.get("profile"):
                extra.append(preset_label(st["profile"]))
            if extra:
                marks.append(DIM.format(esc(" · ".join(extra))))
            r.badges.set_markup("  ".join(marks))

    def show_message(self, title, text):
        self._clear()
        t = Gtk.Label(xalign=0)
        t.set_markup(f"<span size='x-large' weight='bold'>{esc(title)}</span>")
        self.detail.pack_start(t, False, False, 0)
        self.detail.pack_start(Gtk.Label(label=text, xalign=0, wrap=True), False, False, 0)
        self.detail.show_all()

    def _clear(self):
        for c in self.detail.get_children():
            self.detail.remove(c)

    # ================================================================ detalle
    def on_row_selected(self, _lb, row):
        if not row:
            return
        self.current = row.game
        self.build_detail()

    def build_detail(self):
        g = self.current
        self._clear()
        is_default = g["appid"] == DEFAULTS_ID
        # ---- cabecera
        head = Gtk.Box(spacing=16)
        path = None if is_default else steam.cover_image(g["appid"], self.root)
        if path:
            try:
                head.pack_start(Gtk.Image.new_from_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 300, 140, True)), False, False, 0)
            except GLib.Error:
                pass
        hcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        t = Gtk.Label(xalign=0, wrap=True)
        t.set_markup(f"<span size='x-large' weight='bold'>{esc(g['name'])}</span>")
        hcol.pack_start(t, False, False, 0)
        if is_default:
            hcol.pack_start(Gtk.Label(xalign=0, wrap=True, max_width_chars=60, label=_(
                "Se usan en todos los juegos que tengan el lanzador activado y no tengan ajustes propios.")), False, False, 0)
            d = self.dev
            dev_l = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
            dev_l.set_markup(DIM.format(esc(_("Este equipo: {model}{cpu}, {ram} GB de RAM, {arch}.",
                                               model=(d["model"] + ", ") if d["model"] else "", cpu=d["cpu"],
                                               ram=d["ram_gb"], arch=d["arch"]))))
            hcol.pack_start(dev_l, False, False, 0)
            b = Gtk.Button(label=_("Usar los recomendados para este equipo"), halign=Gtk.Align.START)
            b.get_style_context().add_class("suggested-action")
            b.connect("clicked", self.on_recommended_defaults)
            hcol.pack_start(b, False, False, 0)
        else:
            sub = Gtk.Label(xalign=0)
            sub.set_markup(DIM.format(esc(f"AppID {g['appid']}" + ("" if g.get("proton") else " · " + _("sin Proton (juego nativo o aún no lanzado)")))))
            hcol.pack_start(sub, False, False, 0)
            b = Gtk.Button(label=_("Optimizar para este equipo ({m})", m=mode_label(optimize.recommended_mode(self.dev))), halign=Gtk.Align.START)
            b.get_style_context().add_class("suggested-action")
            b.connect("clicked", lambda *a: self.on_auto(g))
            hcol.pack_start(b, False, False, 0)
        head.pack_start(hcol, True, True, 0)
        self.detail.pack_start(head, False, False, 0)

        if not is_default:
            self.detail.pack_start(self.build_wrapper_frame(g), False, False, 0)
            self.detail.pack_start(self.build_mode_frame(g), False, False, 0)
        self.detail.pack_start(self.build_launch_frame(g, is_default), False, False, 0)
        self.detail.show_all()
        self.detail_sw.get_vadjustment().set_value(0)

    def on_recommended_defaults(self, *a):
        settings.save_defaults(optimize.recommended_defaults(self.dev))
        self.build_detail()
        self.toast(_("Ajustes por defecto recomendados guardados."))

    def on_auto(self, g):
        self.run_mode(g, optimize.recommended_mode(self.dev), title=_("Optimizado para este equipo"))

    def run_mode(self, g, mode, resolution=None, lock=None, title=None):
        try:
            r = optimize.apply_mode(g, mode, self.profiles, self.dev, resolution=resolution, lock=lock)
        except OSError as e:
            self.error(_("No se pudo guardar"), str(e))
            return
        lines = ["✔ " + _("Modo: {m}", m=mode_label(mode))]
        la = r["launch"]
        parts = []
        if la.get("fex") and la["fex"] != "none":
            parts.append(_("traductor FEX «{p}»", p=la["fex"]))
        if la.get("ntsync"):
            parts.append("NTSync")
        if la.get("deck"):
            parts.append(_("modo Steam Deck"))
        if la.get("fps"):
            parts.append(_("límite de {n} fps", n=la["fps"]))
        lines.append("✔ " + _("Arranque: {what}.", what=", ".join(parts) if parts else _("sin cambios")))
        if r["args"]:
            lines.append("✔ " + _("Argumentos del perfil: {args}", args=r["args"]))
        if r["preset"]:
            lines.append("✔ " + _("Gráficos: {p}", p=preset_label(r["preset"])) +
                         (" · " + r["resolution"] if r["resolution"] else ""))
        elif r["missing"]:
            lines.append("• " + _("Perfil gráfico pendiente: abre el juego una vez desde Steam, ciérralo y vuelve a aplicar el modo."))
        elif not r["profile"]:
            lines.append("• " + _("Este juego no tiene perfil gráfico propio: ajusta la calidad dentro del juego y usa 1280 × 720."))
        if not settings.wrapper_active(self.launch_opts.get(g["appid"], "")):
            lines.append("• " + _("Falta activar el lanzador para que se aplique el arranque."))
        if mode == "max" and la.get("fex") == "fastest":
            lines.append("• " + _("El traductor «fastest» puede cerrar algunos juegos. Si pasa, elige Rendimiento."))
        lines.append("")
        lines.append(_("Consejo: activa el escalado FSR en el menú rápido de Steam."))
        self.refresh_badges()
        self.build_detail()
        self.info(title or _("Modo aplicado"), "\n".join(lines))
        if not settings.wrapper_active(self.launch_opts.get(g["appid"], "")) and \
                self.confirm(_("¿Activar el lanzador ahora?"), _("Sin él, los ajustes de arranque no se aplican.")):
            self.set_wrapper([g["appid"]], True)

    # ---- lanzador ----------------------------------------------------------------
    def build_wrapper_frame(self, g):
        fr = Gtk.Frame(label=" " + _("Lanzador") + " ")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        fr.add(box)
        lo = self.launch_opts.get(g["appid"], "")
        active = settings.wrapper_active(lo)
        lbl = Gtk.Label(xalign=0, wrap=True)
        if active:
            lbl.set_markup(OK.format("✔ " + esc(_("Activo: los ajustes de abajo se aplican cada vez que abres el juego."))))
        else:
            lbl.set_markup(WARN.format(esc(_("No activo."))) + " " + esc(_(
                "Para que los ajustes generales funcionen, hay que añadir el lanzador a las opciones de lanzamiento "
                "del juego. Solo se hace una vez.")))
        box.pack_start(lbl, False, False, 0)
        if lo:
            cur = Gtk.Label(xalign=0, wrap=True, selectable=True)
            cur.set_markup(DIM.format(esc(_("Opciones de lanzamiento actuales:"))) + f" <tt>{esc(lo)}</tt>")
            box.pack_start(cur, False, False, 0)
        row = Gtk.Box(spacing=8)
        b = Gtk.Button(label=_("Desactivar") if active else _("Activar"))
        if not active:
            b.get_style_context().add_class("suggested-action")
        b.connect("clicked", lambda *a: self.set_wrapper([g["appid"]], not active))
        row.pack_start(b, False, False, 0)
        if not active:
            cp = Gtk.Button(label=_("Copiar texto para ponerlo a mano"))
            cp.connect("clicked", lambda *a: self.copy_manual(g))
            row.pack_start(cp, False, False, 0)
        box.pack_start(row, False, False, 0)
        return fr

    def copy_manual(self, g):
        new, _fex = settings.with_wrapper(self.launch_opts.get(g["appid"], ""))
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(new, -1)
        self.info(_("Copiado"), _("En Steam: juego → Propiedades → General → Opciones de lanzamiento, y pega:") +
                  "\n\n" + new)

    def set_wrapper(self, appids, enable):
        changes, imported = {}, {}
        for a in appids:
            lo = self.launch_opts.get(a, "")
            if enable:
                new, fex = settings.with_wrapper(lo)
                if fex:
                    imported[a] = fex
            else:
                new = settings.without_wrapper(lo)
            if new != lo:
                changes[a] = new
        if not changes:
            return
        if steam.steam_running():
            if steam.in_game_mode():
                self.info(_("Steam está abierto"),
                          _("En Modo Juego no se pueden cambiar las opciones de lanzamiento desde aquí. Usa «Copiar texto "
                            "para ponerlo a mano» o abre este programa en Modo Escritorio."))
                return
            if not self.confirm(_("Hay que cerrar Steam un momento"),
                                _("Steam guarda las opciones de lanzamiento al cerrarse y pisaría el cambio. "
                                  "¿Cierro Steam, aplico el cambio y lo vuelvo a abrir?")):
                return
        self._apply_launch(changes, imported, manual=False)

    def _apply_launch(self, changes, imported, manual):
        def done(res):
            self.reload()
            if res == "steam-not-started":
                self.info(_("Cambio aplicado"), _("No he podido volver a abrir Steam. Ábrelo tú desde el menú."))
            else:
                self.toast(_("Hecho: {n} juego(s) actualizados.", n=len(changes)))

        def failed(err):
            if str(err) != "steam-wont-close":
                return False
            if self.confirm(_("Steam no se cierra solo"),
                            _("Ciérralo tú: en la ventana de Steam, menú Steam → Salir (o clic derecho en su icono "
                              "de la bandeja → Salir). Después pulsa Aceptar y aplico el cambio.")):
                self._apply_launch(changes, imported, manual=True)
            return True
        label = _("Esperando a que Steam se cierre…") if manual else (
            _("Cerrando Steam y aplicando… (puede tardar un minuto)") if steam.steam_running() else _("Aplicando…"))
        self.run_bg(label, lambda: self._write_launch(changes, imported, manual), done, failed)

    def _write_launch(self, changes, imported, manual=False):
        restart = False
        if steam.steam_running():
            closed = steam._wait_closed(90) if manual else steam.shutdown_steam()
            if not closed:
                raise RuntimeError("steam-wont-close")
            restart = True
        steam.set_launch_options(changes, self.root, os.path.join(settings.DATA_DIR, "backups", "steam"))
        for appid, fex in imported.items():
            st = settings.game_state(appid)
            launch = st.get("launch") or settings.defaults()
            launch["fex"] = fex
            st["launch"], st["custom"] = launch, True
            settings.save_game_state(appid, st)
        if restart and not steam.start_steam():
            return "steam-not-started"

    def on_activate_all(self, *a):
        ids = [g["appid"] for g in self.games if g.get("proton") and not settings.wrapper_active(self.launch_opts.get(g["appid"], ""))]
        if not ids:
            self.info(_("Nada que hacer"), _("Todos los juegos con Proton ya tienen el lanzador."))
            return
        if self.confirm(_("Activar el lanzador en {n} juegos", n=len(ids)),
                        _("Se añade a sus opciones de lanzamiento (las que ya tengan se conservan). "
                          "Mientras no les pongas ajustes, arrancan exactamente igual que ahora.")):
            self.set_wrapper(ids, True)

    # ---- ajustes generales -------------------------------------------------------
    def build_launch_frame(self, g, is_default):
        fr = Gtk.Frame(label=" " + _("Ajustes al arrancar") + " ")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        fr.add(box)
        if is_default:
            values, custom = settings.defaults(), True
        else:
            values, custom = settings.effective(g["appid"])
            row = Gtk.Box(spacing=10)
            sw = Gtk.Switch(active=custom, valign=Gtk.Align.CENTER)
            row.pack_start(sw, False, False, 0)
            row.pack_start(Gtk.Label(label=_("Ajustes propios para este juego (si no, usa los de por defecto)"),
                                     xalign=0, wrap=True), True, True, 0)
            box.pack_start(row, False, False, 0)
        grid = Gtk.Grid(column_spacing=14, row_spacing=10)
        box.pack_start(grid, False, False, 0)
        widgets = {}
        r = 0

        def add(label, widget, hint=None):
            nonlocal r
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)
            if hint:
                h = Gtk.Label(xalign=0, wrap=True, max_width_chars=48)
                h.set_markup(DIM.format(esc(hint)))
                grid.attach(h, 2, r, 1, 1)
            r += 1

        ints = set()
        for grp in launchopts.GROUPS:
            opts = [o for o in launchopts.catalog() if o["group"] == grp]
            if not opts:
                continue
            hdr = Gtk.Label(xalign=0, margin_top=6 if r else 0)
            hdr.set_markup(f"<b>{esc(launchopts.group_label(grp))}</b>")
            grid.attach(hdr, 0, r, 3, 1)
            r += 1
            for o in opts:
                avail = o.get("avail", True)
                if o.get("only_if_avail") and not avail and values.get(o["key"]) in (None, "none", ""):
                    continue
                if o["kind"] == "choice":
                    w = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
                    for v, lbl in o["choices"]:
                        w.append(str(v), lbl)
                    cur = str(values.get(o["key"], o["choices"][0][0]))
                    w.set_active_id(cur if cur in [str(v) for v, _l in o["choices"]] else str(o["choices"][0][0]))
                    if o.get("int"):
                        ints.add(o["key"])
                else:
                    w = Gtk.Switch(active=bool(values.get(o["key"])), halign=Gtk.Align.START,
                                   valign=Gtk.Align.CENTER, sensitive=avail)
                widgets[o["key"]] = w
                add(o["label"], w, o["hint"] if avail else _("No está disponible en este equipo."))
        e = Gtk.Entry(text=values.get("args", ""), placeholder_text="-skipintro -windowed …", width_chars=28)
        widgets["args"] = e
        add(_("Argumentos del juego"), e)
        e2 = Gtk.Entry(text=values.get("env", ""), placeholder_text="VARIABLE=valor OTRA=1", width_chars=28)
        widgets["env"] = e2
        add(_("Variables de entorno"), e2)

        def collect():
            out = dict(values)
            for k, w in widgets.items():
                if isinstance(w, Gtk.Switch):
                    out[k] = w.get_active()
                elif isinstance(w, Gtk.ComboBoxText):
                    out[k] = int(w.get_active_id()) if k in ints else w.get_active_id()
                else:
                    out[k] = w.get_text().strip()
            return out

        def save(*_a):
            if is_default:
                settings.save_defaults(collect())
            else:
                st = settings.game_state(g["appid"])
                st["custom"] = True
                st["launch"] = collect()
                settings.save_game_state(g["appid"], st)
                self.refresh_badges()
            self.toast(_("Guardado. Se aplica la próxima vez que abras el juego."))

        for k, w in widgets.items():
            if isinstance(w, Gtk.Switch):
                w.connect("notify::active", save)
            elif isinstance(w, Gtk.ComboBoxText):
                w.connect("changed", save)
            else:
                w.connect("activate", save)
                w.connect("focus-out-event", lambda *a: (save(), False)[1])
        if not is_default:
            grid.set_sensitive(custom)

            def on_custom(sw, _p):
                st = settings.game_state(g["appid"])
                st["custom"] = sw.get_active()
                if sw.get_active() and "launch" not in st:
                    st["launch"] = settings.defaults()
                settings.save_game_state(g["appid"], st)
                self.refresh_badges()
                self.build_detail()
            sw.connect("notify::active", on_custom)
        return fr

    # ---- modo -------------------------------------------------------------------
    def build_mode_frame(self, g):
        fr = Gtk.Frame(label=" " + _("Modo") + " ")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        fr.add(box)
        gp = profiles.for_game(g, self.profiles)
        st = settings.game_state(g["appid"])
        missing = gp.missing_files() if gp else []

        row = Gtk.Box(spacing=6)
        radios = {}
        group = None
        for key in optimize.MODES:
            rb = Gtk.RadioButton.new_with_label_from_widget(group, mode_label(key))
            group = group or rb
            rb.set_mode(False)  # aspecto de botón (cómodo en táctil)
            radios[key] = rb
            row.pack_start(rb, True, True, 0)
        box.pack_start(row, False, False, 0)
        hint = Gtk.Label(xalign=0, wrap=True, max_width_chars=90)
        box.pack_start(hint, False, False, 0)
        what = Gtk.Label(xalign=0, wrap=True, max_width_chars=90)
        box.pack_start(what, False, False, 0)

        def selected():
            return next((k for k, rb in radios.items() if rb.get_active()), "perf")

        def describe(*_a):
            m = selected()
            pl = optimize.plan(m, gp, self.dev)
            hint.set_text(mode_hint(m))
            bits = []
            if pl["preset"] and not missing:
                bits.append(_("Gráficos: {p}", p=preset_label(pl["preset"])))
            if pl["resolution"] and not missing:
                bits.append(pl["resolution"].replace("x", " × "))
            if pl["launch"].get("fex") not in (None, "none"):
                bits.append("FEX " + pl["launch"]["fex"])
            bits.append(_("límite de {n} fps", n=pl["fps"]) if pl["fps"] else _("sin límite de fps"))
            if pl["launch"].get("deck"):
                bits.append(_("modo Steam Deck"))
            what.set_markup(DIM.format(esc(" · ".join(bits))))
        for rb in radios.values():
            rb.connect("toggled", describe)
        radios[st.get("mode") if st.get("mode") in radios else optimize.recommended_mode(self.dev)].set_active(True)
        describe()

        # ---- perfil gráfico del juego
        if gp:
            title = Gtk.Label(xalign=0, wrap=True)
            title.set_markup(_("Perfil gráfico") + f": <b>{esc(gp.p.get('name', ''))}</b>" +
                             (" " + WARN.format(esc(_("(experimental)"))) if gp.p.get("experimental") else ""))
            box.pack_start(title, False, False, 0)
            box.pack_start(Gtk.Label(label=profiles.text(gp.p.get("notes"), i18n.current()), xalign=0, wrap=True,
                                     max_width_chars=90), False, False, 0)
        else:
            box.pack_start(Gtk.Label(xalign=0, wrap=True, max_width_chars=90, label=_(
                "Este juego no tiene perfil gráfico: el modo solo cambia los ajustes de arranque. "
                "Baja la calidad dentro del juego. Se pueden añadir perfiles nuevos (ver README).")), False, False, 0)
        if missing:
            m = Gtk.Label(xalign=0, wrap=True)
            m.set_markup(WARN.format(esc(_("Falta el archivo de configuración: de momento solo se aplica el arranque. "
                                           "Abre el juego una vez desde Steam, ciérralo y vuelve aquí."))) +
                         "\n" + DIM.format(esc(gp.files[missing[0]])))
            box.pack_start(m, False, False, 0)

        res_combo = lock_chk = None
        if gp and not missing and gp.p.get("resolution"):
            rrow = Gtk.Box(spacing=8)
            rrow.pack_start(Gtk.Label(label=_("Resolución interna:")), False, False, 0)
            res_combo = Gtk.ComboBoxText()
            res_combo.append("auto", _("Según el modo"))
            res_combo.append("", _("No cambiar ({res})", res=gp.current_resolution() or "?"))
            for c in gp.p["resolution"].get("choices", []):
                res_combo.append(c, c.replace("x", " × "))
            res_combo.set_active_id("auto")
            rrow.pack_start(res_combo, False, False, 0)
            box.pack_start(rrow, False, False, 0)
        if gp and not missing and gp.lockable():
            lock_chk = Gtk.CheckButton(label=_("Proteger el archivo (solo lectura) para que el juego no deshaga los cambios"))
            lock_chk.set_active(st.get("locked", True))
            box.pack_start(lock_chk, False, False, 0)

        brow = Gtk.Box(spacing=8)
        apply_b = Gtk.Button(label=_("Aplicar modo"))
        apply_b.get_style_context().add_class("suggested-action")
        brow.pack_start(apply_b, False, False, 0)
        if gp:
            restore_b = Gtk.Button(label=_("Restaurar original"))
            restore_b.set_sensitive(gp.has_backup())
            brow.pack_start(restore_b, False, False, 0)
        box.pack_start(brow, False, False, 0)
        if st.get("mode"):
            cur = Gtk.Label(xalign=0)
            cur.set_markup(OK.format("✔ " + esc(_("Aplicado: {what}", what=", ".join(
                x for x in (mode_label(st["mode"]), st.get("resolution", "").replace("x", " × ")) if x)))))
            box.pack_start(cur, False, False, 0)

        def do_apply(*_a):
            res = res_combo.get_active_id() if res_combo else None
            self.run_mode(g, selected(), resolution=None if res in (None, "auto") else res,
                          lock=lock_chk.get_active() if lock_chk else None)

        def do_restore(*_a):
            if self.confirm(_("¿Restaurar la configuración original?"),
                            _("Se vuelve a poner el archivo tal como estaba antes del primer cambio. "
                              "Los ajustes de arranque se mantienen.")):
                gp.restore()
                self.refresh_badges()
                self.build_detail()
                self.toast(_("Configuración original restaurada."))
        apply_b.connect("clicked", do_apply)
        if gp:
            restore_b.connect("clicked", do_restore)
        return fr

    # ================================================================ utilidades
    def toast(self, text):
        self.get_titlebar().props.subtitle = text
        GLib.timeout_add_seconds(5, lambda: (setattr(self.get_titlebar().props, "subtitle",
                                                     _("Optimizaciones por juego")), False)[1])

    def _dialog(self, kind, buttons, title, detail):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind, buttons=buttons, text=title)
        if detail:
            d.format_secondary_text(detail)
        r = d.run()
        d.destroy()
        return r

    def info(self, title, detail=""):
        self._dialog(Gtk.MessageType.INFO, Gtk.ButtonsType.OK, title, detail)

    def error(self, title, detail=""):
        self._dialog(Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, title, detail)

    def confirm(self, title, detail=""):
        return self._dialog(Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, title, detail) == Gtk.ResponseType.YES

    def run_bg(self, label, fn, done, on_error=None):
        if self.busy:
            return
        self.busy = True
        self.set_sensitive(False)
        self.get_titlebar().props.subtitle = "⏳ " + label   # se queda hasta que termine

        def worker():
            try:
                res, err = fn(), None
            except Exception as e:  # noqa
                res, err = None, e
                traceback.print_exc()
            GLib.idle_add(finish, res, err)

        def finish(res, err):
            self.busy = False
            self.set_sensitive(True)
            self.get_titlebar().props.subtitle = _("Optimizaciones por juego")
            if err and on_error and on_error(err):
                return False
            if err:
                msg = {"steam-wont-close": _("Steam no se ha cerrado. Ciérralo tú y vuelve a intentarlo."),"steam-running": _("Steam sigue abierto."),
                       "no-localconfig": _("No encuentro la configuración de usuario de Steam (inicia sesión en Steam una vez).")
                       }.get(str(err), str(err))
                self.error(_("No se pudo aplicar"), msg)
            else:
                done(res)
            return False
        threading.Thread(target=worker, daemon=True).start()

    def on_about(self, *a):
        d = Gtk.Dialog(title="Konkr Tweaks", transient_for=self, modal=True)
        d.add_button(_("Cerrar"), Gtk.ResponseType.CLOSE)
        area = d.get_content_area()
        area.set_spacing(10)
        area.set_border_width(16)
        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label=_("Idioma:")), False, False, 0)
        combo = Gtk.ComboBoxText()
        combo.append("auto", _("Automático (el del sistema)"))
        for code, name in i18n.available().items():
            combo.append(code, name)
        combo.set_active_id(self.cfg.get("language", "auto"))
        if combo.get_active_id() is None:
            combo.set_active_id("auto")
        row.pack_start(combo, False, False, 0)
        area.pack_start(row, False, False, 0)
        info = Gtk.Label(xalign=0, wrap=True, max_width_chars=60, selectable=True)
        info.set_markup(esc(f"Konkr Tweaks {__version__}") + "\n" + DIM.format(esc(
            _("Ajustes guardados en {path}", path=settings.CONFIG_DIR) + "\n" +
            _("Último arranque con el lanzador: {path}", path=os.path.join(settings.STATE_DIR, "last-launch.txt")))))
        area.pack_start(info, False, False, 0)
        d.show_all()
        d.run()
        code = combo.get_active_id() or "auto"
        d.destroy()
        if code != self.cfg.get("language", "auto"):
            self.cfg["language"] = code
            settings.save_app_config(self.cfg)
            self.info(_("Idioma cambiado"), _("Cierra y vuelve a abrir el programa para ver el nuevo idioma."))


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.konkr_tweaks")
        self.win = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        if not self.win:
            self.win = MainWindow(self)
            self.win.show_all()
        self.win.present()


def main():
    return App().run(sys.argv)
