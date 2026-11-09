#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoTranslator 1.0
================
Editor y traductor asistido por IA para archivos .po / .pot / .mo (gettext).

Flujo de trabajo (estilo "ESP translate"):
  1. Abre tu .po (o actualízalo desde un .pot nuevo).
  2. Filtra las entradas sin traducir / fuzzy y selección en masa.
  3. Prepara un lote: la app arma un prompt con las líneas numeradas
     (respetando un máximo de caracteres por lote) y lo copia al portapapeles.
  4. Pega el prompt en tu IA favorita (ChatGPT, Claude, Gemini...).
  5. Copia la respuesta de la IA y pégala en el panel derecho.
  6. Pulsa "Aplicar y siguiente lote": cada línea traducida reemplaza la
     entrada correspondiente. Repite hasta terminar.
  7. Guarda el .po y compila el .mo.

Requisitos: Python 3.8+ con tkinter (incluido en el instalador de python.org)
y polib (polib.py viene incluido en esta misma carpeta).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

# ----------------------------------------------------------------------------
# polib: se usa la copia local (polib.py en esta carpeta) o la instalada
# ----------------------------------------------------------------------------
try:
    import polib
except ImportError:  # pragma: no cover - solo si el usuario movió el archivo
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', 'polib'])
        import polib
    except Exception:
        print('ERROR: falta el módulo "polib".')
        print('Asegúrate de que polib.py esté en la misma carpeta que este')
        print('archivo, o instálalo con:  pip install polib')
        sys.exit(1)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = 'PoTranslator'
APP_VERSION = '1.1'
CONFIG_PATH = Path.home() / '.potranslator.json'

CHAT_URLS = {
    'ChatGPT': 'https://chatgpt.com/',
    'Claude': 'https://claude.ai/chat',
    'Gemini': 'https://gemini.google.com/app',
    'Copilot': 'https://copilot.microsoft.com/',
    'DeepL (trad.)': 'https://www.deepl.com/translator',
}

DEFAULT_PROMPT = (
    'Eres un traductor profesional de software. Traduce al ESPAÑOL los textos '
    'de la interfaz de un programa (BodySlide / Outfit Studio, herramienta de '
    'modding de videojuegos).\n'
    '\n'
    'Reglas estrictas:\n'
    '1. Responde SOLO con las traducciones, una por línea, con el formato '
    '"N) traducción".\n'
    '2. Mantén el mismo número de líneas, el mismo orden y la misma numeración. '
    'No añadas explicaciones ni comentarios.\n'
    '3. Conserva intactos los marcadores: %s, %d, %lu, {{PLACEHOLDER}} y los '
    'saltos de línea escritos como \\n.\n'
    '4. Conserva el símbolo & de los atajos de menú (ej.: "&OK" se traduce '
    '"&Aceptar").\n'
    '5. No traduzcas términos técnicos ni nombres propios: NIF, TRI, BodySlide, '
    'Outfit Studio, morph, zap, OSD, BGSM, etc.\n'
    '6. Español neutro, con tildes y eñes correctas. Glosario: mesh = malla, '
    'shape = forma, bone = hueso, vertex = vértice, weight = peso, '
    'slider = deslizador, preset = preajuste, seam = costura, clip = recorte.\n'
    '7. Si un texto es solo un número o un código (ej.: "0.100"), devuélvelo '
    'tal cual.'
)

DEFAULT_CONFIG = {
    'separator': '<SEPARATOR>',
    'max_chars': 8000,
    'prompt': DEFAULT_PROMPT,
    'include_translated': False,
    'chat': 'ChatGPT',
    'geometry': '1280x820',
    'theme': 'auto',            # 'auto' | 'claro' | 'oscuro'
}

# ----------------------------------------------------------------------------
# Paletas de color (tema claro / oscuro)
# ----------------------------------------------------------------------------
THEMES = {
    'claro': {
        'bg': '#f0f0f0', 'fg': '#000000',
        'tree_bg': '#ffffff', 'tree_fg': '#000000',
        'tree_sel': '#0078d7', 'tree_selfg': '#ffffff',
        'head_bg': '#ebebeb', 'head_fg': '#000000', 'head_active': '#dcdcdc',
        'row_trans': '#eaf6ea', 'row_fuzzy': '#fdf0dc', 'row_untr': '#fdeaea',
        'row_obs': '#eeeeee', 'row_obs_fg': '#888888',
        'text_bg': '#ffffff', 'text_readonly': '#f2f2f2', 'text_fg': '#000000',
        'text_sel': '#b3d4fc',
        'muted': '#666666', 'ok': '#00aa55', 'warn': '#aa6600',
        'accent': '#0078d7', 'menu_bg': '#f0f0f0',
        'btn': '#e1e1e1', 'btn_active': '#d5e3f8',
        'border': '#c9c9c9', 'insert': '#000000',
    },
    'oscuro': {
        'bg': '#1e1f24', 'fg': '#e4e4e7',
        'tree_bg': '#25262b', 'tree_fg': '#e4e4e7',
        'tree_sel': '#3d5a8a', 'tree_selfg': '#ffffff',
        'head_bg': '#2d2e34', 'head_fg': '#c8c8cc', 'head_active': '#35363d',
        'row_trans': '#243824', 'row_fuzzy': '#3a3122', 'row_untr': '#3a2726',
        'row_obs': '#26272c', 'row_obs_fg': '#8a8a90',
        'text_bg': '#25262b', 'text_readonly': '#202125', 'text_fg': '#e4e4e7',
        'text_sel': '#3d5a8a',
        'muted': '#9b9ba3', 'ok': '#66c88a', 'warn': '#e2a75e',
        'accent': '#4a7dd8', 'menu_bg': '#25262b',
        'btn': '#33343b', 'btn_active': '#3d3e46',
        'border': '#3a3b42', 'insert': '#e4e4e7',
    },
}


def _detect_system_dark():
    """True si el sistema operativo esta en modo oscuro (si no se sabe, False)."""
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as k:
                val, _ = winreg.QueryValueEx(k, 'AppsUseLightTheme')
            return int(val) == 0
        except Exception:
            return False
    if sys.platform == 'darwin':
        try:
            out = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                 capture_output=True, text=True, timeout=2)
            return 'Dark' in (out.stdout or '')
        except Exception:
            return False
    # Linux y demas: preguntar a GNOME/KDE si hay respuesta
    try:
        out = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface',
                              'color-scheme'], capture_output=True, text=True,
                             timeout=2)
        if 'prefer-dark' in (out.stdout or ''):
            return True
    except Exception:
        pass
    try:
        out = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface',
                              'gtk-theme'], capture_output=True, text=True,
                             timeout=2)
        return 'dark' in (out.stdout or '').lower()
    except Exception:
        return False

BATCH_INSTRUCTION = (
    'Traduce cada línea y responde SOLO con la traducción en el formato '
    '"N) traducción", una por línea y con la misma numeración:'
)

STATE_LABELS = {
    'trans': 'Traducida',
    'untr': 'Vacía',
    'fuzzy': 'Fuzzy',
    'obs': 'Obsoleta',
}

GUIA_RAPIDA = """CÓMO USAR PoTranslator (flujo con IA)
=====================================

1) ACTUALIZAR TU TRADUCCIÓN
   - Menú "Archivo > Abrir .po" y elige tu BodySlide.po
   - Menú "Archivo > Actualizar desde POT" y elige el BodySlide.pot nuevo
   - La app conserva tus traducciones, marca como "fuzzy" los textos que
     cambiaron y deja vacías las cadenas nuevas.

2) TRADUCIR EN MASA CON LA IA (pestaña "Traducción IA por lotes")
   - En el filtro de arriba elige "Sin traducir" (o "Con fuzzy" para revisar)
   - Pulsa "Preparar lote" (usa las entradas filtradas o las seleccionadas
     con Ctrl+clic / Mayús+clic en la tabla)
   - El prompt queda copiado en tu portapapeles: pégalo en ChatGPT, Claude,
     Gemini... (el botón "Abrir chat" abre el que elijas)
   - Copia la respuesta de la IA y pégala en el panel derecho
   - Pulsa "Aplicar y siguiente lote": cada línea reemplaza a su entrada
     y se prepara automáticamente el siguiente lote
   - Si algo sale mal: "Deshacer último lote"

3) EDITAR A MANO (pestaña "Editor de entrada")
   - Doble clic en una fila de la tabla, edita y usa Anterior/Siguiente
   - "Copiar original" sirve para números o términos que no se traducen

4) GUARDAR
   - "Guardar .po" guarda el catálogo (con copia de seguridad .bak)
   - "Compilar .mo" genera el archivo binario que usa el programa
     (BodySlide: reemplaza tu BodySlide.mo existente en la carpeta de
     idioma, p. ej. lang/es/)

CONSEJOS
- El máximo de caracteres por lote evita respuestas cortadas por la IA.
- Las entradas "fuzzy" son traducciones reaprovechadas de textos que
  cambiaron: revísalas antes de compilar el .mo.
- Los textos multilínea viajan con \\n literal; la app los reconvierte sola.
"""


