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
import os
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
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

APP_NAME = 'PoTranslator'
APP_VERSION = '1.5'

def _config_path():
    """Ruta del archivo de configuración.

    - Ejecutando desde Python:  ~/.potranslator.json
    - Versión portable compilada: dentro de la carpeta _internal, junto
      al resto de archivos de la app (así los ajustes — incluido el
      idioma elegido — viajan con la carpeta). Si existe una
      configuración vieja en el HOME, se migra automáticamente.
    """
    home_cfg = Path.home() / '.potranslator.json'
    if not getattr(sys, 'frozen', False):
        return home_cfg
    base = Path(getattr(sys, '_MEIPASS', '') or Path(sys.executable).parent)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return home_cfg
    cfg = base / '.potranslator.json'
    if not cfg.exists() and home_cfg.exists():
        try:
            shutil.copy2(str(home_cfg), str(cfg))
        except Exception:
            return home_cfg
    return cfg


CONFIG_PATH = _config_path()

CHAT_URLS = {
    'ChatGPT': 'https://chatgpt.com/',
    'Claude': 'https://claude.ai/chat',
    'Gemini': 'https://gemini.google.com/app',
    'Copilot': 'https://copilot.microsoft.com/',
    'DeepL (trad.)': 'https://www.deepl.com/translator',
}

# ----------------------------------------------------------------------------
# Idiomas de la interfaz (v1.5+)
# ----------------------------------------------------------------------------
APP_LANGS = [
    ('es', 'Español'),
    ('en', 'English'),
    ('fr', 'Français'),
    ('it', 'Italiano'),
    ('pt', 'Português'),
    ('pl', 'Polski'),
    ('ru', 'Русский'),
    ('zh', '中文'),
    ('ja', '日本語'),
]
_LANG_CODES = {c for c, _n in APP_LANGS}

_LANG = ['es']          # idioma activo de la interfaz


def set_app_lang(code):
    """Fija el idioma activo de la interfaz (fallback: español)."""
    _LANG[0] = code if code in _LANG_CODES else 'es'


def _(key, *args):
    """Devuelve la cadena `key` en el idioma activo (fallback: español)."""
    d = TR.get(key)
    txt = (d.get(_LANG[0]) or d.get('es')) if d else None
    if txt is None:
        return key
    if args:
        try:
            return txt % args
        except Exception:
            return txt
    return txt


def _detect_system_lang():
    """Idioma del sistema ('es', 'en', ...) o 'en' si no se puede saber."""
    cands = []
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        v = os.environ.get(var)
        if v:
            cands.extend(v.split(':'))
    try:
        import locale
        for getter in (locale.getlocale, locale.getdefaultlocale):
            try:
                loc = getter()[0]
            except Exception:
                loc = None
            if loc:
                cands.append(loc)
                break
    except Exception:
        pass
    # nombres de configuración regional de Windows: 'Spanish_Spain', ...
    win_names = {'spanish': 'es', 'english': 'en', 'french': 'fr',
                 'italian': 'it', 'portuguese': 'pt', 'polish': 'pl',
                 'russian': 'ru', 'chinese': 'zh', 'japanese': 'ja'}
    for c in cands:
        cl = (c or '').lower()
        if not cl or cl in ('c', 'posix'):
            continue
        for code in sorted(_LANG_CODES):
            if (cl.startswith(code + '_') or cl.startswith(code + '-')
                    or cl.startswith(code + '.') or cl == code):
                return code
        for name, code in win_names.items():
            if cl.startswith(name):
                return code
    return 'en'


# ---------------------------------------------------------------------------
# Tabla de traducciones de la interfaz: clave -> {idioma: texto}
# (el español es la referencia; si faltara un idioma se muestra el español)
# ---------------------------------------------------------------------------
TR = {
    # ---------- menús ----------
    'm_archivo': {
        'es': 'Archivo', 'en': 'File', 'fr': 'Fichier', 'it': 'File',
        'pt': 'Arquivo', 'pl': 'Plik', 'ru': 'Файл', 'zh': '文件',
        'ja': 'ファイル',
    },
    'm_editar': {
        'es': 'Editar', 'en': 'Edit', 'fr': 'Édition', 'it': 'Modifica',
        'pt': 'Editar', 'pl': 'Edycja', 'ru': 'Правка', 'zh': '编辑',
        'ja': '編集',
    },
    'm_lote': {
        'es': 'Lote', 'en': 'Batch', 'fr': 'Lot', 'it': 'Lotto',
        'pt': 'Lote', 'pl': 'Partia', 'ru': 'Пакет', 'zh': '批量',
        'ja': 'バッチ',
    },
    'm_ver': {
        'es': 'Ver', 'en': 'View', 'fr': 'Affichage', 'it': 'Visualizza',
        'pt': 'Exibir', 'pl': 'Widok', 'ru': 'Вид', 'zh': '查看',
        'ja': '表示',
    },
    'm_ayuda': {
        'es': 'Ayuda', 'en': 'Help', 'fr': 'Aide', 'it': 'Aiuto',
        'pt': 'Ajuda', 'pl': 'Pomoc', 'ru': 'Справка', 'zh': '帮助',
        'ja': 'ヘルプ',
    },
    'mi_abrir': {
        'es': 'Abrir .po / .pot / .mo…', 'en': 'Open .po / .pot / .mo…',
        'fr': 'Ouvrir .po / .pot / .mo…', 'it': 'Apri .po / .pot / .mo…',
        'pt': 'Abrir .po / .pot / .mo…', 'pl': 'Otwórz .po / .pot / .mo…',
        'ru': 'Открыть .po / .pot / .mo…', 'zh': '打开 .po / .pot / .mo…',
        'ja': '.po / .pot / .mo を開く…',
    },
    'mi_actualizar': {
        'es': 'Actualizar desde POT…', 'en': 'Update from POT…',
        'fr': 'Mettre à jour depuis le POT…', 'it': 'Aggiorna dal POT…',
        'pt': 'Atualizar a partir do POT…', 'pl': 'Aktualizuj z POT…',
        'ru': 'Обновить из POT…', 'zh': '从 POT 更新…',
        'ja': 'POT から更新…',
    },
    'mi_guardar': {
        'es': 'Guardar .po', 'en': 'Save .po', 'fr': 'Enregistrer le .po',
        'it': 'Salva .po', 'pt': 'Salvar .po', 'pl': 'Zapisz .po',
        'ru': 'Сохранить .po', 'zh': '保存 .po', 'ja': '.po を保存',
    },
    'mi_guardar_como': {
        'es': 'Guardar como…', 'en': 'Save as…',
        'fr': 'Enregistrer sous…', 'it': 'Salva come…',
        'pt': 'Salvar como…', 'pl': 'Zapisz jako…',
        'ru': 'Сохранить как…', 'zh': '另存为…', 'ja': '名前を付けて保存…',
    },
    'mi_compilar': {
        'es': 'Compilar .mo', 'en': 'Compile .mo',
        'fr': 'Compiler le .mo', 'it': 'Compila .mo', 'pt': 'Compilar .mo',
        'pl': 'Kompiluj .mo', 'ru': 'Компилировать .mo', 'zh': '编译 .mo',
        'ja': '.mo をコンパイル',
    },
    'mi_salir': {
        'es': 'Salir', 'en': 'Exit', 'fr': 'Quitter', 'it': 'Esci',
        'pt': 'Sair', 'pl': 'Zakończ', 'ru': 'Выход', 'zh': '退出',
        'ja': '終了',
    },
    'mi_ent_ant': {
        'es': 'Entrada anterior', 'en': 'Previous entry',
        'fr': 'Entrée précédente', 'it': 'Voce precedente',
        'pt': 'Entrada anterior', 'pl': 'Poprzedni wpis',
        'ru': 'Предыдущая запись', 'zh': '上一条目', 'ja': '前のエントリ',
    },
    'mi_ent_sig': {
        'es': 'Entrada siguiente', 'en': 'Next entry',
        'fr': 'Entrée suivante', 'it': 'Voce successiva',
        'pt': 'Próxima entrada', 'pl': 'Następny wpis',
        'ru': 'Следующая запись', 'zh': '下一条目', 'ja': '次のエントリ',
    },
    'mi_guardar_ent': {
        'es': 'Guardar entrada', 'en': 'Save entry',
        'fr': "Enregistrer l'entrée", 'it': 'Salva voce',
        'pt': 'Salvar entrada', 'pl': 'Zapisz wpis',
        'ru': 'Сохранить запись', 'zh': '保存条目', 'ja': 'エントリを保存',
    },
    'mi_copiar_orig': {
        'es': 'Copiar original a traducción',
        'en': 'Copy original to translation',
        'fr': "Copier l'original vers la traduction",
        'it': 'Copia l\u2019originale nella traduzione',
        'pt': 'Copiar original para a tradução',
        'pl': 'Kopiuj oryginał do tłumaczenia',
        'ru': 'Копировать оригинал в перевод',
        'zh': '复制原文到译文', 'ja': '原文を翻訳にコピー',
    },
    'mi_fuzzy_toggle': {
        'es': 'Marcar / quitar fuzzy', 'en': 'Toggle fuzzy',
        'fr': 'Activer / désactiver fuzzy', 'it': 'Attiva / disattiva fuzzy',
        'pt': 'Marcar / desmarcar fuzzy', 'pl': 'Zaznacz / odznacz fuzzy',
        'ru': 'Вкл./выкл. fuzzy', 'zh': '标记/取消 fuzzy',
        'ja': 'fuzzy を切り替え',
    },
    'mi_preparar': {
        'es': 'Preparar lote', 'en': 'Prepare batch',
        'fr': 'Préparer le lot', 'it': 'Prepara lotto',
        'pt': 'Preparar lote', 'pl': 'Przygotuj partię',
        'ru': 'Подготовить пакет', 'zh': '准备批次', 'ja': 'バッチを準備',
    },
    'mi_aplicar': {
        'es': 'Aplicar resultado', 'en': 'Apply result',
        'fr': 'Appliquer le résultat', 'it': 'Applica risultato',
        'pt': 'Aplicar resultado', 'pl': 'Zastosuj wynik',
        'ru': 'Применить результат', 'zh': '应用结果', 'ja': '結果を適用',
    },
    'mi_aplicar_sig': {
        'es': 'Aplicar y siguiente lote', 'en': 'Apply and next batch',
        'fr': 'Appliquer et lot suivant', 'it': 'Applica e prossimo lotto',
        'pt': 'Aplicar e próximo lote', 'pl': 'Zastosuj i następna partia',
        'ru': 'Применить и следующий пакет', 'zh': '应用并下一批次',
        'ja': '適用して次のバッチ',
    },
    'mi_sig_lote': {
        'es': 'Siguiente lote (sin aplicar)',
        'en': 'Next batch (without applying)',
        'fr': 'Lot suivant (sans appliquer)',
        'it': 'Lotto successivo (senza applicare)',
        'pt': 'Próximo lote (sem aplicar)',
        'pl': 'Następna partia (bez stosowania)',
        'ru': 'Следующий пакет (без применения)',
        'zh': '下一批次（不应用）', 'ja': '次のバッチ（適用なし）',
    },
    'mi_deshacer': {
        'es': 'Deshacer último lote', 'en': 'Undo last batch',
        'fr': 'Annuler le dernier lot', 'it': 'Annulla ultimo lotto',
        'pt': 'Desfazer último lote', 'pl': 'Cofnij ostatnią partię',
        'ru': 'Отменить последний пакет', 'zh': '撤销上一批次',
        'ja': '最後のバッチを元に戻す',
    },
    'mi_tema': {
        'es': 'Tema', 'en': 'Theme', 'fr': 'Thème', 'it': 'Tema',
        'pt': 'Tema', 'pl': 'Motyw', 'ru': 'Тема', 'zh': '主题',
        'ja': 'テーマ',
    },
    'tema_auto': {
        'es': 'Automático (según el sistema)', 'en': 'Automatic (system)',
        'fr': 'Automatique (système)', 'it': 'Automatico (sistema)',
        'pt': 'Automático (sistema)', 'pl': 'Automatycznie (system)',
        'ru': 'Автоматически (по системе)', 'zh': '自动（跟随系统）',
        'ja': '自動（システムに従う）',
    },
    'tema_claro': {
        'es': 'Claro', 'en': 'Light', 'fr': 'Clair', 'it': 'Chiaro',
        'pt': 'Claro', 'pl': 'Jasny', 'ru': 'Светлая', 'zh': '浅色',
        'ja': 'ライト',
    },
    'tema_oscuro': {
        'es': 'Oscuro', 'en': 'Dark', 'fr': 'Sombre', 'it': 'Scuro',
        'pt': 'Escuro', 'pl': 'Ciemny', 'ru': 'Тёмная', 'zh': '深色',
        'ja': 'ダーク',
    },
    'mi_idioma': {
        'es': 'Idioma', 'en': 'Language', 'fr': 'Langue', 'it': 'Lingua',
        'pt': 'Idioma', 'pl': 'Język', 'ru': 'Язык', 'zh': '语言',
        'ja': '言語',
    },
    'mi_guia': {
        'es': 'Guía rápida', 'en': 'Quick guide', 'fr': 'Guide rapide',
        'it': 'Guida rapida', 'pt': 'Guia rápido',
        'pl': 'Szybki przewodnik', 'ru': 'Краткое руководство',
        'zh': '快速指南', 'ja': 'クイックガイド',
    },
    'mi_acerca': {
        'es': 'Acerca de…', 'en': 'About…', 'fr': 'À propos…',
        'it': 'Informazioni su…', 'pt': 'Sobre…', 'pl': 'O programie…',
        'ru': 'О программе…', 'zh': '关于…', 'ja': 'バージョン情報…',
    },
    'acc_up': {
        'es': 'Ctrl+Arriba', 'en': 'Ctrl+Up', 'fr': 'Ctrl+Haut',
        'it': 'Ctrl+Su', 'pt': 'Ctrl+Acima', 'pl': 'Ctrl+Góra',
        'ru': 'Ctrl+Вверх', 'zh': 'Ctrl+↑', 'ja': 'Ctrl+↑',
    },
    'acc_down': {
        'es': 'Ctrl+Abajo', 'en': 'Ctrl+Down', 'fr': 'Ctrl+Bas',
        'it': 'Ctrl+Giù', 'pt': 'Ctrl+Abaixo', 'pl': 'Ctrl+Dół',
        'ru': 'Ctrl+Вниз', 'zh': 'Ctrl+↓', 'ja': 'Ctrl+↓',
    },
}
# fin TR parte 1 (menús)

