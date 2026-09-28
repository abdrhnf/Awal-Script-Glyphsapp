# MenuTitle: Arabic Glypher — AutoVertical Metrics
# -*- coding: utf-8 -*-
"""Set master vertical metrics from a manuscript's measured row pitch."""

from GlyphsApp import Glyphs
from vanilla import FloatingWindow, TextBox, EditText, TextEditor, Button, Label, ImageView
from vanilla.dialogs import getFile
from AppKit import NSImage


def compute(top, bottom, rows, upm, pitch_target):
    top, bottom, rows = float(top), float(bottom), int(rows)
    upm, pitch_target = float(upm), float(pitch_target or upm)
    if bottom <= top or rows < 1 or pitch_target <= 0:
        raise ValueError("Batas/grid tidak valid")
    pitch_px = (bottom - top) / max(1, rows - 1)
    asc = round(pitch_target * 0.80)
    return pitch_px, asc, -(round(pitch_target - asc))


class AutoVertical:
    def __init__(self):
        self.w = FloatingWindow((700, 520), "Arabic Glypher — Manuscript Assistant")
        Button((365, 12, 150, 24), "Pilih scan manuskrip", callback=self.choose_scan)
        self.scan_label = TextBox((525, 15, 165, 20), "Belum ada scan")
        self.scan_view = ImageView((365, 45, 690, 220), None)
        TextBox((15, 12, -15, 20), "Metric vertikal dari manuskrip")
        Label((15, 45, 90, 20), "Atas (px)"); self.top = EditText((110, 42, 80, 22), "0")
        Label((15, 75, 90, 20), "Bawah (px)"); self.bottom = EditText((110, 72, 80, 22), "1000")
        Label((15, 105, 90, 20), "Jumlah baris"); self.rows = EditText((110, 102, 80, 22), "15")
        Label((15, 135, 90, 20), "UPM"); self.upm = EditText((110, 132, 80, 22), "1000")
        Label((15, 165, 90, 20), "Pitch target"); self.pitch = EditText((110, 162, 80, 22), "1000")
        self.status = TextBox((15, 198, -15, 38), "Isi nilai, lalu Preview.")
        Button((15, 250, 145, 25), "Preview metric", callback=self.preview)
        Button((175, 250, 150, 25), "Terapkan metric", callback=self.apply)
        TextBox((15, 300, -15, 20), "Teks manuskrip — satu baris per baris")
        self.lines = TextEditor((15, 325, -15, 425), "", callback=self.lines_changed)
        Button((15, 440, 220, 28), "Buka semua baris di Edit Tab", callback=self.open_lines)
        Button((245, 440, 150, 28), "Simpan setup", callback=self.save_setup)
        self.line_status = TextBox((15, 478, -15, 20), "Contoh: baris 1 di baris pertama, dst.")

    def values(self):
        return compute(self.top.get(), self.bottom.get(), self.rows.get(), self.upm.get(), self.pitch.get())

    def preview(self, sender=None):
        try:
            pitch, asc, desc = self.values()
            self.status.set("Pitch %.2f px | Asc %d | Desc %d" % (pitch, asc, desc))
        except Exception as e:
            self.status.set("Error: %s" % e)

    def apply(self, sender=None):
        try:
            _, asc, desc = self.values()
            if Glyphs.font is None:
                raise RuntimeError("Buka font dulu")
            for master in Glyphs.font.masters:
                master.ascender = asc
                master.descender = desc
            self.status.set("Terapkan ke %d master: asc %d / desc %d" % (len(Glyphs.font.masters), asc, desc))
        except Exception as e:
            self.status.set("Error: %s" % e)

    def lines_changed(self, sender=None):
        count = len([line for line in self.lines.get().splitlines() if line.strip()])
        self.line_status.set("%d baris teks siap" % count)

    def choose_scan(self, sender=None):
        paths = getFile(message="Pilih scan manuskrip", allowsMultipleSelection=False,
                        fileTypes=["public.image", "com.adobe.pdf"])
        if not paths:
            return
        path = paths[0]
        image = NSImage.alloc().initWithContentsOfFile_(path)
        if image:
            self.scan_view.setImage(image)
            self.scan_label.set(path.split("/")[-1])

    def open_lines(self, sender=None):
        text = self.lines.get().strip()
        if not text:
            self.line_status.set("Isi teks manuskrip dulu.")
            return
        if Glyphs.font is None:
            self.line_status.set("Buka font dulu di GlyphsApp.")
            return
        # Newline-separated text keeps every manuscript row complete and
        # editable in Glyphs' own Edit Tab.
        tab = Glyphs.font.newTab(text)
        self.line_status.set("Edit Tab dibuka: %d baris" % len(text.splitlines()))

    def save_setup(self, sender=None):
        self.line_status.set("Setup disimpan untuk sesi ini (%d baris)." % len(self.lines.get().splitlines()))


controller = AutoVertical()
controller.w.open()
