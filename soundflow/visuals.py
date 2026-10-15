"""Componentes visuales de Tkinter; no contienen lógica de audio ni de red."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk


COLORS = {
    'canvas': '#F4F3F8', 'surface': '#FFFFFF', 'soft': '#FAF9FD',
    'primary': '#4B2FA3', 'dark': '#1E0A4E', 'purple': '#7A4FD6',
    'text': '#202335', 'muted': '#6E6680', 'border': '#E7E3EF',
    'lavender': '#EEE8FB', 'selected': '#E4D9FA',
}


def background_of(master):
    try:
        return master.cget('background')
    except tk.TclError:
        style = master.cget('style') or master.winfo_class()
        return ttk.Style(master).lookup(style, 'background') or COLORS['surface']


def rounded(canvas, x1, y1, x2, y2, radius=12, **options):
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    return canvas.create_polygon(
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        smooth=True, splinesteps=24, **options)


def draw_icon(canvas, name, x, y, size=22, color=None):
    """Iconos vectoriales en coordenadas de 24 unidades, sin fuentes externas."""
    color = color or COLORS['primary']
    scale = size / 24

    def coords(points):
        return [value * scale + (x if index % 2 == 0 else y)
                for index, value in enumerate(points)]

    def line(*points, **options):
        canvas.create_line(*coords(points), fill=color, width=max(1.5, 1.8 * scale),
                           capstyle='round', joinstyle='round', **options)

    def polygon(*points):
        canvas.create_polygon(*coords(points), fill=color, outline=color)

    def rectangle(*points):
        canvas.create_rectangle(*coords(points), fill=color, outline=color)

    if name == 'play':
        polygon(8, 4, 20, 12, 8, 20)
    elif name == 'pause':
        rectangle(6, 5, 10, 19)
        rectangle(14, 5, 18, 19)
    elif name == 'stop':
        rectangle(6, 6, 18, 18)
    elif name in {'previous', 'next'}:
        if name == 'previous':
            rectangle(5, 5, 7, 19)
            polygon(18, 5, 8, 12, 18, 19)
        else:
            polygon(6, 5, 16, 12, 6, 19)
            rectangle(17, 5, 19, 19)
    elif name == 'queue':
        for row, end in [(6, 20), (12, 20), (18, 14)]:
            line(4, row, end, row)
        polygon(18, 15, 23, 18, 18, 21)
    elif name == 'refresh':
        canvas.create_arc(*coords((4, 4, 20, 20)), start=40, extent=290,
                          style='arc', outline=color, width=max(1.5, 1.8 * scale))
        line(19, 3, 20, 8, 15, 8)
    elif name == 'plus':
        line(5, 12, 19, 12)
        line(12, 5, 12, 19)
    elif name == 'minus':
        line(5, 12, 19, 12)
    elif name == 'trash':
        line(4, 6, 20, 6)
        line(9, 6, 9, 3, 15, 3, 15, 6)
        line(6, 7, 7, 21, 17, 21, 18, 7)
        line(10, 10, 10, 17)
        line(14, 10, 14, 17)
    elif name == 'volume':
        polygon(3, 9, 7, 9, 12, 5, 12, 19, 7, 15, 3, 15)
        canvas.create_arc(*coords((9, 5, 21, 19)), start=-65, extent=130,
                          style='arc', outline=color, width=1.6 * scale)
        canvas.create_arc(*coords((12, 8, 18, 16)), start=-65, extent=130,
                          style='arc', outline=color, width=1.6 * scale)
    elif name == 'search':
        canvas.create_oval(*coords((4, 3, 17, 16)), outline=color, width=1.8 * scale)
        line(15, 15, 21, 21)
    elif name == 'music':
        line(9, 17, 9, 5, 20, 3, 20, 15)
        line(9, 8, 20, 6)
        for box in [(3, 15, 9, 20), (14, 13, 20, 18)]:
            canvas.create_oval(*coords(box), fill=color, outline=color)
    elif name == 'loading':
        for cx in [5, 12, 19]:
            canvas.create_oval(*coords((cx - 1.5, 10.5, cx + 1.5, 13.5)), fill=color, outline='')
    elif name == 'alert':
        canvas.create_oval(*coords((3, 3, 21, 21)), outline=color, width=1.8 * scale)
        line(12, 7, 12, 13)
        rectangle(11.3, 16, 12.7, 17.4)


class ActionButton(tk.Canvas):
    """Botón con icono, foco, teclado y ayuda contextual.

    Acepta los mismos cambios text/state usados por el controlador existente.
    La etiqueta semántica se conserva aunque solo se dibuje el icono.
    """
    PLAY_STATES = {
        'Reproducir': 'play', 'Continuar': 'play', 'Pausar': 'pause',
        'Cargando…': 'loading', 'Iniciando audio…': 'loading',
        'Reintentar': 'refresh', 'Audio no disponible': 'alert',
    }

    def __init__(self, master, *, text, icon, command, variant='soft',
                 icon_only=False, width=44, height=44, **options):
        self.label = text
        self.icon = icon
        self.command = command
        self.variant = variant
        self.icon_only = icon_only
        self._disabled = self._hover = self._pressed = False
        self._tip = None
        self._tip_job = None
        self._font = tkfont.Font(master, family=tkfont.nametofont('TkDefaultFont').actual('family'),
                                 size=11, weight='bold')
        if not icon_only:
            width = max(width, self._font.measure(text) + 58)
        super().__init__(master, width=width, height=height,
                         background=background_of(master), highlightthickness=0,
                         borderwidth=0, takefocus=True, cursor='hand2', **options)
        self.bind('<Configure>', lambda _: self._draw())
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<FocusIn>', lambda _: self._draw())
        self.bind('<FocusOut>', self._focus_out)
        self.bind('<KeyPress-space>', self._key_press)
        self.bind('<KeyRelease-space>', self._key_release)
        self.bind('<Return>', self._enter_key)
        self.bind('<Escape>', lambda _: self._hide_tip())

    def configure(self, cnf=None, **options):
        if isinstance(cnf, dict):
            options = {**cnf, **options}
            cnf = None
        changed = False
        for key in ['text', 'state', 'command']:
            if key in options:
                value = options.pop(key)
                if key == 'text':
                    self.label = value
                    self._hide_tip()
                elif key == 'state':
                    self._disabled = value == 'disabled'
                    if self._disabled:
                        self._pressed = False
                        self._hide_tip()
                    options['cursor'] = 'arrow' if self._disabled else 'hand2'
                else:
                    self.command = value
                changed = True
        result = super().configure(cnf, **options) if options or cnf is not None or not changed else None
        if changed:
            self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == 'text':
            return self.label
        if key == 'state':
            return 'disabled' if self._disabled else 'normal'
        return super().cget(key)

    def invoke(self):
        if not self._disabled:
            self.command()

    def _draw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        dark = self.variant == 'header'
        if self.variant == 'primary':
            background = '#3B2389' if self._hover or self._pressed else COLORS['primary']
            foreground = 'white'
        elif dark:
            background = '#513381' if self._hover or self._pressed else '#35205F'
            foreground = '#F5F0FF'
        else:
            background = '#E2D8F7' if self._hover or self._pressed else COLORS['lavender']
            foreground = COLORS['primary']
        if self._disabled:
            background, foreground = '#ECE9F1', '#A19AAE'
        rounded(self, 2, 2, w - 2, h - 2, 12, fill=background, outline='')
        if self.focus_get() == self:
            rounded(self, 0.8, 0.8, w - 0.8, h - 0.8, 13, fill='', outline=COLORS['purple'], width=2)
        icon = self.PLAY_STATES.get(self.label, self.icon) if self.icon_only else self.icon
        size = 25 if self.variant == 'primary' and self.icon_only else 20
        offset = 1 if self._pressed else 0
        draw_icon(self, icon, (w - size) / 2 if self.icon_only else 16,
                  (h - size) / 2 + offset, size, foreground)
        if not self.icon_only:
            self.create_text(44, h / 2 + offset, text=self.label, anchor='w',
                             fill=foreground, font=self._font)

    def _enter(self, _event=None):
        self._hover = True
        self._draw()
        if self.icon_only:
            self._tip_job = self.after(500, self._show_tip)

    def _leave(self, _event=None):
        self._hover = self._pressed = False
        self._hide_tip()
        self._draw()

    def _press(self, _event=None):
        if not self._disabled:
            self.focus_set()
            self._pressed = True
            self._hide_tip()
            self._draw()

    def _release(self, event):
        pressed = self._pressed
        self._pressed = False
        self._draw()
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _key_press(self, _event=None):
        if not self._disabled:
            self._pressed = True
            self._draw()
        return 'break'

    def _key_release(self, _event=None):
        pressed = self._pressed
        self._pressed = False
        self._draw()
        if pressed:
            self.invoke()
        return 'break'

    def _enter_key(self, _event=None):
        self.invoke()
        return 'break'

    def _focus_out(self, _event=None):
        self._pressed = False
        self._hide_tip()
        self._draw()

    def _show_tip(self):
        self._tip_job = None
        self._tip = tk.Toplevel(self)
        self._tip.overrideredirect(True)
        self._tip.configure(background=COLORS['dark'])
        tk.Label(self._tip, text=self.label, background=COLORS['dark'], foreground='white',
                 padx=10, pady=6, font=self._font).pack()
        self._tip.update_idletasks()
        x = min(self.winfo_rootx(), self.winfo_screenwidth() - self._tip.winfo_reqwidth() - 8)
        self._tip.geometry(f'+{max(0, x)}+{self.winfo_rooty() + self.winfo_height() + 5}')

    def _hide_tip(self):
        if self._tip_job is not None:
            self.after_cancel(self._tip_job)
            self._tip_job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def destroy(self):
        self._hide_tip()
        super().destroy()


def artwork(master, size=132):
    """Ilustración de un vinilo, decorativa; no simula una portada real."""
    canvas = tk.Canvas(master, width=size, height=size, background=background_of(master),
                       borderwidth=0, highlightthickness=0)
    rounded(canvas, 0, 0, size, size, 18, fill=COLORS['dark'], outline='')
    for inset, color in [(14, '#382365'), (23, '#483174'), (25, '#2A174E'),
                         (32, '#39255C'), (34, '#2A174E'), (41, '#483174')]:
        canvas.create_oval(inset, inset, size - inset, size - inset, fill=color, outline='')
    canvas.create_oval(size / 2 - 20, size / 2 - 20, size / 2 + 20, size / 2 + 20,
                       fill='#B597EB', outline='')
    draw_icon(canvas, 'music', size / 2 - 12, size / 2 - 12, 24, COLORS['dark'])
    return canvas