# ============================================================================
#  LÓGICA CORE (sin interfaz, para poder probarla automáticamente)
# ============================================================================

def get_nplurals(po):
    """Número de formas plurales según la cabecera del .po."""
    pf = (po.metadata or {}).get('Plural-Forms', '') or ''
    m = re.search(r'nplurals\s*=\s*(\d+)', pf)
    return int(m.group(1)) if m else 2


def entry_state(e):
    """Estado de una entrada: 'trans' | 'untr' | 'fuzzy' | 'obs'."""
    if e.obsolete:
        return 'obs'
    if 'fuzzy' in e.flags:
        return 'fuzzy'
    if e.msgid_plural:
        return 'trans' if e.translated() else 'untr'
    return 'trans' if e.msgstr else 'untr'


def escape_for_ai(s):
    """Prepara un texto para viajar en UNA línea del prompt."""
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')
    return s


_UNESCAPE_MAP = {'n': '\n', 't': '\t', 'r': '\n', '"': '"', "'": "'", '\\': '\\'}


def unescape_from_ai(s):
    """Revierte escape_for_ai sobre una línea devuelta por la IA."""
    return re.sub(r'\\(.)', lambda m: _UNESCAPE_MAP.get(m.group(1), '\\' + m.group(1)), s)


def normalize_for_match(s):
    return ' '.join(s.lower().split())


def _prepare_fuzzy_pool(old_entries):
    """Info precalculada de las entradas viejas para el matching difuso."""
    pool = []
    for e in old_entries:
        if not e.msgstr:  # sin traducción no hay nada que reaprovechar
            continue
        norm = normalize_for_match(e.msgid)
        pool.append((e, norm, set(re.findall(r'\w+', norm)), e.msgctxt or '',
                     bool(e.msgid_plural)))
    return pool


def find_fuzzy_match(entry, pool, threshold=0.90, min_len=8):
    """Busca la mejor coincidencia difusa de una cadena nueva entre las viejas.

    Nota: puede devolver una entrada cuya clave siga existiendo en el POT (una
    variante reescrita, p. ej. "Slider Data" -> "Slider Data:"); en ese caso la
    traducción se REUTILIZA como fuzzy pero la entrada original conserva la
    suya, así que nunca se pierde nada.
    """
    target = normalize_for_match(entry.msgid)
    if len(target) < min_len:
        return None, 0.0
    t_words = set(re.findall(r'\w+', target))
    if not t_words:
        return None, 0.0
    best, best_ratio = None, 0.0
    for old, norm, words, ctxt, has_plural in pool:
        if ctxt != (entry.msgctxt or ''):
            continue
        if has_plural != bool(entry.msgid_plural):
            continue
        if len(norm) < min_len:
            continue
        # prefiltro barato por vocabulario compartido (jaccard)
        union = t_words | words
        if not union or len(t_words & words) / len(union) < 0.5:
            continue
        ratio = SequenceMatcher(None, norm, target).ratio()
        if ratio > best_ratio:
            best, best_ratio = old, ratio
    if best is not None and best_ratio >= threshold:
        return best, best_ratio
    return None, 0.0


def _copy_translation(old, new):
    """Copia la traducción (y notas) de una entrada vieja a una nueva."""
    new.msgstr = old.msgstr
    if old.msgstr_plural:
        new.msgstr_plural = dict(old.msgstr_plural)
    if old.comment:
        new.comment = old.comment
    if 'fuzzy' in old.flags and 'fuzzy' not in new.flags:
        new.flags.append('fuzzy')


def update_from_pot(po, pot, threshold=0.90, min_len=8):
    """
    Fusiona un .pot nuevo dentro del .po abierto (estilo msgmerge).

    - Pasada 1 — coincidencia exacta de msgid: conserva la traducción tal cual.
    - Pasada 2 — texto parecido (ratio >= threshold, longitud >= min_len):
      conserva la traducción y marca la entrada como "fuzzy" para revisión.
    - Cadena nueva: queda vacía.
    - Cadenas que desaparecieron: se conservan al final como obsoletas (#~).
    Devuelve un dict con estadísticas.
    """
    old_by_key = {}
    old_order = []
    for e in po:
        if e.obsolete or not e.msgid:
            continue
        key = (e.msgctxt or '', e.msgid)
        if key not in old_by_key:
            old_by_key[key] = e
            old_order.append(e)

    pool = _prepare_fuzzy_pool(old_order)
    used = set()
    pot_entries = [e for e in pot if e.msgid]
    done = {}          # clave -> entrada del pot ya resuelta
    kept = fuzzy_n = new_n = 0

    # pasada 1: TODAS las coincidencias exactas primero
    for e in pot_entries:
        key = (e.msgctxt or '', e.msgid)
        if key in done:
            continue
        old = old_by_key.get(key)
        if old is not None and id(old) not in used:
            used.add(id(old))
            _copy_translation(old, e)
            done[key] = e
            kept += 1

    # pasada 2: coincidencias difusas para lo que quedó sin resolver.
    # Se recorre TODO el po viejo (aunque su clave siga en el POT): solo se
    # referencia la traducción, no se consume, así que nada se pierde.
    for e in pot_entries:
        key = (e.msgctxt or '', e.msgid)
        if key in done:
            continue
        best, ratio = find_fuzzy_match(e, pool, threshold, min_len)
        if best is not None:
            _copy_translation(best, e)
            if 'fuzzy' not in e.flags:
                e.flags.append('fuzzy')
            e.previous_msgid = best.msgid
            done[key] = e
            fuzzy_n += 1

    # lo demás: cadenas nuevas (y duplicados del pot replican su traducción)
    for e in pot_entries:
        key = (e.msgctxt or '', e.msgid)
        if key in done:
            if done[key] is not e:
                e.msgstr = done[key].msgstr
                if done[key].msgstr_plural:
                    e.msgstr_plural = dict(done[key].msgstr_plural)
        else:
            new_n += 1

    obsolete = [o for o in old_order if id(o) not in used]
    for o in obsolete:
        o.obsolete = True
    prev_obs = [e for e in list(po) if e.obsolete and e not in obsolete]

    # nota: polib guarda la cabecera en po.metadata / po.header, no en la lista
    po[:] = pot_entries + obsolete + prev_obs
    if pot.metadata:
        for k in ('Project-Id-Version', 'POT-Creation-Date'):
            v = (pot.metadata or {}).get(k)
            if v and not (po.metadata or {}).get(k):
                po.metadata[k] = v
    return {'kept': kept, 'fuzzy': fuzzy_n, 'new': new_n, 'obsolete': len(obsolete)}


def build_batch(queue, pos, prompt_tpl, separator, max_chars):
    """
    Construye el prompt del siguiente lote.

    Devuelve (prompt, items, nueva_posicion):
    - items: lista de (numero, entrada) incluidas en el lote (numeración 1..N
      propia del lote, como en ESP translate).
    - nueva_posicion: por dónde continuar en la cola para el siguiente lote.
    """
    parts = [prompt_tpl.rstrip(), '', separator, '', BATCH_INSTRUCTION, '']
    total = sum(len(p) + 1 for p in parts)
    items = []
    n = 0
    i = pos
    while i < len(queue):
        e = queue[i]
        n += 1
        line = '%d) %s' % (n, escape_for_ai(e.msgid))
        if items and total + len(line) + 1 > max_chars:
            break
        items.append((n, e))
        parts.append(line)
        total += len(line) + 1
        i += 1
    return '\n'.join(parts), items, i


_LINE_NUM_RE = re.compile(r'^[\[\(]?\s*(\d{1,4})\s*[\]\).:\-–—]?\*?\s*(.*)$')
_DECOR_RE = re.compile(r'^[\s\-\=_\*~#>·•]+$')