TR.update({
    # ---------- barra de herramientas ----------
    'tb_abrir': {
        'es': 'Abrir .po...', 'en': 'Open .po...', 'fr': 'Ouvrir .po...',
        'it': 'Apri .po...', 'pt': 'Abrir .po...', 'pl': 'Otwórz .po...',
        'ru': 'Открыть .po...', 'zh': '打开 .po...', 'ja': '.po を開く...',
    },
    'tb_actualizar': {
        'es': 'Actualizar desde POT...', 'en': 'Update from POT...',
        'fr': 'Mettre à jour depuis POT...', 'it': 'Aggiorna dal POT...',
        'pt': 'Atualizar do POT...', 'pl': 'Aktualizuj z POT...',
        'ru': 'Обновить из POT...', 'zh': '从 POT 更新...',
        'ja': 'POT から更新...',
    },
    'tb_guardar': {
        'es': 'Guardar .po', 'en': 'Save .po', 'fr': 'Enregistrer .po',
        'it': 'Salva .po', 'pt': 'Salvar .po', 'pl': 'Zapisz .po',
        'ru': 'Сохранить .po', 'zh': '保存 .po', 'ja': '.po を保存',
    },
    'tb_guardar_como': {
        'es': 'Guardar como...', 'en': 'Save as...',
        'fr': 'Enregistrer sous...', 'it': 'Salva come...',
        'pt': 'Salvar como...', 'pl': 'Zapisz jako...',
        'ru': 'Сохранить как...', 'zh': '另存为...',
        'ja': '名前を付けて保存...',
    },
    'tb_compilar': {
        'es': 'Compilar .mo', 'en': 'Compile .mo', 'fr': 'Compiler .mo',
        'it': 'Compila .mo', 'pt': 'Compilar .mo', 'pl': 'Kompiluj .mo',
        'ru': 'Компилировать .mo', 'zh': '编译 .mo', 'ja': '.mo をコンパイル',
    },
    'sin_archivo': {
        'es': '(ningún archivo abierto)', 'en': '(no file open)',
        'fr': '(aucun fichier ouvert)', 'it': '(nessun file aperto)',
        'pt': '(nenhum arquivo aberto)', 'pl': '(brak otwartego pliku)',
        'ru': '(файл не открыт)', 'zh': '（未打开文件）',
        'ja': '（ファイル未開）',
    },
    # ---------- filtros y tabla ----------
    'fl_mostrar': {
        'es': 'Mostrar:', 'en': 'Show:', 'fr': 'Afficher :', 'it': 'Mostra:',
        'pt': 'Exibir:', 'pl': 'Pokaż:', 'ru': 'Показать:', 'zh': '显示：',
        'ja': '表示：',
    },
    'filter_all': {
        'es': 'Todas', 'en': 'All', 'fr': 'Toutes', 'it': 'Tutte',
        'pt': 'Todas', 'pl': 'Wszystkie', 'ru': 'Все', 'zh': '全部',
        'ja': 'すべて',
    },
    'filter_untr': {
        'es': 'Sin traducir', 'en': 'Untranslated', 'fr': 'Non traduites',
        'it': 'Non tradotte', 'pt': 'Sem tradução',
        'pl': 'Nieprzetłumaczone', 'ru': 'Без перевода', 'zh': '未翻译',
        'ja': '未翻訳',
    },
    'filter_fuzzy': {
        'es': 'Con fuzzy', 'en': 'With fuzzy', 'fr': 'Avec fuzzy',
        'it': 'Con fuzzy', 'pt': 'Com fuzzy', 'pl': 'Z fuzzy',
        'ru': 'С fuzzy', 'zh': '含 fuzzy', 'ja': 'fuzzy あり',
    },
    'filter_trans': {
        'es': 'Traducidas', 'en': 'Translated', 'fr': 'Traduites',
        'it': 'Tradotte', 'pt': 'Traduzidas', 'pl': 'Przetłumaczone',
        'ru': 'Переведённые', 'zh': '已翻译', 'ja': '翻訳済み',
    },
    'fl_buscar': {
        'es': 'Buscar:', 'en': 'Search:', 'fr': 'Rechercher :',
        'it': 'Cerca:', 'pt': 'Buscar:', 'pl': 'Szukaj:', 'ru': 'Поиск:',
        'zh': '搜索：', 'ja': '検索：',
    },
    'fl_obs': {
        'es': 'Incluir obsoletas', 'en': 'Include obsolete',
        'fr': 'Inclure obsolètes', 'it': 'Includi obsolete',
        'pt': 'Incluir obsoletas', 'pl': 'Uwzględnij przestarzałe',
        'ru': 'Показывать устаревшие', 'zh': '包含已废弃',
        'ja': '廃止を含む',
    },
    'fl_seleccionar': {
        'es': 'Seleccionar filtradas', 'en': 'Select filtered',
        'fr': 'Sélectionner filtrées', 'it': 'Seleziona filtrate',
        'pt': 'Selecionar filtradas', 'pl': 'Zaznacz przefiltrowane',
        'ru': 'Выделить отфильтрованные', 'zh': '选择筛选结果',
        'ja': '絞り込みを選択',
    },
    'lbl_sel_1': {
        'es': '1 seleccionada', 'en': '1 selected', 'fr': '1 sélectionnée',
        'it': '1 selezionata', 'pt': '1 selecionada', 'pl': 'Zaznaczono 1',
        'ru': 'Выбрана 1', 'zh': '已选 1 项', 'ja': '1 件選択',
    },
    'lbl_sel_n': {
        'es': '%d seleccionadas', 'en': '%d selected',
        'fr': '%d sélectionnées', 'it': '%d selezionate',
        'pt': '%d selecionadas', 'pl': 'Zaznaczono: %d',
        'ru': 'Выбрано: %d', 'zh': '已选 %d 项', 'ja': '%d 件選択',
    },
    'col_estado': {
        'es': 'Estado', 'en': 'State', 'fr': 'État', 'it': 'Stato',
        'pt': 'Estado', 'pl': 'Stan', 'ru': 'Состояние', 'zh': '状态',
        'ja': '状態',
    },
    'col_orig': {
        'es': 'Original', 'en': 'Original', 'fr': 'Original',
        'it': 'Originale', 'pt': 'Original', 'pl': 'Oryginał',
        'ru': 'Оригинал', 'zh': '原文', 'ja': '原文',
    },
    'col_trad': {
        'es': 'Traducción', 'en': 'Translation', 'fr': 'Traduction',
        'it': 'Traduzione', 'pt': 'Tradução', 'pl': 'Tłumaczenie',
        'ru': 'Перевод', 'zh': '译文', 'ja': '訳文',
    },
    'col_refs': {
        'es': 'Origen', 'en': 'Source', 'fr': 'Source', 'it': 'Origine',
        'pt': 'Origem', 'pl': 'Źródło', 'ru': 'Источник', 'zh': '位置',
        'ja': '参照',
    },
    'state_trans': {
        'es': 'Traducida', 'en': 'Translated', 'fr': 'Traduite',
        'it': 'Tradotta', 'pt': 'Traduzida', 'pl': 'Przetłumaczona',
        'ru': 'Переведено', 'zh': '已翻译', 'ja': '翻訳済み',
    },
    'state_untr': {
        'es': 'Vacía', 'en': 'Empty', 'fr': 'Vide', 'it': 'Vuota',
        'pt': 'Vazia', 'pl': 'Pusta', 'ru': 'Пусто', 'zh': '空',
        'ja': '空',
    },
    'state_fuzzy': {
        'es': 'Fuzzy', 'en': 'Fuzzy', 'fr': 'Fuzzy', 'it': 'Fuzzy',
        'pt': 'Fuzzy', 'pl': 'Fuzzy', 'ru': 'Fuzzy', 'zh': 'Fuzzy',
        'ja': 'Fuzzy',
    },
    'state_obs': {
        'es': 'Obsoleta', 'en': 'Obsolete', 'fr': 'Obsolète',
        'it': 'Obsoleta', 'pt': 'Obsoleta', 'pl': 'Przestarzała',
        'ru': 'Устаревшая', 'zh': '已废弃', 'ja': '廃止',
    },
    # ---------- barra de estado ----------
    'st_abre': {
        'es': 'Abre un archivo .po para comenzar',
        'en': 'Open a .po file to get started',
        'fr': 'Ouvrez un fichier .po pour commencer',
        'it': 'Apri un file .po per iniziare',
        'pt': 'Abra um arquivo .po para começar',
        'pl': 'Otwórz plik .po, aby rozpocząć',
        'ru': 'Откройте файл .po, чтобы начать',
        'zh': '打开 .po 文件开始', 'ja': '.po ファイルを開いて開始',
    },
    'st_counts': {
        'es': 'Entradas: %d   ·   Traducidas: %d   ·   Fuzzy: %d   ·   '
             'Sin traducir: %d%s   ·   %d%%',
        'en': 'Entries: %d   ·   Translated: %d   ·   Fuzzy: %d   ·   '
              'Untranslated: %d%s   ·   %d%%',
        'fr': 'Entrées : %d   ·   Traduites : %d   ·   Fuzzy : %d   ·   '
              'Non traduites : %d%s   ·   %d%%',
        'it': 'Voci: %d   ·   Tradotte: %d   ·   Fuzzy: %d   ·   '
              'Non tradotte: %d%s   ·   %d%%',
        'pt': 'Entradas: %d   ·   Traduzidas: %d   ·   Fuzzy: %d   ·   '
              'Sem tradução: %d%s   ·   %d%%',
        'pl': 'Wpisy: %d   ·   Przetłumaczone: %d   ·   Fuzzy: %d   ·   '
              'Nieprzetłumaczone: %d%s   ·   %d%%',
        'ru': 'Записей: %d   ·   Переведено: %d   ·   Fuzzy: %d   ·   '
              'Без перевода: %d%s   ·   %d%%',
        'zh': '条目：%d   ·   已翻译：%d   ·   Fuzzy：%d   ·   '
              '未翻译：%d%s   ·   %d%%',
        'ja': 'エントリ：%d   ·   翻訳済：%d   ·   Fuzzy：%d   ·   '
              '未翻訳：%d%s   ·   %d%%',
    },
    'st_counts_obs': {
        'es': '   ·   Obsoletas: %d', 'en': '   ·   Obsolete: %d',
        'fr': '   ·   Obsolètes : %d', 'it': '   ·   Obsolete: %d',
        'pt': '   ·   Obsoletas: %d', 'pl': '   ·   Przestarzałe: %d',
        'ru': '   ·   Устаревших: %d', 'zh': '   ·   已废弃：%d',
        'ja': '   ·   廃止：%d',
    },
    'st_guardado': {
        'es': 'Guardado %s', 'en': 'Saved %s', 'fr': 'Enregistré %s',
        'it': 'Salvato %s', 'pt': 'Salvo %s', 'pl': 'Zapisano %s',
        'ru': 'Сохранено %s', 'zh': '已保存 %s', 'ja': '保存しました %s',
    },
    'st_mo_ok': {
        'es': '.mo compilado (%s)', 'en': '.mo compiled (%s)',
        'fr': '.mo compilé (%s)', 'it': '.mo compilato (%s)',
        'pt': '.mo compilado (%s)', 'pl': '.mo skompilowany (%s)',
        'ru': '.mo скомпилирован (%s)', 'zh': '.mo 已编译（%s）',
        'ja': '.mo をコンパイルしました（%s）',
    },
    'st_orig_copiados': {
        'es': '%d originales copiados', 'en': '%d originals copied',
        'fr': '%d originaux copiés', 'it': '%d originali copiati',
        'pt': '%d originais copiados', 'pl': 'Skopiowano %d oryginałów',
        'ru': 'Скопировано оригиналов: %d', 'zh': '已复制 %d 条原文',
        'ja': '%d 件の原文をコピーしました',
    },
    'default_po_name': {
        'es': 'traduccion', 'en': 'translation', 'fr': 'traduction',
        'it': 'traduzione', 'pt': 'traducao', 'pl': 'tlumaczenie',
        'ru': 'perevod', 'zh': 'fanyi', 'ja': 'honyaku',
    },
})
# fin TR parte 2 (herramientas/filtros/tabla)

