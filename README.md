# PoTranslator

**Editor de traducciones gettext (.po / .pot / .mo) con traducción masiva por IA, sin APIs ni claves.**

<p align="center">
  <img src="capturas/app_tabla.png" alt="PoTranslator" width="720">
</p>

Pensado para el flujo de trabajo de *ESP translate*: seleccionas un montón de
cadenas, la app genera un prompt numerado (`1) texto`, una entrada por línea),
lo pegas en el chat de IA que prefieras (ChatGPT, Claude, Gemini, Copilot...),
copias la respuesta de vuelta y PoTranslator reemplaza cada traducción en su
sitio. Cero configuración: solo tu navegador y el portapapeles.

## Características

- **Actualizar un .po desde un .pot nuevo** — fusión al estilo `msgmerge`:
  las traducciones exactas se conservan, los textos que cambiaron quedan
  marcados como *fuzzy* (con el texto anterior visible en `#| msgid`), las
  cadenas nuevas quedan vacías y las eliminadas se guardan como obsoletas
  (`#~`) al final del archivo.
- **Traducción por lotes con cualquier IA** — prompt numerado copiado al
  portapapeles, respuesta pegada y aplicada en un clic, y el lote siguiente
  se prepara solo (con límite de caracteres para que la IA no corte la
  respuesta).
- **Parseo tolerante de la respuesta** — acepta numeración `1)`, `1.`, `1 -`,
  `[1]`, `(1)`, negritas de Markdown (`**1)**`), bloques de código de la IA
  y comillas envolventes. Si la IA no numera, asigna por posición.
- **Protección de marcadores** — `%s`, `%d`, `%lu`, `{{PLACEHOLDER}}`, `\n`
  literales y `&` de atajos de menú se piden intactos en el prompt.
- **Tabla con filtros y multiselección** — Todas / Sin traducir / Con fuzzy /
  Traducidas, color por estado, selección múltiple con Ctrl+clic o Mayús+clic.
- **Editor manual** — edición de entradas con soporte de plurales, "copiar
  original a traducción" para números o términos que no se traducen, y
  acciones en masa con clic derecho.
- **Compilación .mo igual que `msgfmt`** — solo entran las cadenas traducidas
  y revisadas (las *fuzzy* y vacías quedan fuera).
- **Deshacer por lotes** y copias de seguridad `.bak` automáticas.
- 100 % Python estándar (tkinter) con polib incluida: sin dependencias.

## Descargar el ejecutable (Windows)

1. Entra en la página de [Releases](../../releases).
2. Descarga **`PoTranslator.exe`** de la última versión.
3. Doble clic. No necesita Python ni instalación.

El `.exe` se compila automáticamente con GitHub Actions cada vez que se
publica una versión nueva (ver más abajo).

## Ejecutar con Python (Windows / Linux / macOS)

Requisito: Python 3.8 o superior. En Windows, el instalador de
[python.org](https://www.python.org/downloads/) ya incluye tkinter.

```
python po_translator.py        (o doble clic en "Iniciar PoTranslator.bat")
```

## El flujo de traducción con IA

| Paso | Acción |
|-----:|--------|
| 1 | Abre tu `.po` y actualízalo desde el `.pot` nuevo (**Actualizar desde POT**). |
| 2 | Filtro **"Sin traducir"** y pulsa **Preparar lote**: el prompt ya queda en el portapapeles. |
| 3 | Pega el prompt en tu chat de IA favorito (el botón **Abrir chat** abre ChatGPT, Claude, Gemini...). |
| 4 | Copia la respuesta de la IA y pégala en el panel derecho de la pestaña de lotes. |
| 5 | Pulsa **Aplicar y siguiente lote**: cada línea `N)` reemplaza su entrada y se prepara el siguiente. |
| 6 | Repite hasta vaciar la cola y pulsa **Compilar .mo**. |

![Traducción por lotes con IA](capturas/app_ia.png)

Consejos:

- Si la IA corta la respuesta, baja el "Máx. caracteres por lote" (p. ej. a
  6000) y vuelve a preparar el lote.
- Para re-traducir cadenas que cambiaron, usa el filtro **"Con fuzzy"**.
- Si te equivocas en un lote: **Deshacer último lote**.
- Los textos multilínea viajan con `\n` literal y la app los reconvierte sola.

## Compilar el .exe

### Automático con GitHub Actions (recomendado)

El repositorio ya incluye el *workflow* `.github/workflows/build.yml`:

- Cada **push** a `main` compila un `PoTranslator.exe` nuevo. Descárgalo en la
  pestaña **Actions** → última ejecución → artefacto `PoTranslator-exe`
  (los artefactos expiran a los 90 días).
- Cada **etiqueta** `v1.1`, `v1.2`... crea además un **Release** permanente
  con el `.exe` adjunto, listo para compartir:

  ```
  git tag v1.1
  git push --tags
  ```

- También se puede lanzar a mano: **Actions → Compilar EXE → Run workflow**.

Es decir: para actualizar la app solo hay que subir los cambios del código;
el ejecutable se recompila solo en la nube, sin instalar nada.

### Local (Windows)

Doble clic en **`build.bat`**. Requiere Python 3.8+; el script instala
PyInstaller él solo y deja el ejecutable en `dist\PoTranslator.exe`.

## Estructura del proyecto

```
po_translator.py              La aplicación (un solo archivo)
polib.py                      Librería gettext (MIT), incluida
Iniciar PoTranslator.bat      Iniciador para Windows (con Python)
build.bat                     Compila PoTranslator.exe (PyInstaller)
PoTranslator.spec             Configuración de la compilación
icono.ico / icono.png         Icono del ejecutable
capturas/                     Capturas de la app
.github/workflows/build.yml   Compilación automática (GitHub Actions)
LEEME.txt                     Guía rápida incluida en el zip
```

## Créditos

- [polib](https://github.com/izimobil/polib/) de David Jean Louis (licencia MIT),
  incluida como archivo local.
- Creada para mantener la traducción al español de
  [BodySlide and Outfit Studio](https://github.com/ousnius/BodySlide-and-Outfit-Studio).
