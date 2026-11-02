"""Cola de tareas largas (descargas, instalaciones, aplicar) pedidas desde el móvil.
Se ejecutan de una en una en un hilo propio; el móvil consulta su progreso."""
import os
import threading
import time
import traceback
import uuid

from . import core, nexus
from .i18n import _


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, title, game, fn, kind="install"):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.title = title
        self.game = game
        self.fn = fn
        self.state = "queued"   # queued | running | needs_choice | done | error | cancelled
        self.progress = 0.0
        self.text = _("En cola")
        self.error = ""
        self.result = None
        self.created = time.time()
        self.finished = None
        self.cancelled = False
        self.choice_req = None
        self._choice = None
        self._ev = threading.Event()

    def set_progress(self, frac, text):
        if self.cancelled:
            raise Cancelled()
        if frac is not None:
            self.progress = max(0.0, min(1.0, frac))
        if text:
            self.text = text

    def ask_choice(self, tmp, analysis):
        """Llamado por install_archive cuando hace falta elegir carpetas (FOMOD o estructura rara)."""
        cands = []
        for rel in analysis["candidates"]:
            try:
                peek = sorted(os.listdir(os.path.join(tmp, rel)))[:8]
            except OSError:
                peek = []
            cands.append({"path": rel, "peek": peek})
        self.choice_req = {"fomod": analysis["fomod"], "candidates": cands}
        self.state = "needs_choice"
        self.text = _("Esperando a que elijas qué instalar")
        self._ev.clear()
        if not self._ev.wait(timeout=30 * 60) or self.cancelled:
            self.choice_req = None
            return None
        self.state = "running"
        self.choice_req = None
        self.text = _("Instalando…")
        return self._choice

    def answer(self, choice):
        self._choice = choice
        self._ev.set()

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "title": self.title, "game": self.game, "state": self.state,
                "progress": round(self.progress, 3), "text": self.text, "error": self.error,
                "choice": self.choice_req, "created": self.created, "finished": self.finished}


class JobQueue:
    def __init__(self, mgr):
        self.mgr = mgr
        self.jobs = []
        self._cv = threading.Condition()
        threading.Thread(target=self._loop, daemon=True, name="kmm-jobs").start()

    def submit(self, title, game, fn, kind="install"):
        job = Job(title, game, fn, kind)
        with self._cv:
            self.jobs.append(job)
            self._cv.notify()
        self.mgr.notify(None)
        return job

    def get(self, job_id):
        return next((j for j in self.jobs if j.id == job_id), None)

    def cancel(self, job_id):
        j = self.get(job_id)
        if j and j.state in ("queued", "running", "needs_choice"):
            j.cancelled = True
            if j.state == "queued":
                j.state = "cancelled"
                j.text = _("Cancelada")
                j.finished = time.time()
            j._ev.set()
        return j

    def clear_finished(self):
        with self._cv:
            self.jobs = [j for j in self.jobs if j.state in ("queued", "running", "needs_choice")]

    def active(self):
        return [j for j in self.jobs if j.state in ("queued", "running", "needs_choice")]

    def _loop(self):
        while True:
            with self._cv:
                while not any(j.state == "queued" for j in self.jobs):
                    self._cv.wait()
                job = next(j for j in self.jobs if j.state == "queued")
                job.state = "running"
                job.text = _("Empezando…")
            try:
                job.result = job.fn(job)
                if job.cancelled:
                    raise Cancelled()
                if job.result is None:
                    job.state, job.text = "cancelled", _("Cancelada")
                else:
                    job.state, job.progress = "done", 1.0
            except Cancelled:
                job.state, job.text = "cancelled", _("Cancelada")
            except (core.ModError, nexus.NexusError) as e:
                job.state, job.error = "error", str(e)
                job.text = "Error"
            except Exception as e:  # noqa
                job.state, job.error = "error", _("Error inesperado: {error}", error=e)
                job.text = "Error"
                self.mgr.log(traceback.format_exc())
            job.finished = time.time()
            # se guardan solo las 30 últimas terminadas
            with self._cv:
                done = [j for j in self.jobs if j.finished]
                for j in done[:-30]:
                    self.jobs.remove(j)
            self.mgr.notify(job.game)