TR.update({
    # ---------- pestaña: editor de entrada ----------
    'tab_editor': {
        'es': '  Editor de entrada  ', 'en': '  Entry editor  ',
        'fr': "  Éditeur d'entrée  ", 'it': '  Editor voce  ',
        'pt': '  Editor de entrada  ', 'pl': '  Edytor wpisu  ',
        'ru': '  Редактор записи  ', 'zh': '  条目编辑器  ',
        'ja': '  エントリエディタ  ',
    },
    'chk_fuzzy': {
        'es': 'Fuzzy (revisar)', 'en': 'Fuzzy (review)',
        'fr': 'Fuzzy (à vérifier)', 'it': 'Fuzzy (da rivedere)',
        'pt': 'Fuzzy (revisar)', 'pl': 'Fuzzy (do sprawdzenia)',
        'ru': 'Fuzzy (проверить)', 'zh': 'Fuzzy（待复查）',
        'ja': 'Fuzzy（要確認）',
    },
    'lf_original': {
        'es': ' Original ', 'en': ' Original ', 'fr': ' Original ',
        'it': ' Originale ', 'pt': ' Original ', 'pl': ' Oryginał ',
        'ru': ' Оригинал ', 'zh': ' 原文 ', 'ja': ' 原文 ',
    },
    'lf_trad': {
        'es': ' Traducción ', 'en': ' Translation ', 'fr': ' Traduction ',
        'it': ' Traduzione ', 'pt': ' Tradução ', 'pl': ' Tłumaczenie ',
        'ru': ' Перевод ', 'zh': ' 译文 ', 'ja': ' 訳文 ',
    },
    'btn_anterior': {
        'es': '<< Anterior', 'en': '<< Previous', 'fr': '<< Précédent',
        'it': '<< Precedente', 'pt': '<< Anterior', 'pl': '<< Poprzedni',
        'ru': '<< Назад', 'zh': '<< 上一条', 'ja': '<< 前へ',
    },
    'btn_siguiente': {
        'es': 'Siguiente >>', 'en': 'Next >>', 'fr': 'Suivant >>',
        'it': 'Successivo >>', 'pt': 'Próxima >>', 'pl': 'Następny >>',
        'ru': 'Вперёд >>', 'zh': '下一条 >>', 'ja': '次へ >>',
    },
    'lbl_entrada_pos': {
        'es': 'Entrada %d / %d', 'en': 'Entry %d / %d',
        'fr': 'Entrée %d / %d', 'it': 'Voce %d / %d',
        'pt': 'Entrada %d / %d', 'pl': 'Wpis %d / %d',
        'ru': 'Запись %d / %d', 'zh': '条目 %d / %d',
        'ja': 'エントリ %d / %d',
    },
    # ---------- pestaña: traducción IA por lotes ----------
    'tab_ia': {
        'es': '  Traducción IA por lotes  ',
        'en': '  AI batch translation  ',
        'fr': '  Traduction IA par lots  ',
        'it': '  Traduzione IA per lotti  ',
        'pt': '  Tradução IA por lotes  ',
        'pl': '  Tłumaczenie AI partiami  ',
        'ru': '  Пакетный перевод с ИИ  ',
        'zh': '  AI 批量翻译  ', 'ja': '  AI 一括翻訳  ',
    },
    'lbl_origen': {
        'es': 'Origen del lote:', 'en': 'Batch source:',
        'fr': 'Source du lot :', 'it': 'Origine del lotto:',
        'pt': 'Origem do lote:', 'pl': 'Źródło partii:',
        'ru': 'Источник пакета:', 'zh': '批次来源：', 'ja': 'バッチの範囲：',
    },
    'rb_seleccionadas': {
        'es': 'Seleccionadas en la tabla (%d)',
        'en': 'Selected in table (%d)',
        'fr': 'Sélectionnées dans le tableau (%d)',
        'it': 'Selezionate nella tabella (%d)',
        'pt': 'Selecionadas na tabela (%d)',
        'pl': 'Zaznaczone w tabeli (%d)',
        'ru': 'Выделенные в таблице (%d)',
        'zh': '表中选中（%d）', 'ja': '表で選択（%d）',
    },
    'rb_filtradas': {
        'es': 'Entradas filtradas (%d)', 'en': 'Filtered entries (%d)',
        'fr': 'Entrées filtrées (%d)', 'it': 'Voci filtrate (%d)',
        'pt': 'Entradas filtradas (%d)', 'pl': 'Wpisy przefiltrowane (%d)',
        'ru': 'Отфильтрованные записи (%d)', 'zh': '筛选的条目（%d）',
        'ja': '絞り込んだエントリ（%d）',
    },
    'chk_incluir_tr': {
        'es': 'Incluir ya traducidas', 'en': 'Include already translated',
        'fr': 'Inclure déjà traduites', 'it': 'Includi già tradotte',
        'pt': 'Incluir já traduzidas', 'pl': 'Uwzględnij przetłumaczone',
        'ru': 'Включить уже переведённые', 'zh': '包含已翻译',
        'ja': '翻訳済みを含む',
    },
    'lbl_separador': {
        'es': 'Separador:', 'en': 'Separator:', 'fr': 'Séparateur :',
        'it': 'Separatore:', 'pt': 'Separador:', 'pl': 'Separator:',
        'ru': 'Разделитель:', 'zh': '分隔符：', 'ja': '区切り文字：',
    },
    'lbl_max': {
        'es': 'Máx. caracteres por lote:',
        'en': 'Max chars per batch:',
        'fr': 'Car. max par lot :',
        'it': 'Max caratteri per lotto:',
        'pt': 'Máx. caracteres por lote:',
        'pl': 'Maks. znaków na partię:',
        'ru': 'Макс. символов на пакет:',
        'zh': '每批次最多字符：', 'ja': 'バッチあたりの最大文字数：',
    },
    'lbl_chat': {
        'es': 'Chat de IA:', 'en': 'AI chat:', 'fr': 'Chat IA :',
        'it': 'Chat IA:', 'pt': 'Chat de IA:', 'pl': 'Czat AI:',
        'ru': 'ИИ-чат:', 'zh': 'AI 聊天：', 'ja': 'AI チャット：',
    },
    'btn_abrir_chat': {
        'es': 'Abrir chat', 'en': 'Open chat', 'fr': 'Ouvrir le chat',
        'it': 'Apri chat', 'pt': 'Abrir chat', 'pl': 'Otwórz czat',
        'ru': 'Открыть чат', 'zh': '打开聊天', 'ja': 'チャットを開く',
    },
    'lf_prompt': {
        'es': ' Prompt para la IA (se copia al preparar) ',
        'en': ' Prompt for the AI (copied when preparing) ',
        'fr': " Prompt pour l'IA (copié lors de la préparation) ",
        'it': ' Prompt per l\u2019IA (copiato alla preparazione) ',
        'pt': ' Prompt para a IA (copiado ao preparar) ',
        'pl': ' Prompt dla AI (kopiowany przy przygotowaniu) ',
        'ru': ' Запрос для ИИ (копируется при подготовке) ',
        'zh': ' 给 AI 的提示词（准备时复制） ',
        'ja': ' AI 用プロンプト（準備時にコピー） ',
    },
    'lf_respuesta': {
        'es': ' Respuesta de la IA (pega aquí) ',
        'en': ' AI response (paste here) ',
        'fr': " Réponse de l'IA (collez ici) ",
        'it': " Risposta dell'IA (incolla qui) ",
        'pt': ' Resposta da IA (cole aqui) ',
        'pl': ' Odpowiedź AI (wklej tutaj) ',
        'ru': ' Ответ ИИ (вставьте здесь) ',
        'zh': ' AI 回复（粘贴到此处） ',
        'ja': ' AI の回答（ここに貼り付け） ',
    },
    'lf_plantilla': {
        'es': ' Plantilla del prompt (se guarda automáticamente) ',
        'en': ' Prompt template (saved automatically) ',
        'fr': ' Modèle de prompt (enregistré automatiquement) ',
        'it': ' Modello di prompt (salvato automaticamente) ',
        'pt': ' Modelo do prompt (salvo automaticamente) ',
        'pl': ' Szablon promptu (zapisywany automatycznie) ',
        'ru': ' Шаблон запроса (сохраняется автоматически) ',
        'zh': ' 提示词模板（自动保存） ',
        'ja': ' プロンプトテンプレート（自動保存） ',
    },
    'btn_copiar_todo': {
        'es': 'Copiar todo', 'en': 'Copy all', 'fr': 'Tout copier',
        'it': 'Copia tutto', 'pt': 'Copiar tudo',
        'pl': 'Kopiuj wszystko', 'ru': 'Копировать всё',
        'zh': '全部复制', 'ja': 'すべてコピー',
    },
    'chars_n': {
        'es': '%d caracteres', 'en': '%d characters',
        'fr': '%d caractères', 'it': '%d caratteri',
        'pt': '%d caracteres', 'pl': '%d znaków', 'ru': '%d символов',
        'zh': '%d 字符', 'ja': '%d 文字',
    },
    'chars_entradas': {
        'es': '%d caracteres · %d entradas',
        'en': '%d characters · %d entries',
        'fr': '%d caractères · %d entrées',
        'it': '%d caratteri · %d voci',
        'pt': '%d caracteres · %d entradas',
        'pl': '%d znaków · %d wpisów',
        'ru': '%d символов · %d записей',
        'zh': '%d 字符 · %d 条', 'ja': '%d 文字 · %d 件',
    },
    # ---------- editor de plurales ----------
    'lf_plurales': {
        'es': ' Formas plurales ', 'en': ' Plural forms ',
        'fr': ' Formes plurielles ', 'it': ' Forme plurali ',
        'pt': ' Formas plurais ', 'pl': ' Formy liczby mnogiej ',
        'ru': ' Формы множественного числа ', 'zh': ' 复数形式 ',
        'ja': ' 複数形 ',
    },
    'lbl_msgid_plural': {
        'es': 'msgid_plural (original):', 'en': 'msgid_plural (original):',
        'fr': 'msgid_plural (original) :',
        'it': 'msgid_plural (originale):',
        'pt': 'msgid_plural (original):', 'pl': 'msgid_plural (oryginał):',
        'ru': 'msgid_plural (оригинал):', 'zh': 'msgid_plural（原文）：',
        'ja': 'msgid_plural（原文）：',
    },
    'lbl_singular': {
        'es': 'singular', 'en': 'singular', 'fr': 'singulier',
        'it': 'singolare', 'pt': 'singular',
        'pl': 'liczba pojedyncza', 'ru': 'ед. число', 'zh': '单数',
        'ja': '単数',
    },
    'lbl_plural': {
        'es': 'plural', 'en': 'plural', 'fr': 'pluriel', 'it': 'plurale',
        'pt': 'plural', 'pl': 'liczba mnoga', 'ru': 'мн. число',
        'zh': '复数', 'ja': '複数',
    },
    'lbl_forma_n': {
        'es': 'forma %d', 'en': 'form %d', 'fr': 'forme %d',
        'it': 'forma %d', 'pt': 'forma %d', 'pl': 'forma %d',
        'ru': 'форма %d', 'zh': '形式 %d', 'ja': '形式 %d',
    },
    'lbl_msgstr_n': {
        'es': 'msgstr[%d] (%s):', 'en': 'msgstr[%d] (%s):',
        'fr': 'msgstr[%d] (%s) :', 'it': 'msgstr[%d] (%s):',
        'pt': 'msgstr[%d] (%s):', 'pl': 'msgstr[%d] (%s):',
        'ru': 'msgstr[%d] (%s):', 'zh': 'msgstr[%d]（%s）：',
        'ja': 'msgstr[%d]（%s）：',
    },
})
# fin TR parte 3 (pestañas/plurales)