def parse_ai_result(raw, separator):
    """
    Extrae las líneas numeradas de la respuesta de la IA.

    Acepta formatos "1)", "1.", "1 -", "[1]", "(1)", "**1)**", "1 texto",
    líneas con comillas envolventes, bloques de código ```...```, líneas
    vacías y separadores decorativos. Devuelve {numero: texto}.
    """
    text = (raw or '').strip()
    text = re.sub(r'^```[A-Za-z]*\s*', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    results = {}
    for line in text.split('\n'):
        line = line.strip()
        line = line.lstrip('*').rstrip('*').strip()  # **1)** -> 1)
        if not line or line == (separator or '').strip():
            continue
        if _DECOR_RE.match(line):
            continue
        m = _LINE_NUM_RE.match(line)
        if not m:
            continue
        num = int(m.group(1))
        val = m.group(2).strip().lstrip('*').strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in '"\'«»“”':
            val = val[1:-1].strip()
        if val:
            results[num] = unescape_from_ai(val)
    return results


def apply_batch(items, results):
    """
    Aplica las traducciones parseadas a las entradas del lote.

    Devuelve (aplicadas, numeros_faltantes, vacias, snapshots_para_undo).
    """
    applied, missing, empties, undo = 0, [], 0, []
    for num, e in items:
        val = results.get(num)
        if val is None:
            missing.append(num)
            continue
        val = val.strip()
        if not val:
            empties += 1
            continue
        undo.append((e, e.msgstr, (dict(e.msgstr_plural) if e.msgstr_plural else None),
                     list(e.flags)))
        e.msgstr = val
        if 'fuzzy' in e.flags:
            e.flags.remove('fuzzy')
        applied += 1
    return applied, missing, empties, undo


def load_any(path):
    """Carga .po, .pot o .mo como POFile editable."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == '.mo':
        mo = polib.mofile(str(p))
        po = polib.POFile()
        po.metadata = dict(mo.metadata or {})
        for e in mo:
            if e.msgid:
                po.append(e)
        return po
    return polib.pofile(str(p))


def touch_metadata(po):
    """Actualiza la fecha de revisión y limpia la cabecera fuzzy.

    Nota: en polib la cabecera se gestiona vía ``po.metadata`` (dict) y el
    flag fuzzy de cabecera con ``po.metadata_is_fuzzy``.
    """
    if po.metadata is None:
        po.metadata = {}
    now = datetime.now().astimezone()
    po.metadata['PO-Revision-Date'] = now.strftime('%Y-%m-%d %H:%M') + now.strftime('%z')
    if 'Content-Type' not in (po.metadata or {}):
        po.metadata['Content-Type'] = 'text/plain; charset=UTF-8'
    try:
        po.metadata_is_fuzzy = 0
    except Exception:
        pass


def backup_file(path):
    """Copia de seguridad .bak antes de sobrescribir."""
    p = Path(path)
    if p.exists():
        bak = p.with_name(p.name + '.bak')
        shutil.copy2(str(p), str(bak))
        return bak
    return None


def preview_text(s, maxlen=180):
    s = (s or '').replace('\r', '').replace('\n', '\\n').replace('\t', ' ')
    return s[:maxlen] + ('...' if len(s) > maxlen else '')


def refs_short(e):
    occ = getattr(e, 'occurrences', None) or []
    if not occ:
        return ''
    name, line = occ[0][0], occ[0][1]
    s = ('%s:%s' % (name, line)) if line else str(name)
    if len(occ) > 1:
        s += '  (+%d)' % (len(occ) - 1)
    return s


# ============================================================================
#  INTERFAZ GRÁFICA
# ============================================================================

class PoTranslatorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('%s %s' % (APP_NAME, APP_VERSION))
        self.cfg = dict(DEFAULT_CONFIG)
        self._load_config()
        self._resolve_theme()

        self.po = None
        self.po_path = None
        self.entries = []          # entradas visibles/en archivo (sin cabecera)
        self._idx_by_id = {}
        self.displayed = []        # índices mostrados en la tabla (filtro actual)
        self.current_idx = None    # entrada cargada en el editor
        self.dirty = False

        # estado del flujo por lotes
        self.queue = []
        self.queue_pos = 0
        self.batch_no = 0
        self.batch_items = []
        self.undo_stack = []

        self._search_job = None
        self._plural_texts = []

        self.minsize(1010, 660)
        self._build_ui()
        self._apply_config()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(50, self._set_placeholder_states)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.style = ttk.Style(self)
        for theme in ('vista', 'xpnative', 'clam'):
            if theme in self.style.theme_names():
                self.style.theme_use(theme)
                break
        self.style.configure('Treeview', rowheight=24)
        self.style.configure('TButton', padding=(10, 4))
        self.style.configure('Big.TButton', font=('', 10, 'bold'), padding=(14, 6))

        self._build_menu()

        # ---- barra de herramientas
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill='x')
        ttk.Button(bar, text='Abrir .po...', command=self.open_file).pack(side='left')
        ttk.Button(bar, text='Actualizar desde POT...', command=self.update_from_pot_dialog
                   ).pack(side='left', padx=(6, 0))
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=8, pady=2)
        ttk.Button(bar, text='Guardar .po', command=self.save_po).pack(side='left')
        ttk.Button(bar, text='Guardar como...', command=self.save_po_as).pack(side='left', padx=(6, 0))
        ttk.Button(bar, text='Compilar .mo', command=self.compile_mo).pack(side='left', padx=(6, 0))
        self.lbl_file = ttk.Label(bar, text='(ningún archivo abierto)',
                                  foreground=self.theme['muted'])
        self.lbl_file.pack(side='right')

        # ---- filtros
        fbar = ttk.Frame(self, padding=(8, 0))
        fbar.pack(fill='x')
        ttk.Label(fbar, text='Mostrar:').pack(side='left')
        self.var_filter = tk.StringVar(value='Todas')
        cb = ttk.Combobox(fbar, textvariable=self.var_filter, state='readonly', width=13,
                          values=('Todas', 'Sin traducir', 'Con fuzzy', 'Traducidas'))
        cb.pack(side='left', padx=(4, 10))
        cb.bind('<<ComboboxSelected>>', lambda e: self.refresh_tree())
        ttk.Label(fbar, text='Buscar:').pack(side='left')
        self.var_search = tk.StringVar()
        self.ent_search = ttk.Entry(fbar, textvariable=self.var_search, width=34)
        self.ent_search.pack(side='left', padx=(4, 10))
        self.ent_search.bind('<KeyRelease>', self._on_search_key)
        self.var_obs = tk.BooleanVar(value=False)
        ttk.Checkbutton(fbar, text='Incluir obsoletas', variable=self.var_obs,
                        command=self.refresh_tree).pack(side='left', padx=(0, 10))
        ttk.Button(fbar, text='Seleccionar filtradas', command=self.select_filtered
                   ).pack(side='left')
        self.lbl_sel = ttk.Label(fbar, text='', foreground=self.theme['muted'])
        self.lbl_sel.pack(side='left', padx=10)

        # ---- notebook inferior y barra de estado (se reservan desde abajo
        # para que nunca queden fuera de pantalla)
        sbar = ttk.Frame(self, padding=(10, 4))
        sbar.pack(side='bottom', fill='x')
        self.lbl_counts = ttk.Label(sbar, text='Abre un archivo .po para comenzar')
        self.lbl_counts.pack(side='left')
        self.progress = ttk.Progressbar(sbar, length=170, mode='determinate')
        self.progress.pack(side='right')
        self.lbl_batch_state = ttk.Label(sbar, text='', foreground=self.theme['ok'])
        self.lbl_batch_state.pack(side='right', padx=14)

        self.nb = ttk.Notebook(self)
        self.nb.pack(side='bottom', fill='x', padx=8, pady=(0, 4))
        self._build_editor_tab()
        self._build_ai_tab()

        # ---- tabla principal (ocupa el espacio restante)
        wrapper = ttk.Frame(self, padding=(8, 4))
        wrapper.pack(fill='both', expand=True)
        cols = ('num', 'estado', 'orig', 'trad', 'refs')
        self.tree = ttk.Treeview(wrapper, columns=cols, selectmode='extended',
                                 show='headings')
        vsb = ttk.Scrollbar(wrapper, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        headings = ('#', 'Estado', 'Original', 'Traducción', 'Origen')
        widths = (52, 90, 440, 440, 195)
        anchors = ('e', 'w', 'w', 'w', 'w')
        for c, h, w, a in zip(cols, headings, widths, anchors):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor=a, stretch=(c in ('orig', 'trad')))
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)

        self.tree.tag_configure('trans', background=self.theme['row_trans'])
        self.tree.tag_configure('fuzzy', background=self.theme['row_fuzzy'])
        self.tree.tag_configure('untr', background=self.theme['row_untr'])
        self.tree.tag_configure('obs', background=self.theme['row_obs'],
                                foreground=self.theme['row_obs_fg'])

        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.tree.bind('<Double-1>', self._on_tree_double)
        self.tree.bind('<Button-3>', self._show_context_menu)
        self.tree.bind('<Control-a>', lambda e: self.select_filtered())

        # ---- atajos
        self.bind('<Control-o>', lambda e: self.open_file())
        self.bind('<Control-s>', lambda e: self.save_po())
        self.bind('<Control-S>', lambda e: self.save_po_as())
        self.bind('<Control-f>', lambda e: self.ent_search.focus_set())
        self.bind('<F5>', lambda e: self.compile_mo())
        self.bind('<Control-Return>', lambda e: self.apply_editor())
        self.bind('<Control-Down>', lambda e: self.nav_entry(1))
        self.bind('<Control-Up>', lambda e: self.nav_entry(-1))

        self._apply_theme()

    # --------------------------------------------------------------- tema
    def _resolve_theme(self):
        pref = self.cfg.get('theme', 'auto')
        if pref in THEMES:
            self.theme_name = pref
        else:
            self.theme_name = 'oscuro' if _detect_system_dark() else 'claro'
        self.theme = THEMES[self.theme_name]

    def set_theme(self, pref):
        self.var_theme.set(pref)
        self.cfg['theme'] = pref
        self._save_config()
        self._resolve_theme()
        self._apply_theme()

    def _apply_theme(self):
        t = self.theme
        s = self.style
        if self.theme_name == 'oscuro':
            # en oscuro se usa 'clam', el unico tema ttk que admite colores
            # completos de forma fiable en Windows/Linux/macOS
            if 'clam' in s.theme_names():
                s.theme_use('clam')
        else:
            # en claro se recupera el tema nativo (vista/xpnative en Windows);
            # en sistemas sin tema nativo se queda en 'clam' y los colores
            # de abajo lo dejan con el aspecto claro correcto
            for name in ('vista', 'xpnative', 'clam'):
                if name in s.theme_names():
                    s.theme_use(name)
                    break
        # configuracion completa de estilos con la paleta vigente: en temas
        # nativos (vista/xpnative) casi todo se ignora y manda el dibujado
        # nativo de Windows; en 'clam' se aplica al 100%
        s.configure('.', background=t['bg'], foreground=t['fg'],
                    fieldbackground=t['tree_bg'], bordercolor=t['border'],
                    lightcolor=t['border'], darkcolor=t['border'],
                    troughcolor=t['text_readonly'], arrowcolor=t['fg'],
                    selectbackground=t['text_sel'], selectforeground='#ffffff')
        s.configure('TFrame', background=t['bg'])
        s.configure('TLabel', background=t['bg'], foreground=t['fg'])
        s.configure('TLabelframe', background=t['bg'], bordercolor=t['border'],
                    lightcolor=t['border'], darkcolor=t['border'])
        s.configure('TLabelframe.Label', background=t['bg'], foreground=t['fg'])
        s.configure('TButton', background=t['btn'], foreground=t['fg'],
                    bordercolor=t['border'], lightcolor=t['btn'],
                    darkcolor=t['btn'], padding=(10, 4))
        s.map('TButton',
              background=[('disabled', t['bg']), ('pressed', t['btn_active']),
                          ('active', t['btn_active'])],
              foreground=[('disabled', t['muted'])])
        s.configure('Big.TButton', font=('', 10, 'bold'), padding=(14, 6))
        s.configure('TEntry', fieldbackground=t['text_bg'],
                    foreground=t['text_fg'], insertcolor=t['insert'],
                    bordercolor=t['border'], lightcolor=t['border'],
                    darkcolor=t['border'], selectbackground=t['text_sel'])
        s.configure('TCombobox', fieldbackground=t['tree_bg'],
                    foreground=t['fg'], arrowcolor=t['fg'],
                    bordercolor=t['border'], lightcolor=t['border'],
                    darkcolor=t['border'], selectbackground=t['text_sel'])
        s.map('TCombobox',
              fieldbackground=[('readonly', t['tree_bg'])],
              foreground=[('readonly', t['fg'])],
              arrowcolor=[('active', t['fg'])])
        s.configure('TCheckbutton', background=t['bg'], foreground=t['fg'],
                    focuscolor=t['bg'])
        s.map('TCheckbutton', background=[('active', t['bg'])])
        s.configure('Treeview', background=t['tree_bg'],
                    foreground=t['tree_fg'], fieldbackground=t['tree_bg'],
                    rowheight=24, bordercolor=t['border'])
        s.map('Treeview',
              background=[('selected', t['tree_sel'])],
              foreground=[('selected', t['tree_selfg'])])
        s.configure('Treeview.Heading', background=t['head_bg'],
                    foreground=t['head_fg'], relief='flat', padding=(6, 4))
        s.map('Treeview.Heading', background=[('active', t['head_active'])])
        s.configure('TNotebook', background=t['bg'], borderwidth=0,
                    tabmargins=(8, 6, 8, 0))
        s.configure('TNotebook.Tab', background=t['text_readonly'],
                    foreground=t['fg'], padding=(14, 6))
        s.map('TNotebook.Tab', background=[('selected', t['tree_bg'])])
        s.configure('TProgressbar', troughcolor=t['text_readonly'],
                    background=t['accent'], lightcolor=t['accent'],
                    darkcolor=t['accent'], bordercolor=t['bg'])
        s.configure('TScrollbar', background=t['head_bg'],
                    troughcolor=t['bg'], bordercolor=t['bg'],
                    arrowcolor=t['fg'], lightcolor=t['head_bg'],
                    darkcolor=t['head_bg'])
        s.configure('TSeparator', background=t['border'])
        # menus
        for menu in self._menus:
            try:
                menu.config(background=t['menu_bg'], foreground=t['fg'],
                            activebackground=t['accent'],
                            activeforeground='#ffffff')
            except Exception:
                pass

        # colores a nivel de widget (siempre, para ambos temas)
        self.configure(background=t['bg'])
        self.lbl_file.configure(foreground=t['muted'])
        self.lbl_sel.configure(foreground=t['muted'])
        self.lbl_refs.configure(foreground=t['muted'])
        self.lbl_prompt_chars.configure(foreground=t['muted'])
        self.lbl_batch_state.configure(foreground=t['ok'])
        self.tree.tag_configure('trans', background=t['row_trans'])
        self.tree.tag_configure('fuzzy', background=t['row_fuzzy'])
        self.tree.tag_configure('untr', background=t['row_untr'])
        self.tree.tag_configure('obs', background=t['row_obs'],
                                foreground=t['row_obs_fg'])
        for w in (self.ed_orig, self.txt_prompt):
            w.configure(background=t['text_readonly'], foreground=t['text_fg'],
                        insertbackground=t['insert'],
                        selectbackground=t['text_sel'])
        for w in (self.ed_trad, self.txt_result, self.txt_tpl):
            w.configure(background=t['text_bg'], foreground=t['text_fg'],
                        insertbackground=t['insert'],
                        selectbackground=t['text_sel'])
        for w in self._plural_texts:
            w.configure(background=t['text_bg'], foreground=t['text_fg'],
                        insertbackground=t['insert'],
                        selectbackground=t['text_sel'])

    def _build_menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label='Abrir .po / .pot / .mo…', accelerator='Ctrl+O',
                       command=self.open_file)
        fm.add_separator()
        fm.add_command(label='Actualizar desde POT…', command=self.update_from_pot_dialog)
        fm.add_separator()
        fm.add_command(label='Guardar .po', accelerator='Ctrl+S', command=self.save_po)
        fm.add_command(label='Guardar como…', accelerator='Ctrl+Shift+S', command=self.save_po_as)
        fm.add_command(label='Compilar .mo', accelerator='F5', command=self.compile_mo)
        fm.add_separator()
        fm.add_command(label='Salir', command=self._on_close)
        m.add_cascade(label='Archivo', menu=fm)

        em = tk.Menu(m, tearoff=0)
        em.add_command(label='Entrada anterior', accelerator='Ctrl+Arriba',
                       command=lambda: self.nav_entry(-1))
        em.add_command(label='Entrada siguiente', accelerator='Ctrl+Abajo',
                       command=lambda: self.nav_entry(1))
        em.add_command(label='Guardar entrada', accelerator='Ctrl+Enter',
                       command=self.apply_editor)
        em.add_separator()
        em.add_command(label='Copiar original a traducción', command=self.bulk_copy_original)
        em.add_command(label='Marcar / quitar fuzzy', command=self.bulk_toggle_fuzzy)
        m.add_cascade(label='Editar', menu=em)

        bm = tk.Menu(m, tearoff=0)
        bm.add_command(label='Preparar lote', command=self.prepare_batch)
        bm.add_command(label='Aplicar resultado', command=lambda: self.apply_result(False))
        bm.add_command(label='Aplicar y siguiente lote', command=lambda: self.apply_result(True))
        bm.add_command(label='Siguiente lote (sin aplicar)', command=self.next_batch)
        bm.add_separator()
        bm.add_command(label='Deshacer último lote', command=self.undo_last)
        m.add_cascade(label='Lote', menu=bm)

        vm = tk.Menu(m, tearoff=0)
        self.var_theme = tk.StringVar(value=self.cfg.get('theme', 'auto'))
        for valor, texto in (('auto', 'Automático (según el sistema)'),
                             ('claro', 'Claro'),
                             ('oscuro', 'Oscuro')):
            vm.add_radiobutton(label=texto, value=valor, variable=self.var_theme,
                               command=lambda v=valor: self.set_theme(v))
        m.add_cascade(label='Ver', menu=vm)

        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label='Guía rápida', command=self.show_guide)
        hm.add_command(label='Acerca de…', command=self.show_about)
        m.add_cascade(label='Ayuda', menu=hm)
        self._menus = (m, fm, em, bm, vm, hm)
        self.config(menu=m)

    # -------------------------------------------------- pestaña: editor
    def _build_editor_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text='  Editor de entrada  ')

        top = ttk.Frame(tab)
        top.pack(fill='x')
        self.lbl_entry_pos = ttk.Label(top, text='—', font=('', 10, 'bold'))
        self.lbl_entry_pos.pack(side='left')
        self.var_fuzzy = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='Fuzzy (revisar)', variable=self.var_fuzzy,
                        command=self.apply_editor).pack(side='right')
        self.lbl_refs = ttk.Label(top, text='', foreground=self.theme['muted'])
        self.lbl_refs.pack(side='right', padx=14)

        mid = ttk.Frame(tab)
        mid.pack(fill='both', expand=True, pady=(6, 0))
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)

        lf_orig = ttk.LabelFrame(mid, text=' Original ', padding=4)
        lf_orig.grid(row=0, column=0, sticky='nsew', padx=(0, 4))
        self.ed_orig = tk.Text(lf_orig, height=5, width=52, wrap='word', state='disabled',
                               background=self.theme['text_readonly'],
                               foreground=self.theme['text_fg'],
                               insertbackground=self.theme['insert'],
                               selectbackground=self.theme['text_sel'], relief='flat')
        sb1 = ttk.Scrollbar(lf_orig, command=self.ed_orig.yview)
        self.ed_orig.configure(yscrollcommand=sb1.set)
        self.ed_orig.pack(side='left', fill='both', expand=True)
        sb1.pack(side='right', fill='y')

        lf_trad = ttk.LabelFrame(mid, text=' Traducción ', padding=4)
        lf_trad.grid(row=0, column=1, sticky='nsew', padx=(4, 0))
        self.ed_trad = tk.Text(lf_trad, height=5, width=52, wrap='word', undo=True)
        sb2 = ttk.Scrollbar(lf_trad, command=self.ed_trad.yview)
        self.ed_trad.configure(yscrollcommand=sb2.set)
        self.ed_trad.pack(side='left', fill='both', expand=True)
        sb2.pack(side='right', fill='y')

        # contenedor dinámico para plurales
        self.plural_frame = ttk.Frame(tab)
        self.plural_frame.pack(fill='x', pady=(6, 0))

        bots = ttk.Frame(tab)
        bots.pack(fill='x', pady=(8, 0))
        ttk.Button(bots, text='<< Anterior', command=lambda: self.nav_entry(-1)
                   ).pack(side='left')
        ttk.Button(bots, text='Siguiente >>', command=lambda: self.nav_entry(1)
                   ).pack(side='left', padx=6)
        ttk.Button(bots, text='Copiar original a traducción',
                   command=self.copy_original_to_editor).pack(side='left', padx=6)
        ttk.Button(bots, text='Guardar entrada', command=self.apply_editor).pack(side='right')

        self.editor_tab = tab

    # ------------------------------------------------ pestaña: lotes IA
    def _build_ai_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text='  Traducción IA por lotes  ')
        self.ai_tab = tab

        # fila 1: origen del lote
        r1 = ttk.Frame(tab)
        r1.pack(fill='x')
        ttk.Label(r1, text='Origen del lote:', font=('', 10, 'bold')).pack(side='left')
        self.var_source = tk.StringVar(value='filtered')
        self.rb_sel = ttk.Radiobutton(r1, text='Seleccionadas en la tabla (0)',
                                      variable=self.var_source, value='selected')
        self.rb_sel.pack(side='left', padx=(10, 4))
        self.rb_fil = ttk.Radiobutton(r1, text='Entradas filtradas (0)',
                                      variable=self.var_source, value='filtered')
        self.rb_fil.pack(side='left', padx=4)
        self.var_include_tr = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text='Incluir ya traducidas', variable=self.var_include_tr
                        ).pack(side='left', padx=12)
        ttk.Button(r1, text='Preparar lote', style='Big.TButton',
                   command=self.prepare_batch).pack(side='right')
        ttk.Button(r1, text='Siguiente lote (sin aplicar)',
                   command=self.next_batch).pack(side='right', padx=8)

        # fila 2: ajustes del lote
        r2 = ttk.Frame(tab)
        r2.pack(fill='x', pady=(8, 0))
        ttk.Label(r2, text='Separador:').pack(side='left')
        self.var_sep = tk.StringVar(value=DEFAULT_CONFIG['separator'])
        ent_sep = ttk.Entry(r2, textvariable=self.var_sep, width=14)
        ent_sep.pack(side='left', padx=(4, 12))
        ent_sep.bind('<FocusOut>', lambda e: self._save_config())
        ttk.Label(r2, text='Máx. caracteres por lote:').pack(side='left')
        self.var_max = tk.IntVar(value=DEFAULT_CONFIG['max_chars'])
        sp = ttk.Spinbox(r2, from_=500, to=100000, increment=500, width=8,
                         textvariable=self.var_max)
        sp.pack(side='left', padx=(4, 12))
        sp.bind('<FocusOut>', lambda e: self._save_config())
        ttk.Label(r2, text='Chat de IA:').pack(side='left')
        self.var_chat = tk.StringVar(value=DEFAULT_CONFIG['chat'])
        cbc = ttk.Combobox(r2, textvariable=self.var_chat, state='readonly', width=12,
                           values=list(CHAT_URLS.keys()))
        cbc.pack(side='left', padx=(4, 4))
        ttk.Button(r2, text='Abrir chat', command=self.open_chat).pack(side='left')

        # fila 3: prompt | respuesta
        r3 = ttk.PanedWindow(tab, orient='horizontal')
        r3.pack(fill='both', expand=True, pady=(8, 0))

        lf_prompt = ttk.LabelFrame(r3, text=' Prompt para la IA (se copia al preparar) ',
                                   padding=4)
        self.txt_prompt = tk.Text(lf_prompt, height=8, width=56, wrap='word',
                                  state='disabled', background=self.theme['text_readonly'],
                                  foreground=self.theme['text_fg'],
                                  insertbackground=self.theme['insert'],
                                  selectbackground=self.theme['text_sel'],
                                  relief='flat')
        sbp = ttk.Scrollbar(lf_prompt, command=self.txt_prompt.yview)
        self.txt_prompt.configure(yscrollcommand=sbp.set)
        self.txt_prompt.pack(side='top', fill='both', expand=True)
        sbp.pack(side='right', fill='y')
        pb = ttk.Frame(lf_prompt)
        pb.pack(fill='x', pady=(4, 0))
        self.lbl_prompt_chars = ttk.Label(pb, text='0 caracteres',
                                          foreground=self.theme['muted'])
        self.lbl_prompt_chars.pack(side='left')
        ttk.Button(pb, text='Copiar todo', command=self.copy_prompt).pack(side='right')

        lf_result = ttk.LabelFrame(r3, text=' Respuesta de la IA (pega aquí) ', padding=4)
        self.txt_result = tk.Text(lf_result, height=8, width=56, wrap='word', undo=True)
        sbr = ttk.Scrollbar(lf_result, command=self.txt_result.yview)
        self.txt_result.configure(yscrollcommand=sbr.set)
        self.txt_result.pack(side='top', fill='both', expand=True)
        sbr.pack(side='right', fill='y')
        rb = ttk.Frame(lf_result)
        rb.pack(fill='x', pady=(4, 0))
        ttk.Button(rb, text='Aplicar resultado', command=lambda: self.apply_result(False)
                   ).pack(side='left')
        ttk.Button(rb, text='Aplicar y siguiente lote', style='Big.TButton',
                   command=lambda: self.apply_result(True)).pack(side='left', padx=8)
        ttk.Button(rb, text='Deshacer último lote', command=self.undo_last
                   ).pack(side='right')
        r3.add(lf_prompt, weight=1)
        r3.add(lf_result, weight=1)

        # fila 4: plantilla del prompt
        lf_tpl = ttk.LabelFrame(tab, text=' Plantilla del prompt (se guarda automáticamente) ',
                                padding=4)
        lf_tpl.pack(fill='x', pady=(8, 0))
        self.txt_tpl = tk.Text(lf_tpl, height=5, width=148, wrap='word', undo=True)
        self.txt_tpl.pack(fill='both', expand=True)
        self.txt_tpl.bind('<FocusOut>', lambda e: self._save_config())

    # ----------------------------------------------------------- archivo
    def open_file(self, path=None):
        if not self._check_save_changes():
            return
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, title='Abrir archivo de traducción',
                filetypes=[('Archivos de traducción', '*.po *.pot *.mo'),
                           ('Todos los archivos', '*.*')])
        if not path:
            return
        try:
            po = load_any(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, 'No se pudo abrir el archivo:\n\n%s' % exc,
                                 parent=self)
            return
        po.wrapwidth = 100000  # guardar sin re-envolver líneas
        self.po = po
        self.po_path = Path(path)
        self._rebuild_entries()
        self.refresh_tree()
        self.load_editor(0 if self.entries else None)
        self.dirty = False
        self._update_title()
        self.lbl_file.config(text=self.po_path.name)
        if self.po_path.suffix.lower() == '.pot':
            messagebox.showinfo(
                APP_NAME, 'Has abierto un archivo .pot (plantilla sin traducir).\n'
                'Al guardar se te pedirá un nombre terminado en .po.', parent=self)

    def _rebuild_entries(self):
        self.entries = [e for e in self.po if e.msgid]
        self._idx_by_id = {id(e): i for i, e in enumerate(self.entries)}

    def update_from_pot_dialog(self):
        if self.po is None:
            messagebox.showinfo(APP_NAME, 'Abre primero tu archivo .po.', parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self, title='Elegir la plantilla nueva (.pot)',
            filetypes=[('Plantilla POT', '*.pot'), ('Archivos PO', '*.po'),
                       ('Todos los archivos', '*.*')])
        if not path:
            return
        self.apply_editor()
        try:
            pot = polib.pofile(str(path))
            t0 = time.time()
            stats = update_from_pot(self.po, pot)
            seg = time.time() - t0
        except Exception as exc:
            messagebox.showerror(APP_NAME, 'Error al actualizar desde el POT:\n\n%s' % exc,
                                 parent=self)
            return
        self.po.wrapwidth = 100000
        self._rebuild_entries()
        self.refresh_tree()
        self.refresh_counts()
        self.load_editor(None)
        self.mark_dirty()
        msg = (
            'Actualización completada en %.1f s:\n\n'
            '• Traducciones conservadas: %d\n'
            '• Textos cambiados marcados como fuzzy: %d\n'
            '• Cadenas nuevas sin traducir: %d\n'
            '• Cadenas eliminadas (obsoletas): %d\n\n'
            'Consejo: revisa el filtro «Con fuzzy» y traduce las vacías\n'
            'en la pestaña «Traducción IA por lotes».'
            % (seg, stats['kept'], stats['fuzzy'], stats['new'], stats['obsolete']))
        messagebox.showinfo(APP_NAME + ' — Resultado de la actualización', msg, parent=self)

    def save_po(self):
        if self.po is None:
            return
        if self.po_path is None or self.po_path.suffix.lower() in ('.pot', '.mo'):
            return self.save_po_as()
        self.apply_editor()
        try:
            touch_metadata(self.po)
            backup_file(self.po_path)
            self.po.save(str(self.po_path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, 'No se pudo guardar:\n\n%s' % exc, parent=self)
            return
        self.dirty = False
        self._update_title()
        self.lbl_batch_state.config(text='Guardado %s' % datetime.now().strftime('%H:%M'))

    def save_po_as(self):
        if self.po is None:
            return
        self.apply_editor()
        default = str(self.po_path) if self.po_path else 'traduccion.po'
        path = filedialog.asksaveasfilename(
            parent=self, title='Guardar .po como', defaultextension='.po',
            initialfile=Path(default).with_suffix('.po').name,
            filetypes=[('Catálogo PO', '*.po')])
        if not path:
            return
        self.po_path = Path(path)
        self.lbl_file.config(text=self.po_path.name)
        self.save_po()

    def compile_mo(self):
        if self.po is None:
            return
        if self.po_path is None or self.po_path.suffix.lower() == '.mo':
            return self._compile_mo_as()
        self._write_mo(self.po_path.with_suffix('.mo'))

    def _compile_mo_as(self):
        path = filedialog.asksaveasfilename(
            parent=self, title='Compilar .mo en…', defaultextension='.mo',
            filetypes=[('Catálogo compilado MO', '*.mo')])
        if path:
            self._write_mo(Path(path))

    def _write_mo(self, path):
        self.apply_editor()
        try:
            touch_metadata(self.po)
            backup_file(path)
            self.po.save_as_mofile(str(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, 'No se pudo compilar el .mo:\n\n%s' % exc,
                                 parent=self)
            return
        self.lbl_batch_state.config(
            text='.mo compilado (%s)' % datetime.now().strftime('%H:%M'),
            foreground=self.theme['ok'])

    # ------------------------------------------------------------- tabla
    def _on_search_key(self, _event):
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(250, self.refresh_tree)

    def row_values(self, i, e):
        st = entry_state(e)
        return (i + 1, STATE_LABELS[st], preview_text(e.msgid),
                preview_text(e.msgstr), refs_short(e))

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.displayed = []
        if self.po is None:
            self._update_source_labels()
            return
        q = (self.var_search.get() or '').strip().lower()
        want = self.var_filter.get()
        show_obs = bool(self.var_obs.get())
        for i, e in enumerate(self.entries):
            st = entry_state(e)
            if st == 'obs':
                if not show_obs:
                    continue
            elif want == 'Sin traducir' and st != 'untr':
                continue
            elif want == 'Con fuzzy' and st != 'fuzzy':
                continue
            elif want == 'Traducidas' and st != 'trans':
                continue
            if q:
                hay = '%s\n%s\n%s' % (e.msgid, e.msgstr, refs_short(e))
                if q not in hay.lower():
                    continue
            self.tree.insert('', 'end', iid=str(i), values=self.row_values(i, e),
                             tags=(st,))
            self.displayed.append(i)
        self._update_source_labels()
        self.refresh_counts()

    def _update_source_labels(self):
        nsel = len(self.tree.selection())
        self.lbl_sel.config(text=('1 seleccionada' if nsel == 1 else '%d seleccionadas' % nsel) if nsel else '')
        self.rb_sel.config(text='Seleccionadas en la tabla (%d)' % nsel)
        self.rb_fil.config(text='Entradas filtradas (%d)' % len(self.displayed))

    def update_row(self, i):
        iid = str(i)
        if self.tree.exists(iid):
            self.tree.item(iid, values=self.row_values(i, self.entries[i]),
                           tags=(entry_state(self.entries[i]),))

    def refresh_counts(self):
        if self.po is None:
            self.lbl_counts.config(text='Abre un archivo .po para comenzar')
            self.progress['value'] = 0
            return
        t = f = u = o = 0
        for e in self.entries:
            st = entry_state(e)
            if st == 'obs':
                o += 1
            elif st == 'fuzzy':
                f += 1
            elif st == 'untr':
                u += 1
            else:
                t += 1
        total = t + f + u
        pct = (100 * t // total) if total else 100
        self.lbl_counts.config(
            text='Entradas: %d   ·   Traducidas: %d   ·   Fuzzy: %d   ·   '
                 'Sin traducir: %d%s   ·   %d%%'
                 % (total, t, f, u, ('   ·   Obsoletas: %d' % o) if o else '', pct))
        self.progress['value'] = pct
        self._update_source_labels()

    def select_filtered(self):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)
            self.tree.focus(children[0])
        self._update_source_labels()

    def _on_tree_select(self, _event):
        self._update_source_labels()
        sel = self.tree.selection()
        if sel:
            self.load_editor(int(sel[0]))

    def _on_tree_double(self, _event):
        self.nb.select(self.editor_tab)

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
        elif not self.tree.selection():
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='Copiar original a traducción',
                         command=self.bulk_copy_original)
        menu.add_command(label='Borrar traducción', command=self.bulk_clear)
        menu.add_command(label='Marcar como fuzzy', command=lambda: self.bulk_fuzzy(True))
        menu.add_command(label='Quitar fuzzy', command=lambda: self.bulk_fuzzy(False))
        menu.add_separator()
        menu.add_command(label='Seleccionar todas las filtradas', command=self.select_filtered)
        menu.add_command(label='Copiar originales al portapapeles',
                         command=self.bulk_copy_msgids)
        menu.tk_popup(event.x_root, event.y_root)

    def _selected_indices(self):
        return [int(i) for i in self.tree.selection()]

    def _push_undo(self, snaps):
        if snaps:
            self.undo_stack.append(snaps)
            if len(self.undo_stack) > 30:
                self.undo_stack.pop(0)

    def bulk_copy_original(self):
        idxs = self._selected_indices() or self.displayed
        snaps = []
        for i in idxs:
            e = self.entries[i]
            snaps.append((e, e.msgstr, (dict(e.msgstr_plural) if e.msgstr_plural else None),
                          list(e.flags)))
            e.msgstr = e.msgid
            if 'fuzzy' in e.flags:
                e.flags.remove('fuzzy')
        self._push_undo(snaps)
        self._after_bulk(idxs)

    def bulk_clear(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        snaps = []
        for i in idxs:
            e = self.entries[i]
            snaps.append((e, e.msgstr, (dict(e.msgstr_plural) if e.msgstr_plural else None),
                          list(e.flags)))
            e.msgstr = ''
            e.msgstr_plural = {}
        self._push_undo(snaps)
        self._after_bulk(idxs)

    def bulk_fuzzy(self, on):
        idxs = self._selected_indices()
        if not idxs:
            return
        snaps = []
        for i in idxs:
            e = self.entries[i]
            snaps.append((e, e.msgstr, (dict(e.msgstr_plural) if e.msgstr_plural else None),
                          list(e.flags)))
            if on and 'fuzzy' not in e.flags:
                e.flags.append('fuzzy')
            elif not on and 'fuzzy' in e.flags:
                e.flags.remove('fuzzy')
        self._push_undo(snaps)
        self._after_bulk(idxs)

    def bulk_toggle_fuzzy(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        on = not any('fuzzy' in self.entries[i].flags for i in idxs)
        self.bulk_fuzzy(on)

    def bulk_copy_msgids(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        text = '\n'.join(self.entries[i].msgid for i in idxs)
        self._to_clipboard(text)
        self.lbl_batch_state.config(text='%d originales copiados' % len(idxs),
                                    foreground=self.theme['ok'])

    def _after_bulk(self, idxs):
        for i in idxs:
            self.update_row(i)
        self.refresh_counts()
        self.mark_dirty()
        if self.current_idx is not None:
            self.load_editor(self.current_idx)

    # ------------------------------------------------------------ editor
    def load_editor(self, idx):
        self.apply_editor()
        self.current_idx = idx
        if idx is None or self.po is None:
            self.ed_orig.config(state='normal')
            self.ed_orig.delete('1.0', 'end')
            self.ed_orig.config(state='disabled')
            self.ed_trad.delete('1.0', 'end')
            self.lbl_entry_pos.config(text='—')
            self.lbl_refs.config(text='')
            self.var_fuzzy.set(False)
            self._build_plural_editor(None)
            return
        e = self.entries[idx]
        self.ed_orig.config(state='normal')
        self.ed_orig.delete('1.0', 'end')
        self.ed_orig.insert('1.0', e.msgid)
        self.ed_orig.config(state='disabled')
        self.ed_trad.delete('1.0', 'end')
        self.ed_trad.insert('1.0', e.msgstr)
        self.var_fuzzy.set('fuzzy' in e.flags)
        refs = refs_short(e)
        self.lbl_refs.config(text=refs)
        self.lbl_entry_pos.config(text='Entrada %d / %d' % (idx + 1, len(self.entries)))
        self._build_plural_editor(e)

    def _build_plural_editor(self, e):
        for w in self.plural_frame.winfo_children():
            w.destroy()
        self._plural_texts = []
        if e is None or not e.msgid_plural:
            return
        n = get_nplurals(self.po)
        lf = ttk.LabelFrame(self.plural_frame, text=' Formas plurales ', padding=4)
        lf.pack(fill='x')
        lf.columnconfigure(1, weight=1)
        ttk.Label(lf, text='msgid_plural (original):').grid(row=0, column=0, sticky='nw',
                                                            padx=(0, 8))
        tp = tk.Text(lf, height=2, wrap='word', state='disabled',
                     background=self.theme['text_readonly'],
                     foreground=self.theme['text_fg'],
                     insertbackground=self.theme['insert'],
                     selectbackground=self.theme['text_sel'], relief='flat')
        tp.insert('1.0', e.msgid_plural)
        tp.config(state='disabled')
        tp.grid(row=0, column=1, sticky='ew', pady=2)
        labels = {0: 'singular', 1: 'plural'}
        for i in range(n):
            lab = 'msgstr[%d] (%s):' % (i, labels.get(i, 'forma %d' % i))
            ttk.Label(lf, text=lab).grid(row=i + 1, column=0, sticky='nw', padx=(0, 8),
                                         pady=(4, 0))
            t = tk.Text(lf, height=2, wrap='word', undo=True,
                        background=self.theme['text_bg'],
                        foreground=self.theme['text_fg'],
                        insertbackground=self.theme['insert'],
                        selectbackground=self.theme['text_sel'])
            t.insert('1.0', (e.msgstr_plural or {}).get(str(i), ''))
            t.grid(row=i + 1, column=1, sticky='ew', pady=2)
            self._plural_texts.append(t)

    def apply_editor(self):
        if self.po is None or self.current_idx is None:
            return
        e = self.entries[self.current_idx]
        new = self.ed_trad.get('1.0', 'end').rstrip('\n')
        changed = False
        if new != e.msgstr:
            e.msgstr = new
            changed = True
        if self._plural_texts:
            plur = {str(i): t.get('1.0', 'end').rstrip('\n')
                    for i, t in enumerate(self._plural_texts)}
            if plur != (e.msgstr_plural or {}):
                e.msgstr_plural = plur
                changed = True
        fuzzy_now = bool(self.var_fuzzy.get())
        has_fuzzy = 'fuzzy' in e.flags
        if fuzzy_now != has_fuzzy:
            if fuzzy_now:
                e.flags.append('fuzzy')
            else:
                e.flags.remove('fuzzy')
            changed = True
        if changed:
            self.update_row(self.current_idx)
            self.refresh_counts()
            self.mark_dirty()

    def nav_entry(self, delta):
        if not self.displayed:
            return
        cur = self.current_idx
        if cur in self.displayed:
            p = self.displayed.index(cur) + delta
        else:
            p = 0 if delta > 0 else len(self.displayed) - 1
        p = max(0, min(len(self.displayed) - 1, p))
        self.load_editor(self.displayed[p])
        iid = str(self.displayed[p])
        if self.tree.exists(iid):
            self.tree.see(iid)

    def copy_original_to_editor(self):
        if self.current_idx is None:
            return
        e = self.entries[self.current_idx]
        self.ed_trad.delete('1.0', 'end')
        self.ed_trad.insert('1.0', e.msgid)
        if self._plural_texts:
            for t in self._plural_texts:
                t.delete('1.0', 'end')
                t.insert('1.0', e.msgid_plural or e.msgid)

    # ---------------------------------------------------- lotes con IA
    def gather_queue(self, source):
        if source == 'selected':
            idxs = self._selected_indices()
            entries = [self.entries[i] for i in idxs]
            if not entries:
                entries = [self.entries[i] for i in self.displayed]
        else:
            entries = [self.entries[i] for i in self.displayed]
        include_tr = bool(self.var_include_tr.get())
        queue, skipped = [], 0
        for e in entries:
            if e.obsolete or not e.msgid:
                continue
            if e.msgid_plural:
                skipped += 1
                continue
            if entry_state(e) == 'trans' and not include_tr:
                continue
            queue.append(e)
        return queue, skipped

    def prepare_batch(self):
        if self.po is None:
            messagebox.showinfo(APP_NAME, 'Abre primero un archivo .po.', parent=self)
            return
        self.apply_editor()
        queue, skipped = self.gather_queue(self.var_source.get())
        if not queue:
            messagebox.showinfo(
                APP_NAME, 'No hay entradas para traducir con los criterios actuales.\n\n'
                'Prueba con el filtro «Sin traducir» o «Todas», o marca\n'
                '«Incluir ya traducidas».', parent=self)
            return
        self.queue = queue
        self.queue_pos = 0
        self.batch_no = 1
        self._build_current_batch()
        if skipped:
            self.lbl_batch_state.config(
                text='Ojo: %d entradas con plurales quedaron fuera del lote '
                     '(edítalas a mano)' % skipped, foreground=self.theme['warn'])

    def next_batch(self):
        if not self.queue:
            messagebox.showinfo(APP_NAME, 'Prepara primero un lote.', parent=self)
            return
        if self.queue_pos >= len(self.queue):
            messagebox.showinfo(APP_NAME, 'No quedan más lotes: cola completada.',
                                parent=self)
            return
        self.batch_no += 1
        self._build_current_batch()

    def _build_current_batch(self):
        prompt, items, self.queue_pos = build_batch(
            self.queue, self.queue_pos, self.txt_tpl.get('1.0', 'end').rstrip('\n'),
            self.var_sep.get().strip() or DEFAULT_CONFIG['separator'],
            int(self.var_max.get()))
        self.batch_items = items
        self.txt_prompt.config(state='normal')
        self.txt_prompt.delete('1.0', 'end')
        self.txt_prompt.insert('1.0', prompt)
        self.txt_prompt.config(state='disabled')
        self.lbl_prompt_chars.config(text='%d caracteres · %d entradas'
                                     % (len(prompt), len(items)))
        remaining = len(self.queue) - self.queue_pos
        self.lbl_batch_state.config(
            text='Lote %d: %d entradas · quedan %d en la cola'
                 % (self.batch_no, len(items), remaining), foreground=self.theme['ok'])
        self._to_clipboard(prompt)
        self.nb.select(self.ai_tab)

    def copy_prompt(self):
        prompt = self.txt_prompt.get('1.0', 'end').rstrip('\n')
        if prompt:
            self._to_clipboard(prompt)
            self.lbl_batch_state.config(text='Prompt copiado al portapapeles',
                                        foreground='#0a5')

    def apply_result(self, then_next):
        if not self.batch_items:
            messagebox.showinfo(APP_NAME, 'Prepara primero un lote.', parent=self)
            return
        raw = self.txt_result.get('1.0', 'end')
        sep = self.var_sep.get().strip()
        results = parse_ai_result(raw, sep)
        if not results:
            messagebox.showwarning(
                APP_NAME, 'No se detectaron líneas numeradas en la respuesta.\n\n'
                'Asegúrate de pegar la traducción completa de la IA.', parent=self)
            return
        applied, missing, empties, undo = apply_batch(self.batch_items, results)

        # respaldo posicional: la IA respetó el orden pero no la numeración
        note = ''
        if applied == 0 and results:
            vals = [results[k] for k in sorted(results)]
            if len(vals) == len(self.batch_items):
                undo = []
                for (num, e), val in zip(self.batch_items, vals):
                    undo.append((e, e.msgstr,
                                 (dict(e.msgstr_plural) if e.msgstr_plural else None),
                                 list(e.flags)))
                    e.msgstr = val.strip()
                    if 'fuzzy' in e.flags:
                        e.flags.remove('fuzzy')
                    applied = len(self.batch_items)
                note = ' (asignadas por orden: la IA no numeró las líneas)'
        if applied == 0:
            messagebox.showwarning(
                APP_NAME, 'Ninguna línea de la respuesta coincidió con el lote.\n\n'
                '¿Pegaste la respuesta de otro lote?', parent=self)
            return

        self._push_undo(undo)
        for num, e in self.batch_items:
            i = self._idx_by_id.get(id(e))
            if i is not None:
                self.update_row(i)
        self.refresh_counts()
        self.mark_dirty()
        self.txt_result.delete('1.0', 'end')

        missing_txt = ''
        if missing:
            shown = ', '.join(str(n) for n in missing[:12])
            if len(missing) > 12:
                shown += '…'
            missing_txt = '\nNo llegó la línea: %s' % shown
        if empties:
            missing_txt += '\n%d líneas llegaron vacías' % empties

        if then_next:
            if self.queue_pos < len(self.queue):
                self.batch_no += 1
                self._build_current_batch()
            else:
                self.lbl_batch_state.config(
                    text='Cola completada: guarda el .po y compila el .mo',
                    foreground=self.theme['ok'])
                if not missing and not empties:
                    messagebox.showinfo(
                        APP_NAME, 'Aplicadas %d traducciones%s.\n\n'
                        '¡Cola completada! No quedan más lotes.' % (applied, note),
                        parent=self)
        else:
            self.lbl_batch_state.config(
                text='Aplicadas %d traducciones%s' % (applied, note), foreground=self.theme['ok'])
        if missing_txt:
            self.lbl_batch_state.config(
                text=('Aplicadas %d%s' % (applied, note)) + missing_txt.replace('\n', ' · '),
                foreground=self.theme['warn'])

    def undo_last(self):
        if not self.undo_stack:
            messagebox.showinfo(APP_NAME, 'No hay acciones que deshacer.', parent=self)
            return
        snaps = self.undo_stack.pop()
        for e, msgstr, plural, flags in snaps:
            e.msgstr = msgstr
            if plural is not None:
                e.msgstr_plural = plural
            e.flags[:] = flags
            i = self._idx_by_id.get(id(e))
            if i is not None:
                self.update_row(i)
        self.refresh_counts()
        self.mark_dirty()
        if self.current_idx is not None:
            self.load_editor(self.current_idx)
        self.lbl_batch_state.config(text='Deshechas %d entradas' % len(snaps),
                                    foreground=self.theme['warn'])

    def open_chat(self):
        url = CHAT_URLS.get(self.var_chat.get())
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------ varios
    def _to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self):
        name = self.po_path.name if self.po_path else ''
        star = ' •' if self.dirty else ''
        self.title('%s %s%s%s' % (APP_NAME, APP_VERSION,
                                  (' — ' + name) if name else '', star))

    def _set_placeholder_states(self):
        pass

    def show_guide(self):
        messagebox.showinfo(APP_NAME + ' — Guía rápida', GUIA_RAPIDA, parent=self)

    def show_about(self):
        messagebox.showinfo(
            'Acerca de', '%s %s\n\nEditor de traducciones .po/.pot/.mo con\n'
            'traducción asistida por IA por lotes (portapapeles).\n\n'
            'Basado en polib (MIT) · Python + tkinter' % (APP_NAME, APP_VERSION),
            parent=self)

    def _check_save_changes(self):
        if not self.dirty or self.po is None:
            return True
        r = messagebox.askyesnocancel(APP_NAME, 'Hay cambios sin guardar.\n\n¿Guardar ahora?',
                                      parent=self)
        if r is None:
            return False
        if r:
            self.save_po()
        return True

    def _on_close(self):
        if not self._check_save_changes():
            return
        self._save_config()
        self.destroy()

    # ------------------------------------------------------------ config
    def _load_config(self):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception:
            pass

    def _apply_config(self):
        self.var_sep.set(self.cfg.get('separator', DEFAULT_CONFIG['separator']))
        try:
            self.var_max.set(int(self.cfg.get('max_chars', 8000)))
        except Exception:
            self.var_max.set(8000)
        self.var_include_tr.set(bool(self.cfg.get('include_translated', False)))
        self.var_chat.set(self.cfg.get('chat', 'ChatGPT'))
        self.txt_tpl.delete('1.0', 'end')
        self.txt_tpl.insert('1.0', self.cfg.get('prompt', DEFAULT_PROMPT))
        geo = self.cfg.get('geometry')
        if geo:
            try:
                self.geometry(geo)
            except Exception:
                pass

    def _save_config(self):
        self.cfg.update({
            'separator': self.var_sep.get(),
            'max_chars': int(self.var_max.get() or 8000),
            'prompt': self.txt_tpl.get('1.0', 'end').rstrip('\n'),
            'include_translated': bool(self.var_include_tr.get()),
            'chat': self.var_chat.get(),
            'geometry': self.geometry(),
            'theme': self.var_theme.get() if hasattr(self, 'var_theme')
                     else self.cfg.get('theme', 'auto'),
        })
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass


def enable_high_dpi():
    """Nitidez en pantallas HiDPI de Windows."""
    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main():
    enable_high_dpi()
    app = PoTranslatorApp()
    app.mainloop()


if __name__ == '__main__':
    main()