TR.update({
    # ---------- títulos y filtros de diálogos ----------
    'dlg_abrir': {
        'es': 'Abrir archivo de traducción',
        'en': 'Open translation file',
        'fr': 'Ouvrir un fichier de traduction',
        'it': 'Apri file di traduzione',
        'pt': 'Abrir arquivo de tradução',
        'pl': 'Otwórz plik tłumaczenia',
        'ru': 'Открыть файл перевода', 'zh': '打开翻译文件',
        'ja': '翻訳ファイルを開く',
    },
    'dlg_pot': {
        'es': 'Elegir la plantilla nueva (.pot)',
        'en': 'Choose the new template (.pot)',
        'fr': 'Choisir le nouveau modèle (.pot)',
        'it': 'Scegli il nuovo modello (.pot)',
        'pt': 'Escolher o novo modelo (.pot)',
        'pl': 'Wybierz nowy szablon (.pot)',
        'ru': 'Выберите новый шаблон (.pot)', 'zh': '选择新模板（.pot）',
        'ja': '新しいテンプレートを選択（.pot）',
    },
    'dlg_guardar_como': {
        'es': 'Guardar .po como', 'en': 'Save .po as',
        'fr': 'Enregistrer le .po sous', 'it': 'Salva .po come',
        'pt': 'Salvar .po como', 'pl': 'Zapisz .po jako',
        'ru': 'Сохранить .po как', 'zh': '保存 .po 为',
        'ja': '.po を名前を付けて保存',
    },
    'dlg_compilar': {
        'es': 'Compilar .mo en…', 'en': 'Compile .mo to…',
        'fr': 'Compiler le .mo vers…', 'it': 'Compila .mo in…',
        'pt': 'Compilar .mo em…', 'pl': 'Kompiluj .mo do…',
        'ru': 'Компилировать .mo в…', 'zh': '编译 .mo 到…',
        'ja': '.mo のコンパイル先…',
    },
    'ft_trad': {
        'es': 'Archivos de traducción', 'en': 'Translation files',
        'fr': 'Fichiers de traduction', 'it': 'File di traduzione',
        'pt': 'Arquivos de tradução', 'pl': 'Pliki tłumaczeń',
        'ru': 'Файлы переводов', 'zh': '翻译文件', 'ja': '翻訳ファイル',
    },
    'ft_todos': {
        'es': 'Todos los archivos', 'en': 'All files',
        'fr': 'Tous les fichiers', 'it': 'Tutti i file',
        'pt': 'Todos os arquivos', 'pl': 'Wszystkie pliki',
        'ru': 'Все файлы', 'zh': '所有文件', 'ja': 'すべてのファイル',
    },
    'ft_pot': {
        'es': 'Plantilla POT', 'en': 'POT template', 'fr': 'Modèle POT',
        'it': 'Modello POT', 'pt': 'Modelo POT', 'pl': 'Szablon POT',
        'ru': 'Шаблон POT', 'zh': 'POT 模板', 'ja': 'POT テンプレート',
    },
    'ft_po': {
        'es': 'Archivos PO', 'en': 'PO files', 'fr': 'Fichiers PO',
        'it': 'File PO', 'pt': 'Arquivos PO', 'pl': 'Pliki PO',
        'ru': 'Файлы PO', 'zh': 'PO 文件', 'ja': 'PO ファイル',
    },
    'ft_po_cat': {
        'es': 'Catálogo PO', 'en': 'PO catalog', 'fr': 'Catalogue PO',
        'it': 'Catalogo PO', 'pt': 'Catálogo PO', 'pl': 'Katalog PO',
        'ru': 'Каталог PO', 'zh': 'PO 目录', 'ja': 'PO カタログ',
    },
    'ft_mo_cat': {
        'es': 'Catálogo compilado MO', 'en': 'Compiled MO catalog',
        'fr': 'Catalogue MO compilé', 'it': 'Catalogo MO compilato',
        'pt': 'Catálogo MO compilado', 'pl': 'Skompilowany katalog MO',
        'ru': 'Скомпилированный каталог MO', 'zh': '已编译 MO 目录',
        'ja': 'コンパイル済み MO カタログ',
    },
    # ---------- mensajes ----------
    'msg_err_abrir': {
        'es': 'No se pudo abrir el archivo:\n\n%s',
        'en': 'Could not open the file:\n\n%s',
        'fr': "Impossible d'ouvrir le fichier :\n\n%s",
        'it': 'Impossibile aprire il file:\n\n%s',
        'pt': 'Não foi possível abrir o arquivo:\n\n%s',
        'pl': 'Nie udało się otworzyć pliku:\n\n%s',
        'ru': 'Не удалось открыть файл:\n\n%s',
        'zh': '无法打开文件：\n\n%s', 'ja': 'ファイルを開けませんでした：\n\n%s',
    },
    'msg_err_mo': {
        'es': 'No se pudo compilar el .mo:\n\n%s',
        'en': 'Could not compile the .mo:\n\n%s',
        'fr': 'Impossible de compiler le .mo :\n\n%s',
        'it': 'Impossibile compilare il .mo:\n\n%s',
        'pt': 'Não foi possível compilar o .mo:\n\n%s',
        'pl': 'Nie udało się skompilować .mo:\n\n%s',
        'ru': 'Не удалось скомпилировать .mo:\n\n%s',
        'zh': '无法编译 .mo：\n\n%s', 'ja': '.mo をコンパイルできませんでした：\n\n%s',
    },
    'msg_abrio_pot': {
        'es': 'Has abierto un archivo .pot (plantilla sin traducir).\n'
              'Al guardar se te pedirá un nombre terminado en .po.',
        'en': 'You opened a .pot file (an untranslated template).\n'
              'When saving, a name ending in .po will be requested.',
        'fr': 'Vous avez ouvert un fichier .pot (modèle non traduit).\n'
              "À l'enregistrement, un nom se terminant par .po sera demandé.",
        'it': 'Hai aperto un file .pot (modello non tradotto).\n'
              'Al salvataggio verrà chiesto un nome che termini in .po.',
        'pt': 'Você abriu um arquivo .pot (modelo sem tradução).\n'
              'Ao salvar, será pedido um nome terminado em .po.',
        'pl': 'Otworzyłeś plik .pot (szablon bez tłumaczenia).\n'
              'Przy zapisaniu zostanie zaproponowana nazwa kończąca się na .po.',
        'ru': 'Вы открыли файл .pot (шаблон без перевода).\n'
              'При сохранении будет предложено имя с расширением .po.',
        'zh': '你打开的是 .pot 文件（未翻译的模板）。\n'
              '保存时会要求使用以 .po 结尾的文件名。',
        'ja': '.pot ファイル（未翻訳のテンプレート）を開きました。\n'
              '保存時に .po で終わる名前を指定してください。',
    },
    'msg_abre_po': {
        'es': 'Abre primero tu archivo .po.',
        'en': 'Open your .po file first.',
        'fr': 'Ouvrez d\u2019abord votre fichier .po.',
        'it': 'Apri prima il tuo file .po.',
        'pt': 'Abra primeiro seu arquivo .po.',
        'pl': 'Najpierw otwórz plik .po.',
        'ru': 'Сначала откройте файл .po.',
        'zh': '请先打开 .po 文件。', 'ja': 'まず .po ファイルを開いてください。',
    },
    'msg_err_pot': {
        'es': 'Error al actualizar desde el POT:\n\n%s',
        'en': 'Error updating from the POT:\n\n%s',
        'fr': 'Erreur lors de la mise à jour depuis le POT :\n\n%s',
        'it': 'Errore durante l\u2019aggiornamento dal POT:\n\n%s',
        'pt': 'Erro ao atualizar a partir do POT:\n\n%s',
        'pl': 'Błąd aktualizacji z POT:\n\n%s',
        'ru': 'Ошибка обновления из POT:\n\n%s',
        'zh': '从 POT 更新时出错：\n\n%s', 'ja': 'POT からの更新エラー：\n\n%s',
    },
    'msg_pot_ok': {
        'es': 'Actualización completada en %.1f s:\n\n'
              '• Traducciones conservadas: %d\n'
              '• Textos cambiados marcados como fuzzy: %d\n'
              '• Cadenas nuevas sin traducir: %d\n'
              '• Cadenas eliminadas (obsoletas): %d\n\n'
              'Consejo: revisa el filtro «Con fuzzy» y traduce las vacías\n'
              'en la pestaña «Traducción IA por lotes».',
        'en': 'Update completed in %.1f s:\n\n'
              '• Translations kept: %d\n'
              '• Changed texts marked as fuzzy: %d\n'
              '• New untranslated strings: %d\n'
              '• Removed strings (obsolete): %d\n\n'
              'Tip: check the “With fuzzy” filter and translate the empty\n'
              'ones in the “AI batch translation” tab.',
        'fr': 'Mise à jour terminée en %.1f s :\n\n'
              '• Traductions conservées : %d\n'
              '• Textes modifiés marqués fuzzy : %d\n'
              '• Nouvelles chaînes non traduites : %d\n'
              '• Chaînes supprimées (obsolètes) : %d\n\n'
              'Astuce : utilisez le filtre « Avec fuzzy » et traduisez les\n'
              'vides dans l\u2019onglet « Traduction IA par lots ».',
        'it': 'Aggiornamento completato in %.1f s:\n\n'
              '• Traduzioni conservate: %d\n'
              '• Testi modificati marcati come fuzzy: %d\n'
              '• Nuove stringhe non tradotte: %d\n'
              '• Stringhe rimosse (obsolete): %d\n\n'
              'Suggerimento: controlla il filtro “Con fuzzy” e traduci le\n'
              'vuote nella scheda “Traduzione IA per lotti”.',
        'pt': 'Atualização concluída em %.1f s:\n\n'
              '• Traduções conservadas: %d\n'
              '• Textos alterados marcados como fuzzy: %d\n'
              '• Novas strings sem tradução: %d\n'
              '• Strings removidas (obsoletas): %d\n\n'
              'Dica: use o filtro “Com fuzzy” e traduza as vazias na\n'
              'aba “Tradução IA por lotes”.',
        'pl': 'Aktualizacja ukończona w %.1f s:\n\n'
              '• Zachowane tłumaczenia: %d\n'
              '• Zmienione teksty oznaczone jako fuzzy: %d\n'
              '• Nowe nieprzetłumaczone ciągi: %d\n'
              '• Usunięte ciągi (przestarzałe): %d\n\n'
              'Wskazówka: sprawdź filtr „Z fuzzy” i przetłumacz puste\n'
              'w zakładce „Tłumaczenie AI partiami”.',
        'ru': 'Обновление завершено за %.1f с:\n\n'
              '• Сохранено переводов: %d\n'
              '• Изменённые тексты помечены fuzzy: %d\n'
              '• Новых строк без перевода: %d\n'
              '• Удалённых строк (устаревших): %d\n\n'
              'Совет: проверьте фильтр «С fuzzy» и переведите пустые\n'
              'на вкладке «Пакетный перевод с ИИ».',
        'zh': '更新完成，用时 %.1f 秒：\n\n'
              '• 保留的翻译：%d\n'
              '• 标记为 fuzzy 的已更改文本：%d\n'
              '• 新增未翻译字符串：%d\n'
              '• 移除的字符串（已废弃）：%d\n\n'
              '提示：使用“含 fuzzy”筛选器，在“AI 批量翻译”标签页\n'
              '翻译空条目。',
        'ja': '更新が %.1f 秒で完了しました：\n\n'
              '• 保持された翻訳：%d\n'
              '• fuzzy とマークされた変更テキスト：%d\n'
              '• 未翻訳の新規文字列：%d\n'
              '• 削除された文字列（廃止）：%d\n\n'
              'ヒント：「fuzzy あり」フィルタで確認し、「AI 一括翻訳」\n'
              'タブで空のエントリを翻訳してください。',
    },
    'title_pot_result': {
        'es': 'Resultado de la actualización',
        'en': 'Update result', 'fr': 'Résultat de la mise à jour',
        'it': "Risultato dell'aggiornamento",
        'pt': 'Resultado da atualização',
        'pl': 'Wynik aktualizacji', 'ru': 'Результат обновления',
        'zh': '更新结果', 'ja': '更新結果',
    },
    'msg_err_guardar': {
        'es': 'No se pudo guardar:\n\n%s',
        'en': 'Could not save:\n\n%s',
        'fr': "Impossible d'enregistrer :\n\n%s",
        'it': 'Impossibile salvare:\n\n%s',
        'pt': 'Não foi possível salvar:\n\n%s',
        'pl': 'Nie udało się zapisać:\n\n%s',
        'ru': 'Не удалось сохранить:\n\n%s',
        'zh': '无法保存：\n\n%s', 'ja': '保存できませんでした：\n\n%s',
    },
    'msg_no_entries': {
        'es': 'No hay entradas para traducir con los criterios actuales.\n\n'
              'Prueba con el filtro «Sin traducir» o «Todas», o marca\n'
              '«Incluir ya traducidas».',
        'en': 'There are no entries to translate with the current criteria.\n\n'
              'Try the “Untranslated” or “All” filter, or check\n'
              '“Include already translated”.',
        'fr': 'Aucune entrée à traduire avec les critères actuels.\n\n'
              'Essayez le filtre « Non traduites » ou « Toutes », ou\n'
              'cochez « Inclure déjà traduites ».',
        'it': 'Non ci sono voci da tradurre con i criteri attuali.\n\n'
              'Prova il filtro “Non tradotte” o “Tutte”, oppure attiva\n'
              '“Includi già tradotte”.',
        'pt': 'Não há entradas para traduzir com os critérios atuais.\n\n'
              'Tente o filtro “Sem tradução” ou “Todas”, ou marque\n'
              '“Incluir já traduzidas”.',
        'pl': 'Brak wpisów do przetłumaczenia przy bieżących kryteriach.\n\n'
              'Spróbuj filtra „Nieprzetłumaczone” lub „Wszystkie”,\n'
              'albo zaznacz „Uwzględnij przetłumaczone”.',
        'ru': 'Нет записей для перевода по текущим критериям.\n\n'
              'Попробуйте фильтр «Без перевода» или «Все» либо включите\n'
              '«Включить уже переведённые».',
        'zh': '当前条件下没有可翻译的条目。\n\n'
              '请尝试“未翻译”或“全部”筛选器，或勾选\n'
              '“包含已翻译”。',
        'ja': '現在の条件で翻訳できるエントリがありません。\n\n'
              '「未翻訳」または「すべて」フィルタを試すか、\n'
              '「翻訳済みを含む」を有効にしてください。',
    },
    'msg_prepara': {
        'es': 'Prepara primero un lote.',
        'en': 'Prepare a batch first.',
        'fr': 'Préparez d\u2019abord un lot.',
        'it': 'Prepara prima un lotto.',
        'pt': 'Prepare primeiro um lote.',
        'pl': 'Najpierw przygotuj partię.',
        'ru': 'Сначала подготовьте пакет.',
        'zh': '请先准备一个批次。', 'ja': 'まずバッチを準備してください。',
    },
    'msg_no_mas_lotes': {
        'es': 'No quedan más lotes: cola completada.',
        'en': 'No more batches left: queue completed.',
        'fr': 'Plus de lots : file terminée.',
        'it': 'Non ci sono più lotti: coda completata.',
        'pt': 'Não há mais lotes: fila concluída.',
        'pl': 'Nie ma więcej partii: kolejka zakończona.',
        'ru': 'Больше нет пакетов: очередь завершена.',
        'zh': '没有更多批次：队列已完成。',
        'ja': 'バッチはこれ以上ありません：キュー完了。',
    },
    'st_plurales_fuera': {
        'es': 'Ojo: %d entradas con plurales quedaron fuera del lote '
              '(edítalas a mano)',
        'en': 'Note: %d plural entries were left out of the batch '
              '(edit them by hand)',
        'fr': 'Attention : %d entrées au pluriel exclues du lot '
              '(à modifier à la main)',
        'it': 'Attenzione: %d voci con plurali escluse dal lotto '
              '(modificale a mano)',
        'pt': 'Atenção: %d entradas com plurais ficaram fora do lote '
              '(edite-as manualmente)',
        'pl': 'Uwaga: %d wpisów z liczbą mnogą pominięto w partii '
              '(edytuj ręcznie)',
        'ru': 'Внимание: %d записей с формами мн. числа исключены '
              'из пакета (отредактируйте вручную)',
        'zh': '注意：%d 条复数条目未纳入批次（请手动编辑）',
        'ja': '注意：複数形のエントリ %d 件はバッチ外です'
              '（手動で編集してください）',
    },
    'st_lote': {
        'es': 'Lote %d: %d entradas · quedan %d en la cola',
        'en': 'Batch %d: %d entries · %d left in the queue',
        'fr': 'Lot %d : %d entrées · %d restantes dans la file',
        'it': 'Lotto %d: %d voci · %d rimaste in coda',
        'pt': 'Lote %d: %d entradas · restam %d na fila',
        'pl': 'Partia %d: %d wpisów · pozostało %d w kolejce',
        'ru': 'Пакет %d: %d записей · в очереди ещё %d',
        'zh': '批次 %d：%d 条 · 队列剩 %d 条',
        'ja': 'バッチ %d：%d 件 · 残り %d 件',
    },
    'st_prompt_copiado': {
        'es': 'Prompt copiado al portapapeles',
        'en': 'Prompt copied to the clipboard',
        'fr': 'Prompt copié dans le presse-papiers',
        'it': 'Prompt copiato negli appunti',
        'pt': 'Prompt copiado para a área de transferência',
        'pl': 'Prompt skopiowany do schowka',
        'ru': 'Запрос скопирован в буфер обмена',
        'zh': '提示词已复制到剪贴板',
        'ja': 'プロンプトをクリップボードにコピーしました',
    },
    'msg_no_numeradas': {
        'es': 'No se detectaron líneas numeradas en la respuesta.\n\n'
              'Asegúrate de pegar la traducción completa de la IA.',
        'en': 'No numbered lines were detected in the response.\n\n'
              'Make sure you pasted the AI\u2019s complete reply.',
        'fr': 'Aucune ligne numérotée détectée dans la réponse.\n\n'
              'Assurez-vous d\u2019avoir collé la réponse complète de l\u2019IA.',
        'it': 'Nessuna riga numerata rilevata nella risposta.\n\n'
              'Assicurati di aver incollato la risposta completa dell\u2019IA.',
        'pt': 'Nenhuma linha numerada detectada na resposta.\n\n'
              'Certifique-se de colar a resposta completa da IA.',
        'pl': 'Nie wykryto numerowanych wierszy w odpowiedzi.\n\n'
              'Upewnij się, że wkleiłeś pełną odpowiedź AI.',
        'ru': 'В ответе не найдено пронумерованных строк.\n\n'
              'Убедитесь, что вставили полный ответ ИИ.',
        'zh': '回复中未检测到带编号的行。\n\n'
              '请确保粘贴了 AI 的完整回复。',
        'ja': '回答に番号付きの行が見つかりません。\n\n'
              'AI の回答全体を貼り付けたか確認してください。',
    },
    'msg_no_coincidio': {
        'es': 'Ninguna línea de la respuesta coincidió con el lote.\n\n'
              '¿Pegaste la respuesta de otro lote?',
        'en': 'No line of the response matched the batch.\n\n'
              'Did you paste the reply of another batch?',
        'fr': 'Aucune ligne de la réponse ne correspond au lot.\n\n'
              'Avez-vous collé la réponse d\u2019un autre lot ?',
        'it': 'Nessuna riga della risposta corrisponde al lotto.\n\n'
              'Hai incollato la risposta di un altro lotto?',
        'pt': 'Nenhuma linha da resposta corresponde ao lote.\n\n'
              'Você colou a resposta de outro lote?',
        'pl': 'Żaden wiersz odpowiedzi nie pasuje do partii.\n\n'
              'Czy wkleiłeś odpowiedź z innej partii?',
        'ru': 'Ни одна строка ответа не совпала с пакетом.\n\n'
              'Возможно, вы вставили ответ другого пакета?',
        'zh': '回复中没有任何行与批次匹配。\n\n'
              '你是否粘贴了其他批次的回复？',
        'ja': '回答の行がバッチと一致しません。\n\n'
              '別のバッチの回答を貼り付けていませんか？',
    },
    'note_orden': {
        'es': ' (asignadas por orden: la IA no numeró las líneas)',
        'en': ' (assigned by order: the AI did not number the lines)',
        'fr': " (affectées par ordre : l'IA n'a pas numéroté les lignes)",
        'it': ' (assegnate in ordine: l\u2019IA non ha numerato le righe)',
        'pt': ' (atribuídas por ordem: a IA não numerou as linhas)',
        'pl': ' (przypisane po kolejności: AI nie ponumerowało wierszy)',
        'ru': ' (распределено по порядку: ИИ не пронумеровал строки)',
        'zh': ' （按顺序分配：AI 未编号）',
        'ja': ' （順序で割り当て：AI が行番号を付けていません）',
    },
    'st_falta_linea': {
        'es': '\nNo llegó la línea: %s',
        'en': '\nMissing line: %s', 'fr': '\nLigne manquante : %s',
        'it': '\nRiga mancante: %s', 'pt': '\nLinha ausente: %s',
        'pl': '\nBrak wiersza: %s', 'ru': '\nНе пришла строка: %s',
        'zh': '\n缺少行：%s', 'ja': '\n不足行：%s',
    },
    'st_vacias': {
        'es': '\n%d líneas llegaron vacías',
        'en': '\n%d lines arrived empty', 'fr': '\n%d lignes vides',
        'it': '\n%d righe vuote', 'pt': '\n%d linhas vazias',
        'pl': '\n%d pustych wierszy', 'ru': '\n%d пустых строк',
        'zh': '\n%d 行为空', 'ja': '\n%d 行が空でした',
    },
    'st_cola_completa': {
        'es': 'Cola completada: guarda el .po y compila el .mo',
        'en': 'Queue completed: save the .po and compile the .mo',
        'fr': 'File terminée : enregistrez le .po et compilez le .mo',
        'it': 'Coda completata: salva il .po e compila il .mo',
        'pt': 'Fila concluída: salve o .po e compile o .mo',
        'pl': 'Kolejka zakończona: zapisz .po i skompiluj .mo',
        'ru': 'Очередь завершена: сохраните .po и скомпилируйте .mo',
        'zh': '队列已完成：保存 .po 并编译 .mo',
        'ja': 'キュー完了：.po を保存して .mo をコンパイルしてください',
    },
    'msg_cola_ok': {
        'es': 'Aplicadas %d traducciones%s.\n\n¡Cola completada! '
              'No quedan más lotes.',
        'en': 'Applied %d translations%s.\n\nQueue completed! '
              'No more batches left.',
        'fr': '%d traductions appliquées%s.\n\nFile terminée ! '
              'Plus de lots.',
        'it': 'Applicate %d traduzioni%s.\n\nCoda completata! '
              'Non ci sono più lotti.',
        'pt': 'Aplicadas %d traduções%s.\n\nFila concluída! '
              'Não há mais lotes.',
        'pl': 'Zastosowano %d tłumaczeń%s.\n\nKolejka zakończona! '
              'Nie ma więcej partii.',
        'ru': 'Применено переводов: %d%s.\n\nОчередь завершена! '
              'Больше нет пакетов.',
        'zh': '已应用 %d 条翻译%s。\n\n队列已完成！没有更多批次。',
        'ja': '%d 件の翻訳を適用しました%s。\n\nキュー完了！'
              'バッチはもうありません。',
    },
    'st_aplicadas': {
        'es': 'Aplicadas %d traducciones%s',
        'en': 'Applied %d translations%s',
        'fr': '%d traductions appliquées%s',
        'it': 'Applicate %d traduzioni%s',
        'pt': 'Aplicadas %d traduções%s',
        'pl': 'Zastosowano %d tłumaczeń%s',
        'ru': 'Применено переводов: %d%s',
        'zh': '已应用 %d 条翻译%s', 'ja': '%d 件の翻訳を適用%s',
    },
    'st_aplicadas_corto': {
        'es': 'Aplicadas %d%s', 'en': 'Applied %d%s',
        'fr': 'Appliquées : %d%s', 'it': 'Applicate %d%s',
        'pt': 'Aplicadas %d%s', 'pl': 'Zastosowano %d%s',
        'ru': 'Применено: %d%s', 'zh': '已应用 %d%s', 'ja': '適用 %d%s',
    },
    'msg_nada_deshacer': {
        'es': 'No hay acciones que deshacer.',
        'en': 'There is nothing to undo.',
        'fr': 'Il n\u2019y a rien à annuler.',
        'it': 'Non c\u2019è nulla da annullare.',
        'pt': 'Não há nada para desfazer.',
        'pl': 'Nie ma nic do cofnięcia.',
        'ru': 'Нечего отменять.', 'zh': '没有可撤销的操作。',
        'ja': '元に戻す操作はありません。',
    },
    'st_deshechas': {
        'es': 'Deshechas %d entradas', 'en': 'Undid %d entries',
        'fr': '%d entrées annulées', 'it': '%d voci annullate',
        'pt': '%d entradas desfeitas', 'pl': 'Cofnięto %d wpisów',
        'ru': 'Отменено записей: %d', 'zh': '已撤销 %d 条',
        'ja': '%d 件を元に戻しました',
    },
    'msg_cambios': {
        'es': 'Hay cambios sin guardar.\n\n¿Guardar ahora?',
        'en': 'There are unsaved changes.\n\nSave now?',
        'fr': 'Des modifications non enregistrées.\n\n'
              'Enregistrer maintenant ?',
        'it': 'Ci sono modifiche non salvate.\n\nSalvare ora?',
        'pt': 'Há alterações não salvas.\n\nSalvar agora?',
        'pl': 'Są niezapisane zmiany.\n\nZapisać teraz?',
        'ru': 'Есть несохранённые изменения.\n\nСохранить сейчас?',
        'zh': '有未保存的更改。\n\n现在保存吗？',
        'ja': '未保存の変更があります。\n\n今保存しますか？',
    },
    'about_title': {
        'es': 'Acerca de', 'en': 'About', 'fr': 'À propos',
        'it': 'Informazioni', 'pt': 'Sobre', 'pl': 'O programie',
        'ru': 'О программе', 'zh': '关于', 'ja': '情報',
    },
    'about_text': {
        'es': '%s %s\n\nEditor de traducciones .po/.pot/.mo con\n'
              'traducción asistida por IA por lotes (portapapeles).\n\n'
              'Basado en polib (MIT) · Python + tkinter',
        'en': '%s %s\n\n.po/.pot/.mo translation editor with\n'
              'batch AI-assisted translation (clipboard).\n\n'
              'Based on polib (MIT) · Python + tkinter',
        'fr': '%s %s\n\nÉditeur de traductions .po/.pot/.mo avec\n'
              'traduction par lots assistée par IA (presse-papiers).\n\n'
              'Basé sur polib (MIT) · Python + tkinter',
        'it': '%s %s\n\nEditor di traduzioni .po/.pot/.mo con\n'
              'traduzione assistita dall\u2019IA per lotti (appunti).\n\n'
              'Basato su polib (MIT) · Python + tkinter',
        'pt': '%s %s\n\nEditor de traduções .po/.pot/.mo com\n'
              'tradução assistida por IA em lotes '
              '(área de transferência).\n\n'
              'Baseado em polib (MIT) · Python + tkinter',
        'pl': '%s %s\n\nEdytor tłumaczeń .po/.pot/.mo z tłumaczeniem\n'
              'partiami wspomaganym przez AI (schowek).\n\n'
              'Oparty na polib (MIT) · Python + tkinter',
        'ru': '%s %s\n\nРедактор переводов .po/.pot/.mo с\n'
              'пакетным переводом с помощью ИИ (буфер обмена).\n\n'
              'На основе polib (MIT) · Python + tkinter',
        'zh': '%s %s\n\n.po/.pot/.mo 翻译编辑器，支持\n'
              'AI 批量辅助翻译（剪贴板）。\n\n'
              '基于 polib (MIT) · Python + tkinter',
        'ja': '%s %s\n\n.po/.pot/.mo 翻訳エディタ（クリップボードを使った\n'
              'AI 一括翻訳対応）。\n\n'
              'polib (MIT) · Python + tkinter ベース',
    },
    # ---------- menú contextual de la tabla ----------
    'ctx_borrar': {
        'es': 'Borrar traducción', 'en': 'Delete translation',
        'fr': 'Effacer la traduction', 'it': 'Cancella traduzione',
        'pt': 'Apagar tradução', 'pl': 'Usuń tłumaczenie',
        'ru': 'Удалить перевод', 'zh': '删除译文', 'ja': '翻訳を削除',
    },
    'ctx_marcar': {
        'es': 'Marcar como fuzzy', 'en': 'Mark as fuzzy',
        'fr': 'Marquer comme fuzzy', 'it': 'Segna come fuzzy',
        'pt': 'Marcar como fuzzy', 'pl': 'Oznacz jako fuzzy',
        'ru': 'Пометить как fuzzy', 'zh': '标记为 fuzzy',
        'ja': 'fuzzy にする',
    },
    'ctx_quitar': {
        'es': 'Quitar fuzzy', 'en': 'Clear fuzzy',
        'fr': 'Retirer fuzzy', 'it': 'Togli fuzzy',
        'pt': 'Remover fuzzy', 'pl': 'Odznacz fuzzy',
        'ru': 'Снять fuzzy', 'zh': '取消 fuzzy', 'ja': 'fuzzy を解除',
    },
    'ctx_sel_todas': {
        'es': 'Seleccionar todas las filtradas',
        'en': 'Select all filtered',
        'fr': 'Sélectionner toutes les filtrées',
        'it': 'Seleziona tutte le filtrate',
        'pt': 'Selecionar todas as filtradas',
        'pl': 'Zaznacz wszystkie przefiltrowane',
        'ru': 'Выделить все отфильтрованные',
        'zh': '选择全部筛选结果', 'ja': '絞り込みをすべて選択',
    },
    'ctx_copiar_originales': {
        'es': 'Copiar originales al portapapeles',
        'en': 'Copy originals to the clipboard',
        'fr': 'Copier les originaux dans le presse-papiers',
        'it': 'Copia gli originali negli appunti',
        'pt': 'Copiar originais para a área de transferência',
        'pl': 'Kopiuj oryginały do schowka',
        'ru': 'Копировать оригиналы в буфер обмена',
        'zh': '复制原文到剪贴板', 'ja': '原文をクリップボードにコピー',
    },
})
# fin TR parte 4 (diálogos/mensajes)

# Plantilla por defecto del prompt de traducción, por idioma elegido.
# El usuario puede editarla libremente en la pestaña de lotes (se guarda
# en su configuracion y NO se toca al cambiar de idioma).
DEFAULT_PROMPTS = {
    'es': (
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
    ),
    'en': (
        'You are a professional software translator. Translate the interface texts '
        'of a program (BodySlide / Outfit Studio, a video game modding tool) into '
        'ENGLISH.\n'
        '\n'
        'Strict rules:\n'
        '1. Reply ONLY with the translations, one per line, in the format '
        '"N) translation".\n'
        '2. Keep the same number of lines, the same order and the same numbering. '
        'Do not add explanations or comments.\n'
        '3. Keep placeholders intact: %s, %d, %lu, {{PLACEHOLDER}} and line '
        'breaks written as \\n.\n'
        '4. Keep the & symbol of menu shortcuts (e.g. "&OK" stays "&OK").\n'
        '5. Do not translate technical terms or proper names: NIF, TRI, '
        'BodySlide, Outfit Studio, morph, zap, OSD, BGSM, etc.\n'
        '6. Natural, consistent software English.\n'
        '7. If a text is just a number or a code (e.g. "0.100"), return it '
        'unchanged.'
    ),
    'fr': (
        'Tu es un traducteur professionnel de logiciels. Traduis en FRANÇAIS les '
        "textes de l'interface d'un programme (BodySlide / Outfit Studio, outil de "
        'modding de jeux vidéo).\n'
        '\n'
        'Règles strictes :\n'
        '1. Réponds UNIQUEMENT avec les traductions, une par ligne, au format '
        '"N) traduction".\n'
        '2. Garde le même nombre de lignes, le même ordre et la même numérotation. '
        "N'ajoute ni explication ni commentaire.\n"
        '3. Conserve intacts les marqueurs : %s, %d, %lu, {{PLACEHOLDER}} et les '
        'sauts de ligne écrits comme \\n.\n'
        '4. Conserve le symbole & des raccourcis de menu (ex. : "&OK" se traduit '
        '"&OK").\n'
        '5. Ne traduis pas les termes techniques ni les noms propres : NIF, TRI, '
        'BodySlide, Outfit Studio, morph, zap, OSD, BGSM, etc.\n'
        '6. Français naturel et soigné. Glossaire : mesh = maillage, '
        'shape = forme, bone = os, vertex = sommet, weight = poids, '
        'slider = curseur, preset = préréglage, seam = couture, clip = clip.\n'
        '7. Si un texte n\u2019est qu\u2019un nombre ou un code (ex. : "0.100"), '
        'renvoie-le tel quel.'
    ),
    'it': (
        'Sei un traduttore professionista di software. Traduci in ITALIANO i testi '
        'dell\u2019interfaccia di un programma (BodySlide / Outfit Studio, '
        'strumento di modding per videogiochi).\n'
        '\n'
        'Regole severe:\n'
        '1. Rispondi SOLO con le traduzioni, una per riga, nel formato '
        '"N) traduzione".\n'
        '2. Mantieni lo stesso numero di righe, lo stesso ordine e la stessa '
        'numerazione. Non aggiungere spiegazioni né commenti.\n'
        '3. Conserva intatti i marcatori: %s, %d, %lu, {{PLACEHOLDER}} e i salti '
        'di riga scritti come \\n.\n'
        '4. Conserva il simbolo & delle scorciatoie dei menu (es.: "&OK" resta '
        '"&OK").\n'
        '5. Non tradurre termini tecnici né nomi propri: NIF, TRI, BodySlide, '
        'Outfit Studio, morph, zap, OSD, BGSM, ecc.\n'
        '6. Italiano naturale e curato. Glossario: mesh = maglia, shape = forma, '
        'bone = osso, vertex = vertice, weight = peso, slider = cursore, '
        'preset = preset, seam = cucitura, clip = clip.\n'
        '7. Se un testo è solo un numero o un codice (es.: "0.100"), '
        'riportalo invariato.'
    ),
    'pt': (
        'Você é um tradutor profissional de software. Traduza para o PORTUGUÊS os '
        'textos da interface de um programa (BodySlide / Outfit Studio, ferramenta '
        'de modding de jogos).\n'
        '\n'
        'Regras estritas:\n'
        '1. Responda APENAS com as traduções, uma por linha, no formato '
        '"N) tradução".\n'
        '2. Mantenha o mesmo número de linhas, a mesma ordem e a mesma numeração. '
        'Não acrescente explicações nem comentários.\n'
        '3. Preserve intactos os marcadores: %s, %d, %lu, {{PLACEHOLDER}} e as '
        'quebras de linha escritas como \\n.\n'
        '4. Preserve o símbolo & dos atalhos de menu (ex.: "&OK" fica "&OK").\n'
        '5. Não traduza termos técnicos nem nomes próprios: NIF, TRI, BodySlide, '
        'Outfit Studio, morph, zap, OSD, BGSM, etc.\n'
        '6. Português natural e consistente. Glossário: mesh = malha, '
        'shape = forma, bone = osso, vertex = vértice, weight = peso, '
        'slider = controle, preset = predefinição, seam = costura, clip = clipe.\n'
        '7. Se um texto for só um número ou um código (ex.: "0.100"), devolva-o '
        'igual.'
    ),
    'pl': (
        'Jesteś profesjonalnym tłumaczem oprogramowania. Przetłumacz na POLSKI '
        'teksty interfejsu programu (BodySlide / Outfit Studio, narzędzie do '
        'moddingu gier).\n'
        '\n'
        'Ścisłe zasady:\n'
        '1. Odpowiadaj WYŁĄCZNIE tłumaczeniami, po jednym w wierszu, w formacie '
        '"N) tłumaczenie".\n'
        '2. Zachowaj tę samą liczbę wierszy, tę samą kolejność i tę samą '
        'numerację. Nie dodawaj wyjaśnień ani komentarzy.\n'
        '3. Zachowaj nienaruszone znaczniki: %s, %d, %lu, {{PLACEHOLDER}} oraz '
        'znaki nowej linii zapisane jako \\n.\n'
        '4. Zachowaj symbol & skrótów menu (np. "&OK" zostaje "&OK").\n'
        '5. Nie tłumacz terminów technicznych ani nazw własnych: NIF, TRI, '
        'BodySlide, Outfit Studio, morph, zap, OSD, BGSM itd.\n'
        '6. Naturalny, spójny polski język oprogramowania. Słowniczek: '
        'mesh = siatka, shape = kształt, bone = kość, vertex = wierzchołek, '
        'weight = waga, slider = suwak, preset = preset, seam = szew, '
        'clip = klip.\n'
        '7. Jeśli tekst to tylko liczba lub kod (np. "0.100"), zwróć go bez '
        'zmian.'
    ),
    'ru': (
        'Ты — профессиональный переводчик программного обеспечения. Переведи на '
        'РУССКИЙ тексты интерфейса программы (BodySlide / Outfit Studio, '
        'инструмент для моддинга игр).\n'
        '\n'
        'Строгие правила:\n'
        '1. Отвечай ТОЛЬКО переводами, по одному в строке, в формате '
        '"N) перевод".\n'
        '2. Сохрани то же количество строк, тот же порядок и ту же нумерацию. '
        'Не добавляй пояснений и комментариев.\n'
        '3. Сохрани неизменными маркеры: %s, %d, %lu, {{PLACEHOLDER}} и переводы '
        'строк, записанные как \\n.\n'
        '4. Сохрани символ & в горячих клавишах меню (напр., "&OK" остаётся '
        '"&OK").\n'
        '5. Не переводи технические термины и имена собственные: NIF, TRI, '
        'BodySlide, Outfit Studio, morph, zap, OSD, BGSM и т.д.\n'
        '6. Естественный русский язык интерфейса. Словарик: mesh = сетка, '
        'shape = форма, bone = кость, vertex = вершина, weight = вес, '
        'slider = ползунок, preset = пресет, seam = шов, clip = клип.\n'
        '7. Если текст — просто число или код (напр., "0.100"), верни его '
        'без изменений.'
    ),
    'zh': (
        '你是一名专业的软件翻译。请将程序界面文本（BodySlide / Outfit '
        'Studio，一款游戏模组工具）翻译成简体中文。\n'
        '\n'
        '严格规则：\n'
        '1. 只输出翻译结果，每行一条，格式为“N) 译文”。\n'
        '2. 保持行数、顺序和编号不变。不要添加解释或注释。\n'
        '3. 保持标记完整：%s、%d、%lu、{{PLACEHOLDER}} 以及写作 \\n 的换行符。\n'
        '4. 保留菜单快捷键的 & 符号（如“&OK”仍为“&OK”）。\n'
        '5. 不要翻译技术术语和专有名词：NIF、TRI、BodySlide、Outfit Studio、'
        'morph、zap、OSD、BGSM 等。\n'
        '6. 使用自然、通顺的简体中文软件用语。词汇表：mesh = 网格，'
        'shape = 形状，bone = 骨骼，vertex = 顶点，weight = 权重，'
        'slider = 滑块，preset = 预设，seam = 接缝，clip = 裁剪。\n'
        '7. 如果文本只是数字或代码（如“0.100”），原样返回。'
    ),
    'ja': (
        'あなたはプロのソフトウェア翻訳者です。プログラムのインターフェース'
        'テキスト（BodySlide / Outfit Studio、ゲームのモッド作成ツール）を'
        '日本語に翻訳してください。\n'
        '\n'
        '厳守ルール:\n'
        '1. 翻訳のみを返信し、1 行に 1 件、「N) 訳文」の形式にしてください。\n'
        '2. 行数・順序・番号を同じに保ち、説明やコメントを追加しないでください。\n'
        '3. プレースホルダー %s、%d、%lu、{{PLACEHOLDER}}、\\n と書かれた改行は'
        'そのまま保持してください。\n'
        '4. メニューのショートカット記号 & は保持してください（例: "&OK" は '
        '"&OK" のまま）。\n'
        '5. 技術用語や固有名名詞は翻訳しないでください: NIF、TRI、BodySlide、'
        'Outfit Studio、morph、zap、OSD、BGSM など。\n'
        '6. 自然で一貫した日本語のソフトウェア用語を使ってください。用語集: '
        'mesh = メッシュ、shape = シェイプ、bone = ボーン、vertex = 頂点、'
        'weight = ウェイト、slider = スライダー、preset = プリセット、'
        'seam = 継ぎ目、clip = クリップ。\n'
        '7. 数字やコードだけのテキスト（例: "0.100"）はそのまま返してください。'
    ),
}
DEFAULT_PROMPT = DEFAULT_PROMPTS['es']   # compatibilidad (tests)

DEFAULT_CONFIG = {
    'separator': '<SEPARATOR>',
    'max_chars': 8000,
    'prompt': DEFAULT_PROMPT,
    'include_translated': False,
    'chat': 'ChatGPT',
    'geometry': '1280x820',
    'theme': 'auto',            # 'auto' | 'claro' | 'oscuro'
    'lang': None,               # None = preguntar al primer arranque
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

BATCH_INSTRUCTIONS = {
    'es': 'Traduce cada línea y responde SOLO con la traducción en el formato '
          '"N) traducción", una por línea y con la misma numeración:',
    'en': 'Translate each line and reply ONLY with the translation in the '
          'format "N) translation", one per line and with the same numbering:',
    'fr': 'Traduis chaque ligne et réponds UNIQUEMENT avec la traduction au '
          'format "N) traduction", une par ligne et avec la même numérotation :',
    'it': 'Traduci ogni riga e rispondi SOLO con la traduzione nel formato '
          '"N) traduzione", una per riga e con la stessa numerazione:',
    'pt': 'Traduza cada linha e responda APENAS com a tradução no formato '
          '"N) tradução", uma por linha e com a mesma numeração:',
    'pl': 'Przetłumacz każdą linijkę i odpowiedz WYŁĄCZNIE tłumaczeniem w '
          'formacie "N) tłumaczenie", po jednym w wierszu i z tą samą '
          'numeracją:',
    'ru': 'Переведи каждую строку и ответь ТОЛЬКО переводом в формате '
          '"N) перевод", по одному в строке и с той же нумерацией:',
    'zh': '翻译每一行，并只以“N) 译文”格式回答，每行一条，保持相同编号：',
    'ja': '各行を翻訳し、「N) 訳文」の形式だけで、1 行に 1 件、同じ番号で回答'
          'してください:',
}

def get_batch_instruction():
    """Instrucción final del prompt en el idioma activo."""
    return BATCH_INSTRUCTIONS.get(_LANG[0], BATCH_INSTRUCTIONS['es'])


def get_guide():
    """Guía rápida en el idioma activo."""
    return GUIAS.get(_LANG[0], GUIAS['es'])

GUIAS = {
    'es': """CÓMO USAR PoTranslator (flujo con IA)
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
- Los textos multilínea viajan con \n literal; la app los reconvierte sola.
"""
,
    'en': """HOW TO USE PoTranslator (AI workflow)
=====================================

1) UPDATE YOUR TRANSLATION
   - Menu "File > Open .po" and choose your BodySlide.po
   - Menu "File > Update from POT" and choose the new BodySlide.pot
   - The app keeps your translations, marks changed texts as "fuzzy"
     and leaves new strings empty.

2) BULK TRANSLATE WITH AI ("AI batch translation" tab)
   - In the filter above choose "Untranslated" (or "With fuzzy" to review)
   - Press "Prepare batch" (uses the filtered entries or those selected
     with Ctrl+click / Shift+click in the table)
   - The prompt is copied to your clipboard: paste it into ChatGPT,
     Claude, Gemini... (the "Open chat" button opens your choice)
   - Copy the AI reply and paste it into the right panel
   - Press "Apply and next batch": each line replaces its entry and the
     next batch is prepared automatically
   - If something goes wrong: "Undo last batch"

3) EDIT BY HAND ("Entry editor" tab)
   - Double-click a table row, edit and use Previous/Next
   - "Copy original to translation" is handy for numbers or terms that
     are not translated

4) SAVE
   - "Save .po" saves the catalog (with a .bak backup)
   - "Compile .mo" builds the binary file the program uses
     (BodySlide: replace your existing BodySlide.mo in the language
     folder, e.g. lang/es/)

TIPS
- The max characters per batch prevents truncated AI replies.
- "Fuzzy" entries are recycled translations of changed texts: review
  them before compiling the .mo.
- Multi-line texts travel with a literal \n; the app converts it back.
"""
,
    'fr': """COMMENT UTILISER PoTranslator (flux IA)
=======================================

1) METTRE À JOUR VOTRE TRADUCTION
   - Menu « Fichier > Ouvrir .po » et choisissez votre BodySlide.po
   - Menu « Fichier > Mettre à jour depuis POT » et choisissez le
     nouveau BodySlide.pot
   - L'app conserve vos traductions, marque les textes modifiés comme
     « fuzzy » et laisse les nouvelles chaînes vides.

2) TRADUIRE EN MASSE AVEC L'IA (onglet « Traduction IA par lots »)
   - Dans le filtre du haut choisissez « Non traduites » (ou « Avec
     fuzzy » pour réviser)
   - Appuyez sur « Préparer le lot » (utilise les entrées filtrées ou
     celles sélectionnées avec Ctrl+clic / Maj+clic dans le tableau)
   - Le prompt est copié dans le presse-papiers : collez-le dans
     ChatGPT, Claude, Gemini... (le bouton « Ouvrir le chat » ouvre
     celui de votre choix)
   - Copiez la réponse de l'IA et collez-la dans le panneau de droite
   - Appuyez sur « Appliquer et lot suivant » : chaque ligne remplace
     son entrée et le lot suivant est préparé automatiquement
   - En cas de problème : « Annuler le dernier lot »

3) MODIFIER À LA MAIN (onglet « Éditeur d'entrée »)
   - Double-cliquez sur une ligne du tableau, modifiez et utilisez
     Précédent/Suivant
   - « Copier l'original vers la traduction » sert pour les nombres ou
     les termes non traduits

4) ENREGISTRER
   - « Enregistrer le .po » enregistre le catalogue (avec copie .bak)
   - « Compiler le .mo » génère le fichier binaire utilisé par le
     programme (BodySlide : remplacez votre BodySlide.mo existant dans
     le dossier de langue, p. ex. lang/fr/)

CONSEILS
- Le maximum de caractères par lot évite les réponses coupées par l'IA.
- Les entrées « fuzzy » sont des traductions recyclées de textes
  modifiés : révisez-les avant de compiler le .mo.
- Les textes multiligne voyagent avec un \n littéral ; l'app le
  reconvertit seule.
"""
,
    'it': """COME USARE PoTranslator (flusso con IA)
=======================================

1) AGGIORNA LA TUA TRADUZIONE
   - Menu "File > Apri .po" e scegli il tuo BodySlide.po
   - Menu "File > Aggiorna dal POT" e scegli il nuovo BodySlide.pot
   - L'app conserva le tue traduzioni, segna come "fuzzy" i testi
     cambiati e lascia vuote le nuove stringhe.

2) TRADUCI IN MASSA CON L'IA (scheda "Traduzione IA per lotti")
   - Nel filtro in alto scegli "Non tradotte" (o "Con fuzzy" per
     rivedere)
   - Premi "Prepara lotto" (usa le voci filtrate o quelle selezionate
     con Ctrl+clic / Maiusc+clic nella tabella)
   - Il prompt viene copiato negli appunti: incollalo in ChatGPT,
     Claude, Gemini... (il pulsante "Apri chat" apre quello che
     preferisci)
   - Copia la risposta dell'IA e incollala nel pannello destro
   - Premi "Applica e prossimo lotto": ogni riga sostituisce la propria
     voce e il lotto successivo viene preparato automaticamente
   - Se qualcosa va storto: "Annulla ultimo lotto"

3) MODIFICA A MANO (scheda "Editor voce")
   - Doppio clic su una riga della tabella, modifica e usa
     Precedente/Successivo
   - "Copia l'originale nella traduzione" serve per numeri o termini
     non tradotti

4) SALVATAGGIO
   - "Salva .po" salva il catalogo (con copia .bak)
   - "Compila .mo" genera il file binario usato dal programma
     (BodySlide: sostituisci il tuo BodySlide.mo nella cartella della
     lingua, es. lang/it/)

CONSIGLI
- Il massimo di caratteri per lotto evita risposte troncate dall'IA.
- Le voci "fuzzy" sono traduzioni riciclate di testi cambiati:
  rivedile prima di compilare il .mo.
- I testi multilinea viaggiano con \n letterale; l'app lo riconverte
  da sola.
"""
,
    'pt': """COMO USAR PoTranslator (fluxo com IA)
=====================================

1) ATUALIZAR SUA TRADUÇÃO
   - Menu "Arquivo > Abrir .po" e escolha seu BodySlide.po
   - Menu "Arquivo > Atualizar a partir do POT" e escolha o novo
     BodySlide.pot
   - O app conserva suas traduções, marca como "fuzzy" os textos que
     mudaram e deixa as novas strings vazias.

2) TRADUZIR EM MASSA COM A IA (aba "Tradução IA por lotes")
   - No filtro de cima escolha "Sem tradução" (ou "Com fuzzy" para
     revisar)
   - Pressione "Preparar lote" (usa as entradas filtradas ou as
     selecionadas com Ctrl+clique / Shift+clique na tabela)
   - O prompt é copiado para a área de transferência: cole-o no
     ChatGPT, Claude, Gemini... (o botão "Abrir chat" abre o de sua
     escolha)
   - Copie a resposta da IA e cole-a no painel direito
   - Pressione "Aplicar e próximo lote": cada linha substitui sua
     entrada e o lote seguinte é preparado automaticamente
   - Se algo der errado: "Desfazer último lote"

3) EDITAR À MÃO (aba "Editor de entrada")
   - Duplo clique numa linha da tabela, edite e use Anterior/Próxima
   - "Copiar original para a tradução" serve para números ou termos
     que não se traduzem

4) SALVAR
   - "Salvar .po" salva o catálogo (com cópia .bak)
   - "Compilar .mo" gera o arquivo binário que o programa usa
     (BodySlide: substitua seu BodySlide.mo na pasta do idioma,
     ex. lang/pt/)

DICAS
- O máximo de caracteres por lote evita respostas cortadas pela IA.
- As entradas "fuzzy" são traduções reaproveitadas de textos mudados:
  revise-as antes de compilar o .mo.
- Textos multilinha viajam com \n literal; o app reconverte sozinho.
"""
,
    'pl': """JAK KORZYSTAĆ Z PoTranslator (przepływ z AI)
============================================

1) AKTUALIZACJA TŁUMACZENIA
   - Menu "Plik > Otwórz .po" i wybierz swój BodySlide.po
   - Menu "Plik > Aktualizuj z POT" i wybierz nowy BodySlide.pot
   - Aplikacja zachowuje Twoje tłumaczenia, oznacza zmienione teksty
     jako "fuzzy", a nowe ciągi zostawia puste.

2) MASZYNOWE TŁUMACZENIE Z AI (zakładka "Tłumaczenie AI partiami")
   - W filtrze u góry wybierz "Nieprzetłumaczone" (lub "Z fuzzy" do
     sprawdzenia)
   - Naciśnij "Przygotuj partię" (używa przefiltrowanych wpisów lub
     zaznaczonych Ctrl+klik / Shift+klik w tabeli)
   - Prompt trafia do schowka: wklej go do ChatGPT, Claude,
     Gemini... (przycisk "Otwórz czat" otwiera wybrany)
   - Skopiuj odpowiedź AI i wklej ją do prawego panelu
   - Naciśnij "Zastosuj i następna partia": każda linia zastępuje swój
     wpis, a kolejna partia przygotowuje się automatycznie
   - Jeśli coś pójdzie nie tak: "Cofnij ostatnią partię"

3) RĘCZNA EDYCJA (zakładka "Edytor wpisu")
   - Dwuklik na wierszu tabeli, edytuj i użyj Poprzedni/Następny
   - "Kopiuj oryginał do tłumaczenia" przydaje się dla liczb lub
     terminów nietłumaczonych

4) ZAPIS
   - "Zapisz .po" zapisuje katalog (z kopią .bak)
   - "Kompiluj .mo" tworzy plik binarny używany przez program
     (BodySlide: podmień swój BodySlide.mo w folderze języka,
     np. lang/pl/)

WSKAZÓWKI
- Maksimum znaków na partię zapobiega ucinanym odpowiedziom AI.
- Wpisy "fuzzy" to powtórnie użyte tłumaczenia zmienionych tekstów:
  sprawdź je przed kompilacją .mo.
- Teksty wieloliniowe podróżują z literalnym \n; aplikacja sama go
  konwertuje z powrotem.
"""
,
    'ru': """КАК ПОЛЬЗОВАТЬСЯ PoTranslator (сценарий с ИИ)
=============================================

1) ОБНОВИТЬ ПЕРЕВОД
   - Меню «Файл > Открыть .po» — выберите свой BodySlide.po
   - Меню «Файл > Обновить из POT» — выберите новый BodySlide.pot
   - Программа сохранит ваши переводы, пометит изменённые тексты как
     «fuzzy», а новые строки оставит пустыми.

2) МАССОВЫЙ ПЕРЕВОД С ИИ (вкладка «Пакетный перевод с ИИ»)
   - В фильтре сверху выберите «Без перевода» (или «С fuzzy» для
     проверки)
   - Нажмите «Подготовить пакет» (используются отфильтрованные записи
     или выделенные Ctrl+клик / Shift+клик в таблице)
   - Запрос копируется в буфер обмена: вставьте его в ChatGPT, Claude,
     Gemini... (кнопка «Открыть чат» открывает выбранный)
   - Скопируйте ответ ИИ и вставьте его в правую панель
   - Нажмите «Применить и следующий пакет»: каждая строка заменяет свою
     запись, а следующий пакет готовится автоматически
   - Если что-то пошло не так: «Отменить последний пакет»

3) РУЧНОЕ РЕДАКТИРОВАНИЕ (вкладка «Редактор записи»)
   - Двойной щелчок по строке таблицы, правка и кнопки Назад/Вперёд
   - «Копировать оригинал в перевод» пригодится для чисел и терминов,
     которые не переводятся

4) СОХРАНЕНИЕ
   - «Сохранить .po» записывает каталог (с копией .bak)
   - «Компилировать .mo» создаёт двоичный файл для программы
     (BodySlide: замените свой BodySlide.mo в папке языка,
     напр. lang/ru/)

СОВЕТЫ
- Максимум символов на пакет защищает от обрезанных ответов ИИ.
- Записи «fuzzy» — повторно использованные переводы изменённых
  текстов: проверьте их перед компиляцией .mo.
- Многострочные тексты передаются с литеральным \n; программа сама
  конвертирует его обратно.
"""
,
    'zh': """PoTranslator 使用指南（AI 流程）
===============================

1) 更新你的翻译
   - 菜单“文件 > 打开 .po”，选择你的 BodySlide.po
   - 菜单“文件 > 从 POT 更新”，选择新的 BodySlide.pot
   - 程序会保留已有翻译，把更改过的文本标记为“fuzzy”，
     新字符串留空。

2) AI 批量翻译（“AI 批量翻译”标签页）
   - 在上方筛选器选择“未翻译”（或“含 fuzzy”进行复查）
   - 点击“准备批次”（使用筛选出的条目，或按 Ctrl+点击 /
     Shift+点击 在表格中选择的条目）
   - 提示词会复制到剪贴板：粘贴到 ChatGPT、Claude、Gemini...
     （“打开聊天”按钮可打开你选择的聊天）
   - 复制 AI 的回复，粘贴到右侧面板
   - 点击“应用并下一批次”：每行会替换对应条目，并自动准备
     下一批次
   - 出问题时：“撤销上一批次”

3) 手动编辑（“条目编辑器”标签页）
   - 双击表格中的行进行编辑，用“上一条/下一条”切换
   - “复制原文到译文”适用于数字或不需要翻译的术语

4) 保存
   - “保存 .po”保存目录（自动备份 .bak）
   - “编译 .mo”生成程序使用的二进制文件
     （BodySlide：替换语言文件夹中的 BodySlide.mo，
     例如 lang/zh/）

小贴士
- 每批次字符上限可防止 AI 回复被截断。
- “fuzzy”条目是更改文本的复用翻译：编译 .mo 前请先复查。
- 多行文本以字面 \n 传输，程序会自动转换回来。
"""
,
    'ja': """PoTranslator の使い方（AI ワークフロー）
========================================

1) 翻訳を更新する
   - メニュー「ファイル > .po を開く」で BodySlide.po を選択
   - メニュー「ファイル > POT から更新」で新しい BodySlide.pot
     を選択
   - 既存の翻訳は保持され、変更されたテキストは "fuzzy" と
     マークされ、新しい文字列は空のままになります。

2) AI で一括翻訳（「AI 一括翻訳」タブ）
   - 上のフィルタで「未翻訳」を選択（確認するなら「fuzzy あり」）
   - 「バッチを準備」を押す（絞り込んだエントリ、または表で
     Ctrl+クリック / Shift+クリックで選択したエントリを使用）
   - プロンプトがクリップボードにコピーされます：ChatGPT、
     Claude、Gemini... に貼り付けてください（「チャットを開く」
     ボタンで選択したチャットが開きます）
   - AI の回答をコピーして右のパネルに貼り付けます
   - 「適用して次のバッチ」を押す：各行が対応するエントリを
     置き換え、次のバッチが自動で準備されます
   - 問題が起きたら：「最後のバッチを元に戻す」

3) 手動編集（「エントリエディタ」タブ）
   - 表の行をダブルクリックして編集し、前へ/次へで移動
   - 「原文を翻訳にコピー」は数字や翻訳しない用語に便利

4) 保存
   - 「.po を保存」でカタログを保存（.bak バックアップ付き）
   - 「.mo をコンパイル」でプログラムが使うバイナリを生成
     （BodySlide：言語フォルダ（例: lang/ja/）の BodySlide.mo を
     置き換えてください）

ヒント
- バッチあたりの最大文字数は、AI の回答が途切れるのを防ぎます。
- "fuzzy" エントリは変更テキストの再利用翻訳です：.mo を
  コンパイルする前に確認してください。
- 複数行テキストはリテラルの \n で送られ、アプリが自動的に
  変換し直します。
"""

}



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
    parts = [prompt_tpl.rstrip(), '', separator, '', get_batch_instruction(), '']
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
        # idioma inicial: el guardado o, en el primer arranque, el del sistema
        # (asi la app nunca aparece en un idioma equivocado)
        set_app_lang(self.cfg.get('lang') or _detect_system_lang())
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
        if not self.cfg.get('lang'):
            # primer arranque (o config sin idioma): dialogo modal SOBRE la
            # app ya visible (nunca oculto, para no bloquear el arranque)
            prov = _LANG[0]
            self._ask_first_language()
            set_app_lang(self.cfg.get('lang') or 'es')
            if (_LANG[0] or 'es') != prov:
                self._rebuild_ui()
        self.after(50, self._set_placeholder_states)

    # ------------------------------------------------------------------ UI
    FILTER_KEYS = ('all', 'untr', 'fuzzy', 'trans')

    def _apply_lang_fonts(self):
        """Fuentes con glifos del idioma activo.

        En Windows la fuente por defecto (Segoe UI) ya trae cirílico, pero
        no CJK: para zh/ja se cambia a una fuente nativa. En algunos Linux
        la fuente por defecto es latin-1 (p. ej. Nimbus), así que ruso
        también lleva lista de respaldo. Si ninguna existe, no se toca nada.
        """
        candidatos = {
            'zh': ('Microsoft YaHei UI', 'Microsoft YaHei', 'SimHei',
                   'Noto Sans CJK SC', 'Noto Sans SC', 'WenQuanYi Micro Hei',
                   'Microsoft JhengHei'),
            'ja': ('Yu Gothic UI', 'Meiryo UI', 'MS Gothic',
                   'Noto Sans CJK JP', 'Noto Sans JP', 'Noto Sans SC',
                   'IPAGothic'),
            'ru': ('Segoe UI', 'DejaVu Sans', 'Noto Sans', 'Liberation Sans',
                   'Arial'),
        }.get(_LANG[0])
        if not candidatos:
            return
        disponibles = set(tkfont.families(self))
        for fuente in candidatos:
            if fuente in disponibles:
                for nombre in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont',
                               'TkHeadingFont', 'TkTooltipFont',
                               'TkSmallCaptionFont', 'TkFixedFont'):
                    try:
                        tkfont.nametofont(nombre).configure(family=fuente)
                    except Exception:
                        pass
                break

    def _build_ui(self):
        self.style = ttk.Style(self)
        for theme in ('vista', 'xpnative', 'clam'):
            if theme in self.style.theme_names():
                self.style.theme_use(theme)
                break
        self.style.configure('Treeview', rowheight=24)
        self.style.configure('TButton', padding=(10, 4))
        self.style.configure('Big.TButton', font=('', 10, 'bold'), padding=(14, 6))
        self._apply_lang_fonts()

        self._build_menu()

        # ---- barra de herramientas
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill='x')
        ttk.Button(bar, text=_('tb_abrir'), command=self.open_file).pack(side='left')
        ttk.Button(bar, text=_('tb_actualizar'), command=self.update_from_pot_dialog
                   ).pack(side='left', padx=(6, 0))
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=8, pady=2)
        ttk.Button(bar, text=_('tb_guardar'), command=self.save_po).pack(side='left')
        ttk.Button(bar, text=_('tb_guardar_como'), command=self.save_po_as).pack(side='left', padx=(6, 0))
        ttk.Button(bar, text=_('tb_compilar'), command=self.compile_mo).pack(side='left', padx=(6, 0))
        self.lbl_file = ttk.Label(bar, text=_('sin_archivo'),
                                  foreground=self.theme['muted'])
        self.lbl_file.pack(side='right')

        # ---- filtros
        fbar = ttk.Frame(self, padding=(8, 0))
        fbar.pack(fill='x')
        ttk.Label(fbar, text=_('fl_mostrar')).pack(side='left')
        self.filter_key = getattr(self, 'filter_key', 'all')
        self.var_filter = tk.StringVar(value=_('filter_' + self.filter_key))
        cb = ttk.Combobox(fbar, textvariable=self.var_filter, state='readonly', width=13,
                          values=[_('filter_' + k) for k in self.FILTER_KEYS])
        cb.pack(side='left', padx=(4, 10))
        cb.bind('<<ComboboxSelected>>', self._on_filter_selected)
        ttk.Label(fbar, text=_('fl_buscar')).pack(side='left')
        self.var_search = tk.StringVar()
        self.ent_search = ttk.Entry(fbar, textvariable=self.var_search, width=34)
        self.ent_search.pack(side='left', padx=(4, 10))
        self.ent_search.bind('<KeyRelease>', self._on_search_key)
        self.var_obs = tk.BooleanVar(value=False)
        ttk.Checkbutton(fbar, text=_('fl_obs'), variable=self.var_obs,
                        command=self.refresh_tree).pack(side='left', padx=(0, 10))
        ttk.Button(fbar, text=_('fl_seleccionar'), command=self.select_filtered
                   ).pack(side='left')
        self.lbl_sel = ttk.Label(fbar, text='', foreground=self.theme['muted'])
        self.lbl_sel.pack(side='left', padx=10)

        # ---- notebook inferior y barra de estado (se reservan desde abajo
        # para que nunca queden fuera de pantalla)
        sbar = ttk.Frame(self, padding=(10, 4))
        sbar.pack(side='bottom', fill='x')
        self.lbl_counts = ttk.Label(sbar, text=_('st_abre'))
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
        headings = ('#', _('col_estado'), _('col_orig'), _('col_trad'),
                    _('col_refs'))
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

    # ------------------------------------------------------------- idioma
    def set_lang(self, code):
        """Cambia el idioma de la interfaz en vivo (menu Ver > Idioma)."""
        if code not in _LANG_CODES:
            return
        self.var_lang.set(code)
        self.cfg['lang'] = code
        self._write_config_file()
        set_app_lang(code)
        # se difiere un instante para no destruir el menu desde su propio
        # callback
        self.after_idle(self._rebuild_ui)

    def _rebuild_ui(self):
        """Reconstruye toda la interfaz (p. ej. tras cambiar de idioma),
        conservando lo que el usuario tiene en pantalla."""
        snap = {
            'tpl': self.txt_tpl.get('1.0', 'end').rstrip('\n'),
            'res': self.txt_result.get('1.0', 'end').rstrip('\n'),
            'prompt': self.txt_prompt.get('1.0', 'end').rstrip('\n'),
            'search': self.var_search.get(),
            'obs': bool(self.var_obs.get()),
            'source': self.var_source.get(),
            'filter': getattr(self, 'filter_key', 'all'),
            'sep': self.var_sep.get(),
            'max': self.var_max.get(),
            'chat': self.var_chat.get(),
            'incl': bool(self.var_include_tr.get()),
        }
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()
        # restaurar el estado del usuario con los textos nuevos
        self.var_search.set(snap['search'])
        self.var_obs.set(snap['obs'])
        self.var_source.set(snap['source'])
        self.var_include_tr.set(snap['incl'])
        self.var_sep.set(snap['sep'])
        try:
            self.var_max.set(int(snap['max']))
        except Exception:
            pass
        self.var_chat.set(snap['chat'])
        self._set_filter(snap['filter'])
        self.txt_tpl.delete('1.0', 'end')
        self.txt_tpl.insert('1.0', snap['tpl'])
        self.txt_result.delete('1.0', 'end')
        self.txt_result.insert('1.0', snap['res'])
        if snap['prompt']:
            self.txt_prompt.config(state='normal')
            self.txt_prompt.delete('1.0', 'end')
            self.txt_prompt.insert('1.0', snap['prompt'])
            self.txt_prompt.config(state='disabled')
        if self.po_path is not None:
            self.lbl_file.config(text=self.po_path.name)
        self.refresh_tree()
        if self.current_idx is not None:
            self.load_editor(self.current_idx)
        self._update_title()

    def _ask_first_language(self):
        """Diálogo de elección de idioma del primer arranque (modal)."""
        win = tk.Toplevel(self)
        win.title('PoTranslator — Language / Idioma')
        win.resizable(False, False)
        win.transient(self)
        frm = ttk.Frame(win, padding=22)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text='Choose your language / Elige tu idioma',
                  font=('', 12, 'bold')).pack(pady=(0, 2))
        ttk.Label(frm, text='(View → Language / Ver → Idioma)',
                  foreground='#666666').pack(pady=(0, 10))
        var = tk.StringVar(value=_LANG[0])   # preselección: idioma detectado
        lf = ttk.LabelFrame(frm, text=' Language / Idioma ', padding=12)
        lf.pack(fill='x')
        for code, nombre in APP_LANGS:
            ttk.Radiobutton(lf, text=nombre, value=code, variable=var
                            ).pack(anchor='w', pady=1)
        ttk.Button(frm, text='OK', command=win.destroy).pack(pady=(14, 0))
        win.protocol('WM_DELETE_WINDOW', win.destroy)
        win.bind('<Return>', lambda e: win.destroy())
        try:
            win.grab_set()          # modal: obliga a elegir antes de seguir
        except Exception:
            pass
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry('+%d+%d' % ((win.winfo_screenwidth() - w) // 2,
                                 (win.winfo_screenheight() - h) // 2))
        self.wait_window(win)
        code = var.get() if var.get() in _LANG_CODES else 'en'
        self.cfg['lang'] = code
        # prompt por defecto en el idioma elegido (solo primera vez;
        # si el usuario ya tenía uno guardado, no se toca)
        if not self.cfg.get('prompt') or self.cfg['prompt'] == DEFAULT_PROMPTS['es']:
            self.cfg['prompt'] = DEFAULT_PROMPTS.get(code, DEFAULT_PROMPTS['es'])
        self._write_config_file()

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
        fm.add_command(label=_('mi_abrir'), accelerator='Ctrl+O',
                       command=self.open_file)
        fm.add_separator()
        fm.add_command(label=_('mi_actualizar'), command=self.update_from_pot_dialog)
        fm.add_separator()
        fm.add_command(label=_('mi_guardar'), accelerator='Ctrl+S', command=self.save_po)
        fm.add_command(label=_('mi_guardar_como'), accelerator='Ctrl+Shift+S', command=self.save_po_as)
        fm.add_command(label=_('mi_compilar'), accelerator='F5', command=self.compile_mo)
        fm.add_separator()
        fm.add_command(label=_('mi_salir'), command=self._on_close)
        m.add_cascade(label=_('m_archivo'), menu=fm)

        em = tk.Menu(m, tearoff=0)
        em.add_command(label=_('mi_ent_ant'), accelerator=_('acc_up'),
                       command=lambda: self.nav_entry(-1))
        em.add_command(label=_('mi_ent_sig'), accelerator=_('acc_down'),
                       command=lambda: self.nav_entry(1))
        em.add_command(label=_('mi_guardar_ent'), accelerator='Ctrl+Enter',
                       command=self.apply_editor)
        em.add_separator()
        em.add_command(label=_('mi_copiar_orig'), command=self.bulk_copy_original)
        em.add_command(label=_('mi_fuzzy_toggle'), command=self.bulk_toggle_fuzzy)
        m.add_cascade(label=_('m_editar'), menu=em)

        bm = tk.Menu(m, tearoff=0)
        bm.add_command(label=_('mi_preparar'), command=self.prepare_batch)
        bm.add_command(label=_('mi_aplicar'), command=lambda: self.apply_result(False))
        bm.add_command(label=_('mi_aplicar_sig'), command=lambda: self.apply_result(True))
        bm.add_command(label=_('mi_sig_lote'), command=self.next_batch)
        bm.add_separator()
        bm.add_command(label=_('mi_deshacer'), command=self.undo_last)
        m.add_cascade(label=_('m_lote'), menu=bm)

        vm = tk.Menu(m, tearoff=0)
        self.var_theme = tk.StringVar(value=self.cfg.get('theme', 'auto'))
        tm = tk.Menu(vm, tearoff=0)
        for valor, clave in (('auto', 'tema_auto'), ('claro', 'tema_claro'),
                             ('oscuro', 'tema_oscuro')):
            tm.add_radiobutton(label=_(clave), value=valor, variable=self.var_theme,
                               command=lambda v=valor: self.set_theme(v))
        vm.add_cascade(label=_('mi_tema'), menu=tm)
        vm.add_separator()
        self.var_lang = tk.StringVar(value=self.cfg.get('lang') or 'es')
        lm = tk.Menu(vm, tearoff=0)
        for code, nombre in APP_LANGS:
            lm.add_radiobutton(label=nombre, value=code, variable=self.var_lang,
                               command=lambda c=code: self.set_lang(c))
        vm.add_cascade(label=_('mi_idioma'), menu=lm)
        m.add_cascade(label=_('m_ver'), menu=vm)

        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label=_('mi_guia'), command=self.show_guide)
        hm.add_command(label=_('mi_acerca'), command=self.show_about)
        m.add_cascade(label=_('m_ayuda'), menu=hm)
        self._menus = (m, fm, em, bm, vm, tm, lm, hm)
        self.config(menu=m)

    # -------------------------------------------------- pestaña: editor
    def _build_editor_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text=_('tab_editor'))

        top = ttk.Frame(tab)
        top.pack(fill='x')
        self.lbl_entry_pos = ttk.Label(top, text='—', font=('', 10, 'bold'))
        self.lbl_entry_pos.pack(side='left')
        self.var_fuzzy = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text=_('chk_fuzzy'), variable=self.var_fuzzy,
                        command=self.apply_editor).pack(side='right')
        self.lbl_refs = ttk.Label(top, text='', foreground=self.theme['muted'])
        self.lbl_refs.pack(side='right', padx=14)

        mid = ttk.Frame(tab)
        mid.pack(fill='both', expand=True, pady=(6, 0))
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)

        lf_orig = ttk.LabelFrame(mid, text=_('lf_original'), padding=4)
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

        lf_trad = ttk.LabelFrame(mid, text=_('lf_trad'), padding=4)
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
        ttk.Button(bots, text=_('btn_anterior'), command=lambda: self.nav_entry(-1)
                   ).pack(side='left')
        ttk.Button(bots, text=_('btn_siguiente'), command=lambda: self.nav_entry(1)
                   ).pack(side='left', padx=6)
        ttk.Button(bots, text=_('mi_copiar_orig'),
                   command=self.copy_original_to_editor).pack(side='left', padx=6)
        ttk.Button(bots, text=_('mi_guardar_ent'), command=self.apply_editor).pack(side='right')

        self.editor_tab = tab

    # ------------------------------------------------ pestaña: lotes IA
    def _build_ai_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text=_('tab_ia'))
        self.ai_tab = tab

        # fila 1: origen del lote
        r1 = ttk.Frame(tab)
        r1.pack(fill='x')
        ttk.Label(r1, text=_('lbl_origen'), font=('', 10, 'bold')).pack(side='left')
        self.var_source = tk.StringVar(value='filtered')
        self.rb_sel = ttk.Radiobutton(r1, text=_('rb_seleccionadas', 0),
                                      variable=self.var_source, value='selected')
        self.rb_sel.pack(side='left', padx=(10, 4))
        self.rb_fil = ttk.Radiobutton(r1, text=_('rb_filtradas', 0),
                                      variable=self.var_source, value='filtered')
        self.rb_fil.pack(side='left', padx=4)
        self.var_include_tr = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text=_('chk_incluir_tr'), variable=self.var_include_tr
                        ).pack(side='left', padx=12)
        ttk.Button(r1, text=_('mi_preparar'), style='Big.TButton',
                   command=self.prepare_batch).pack(side='right')
        ttk.Button(r1, text=_('mi_sig_lote'),
                   command=self.next_batch).pack(side='right', padx=8)

        # fila 2: ajustes del lote
        r2 = ttk.Frame(tab)
        r2.pack(fill='x', pady=(8, 0))
        ttk.Label(r2, text=_('lbl_separador')).pack(side='left')
        self.var_sep = tk.StringVar(value=DEFAULT_CONFIG['separator'])
        ent_sep = ttk.Entry(r2, textvariable=self.var_sep, width=14)
        ent_sep.pack(side='left', padx=(4, 12))
        ent_sep.bind('<FocusOut>', lambda e: self._save_config())
        ttk.Label(r2, text=_('lbl_max')).pack(side='left')
        self.var_max = tk.IntVar(value=DEFAULT_CONFIG['max_chars'])
        sp = ttk.Spinbox(r2, from_=500, to=100000, increment=500, width=8,
                         textvariable=self.var_max)
        sp.pack(side='left', padx=(4, 12))
        sp.bind('<FocusOut>', lambda e: self._save_config())
        ttk.Label(r2, text=_('lbl_chat')).pack(side='left')
        self.var_chat = tk.StringVar(value=DEFAULT_CONFIG['chat'])
        cbc = ttk.Combobox(r2, textvariable=self.var_chat, state='readonly', width=12,
                           values=list(CHAT_URLS.keys()))
        cbc.pack(side='left', padx=(4, 4))
        ttk.Button(r2, text=_('btn_abrir_chat'), command=self.open_chat).pack(side='left')

        # fila 3: prompt | respuesta
        r3 = ttk.PanedWindow(tab, orient='horizontal')
        r3.pack(fill='both', expand=True, pady=(8, 0))

        lf_prompt = ttk.LabelFrame(r3, text=_('lf_prompt'), padding=4)
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
        self.lbl_prompt_chars = ttk.Label(pb, text=_('chars_n', 0),
                                          foreground=self.theme['muted'])
        self.lbl_prompt_chars.pack(side='left')
        ttk.Button(pb, text=_('btn_copiar_todo'), command=self.copy_prompt).pack(side='right')

        lf_result = ttk.LabelFrame(r3, text=_('lf_respuesta'), padding=4)
        self.txt_result = tk.Text(lf_result, height=8, width=56, wrap='word', undo=True)
        sbr = ttk.Scrollbar(lf_result, command=self.txt_result.yview)
        self.txt_result.configure(yscrollcommand=sbr.set)
        self.txt_result.pack(side='top', fill='both', expand=True)
        sbr.pack(side='right', fill='y')
        rb = ttk.Frame(lf_result)
        rb.pack(fill='x', pady=(4, 0))
        ttk.Button(rb, text=_('mi_aplicar'), command=lambda: self.apply_result(False)
                   ).pack(side='left')
        ttk.Button(rb, text=_('mi_aplicar_sig'), style='Big.TButton',
                   command=lambda: self.apply_result(True)).pack(side='left', padx=8)
        ttk.Button(rb, text=_('mi_deshacer'), command=self.undo_last
                   ).pack(side='right')
        r3.add(lf_prompt, weight=1)
        r3.add(lf_result, weight=1)

        # fila 4: plantilla del prompt
        lf_tpl = ttk.LabelFrame(tab, text=_('lf_plantilla'), padding=4)
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
                parent=self, title=_('dlg_abrir'),
                filetypes=[(_('ft_trad'), '*.po *.pot *.mo'),
                           (_('ft_todos'), '*.*')])
        if not path:
            return
        try:
            po = load_any(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, _('msg_err_abrir', exc),
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
            messagebox.showinfo(APP_NAME, _('msg_abrio_pot'), parent=self)

    def _rebuild_entries(self):
        self.entries = [e for e in self.po if e.msgid]
        self._idx_by_id = {id(e): i for i, e in enumerate(self.entries)}

    def update_from_pot_dialog(self):
        if self.po is None:
            messagebox.showinfo(APP_NAME, _('msg_abre_po'), parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self, title=_('dlg_pot'),
            filetypes=[(_('ft_pot'), '*.pot'), (_('ft_po'), '*.po'),
                       (_('ft_todos'), '*.*')])
        if not path:
            return
        self.apply_editor()
        try:
            pot = polib.pofile(str(path))
            t0 = time.time()
            stats = update_from_pot(self.po, pot)
            seg = time.time() - t0
        except Exception as exc:
            messagebox.showerror(APP_NAME, _('msg_err_pot', exc),
                                 parent=self)
            return
        self.po.wrapwidth = 100000
        self._rebuild_entries()
        self.refresh_tree()
        self.refresh_counts()
        self.load_editor(None)
        self.mark_dirty()
        msg = _('msg_pot_ok', seg, stats['kept'], stats['fuzzy'],
                stats['new'], stats['obsolete'])
        messagebox.showinfo(APP_NAME + ' — ' + _('title_pot_result'), msg,
                            parent=self)

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
            messagebox.showerror(APP_NAME, _('msg_err_guardar', exc), parent=self)
            return
        self.dirty = False
        self._update_title()
        self.lbl_batch_state.config(text=_('st_guardado',
                                           datetime.now().strftime('%H:%M')))

    def save_po_as(self):
        if self.po is None:
            return
        self.apply_editor()
        default = str(self.po_path) if self.po_path else _('default_po_name') + '.po'
        path = filedialog.asksaveasfilename(
            parent=self, title=_('dlg_guardar_como'), defaultextension='.po',
            initialfile=Path(default).with_suffix('.po').name,
            filetypes=[(_('ft_po_cat'), '*.po')])
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
            parent=self, title=_('dlg_compilar'), defaultextension='.mo',
            filetypes=[(_('ft_mo_cat'), '*.mo')])
        if path:
            self._write_mo(Path(path))

    def _write_mo(self, path):
        self.apply_editor()
        try:
            touch_metadata(self.po)
            backup_file(path)
            self.po.save_as_mofile(str(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, _('msg_err_mo', exc),
                                 parent=self)
            return
        self.lbl_batch_state.config(
            text=_('st_mo_ok', datetime.now().strftime('%H:%M')),
            foreground=self.theme['ok'])

    # ------------------------------------------------------------- tabla
    def _on_filter_selected(self, _event):
        etiquetas = {_('filter_' + k): k for k in self.FILTER_KEYS}
        self.filter_key = etiquetas.get(self.var_filter.get(), 'all')
        self.refresh_tree()

    def _set_filter(self, key):
        self.filter_key = key if key in self.FILTER_KEYS else 'all'
        self.var_filter.set(_('filter_' + self.filter_key))

    def _on_search_key(self, _event):
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(250, self.refresh_tree)

    def row_values(self, i, e):
        st = entry_state(e)
        return (i + 1, _('state_' + st), preview_text(e.msgid),
                preview_text(e.msgstr), refs_short(e))

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.displayed = []
        if self.po is None:
            self._update_source_labels()
            return
        q = (self.var_search.get() or '').strip().lower()
        want = getattr(self, 'filter_key', 'all')
        show_obs = bool(self.var_obs.get())
        for i, e in enumerate(self.entries):
            st = entry_state(e)
            if st == 'obs':
                if not show_obs:
                    continue
            elif want == 'untr' and st != 'untr':
                continue
            elif want == 'fuzzy' and st != 'fuzzy':
                continue
            elif want == 'trans' and st != 'trans':
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
        self.lbl_sel.config(text=(_('lbl_sel_1') if nsel == 1
                                  else _('lbl_sel_n', nsel)) if nsel else '')
        self.rb_sel.config(text=_('rb_seleccionadas', nsel))
        self.rb_fil.config(text=_('rb_filtradas', len(self.displayed)))

    def update_row(self, i):
        iid = str(i)
        if self.tree.exists(iid):
            self.tree.item(iid, values=self.row_values(i, self.entries[i]),
                           tags=(entry_state(self.entries[i]),))

    def refresh_counts(self):
        if self.po is None:
            self.lbl_counts.config(text=_('st_abre'))
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
            text=_('st_counts', total, t, f, u,
                   (_('st_counts_obs', o) if o else ''), pct))
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
        menu.add_command(label=_('mi_copiar_orig'),
                         command=self.bulk_copy_original)
        menu.add_command(label=_('ctx_borrar'), command=self.bulk_clear)
        menu.add_command(label=_('ctx_marcar'), command=lambda: self.bulk_fuzzy(True))
        menu.add_command(label=_('ctx_quitar'), command=lambda: self.bulk_fuzzy(False))
        menu.add_separator()
        menu.add_command(label=_('ctx_sel_todas'), command=self.select_filtered)
        menu.add_command(label=_('ctx_copiar_originales'),
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
        self.lbl_batch_state.config(text=_('st_orig_copiados', len(idxs)),
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
        self.lbl_entry_pos.config(text=_('lbl_entrada_pos', idx + 1,
                                        len(self.entries)))
        self._build_plural_editor(e)

    def _build_plural_editor(self, e):
        for w in self.plural_frame.winfo_children():
            w.destroy()
        self._plural_texts = []
        if e is None or not e.msgid_plural:
            return
        n = get_nplurals(self.po)
        lf = ttk.LabelFrame(self.plural_frame, text=_('lf_plurales'), padding=4)
        lf.pack(fill='x')
        lf.columnconfigure(1, weight=1)
        ttk.Label(lf, text=_('lbl_msgid_plural')).grid(row=0, column=0, sticky='nw',
                                                        padx=(0, 8))
        tp = tk.Text(lf, height=2, wrap='word', state='disabled',
                     background=self.theme['text_readonly'],
                     foreground=self.theme['text_fg'],
                     insertbackground=self.theme['insert'],
                     selectbackground=self.theme['text_sel'], relief='flat')
        tp.insert('1.0', e.msgid_plural)
        tp.config(state='disabled')
        tp.grid(row=0, column=1, sticky='ew', pady=2)
        labels = {0: _('lbl_singular'), 1: _('lbl_plural')}
        for i in range(n):
            extra = labels.get(i, _('lbl_forma_n', i))
            ttk.Label(lf, text=_('lbl_msgstr_n', i, extra)).grid(
                row=i + 1, column=0, sticky='nw', padx=(0, 8), pady=(4, 0))
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
            messagebox.showinfo(APP_NAME, _('msg_abre_po'), parent=self)
            return
        self.apply_editor()
        queue, skipped = self.gather_queue(self.var_source.get())
        if not queue:
            messagebox.showinfo(APP_NAME, _('msg_no_entries'), parent=self)
            return
        self.queue = queue
        self.queue_pos = 0
        self.batch_no = 1
        self._build_current_batch()
        if skipped:
            self.lbl_batch_state.config(
                text=_('st_plurales_fuera', skipped),
                foreground=self.theme['warn'])

    def next_batch(self):
        if not self.queue:
            messagebox.showinfo(APP_NAME, _('msg_prepara'), parent=self)
            return
        if self.queue_pos >= len(self.queue):
            messagebox.showinfo(APP_NAME, _('msg_no_mas_lotes'),
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
        self.lbl_prompt_chars.config(text=_('chars_entradas', len(prompt),
                                            len(items)))
        remaining = len(self.queue) - self.queue_pos
        self.lbl_batch_state.config(
            text=_('st_lote', self.batch_no, len(items), remaining),
            foreground=self.theme['ok'])
        self._to_clipboard(prompt)
        self.nb.select(self.ai_tab)

    def copy_prompt(self):
        prompt = self.txt_prompt.get('1.0', 'end').rstrip('\n')
        if prompt:
            self._to_clipboard(prompt)
            self.lbl_batch_state.config(text=_('st_prompt_copiado'),
                                        foreground='#0a5')

    def apply_result(self, then_next):
        if not self.batch_items:
            messagebox.showinfo(APP_NAME, _('msg_prepara'), parent=self)
            return
        raw = self.txt_result.get('1.0', 'end')
        sep = self.var_sep.get().strip()
        results = parse_ai_result(raw, sep)
        if not results:
            messagebox.showwarning(APP_NAME, _('msg_no_numeradas'),
                                   parent=self)
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
                note = _('note_orden')
        if applied == 0:
            messagebox.showwarning(APP_NAME, _('msg_no_coincidio'),
                                   parent=self)
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
            missing_txt = _('st_falta_linea', shown)
        if empties:
            missing_txt += _('st_vacias', empties)

        if then_next:
            if self.queue_pos < len(self.queue):
                self.batch_no += 1
                self._build_current_batch()
            else:
                self.lbl_batch_state.config(text=_('st_cola_completa'),
                                            foreground=self.theme['ok'])
                if not missing and not empties:
                    messagebox.showinfo(APP_NAME, _('msg_cola_ok', applied, note),
                                        parent=self)
        else:
            self.lbl_batch_state.config(
                text=_('st_aplicadas', applied, note),
                foreground=self.theme['ok'])
        if missing_txt:
            self.lbl_batch_state.config(
                text=(_('st_aplicadas_corto', applied, note))
                + missing_txt.replace('\n', ' · '),
                foreground=self.theme['warn'])

    def undo_last(self):
        if not self.undo_stack:
            messagebox.showinfo(APP_NAME, _('msg_nada_deshacer'), parent=self)
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
        self.lbl_batch_state.config(text=_('st_deshechas', len(snaps)),
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
        messagebox.showinfo(APP_NAME + ' — ' + _('mi_guia'), get_guide(),
                            parent=self)

    def show_about(self):
        messagebox.showinfo(_('about_title'),
                            _('about_text', APP_NAME, APP_VERSION), parent=self)

    def _check_save_changes(self):
        if not self.dirty or self.po is None:
            return True
        r = messagebox.askyesnocancel(APP_NAME, _('msg_cambios'),
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
            'lang': self.var_lang.get() if hasattr(self, 'var_lang')
                    else self.cfg.get('lang'),
        })
        self._write_config_file()

    def _write_config_file(self):
        """Escribe la configuracion (portable: en _internal; script: HOME)."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
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
