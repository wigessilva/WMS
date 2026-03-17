import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont
from tkinter import ttk
import ctypes
import os
import hashlib
from database.repos.movimentacao import MovementsRepo

try:
    user32 = ctypes.windll.user32
    _is_windows = True
except:
    _is_windows = False

# Verifica se o PIL (Pillow) está disponível
try:
    from PIL import ImageGrab, ImageEnhance, ImageTk, Image
    _pil_available = True
except ImportError:
    _pil_available = False

from database.repositories import (
    recebimento_repo,
    lpn_repo,
    products_repo,
    families_repo,
    global_policies
)
# --- Constantes e Layout ---
from utils.constants import (
    Colors,
    PAGE_SIZE_DEFAULT,
    StatusPR
)
# --- Helpers ---
from utils.helpers import Utils, load_icon, _tint_icon, _pil_ok


# Função auxiliar para verificar PIL
def _pil_available():
    return _pil_ok()


class PillButton(tk.Canvas):
    _IMG_CACHE = {}

    def __init__(self, parent, text, command=None, variant="outline", height=34, radius=None, **kw):
        icon_img = kw.pop("icon", None)
        self._icon_disabled = kw.pop("icon_disabled", None)
        explicit_bg = kw.pop("bg", None)
        self._padx = kw.pop("padx", 16)

        # 1. NOVO: Captura a cor explicita (fg) se for passada
        self._explicit_fg = kw.pop("fg", None)

        base_bg = explicit_bg if explicit_bg is not None else Utils.resolve_parent_bg(parent)
        super().__init__(parent, height=height, bd=0, highlightthickness=0, bg=base_bg, **kw)

        self._bg_app_hex = base_bg
        self._text = text
        self._cmd = command
        self._variant = variant
        self._enabled = True
        self._radius = (radius if radius is not None else 6)
        self._font = ("Segoe UI", 10, "bold" if variant == "primary" else "normal")

        # Cores (Paleta)
        self._colors = {
            "primary": {"fg": "#ffffff", "bg": Colors.PRIMARY, "bg_hover": Colors.PRIMARY_HOVER, "bd": Colors.PRIMARY},
            "outline": {"fg": Colors.TEXT_MAIN, "bg": Colors.BG_INPUT, "bg_hover": "#F1F5F9", "bd": Colors.BORDER},
            "ghost": {"fg": Colors.TEXT_MAIN, "bg": Colors.BG_APP, "bg_hover": "#EEF2F6", "bd": Colors.BORDER},
            "success": {"fg": "#ffffff", "bg": Colors.SUCCESS, "bg_hover": Colors.SUCCESS_HOVER, "bd": Colors.SUCCESS},
            "disabled": {"fg": Colors.TEXT_HINT, "bg": "#F3F4F6", "bg_hover": "#F3F4F6", "bd": Colors.BORDER},
            "tab_selected": {"fg": Colors.PRIMARY, "bg": "#ffffff", "bg_hover": "#ffffff", "bd": "#ffffff"},
            "tab_unselected": {"fg": "#ffffff", "bg": Colors.BG_SIDEBAR, "bg_hover": Colors.ROW_HOVER_SB,
                               "bd": Colors.BG_SIDEBAR},
            "danger": {"fg": "#ffffff", "bg": Colors.DANGER, "bg_hover": Colors.DANGER_HOVER, "bd": Colors.DANGER},
            "warning": {"fg": Colors.TEXT_MAIN, "bg": Colors.WARNING, "bg_hover": Colors.WARNING_HOVER, "bd": Colors.WARNING}
        }

        self._icon = icon_img
        self._icon_pad = 6
        self._has_pil = None

        self._draw(normal=True)
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw(normal=True))
        self.bind("<Button-1>", self._on_click)

    def _palette(self):
        return self._colors["disabled"] if not self._enabled else self._colors.get(self._variant,
                                                                                   self._colors["outline"])

    def _bg_app_rgb(self):
        hx = self._bg_app_hex
        if not (isinstance(hx, str) and hx.startswith("#") and len(hx) == 7):
            hx = Colors.BG_APP
        return Utils.hex_to_rgb(hx)

    def _draw(self, normal=False, hover=False):
        self.delete("all")  # Limpa tudo antes de redesenhar

        pal = self._palette()
        bg = pal["bg_hover"] if (hover and self._enabled) else pal["bg"]
        bd = pal["bd"]
        fg = self._explicit_fg if self._explicit_fg else pal["fg"]

        # Calcula tamanho do texto
        wtxt = tkfont.Font(font=self._font).measure(self._text or "")

        # Tratamento do Ícone (Tintura)
        icon_img = self._icon
        if not self._enabled and self._icon_disabled:
            icon_img = self._icon_disabled
        elif icon_img:
            if not self._enabled:
                icon_img = _tint_icon(icon_img, pal["fg"])
            elif self._explicit_fg:
                icon_img = _tint_icon(icon_img, self._explicit_fg)

        icon_w = icon_img.width() if icon_img else 0
        gap = self._icon_pad if (icon_img and self._text) else 0

        # Largura total do conteúdo
        content_w = icon_w + gap + wtxt
        h = int(self["height"])

        # Largura final do botão
        w = max(28, content_w + self._padx * 2)
        self.configure(width=w)
        r = min(self._radius, h // 2)

        # --- DESENHO DO FUNDO E SOMBRA ---
        if self._has_pil is None:
            try:
                import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk
                self._has_pil = True
            except Exception:
                self._has_pil = False

        if self._has_pil:
            from PIL import Image, ImageDraw, ImageTk
            bg_app_rgb = self._bg_app_rgb()

            # Cache Key Única
            cache_key = (
                "PillButtonV2", w, h, r,
                str(bg), str(bd), tuple(bg_app_rgb),
                self._variant, bool(hover), bool(self._enabled)
            )

            cached = PillButton._IMG_CACHE.get(cache_key)
            if cached is None:
                ss = 3  # Super-sampling
                shadow_pad = 4  # Espaço extra embaixo para a sombra

                img_w = w * ss
                img_h = (h + shadow_pad) * ss

                # CORREÇÃO 1: Fundo Sólido (Alpha 255) com a cor do APP.
                # Isso elimina o "serrilhado" branco/preto nas bordas arredondadas.
                img = Image.new("RGBA", (img_w, img_h), (bg_app_rgb[0], bg_app_rgb[1], bg_app_rgb[2], 255))
                drw = ImageDraw.Draw(img)
                rr = r * ss

                # Desenha Sombra Suave (Apenas se habilitado e não for estilo 'ghost')
                if self._enabled and self._variant not in ["ghost", "tab_unselected"]:
                    layers = [
                        (1, 15, 0),  # Sombra curta
                        (3, 8, 0),  # Sombra média
                        (5, 4, 1)  # Sombra difusa
                    ]
                    for off_y, alpha, expand in layers:
                        oy = off_y * ss
                        exp = expand * ss
                        drw.rounded_rectangle(
                            [0 - exp, 0 + oy - exp, w * ss - 1 + exp, h * ss - 1 + oy + exp],
                            radius=rr + exp,
                            fill=(0, 0, 0, alpha)
                        )

                # Desenha o Botão (Corpo)
                drw.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=rr, fill=bd, outline=None)
                inset = 1 * ss
                drw.rounded_rectangle([inset, inset, w * ss - 1 - inset, h * ss - 1 - inset], radius=max(1, rr - inset),
                                      fill=bg, outline=None)

                img = img.resize((w, h + shadow_pad), resample=Image.LANCZOS)
                cached = ImageTk.PhotoImage(img)
                PillButton._IMG_CACHE[cache_key] = cached

            self._photo = cached
            self.create_image(0, 0, image=self._photo, anchor="nw")

        else:
            # Fallback (Sem PIL)
            bg_app_rgb = self._bg_app_rgb()
            tk.Canvas.configure(self, bg="#%02x%02x%02x" % bg_app_rgb)
            self.create_rectangle(r, 0, w - r, h, fill=bd, outline="")
            self.create_oval(0, 0, r * 2, h, fill=bd, outline="")
            self.create_oval(w - r * 2, 0, w, h, fill=bd, outline="")
            inset = 1
            self.create_rectangle(r, inset, w - r, h - inset, fill=bg, outline="")
            self.create_oval(inset, inset, r * 2 - inset, h - inset, fill=bg, outline="")
            self.create_oval(w - r * 2 + inset, inset, w - inset, h - inset, fill=bg, outline="")

        # --- CORREÇÃO 2: DESENHO DO TEXTO E ÍCONE (Que tinha sumido) ---
        group_left = (w - content_w) // 2
        x = group_left
        y = h // 2

        if icon_img:
            self.create_image(x, y, image=icon_img, anchor="w")
            x += icon_w + gap

        # Texto
        self.create_text(x, y - 1, text=self._text, font=self._font, fill=fg, anchor="w")

    def _on_click(self, _e=None):
        if self._enabled and callable(self._cmd):
            self.after(1, self._cmd)

    def state(self, states=None):
        if states is None:
            return ("!disabled",) if self._enabled else ("disabled",)
        self._enabled = ("disabled" not in states)
        self._draw(normal=True)

    def configure(self, **kw):
        if "fg" in kw:
            self._explicit_fg = kw.pop("fg")
            self._draw(normal=True)
        if "text" in kw:
            self._text = kw.pop("text")
            self._draw(normal=True)
        if "command" in kw: self._cmd = kw.pop("command")
        if "variant" in kw:
            self._variant = kw.pop("variant")
            self._draw(normal=True)
        if "icon" in kw:
            self._icon = kw.pop("icon")
            self._draw(normal=True)
        if "height" in kw:
            super().configure(height=kw.pop("height"))
            self._draw(normal=True)
        if "bg" in kw:
            new_bg = kw.pop("bg")
            super().configure(bg=new_bg)
            self._bg_app_hex = new_bg
            self._draw(normal=True)
        return super().configure(**kw)

    def grid(self, **kwargs):
        # Padrão: 0 na esquerda, 10 na direita.
        # O setdefault só aplica se você NÃO tiver passado padx manualmente.
        kwargs.setdefault("padx", (0, 10))

        super().grid(**kwargs)

class TabButton(PillButton):
    def __init__(self, parent, text, command=None, **kw):
        height = kw.pop("height", 32)

        # CORREÇÃO 1: Raio fixo de 6px.
        # Antes estava (height // 2), que fazia virar uma bola/pílula completa.
        radius = kw.pop("radius", 6)

        # CORREÇÃO 2: Define explicitamente o fundo "pai" para o anti-aliasing funcionar
        # Isso remove as "pontinhas brancas" nos cantos das abas transparentes.
        kw["bg"] = Colors.BG_SIDEBAR

        super().__init__(
            parent,
            text=text,
            command=command,
            variant="tab_unselected",
            height=height,
            radius=radius,
            **kw
        )

        # CORREÇÃO 3: Cores Exatas conforme seu pedido

        # Estado SELECIONADO: Fundo branco, texto azul, borda branca (funde com o card)
        self._colors["tab_selected"] = {
            "fg": Colors.PRIMARY,
            "bg": "#ffffff",
            "bg_hover": "#ffffff",
            "bd": "#ffffff",
        }

        # Estado NÃO SELECIONADO (Ghost):
        # bg = BG_SIDEBAR (finge transparência)
        # bg_hover = ROW_HOVER_SB (azul claro ao passar o mouse)
        # bd = BG_SIDEBAR (borda invisível)
        self._colors["tab_unselected"] = {
            "fg": "#ffffff",  # Texto branco
            "bg": Colors.BG_SIDEBAR,  # "Transparente" (mesma cor do header)
            "bg_hover": Colors.ROW_HOVER_SB,  # Azul mais claro no hover
            "bd": Colors.BG_SIDEBAR,  # Borda camuflada
        }

class BlueRadioButton(tk.Canvas):
    # Cache global: (size, selected) -> PhotoImage
    _IMG_CACHE = {}
    _HAS_PIL = None

    def __init__(self, parent, text, variable, value, command=None, size=18, bg=None):
        base_bg = bg
        try:
            if base_bg is None:
                base_bg = parent.cget("background")
        except Exception:
            pass
        if not base_bg:
            base_bg = Colors.BG_CARD

        tk.Canvas.__init__(self, parent, bd=0, highlightthickness=0, bg=base_bg)
        self._bg = base_bg
        self._text = text
        self._var = variable
        self._value = value
        self._cmd = command
        self._size = int(size)
        self._font = ("Segoe UI", 10)
        self._font_obj = tkfont.Font(font=self._font)
        self._fg_text = Colors.TEXT_MAIN

        # --- ESTADO INICIAL ---
        self._state = "normal"
        self._fg_disabled = Colors.TEXT_HINT

        self._last_checked = None
        self._img_ref = None

        try:
            self.configure(cursor="hand2")
        except tk.TclError:
            pass

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._on_hover(True))
        self.bind("<Leave>", lambda e: self._on_hover(False))

        self._trace_id = self._var.trace_add("write", self._on_var_changed)

        self._draw()

    # ---------- PIL compartilhado ----------

    @classmethod
    def _pil_available(cls):
        if cls._HAS_PIL is None:
            try:
                import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk
                cls._HAS_PIL = True
            except Exception:
                cls._HAS_PIL = False
        return cls._HAS_PIL

    @classmethod
    def _get_image(cls, size, selected):
        if not cls._pil_available():
            return None

        key = (int(size), bool(selected))
        if key in cls._IMG_CACHE:
            return cls._IMG_CACHE[key]

        from PIL import Image, ImageDraw, ImageTk

        ss = 3
        d = int(size) * ss
        radius = d // 2 - 2 * ss

        img = Image.new("RGBA", (d, d), (255, 255, 255, 0))
        drw = ImageDraw.Draw(img)

        border_box = (198, 205, 221, 255)
        bg_fill = (255, 255, 255, 255)
        dot_color = (26, 99, 182, 255)

        border_w = 1 * ss

        drw.ellipse(
            (d // 2 - radius, d // 2 - radius, d // 2 + radius, d // 2 + radius),
            outline=border_box, width=border_w, fill=bg_fill
        )

        if selected:
            inner_r = max(2 * ss, radius - 3 * ss)
            drw.ellipse(
                (d // 2 - inner_r, d // 2 - inner_r, d // 2 + inner_r, d // 2 + inner_r),
                outline=dot_color, fill=dot_color, width=1 * ss
            )

        img = img.resize((int(size), int(size)), resample=Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        cls._IMG_CACHE[key] = tk_img
        return tk_img

    # ---------- lógica de seleção / desenho ----------

    def _is_checked(self):
        try:
            return str(self._var.get()) == str(self._value)
        except Exception:
            return False

    def _draw(self):
        checked = self._is_checked()
        self._last_checked = checked

        self.delete("all")

        text_w = self._font_obj.measure(self._text or "")
        icon_w = self._size
        pad_icon = 6
        total_w = icon_w + pad_icon + text_w + 6
        total_h = max(self._size + 6, 26)

        self.configure(width=total_w, height=total_h)

        # Define cor e cursor baseado no estado
        if self._state == "disabled":
            curr_fg = self._fg_disabled
            curr_cursor = "arrow"
        else:
            curr_fg = self._fg_text
            curr_cursor = "hand2"

        try:
            self.configure(cursor=curr_cursor)
        except tk.TclError:
            pass

        cy = total_h // 2
        x_icon = 3

        img = self._get_image(self._size, checked)
        if img is not None:
            self._img_ref = img
            # Se estiver desabilitado, poderíamos clarear a imagem, mas manteremos simples
            self.create_image(x_icon, cy, image=img, anchor="w")
        else:
            border_box = Colors.BORDER
            bg_fill = Colors.BG_INPUT
            s = self._size
            self.create_oval(x_icon, cy - s // 2, x_icon + s, cy + s // 2,
                             outline=border_box, width=1, fill=bg_fill)
            if checked:
                cx = x_icon + s // 2
                inner_r = max(2, s // 2 - 3)
                col = Colors.PRIMARY if self._state != "disabled" else Colors.TEXT_HINT
                self.create_oval(cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                                 outline=col, fill=col, width=1)

        self.create_text(
            x_icon + icon_w + pad_icon,
            cy,
            text=self._text,
            anchor="w",
            fill=curr_fg,
            font=self._font
        )

    def _on_click(self, _e=None):
        if self._state == "disabled":
            return
        try:
            self._var.set(self._value)
        except Exception:
            pass
        self._draw()
        if callable(self._cmd):
            self.after(1, self._cmd)

    def _on_hover(self, over):
        pass

    def _on_var_changed(self, *args):
        self._draw()

    # --- MÉTODO NOVO PARA SUPORTAR .state(["disabled"]) ---
    def state(self, states=None):
        if states is None:
            return (self._state,)

        if isinstance(states, str):
            states = (states,)

        if "disabled" in states:
            self._state = "disabled"
        elif "!disabled" in states or "normal" in states:
            self._state = "normal"

        self._draw()

    def destroy(self):
        try:
            if self._trace_id:
                self._var.trace_remove("write", self._trace_id)
        except Exception:
            pass
        super().destroy()

class BlueCheckButton(tk.Canvas):
    # Cache global: (size, checked) -> PhotoImage
    _IMG_CACHE = {}
    _HAS_PIL = None

    def __init__(self, parent, text, variable=None, command=None, size=14, bg=None):
        base_bg = bg
        try:
            if base_bg is None:
                base_bg = parent.cget("background")
        except Exception:
            pass
        if not base_bg:
            base_bg = Colors.BG_CARD

        tk.Canvas.__init__(self, parent, bd=0, highlightthickness=0, bg=base_bg)
        self._bg = base_bg
        self._text = text
        self._var = variable or tk.BooleanVar(value=False)
        self._cmd = command
        self._size = int(size)  # largura base
        self._font = ("Segoe UI", 10)
        self._font_obj = tkfont.Font(font=self._font)

        # Cores de texto
        self._fg_normal = Colors.TEXT_MAIN
        self._fg_disabled = Colors.TEXT_HINT
        self._fg_text = self._fg_normal

        # Estado interno
        self._state = "normal"

        self._last_checked = None
        self._img_ref = None

        try:
            self.configure(cursor="hand2")
        except tk.TclError:
            pass

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._on_hover(True))
        self.bind("<Leave>", lambda e: self._on_hover(False))

        self._trace_id = None
        try:
            self._trace_id = self._var.trace_add("write", self._on_var_changed)
        except Exception:
            pass

        self._draw()

    # ---------- PIL compartilhado entre todos os checks ----------

    @classmethod
    def _pil_available(cls):
        if cls._HAS_PIL is None:
            try:
                import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk  # type: ignore
                cls._HAS_PIL = True
            except Exception:
                cls._HAS_PIL = False
        return cls._HAS_PIL

    @classmethod
    def _get_image(cls, size, checked):
        if not cls._pil_available():
            return None

        from PIL import Image, ImageDraw, ImageTk  # type: ignore

        key = (int(size), bool(checked))
        if key in cls._IMG_CACHE:
            return cls._IMG_CACHE[key]

        ss = 3
        w = int(size) * ss
        h = int(size) * ss
        radius = max(3 * ss, min(w, h) // 4)

        img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        drw = ImageDraw.Draw(img)

        # contorno cinza novo
        border_box = (198, 205, 221, 255)  # #C6CDDD
        bg_fill = (255, 255, 255, 255)

        # usa o mesmo azul PRIMARY do radiobutton
        r = int(Colors.PRIMARY[1:3], 16)
        g = int(Colors.PRIMARY[3:5], 16)
        b = int(Colors.PRIMARY[5:7], 16)
        tick_color = (r, g, b, 255)

        border_w = 1 * ss
        drw.rounded_rectangle(
            (0, 0, w - 1, h - 1),
            radius=radius,
            outline=border_box,
            width=border_w,
            fill=bg_fill
        )

        if checked:
            lw = 1 * ss
            x1, y1 = int(0.22 * w), int(0.55 * h)
            x2, y2 = int(0.42 * w), int(0.78 * h)
            x3, y3 = int(0.80 * w), int(0.30 * h)
            drw.line((x1, y1, x2, y2), fill=tick_color, width=lw, joint="round")
            drw.line((x2, y2, x3, y3), fill=tick_color, width=lw, joint="round")

        final_w = int(size)
        final_h = int(size)
        img = img.resize((final_w, final_h), resample=Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        cls._IMG_CACHE[key] = tk_img
        return tk_img

    # ---------- desenho / estados ----------

    def _is_checked(self):
        try:
            v = self._var.get()
        except Exception:
            return False
        return bool(v)

    def _draw(self):
        checked = self._is_checked()

        # Forçamos o redesenho se o estado mudou (para aplicar cor cinza) ou o valor mudou
        # A verificação "checked == self._last_checked" foi removida/adaptada para garantir atualização visual do estado
        self._last_checked = checked

        self.delete("all")

        text_w = self._font_obj.measure(self._text or "")
        icon_w = self._size
        icon_h = self._size
        pad_icon = 6
        total_w = icon_w + pad_icon + text_w + 6
        total_h = max(icon_h + 6, 26)

        self.configure(width=total_w, height=total_h)

        # Define cor do texto e cursor baseado no estado
        if self._state == "disabled":
            current_fg = self._fg_disabled
            cursor = "arrow"
        else:
            current_fg = self._fg_normal
            cursor = "hand2"

        try:
            self.configure(cursor=cursor)
        except tk.TclError:
            pass

        cy = total_h // 2
        x_icon = 3

        img = self._get_image(self._size, checked)

        # Se estiver desabilitado, desenha o checkbox levemente transparente ou apenas confia no texto cinza
        # Para manter simples e elegante, mantemos o ícone igual (ou poderíamos criar versão cinza),
        # mas o texto cinza já indica inatividade.

        if img is not None:
            self._img_ref = img
            # Se quiser deixar o icone "apagado" quando disabled, pode usar um tag e stipple, mas Tkinter canvas é limitado nisso.
            self.create_image(x_icon, cy, image=img, anchor="w")
        else:
            border_box = Colors.BORDER_LIGHT if self._state == "disabled" else Colors.BORDER
            bg_fill = Colors.BG_INPUT
            s_w = icon_w
            s_h = icon_h
            self.create_rectangle(
                x_icon, cy - s_h // 2,
                        x_icon + s_w, cy + s_h // 2,
                outline=border_box, fill=bg_fill, width=1
            )
            if checked:
                check_fill = Colors.TEXT_HINT if self._state == "disabled" else Colors.PRIMARY
                x1, y1 = x_icon + int(0.22 * s_w), cy
                x2, y2 = x_icon + int(0.42 * s_w), cy + int(0.25 * s_h)
                x3, y3 = x_icon + int(0.80 * s_w), cy - int(0.25 * s_h)
                self.create_line(x1, y1, x2, y2, x3, y3, fill=check_fill, width=1)

        self.create_text(
            x_icon + icon_w + pad_icon,
            cy,
            text=self._text,
            anchor="w",
            fill=current_fg,  # Usa a cor correta (normal ou disabled)
            font=self._font
        )

    def _on_click(self, _e=None):
        # Bloqueia clique se estiver disabled
        if self._state == "disabled":
            return

        try:
            self._var.set(not self._is_checked())
        except Exception:
            pass
        self._draw()
        if callable(self._cmd):
            self.after(1, self._cmd)

    def _on_hover(self, over):
        pass

    def _on_var_changed(self, *args):
        self._draw()

    def state(self, states=None):
        """Permite controlar o estado (normal/disabled) via código, similar ao ttk."""
        if states is None:
            return (self._state,)

        # Aceita formato string única ou tupla/lista
        if isinstance(states, str):
            states = (states,)

        if "disabled" in states:
            self._state = "disabled"
        elif "!disabled" in states or "normal" in states:
            self._state = "normal"

        self._draw()

    def destroy(self):
        try:
            if self._trace_id:
                self._var.trace_remove("write", self._trace_id)
        except Exception:
            pass
        super().destroy()


class SplitButton(PillButton):
    # Cache separado para não colidir com o PillButton
    _IMG_CACHE_SPLIT = {}

    def __init__(self, parent, text, command=None, options=None, variant="primary", height=34, width=None, icon=None,
                 radius=None, **kw):
        self._font_obj = tkfont.Font(family="Segoe UI", size=10, weight="bold" if variant == "primary" else "normal")
        self._split_width = 30
        self._menu_options = options or []

        # Estado interno
        self._is_menu_open = False
        self._hover_main = False
        self._hover_split = False
        self._split_x = 0
        self._last_w = 0

        if width is None:
            txt_w = self._font_obj.measure(text)
            icon_w = 26 if icon else 0

            # Padding generoso: 16px Esq + 10px Meio + 16px Dir (na área principal)
            padding_main = 50

            # Largura = Texto + Ícone + Padding Principal + Área da Seta
            calc_w = txt_w + icon_w + padding_main + self._split_width
            width = calc_w

        # 2. Formato: Padrão 6px
        if radius is None:
            radius = 6

            # Inicializa usando a classe mãe PillButton
        super().__init__(parent, text, command=command, variant=variant, height=height, width=width, icon=icon,
                         radius=radius, **kw)

        # Override dos binds
        self.bind("<Motion>", self._on_motion_split)
        self.bind("<Leave>", self._on_leave_split)
        self.bind("<Button-1>", self._on_click_split)

        # 3. CORREÇÃO DA DUPLICAÇÃO: Monitora redimensionamento
        self.bind("<Configure>", self._on_resize_split)

    def _on_resize_split(self, event):
        # Se a largura mudou (ex: ao nascer no modal), redesenha para ajustar o split e fundo
        if event.width > 1 and event.width != self._last_w:
            self._last_w = event.width
            self._draw()

    def _on_motion_split(self, event):
        if not self._enabled: return

        x = event.x
        w = self.winfo_width()
        self._split_x = w - self._split_width

        prev_main = self._hover_main
        prev_split = self._hover_split

        if x < self._split_x:
            self._hover_main = True
            self._hover_split = False
        else:
            self._hover_main = False
            self._hover_split = True

        if prev_main != self._hover_main or prev_split != self._hover_split:
            self._draw()

    def _on_leave_split(self, event):
        self._hover_main = False
        self._hover_split = False
        self._draw()

    def _on_click_split(self, event):
        if not self._enabled: return

        if self._hover_split:
            if self._is_menu_open:
                self._close_menu()
            else:
                self._open_menu()
        else:
            if callable(self._cmd):
                self.after(1, self._cmd)

    def _draw(self, normal=False, hover=False):
        self.delete("all")

        wtxt = tkfont.Font(font=self._font).measure(self._text or "")
        icon_w = self._icon.width() if self._icon else 0
        gap = 8 if (self._icon and self._text) else 0

        # Largura = Conteúdo + Padding de Segurança (30px) + Área da Seta
        w = wtxt + icon_w + gap + 12 + self._split_width

        # Força a largura calculada
        self.configure(width=w)

        h = int(self["height"])
        self._split_x = w - self._split_width
        r = self._radius

        pal = self._palette()
        bg_base = pal["bg"]
        bg_hover = pal["bg_hover"]
        bd = pal["bd"]
        fg = pal["fg"]

        # --- DESENHO DO FUNDO (PIL ou Canvas) ---
        if self._has_pil:
            from PIL import Image, ImageDraw, ImageTk
            bg_app_rgb = self._bg_app_rgb()

            cache_key = (
                "SplitBtnV3", w, h, r,
                str(bg_base), str(bg_hover), str(bd), tuple(bg_app_rgb),
                self._variant, self._hover_main, self._hover_split, self._is_menu_open, self._enabled
            )

            cached = SplitButton._IMG_CACHE_SPLIT.get(cache_key)
            if cached is None:
                ss = 3
                shadow_pad = 4
                img_w = w * ss
                img_h = (h + shadow_pad) * ss

                img = Image.new("RGBA", (img_w, img_h), (bg_app_rgb[0], bg_app_rgb[1], bg_app_rgb[2], 255))
                drw = ImageDraw.Draw(img)
                rr = r * ss

                # Sombra
                if self._enabled and self._variant != "ghost":
                    layers = [(1, 15, 0), (3, 8, 0), (5, 4, 1)]
                    for off_y, alpha, expand in layers:
                        oy = off_y * ss
                        exp = expand * ss
                        drw.rounded_rectangle(
                            [0 - exp, 0 + oy - exp, w * ss - 1 + exp, h * ss - 1 + oy + exp],
                            radius=rr + exp,
                            fill=(0, 0, 0, alpha)
                        )

                # Base Principal
                drw.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=rr, fill=bd, outline=None)
                inset = 1 * ss
                drw.rounded_rectangle([inset, inset, w * ss - 1 - inset, h * ss - 1 - inset], radius=max(1, rr - inset),
                                      fill=bg_base, outline=None)

                # Hover Dividido (Recorte)
                if self._hover_main or self._hover_split or self._is_menu_open:
                    img_hover = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
                    drw_h = ImageDraw.Draw(img_hover)

                    drw_h.rounded_rectangle([inset, inset, w * ss - 1 - inset, h * ss - 1 - inset],
                                            radius=max(1, rr - inset), fill=bg_hover, outline=None)

                    split_px = self._split_x * ss

                    if self._hover_main:
                        crop = img_hover.crop((0, 0, split_px, img_h))
                        img.paste(crop, (0, 0), crop)

                    elif self._hover_split or self._is_menu_open:
                        crop = img_hover.crop((split_px, 0, img_w, img_h))
                        img.paste(crop, (split_px, 0), crop)

                # Linha Divisória
                line_x = self._split_x * ss
                div_color = bd
                if self._variant == "primary": div_color = "#60A5FA"

                drw.line([(line_x, 0), (line_x, h * ss)], fill=div_color, width=1 * ss)

                img = img.resize((w, h + shadow_pad), resample=Image.LANCZOS)
                cached = ImageTk.PhotoImage(img)
                SplitButton._IMG_CACHE_SPLIT[cache_key] = cached

            self._photo = cached
            self.create_image(0, 0, image=self._photo, anchor="nw")

        else:
            # Fallback sem PIL
            super()._draw(normal, hover)
            self.create_line(self._split_x, 0, self._split_x, h, fill=bd)

        # --- CONTEÚDO (Centralizado na Área Principal) ---
        main_w = self._split_x

        wtxt = tkfont.Font(font=self._font).measure(self._text or "")

        icon_img = self._icon
        if icon_img and self._explicit_fg:
            icon_img = _tint_icon(icon_img, self._explicit_fg)

        icon_w = icon_img.width() if icon_img else 0
        gap = 8 if (icon_img and self._text) else 0

        # Largura total do conteúdo (Texto + Icone + Gap)
        content_w = icon_w + gap + wtxt

        # Centraliza na área principal
        x = (main_w - content_w) // 2

        if x < 12: x = 12

        y = h // 2

        if icon_img:
            self.create_image(x, y, image=icon_img, anchor="w")
            x += icon_w + gap

        self.create_text(x, y - 1, text=self._text, font=self._font, fill=fg, anchor="w")

        # Seta (Centralizada na Área Split)
        arrow_x = self._split_x + (self._split_width // 2)
        self.create_polygon(arrow_x - 4, y - 1, arrow_x + 4, y - 1, arrow_x, y + 3, fill=fg)

    def _open_menu(self):
        if not self._menu_options: return
        self._is_menu_open = True
        self._draw()

        top = self.winfo_toplevel()
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        h = self.winfo_height()
        btn_w = self.winfo_width()

        # Calcula largura necessária para o menu não cortar textos
        max_txt_w = 0
        menu_font = tkfont.Font(family="Segoe UI", size=9)
        for txt, _ in self._menu_options:
            w_opt = menu_font.measure(txt)
            if w_opt > max_txt_w: max_txt_w = w_opt

        menu_w = max(btn_w, max_txt_w + 30)

        row_h = 32
        menu_h = len(self._menu_options) * row_h + 4

        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()

        # Posicionamento Y (Cima ou Baixo)
        space_below = screen_h - (root_y + h)
        if space_below < menu_h + 50:
            pos_y = root_y - menu_h - 2
        else:
            pos_y = root_y + h + 2

        # Posicionamento X (Esquerda ou Direita)
        pos_x = root_x
        if pos_x + menu_w > screen_w:
            pos_x = (root_x + btn_w) - menu_w

        self._menu_win = tk.Toplevel(self)
        self._menu_win.wm_overrideredirect(True)
        self._menu_win.configure(bg=Colors.BG_CARD, bd=1, relief="solid")
        self._menu_win.geometry(f"{menu_w}x{menu_h}+{pos_x}+{pos_y}")

        container = tk.Frame(self._menu_win, bg=Colors.BG_CARD)
        container.pack(fill="both", expand=True)

        for text, cmd in self._menu_options:
            btn = tk.Button(container, text=text, font=("Segoe UI", 9),
                            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, bd=0,
                            activebackground=Colors.ROW_SELECTED,
                            activeforeground=Colors.TEXT_MAIN,
                            anchor="w", padx=10, command=lambda c=cmd: self._exec_menu_cmd(c))

            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=Colors.ROW_SELECTED))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=Colors.BG_CARD))

            btn.pack(fill="x", ipady=4)

        self._bind_close = top.bind("<Button-1>", self._check_close, add="+")

    def _exec_menu_cmd(self, cmd):
        self._close_menu()
        if cmd: self.after(50, cmd)

    def _close_menu(self):
        if hasattr(self, "_menu_win"):
            self._menu_win.destroy()
            del self._menu_win

        if hasattr(self, "_bind_close"):
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._bind_close)
            except:
                pass

        self._is_menu_open = False
        self._draw()

    def _check_close(self, event):
        try:
            w = event.widget
            if hasattr(self, "_menu_win") and self._menu_win.winfo_exists():
                if str(w).startswith(str(self._menu_win)): return
                if w == self: return
        except:
            pass
        self._close_menu()


class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, variable=None, command=None,
                 width=35, height=21,  # Dimensões padrão das Políticas Globais
                 on_color=Colors.SUCCESS,  # Verde Teal (Ativo)
                 off_color=Colors.BORDER_LIGHT,  # Cinza Claro (Inativo) - Antes era #D1D5DB
                 **kw):

        # Tenta resolver a cor de fundo do pai automaticamente
        base_bg = kw.pop("bg", None)
        if base_bg is None:
            base_bg = Utils.resolve_parent_bg(parent)

        self._width = int(width)
        self._height = int(height)

        kw.setdefault("width", self._width)
        kw.setdefault("height", self._height)
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bg", base_bg)

        tk.Canvas.__init__(self, parent, **kw)

        self._bg_app_hex = base_bg
        self._on_color = on_color
        self._off_color = off_color
        self._knob_color = "#ffffff"

        self._var = variable if variable is not None else tk.BooleanVar(value=False)
        self._command = command
        self._state = "normal"
        self._img_ref = None
        self._trace_id = None

        try:
            self._trace_id = self._var.trace_add("write", self._on_var_changed)
        except Exception:
            pass

        try:
            self.configure(cursor="hand2")
        except tk.TclError:
            pass

        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _bg_app_rgb(self):
        hx = self._bg_app_hex
        if not (isinstance(hx, str) and hx.startswith("#") and len(hx) == 7):
            hx = Colors.BG_APP
        hx = hx.lstrip("#")
        return Utils.hex_to_rgb(hx)

    def _draw(self):
        if not self.winfo_exists():
            return

        self.delete("all")

        try:
            w = int(self["width"])
            h = int(self["height"])
        except Exception:
            w = self._width
            h = self._height

        on = bool(self._var.get())
        is_disabled = (self._state == "disabled")

        if is_disabled:
            track_color = "#D1D5DB" if on else Colors.BORDER_LIGHT
            knob_color = "#F9FAFB"
            border_color = None
        else:
            track_color = self._on_color if on else self._off_color
            knob_color = self._knob_color
            # Borda: Verde mais escuro se ligado, Cinza se desligado
            border_color = "#009087" if on else "#D1D5DB"

        if _pil_ok():
            from PIL import Image, ImageDraw, ImageTk

            ss = 3
            bg_r, bg_g, bg_b = self._bg_app_rgb()
            img = Image.new("RGBA", (w * ss, h * ss), (bg_r, bg_g, bg_b, 255))
            drw = ImageDraw.Draw(img)

            radius = (h * ss) // 2

            # Desenha o corpo (track)
            drw.rounded_rectangle(
                [0, 0, w * ss - 1, h * ss - 1],
                radius=radius,
                fill=track_color,
                outline=border_color,
                width=1 * ss
            )

            ring = 2 * ss
            knob_radius = max(1, radius - ring)

            cx = radius if not on else w * ss - radius
            cy = (h * ss) // 2

            # Desenha o botão (knob)
            drw.ellipse(
                [cx - knob_radius, cy - knob_radius,
                 cx + knob_radius, cy + knob_radius],
                fill=knob_color,
                outline=border_color,
                width=1 * ss
            )

            img = img.resize((w, h), Image.LANCZOS)
            self._img_ref = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._img_ref, anchor="nw")
        else:
            # Fallback sem PIL
            radius = h // 2
            tk.Canvas.configure(self, bg=self._bg_app_hex)

            self.create_rectangle(radius, 0, w - radius, h,
                                  fill=track_color, outline=border_color)
            self.create_oval(0, 0, 2 * radius, h,
                             fill=track_color, outline=border_color)
            self.create_oval(w - 2 * radius, 0, w, h,
                             fill=track_color, outline=border_color)

            ring = 2
            knob_r = max(1, radius - ring)
            cx = radius if not on else w - radius
            cy = h // 2

            self.create_oval(cx - knob_r, cy - knob_r,
                             cx + knob_r, cy + knob_r,
                             fill=knob_color, outline=border_color)

    def _on_click(self, _e=None):
        if self._state == "disabled":
            return
        try:
            cur = bool(self._var.get())
        except Exception:
            cur = False
        self._var.set(not cur)
        self._draw()
        if callable(self._command):
            self.after(1, self._command)

    def _on_var_changed(self, *args):
        self._draw()

    def state(self, states=None):
        if states is None:
            return ("disabled",) if self._state == "disabled" else ("!disabled",)
        if isinstance(states, str):
            states = (states,)
        self._state = "disabled" if "disabled" in states else "normal"
        self._draw()

    def configure(self, **kw):
        if "state" in kw:
            st = kw.pop("state")
            if isinstance(st, str):
                self._state = "disabled" if st == "disabled" else "normal"
            else:
                self._state = "disabled" if "disabled" in st else "normal"

        if "command" in kw:
            self._command = kw.pop("command")
        if "on_color" in kw:
            self._on_color = kw.pop("on_color")
        if "off_color" in kw:
            self._off_color = kw.pop("off_color")
        if "bg" in kw:
            self._bg_app_hex = kw["bg"]

        res = tk.Canvas.configure(self, **kw)
        self._draw()
        return res

    config = configure

    def destroy(self):
        try:
            if self._trace_id:
                self._var.trace_remove("write", self._trace_id)
        except Exception:
            pass
        tk.Canvas.destroy(self)


class PillEntry(tk.Canvas):
    def __init__(self, parent, placeholder="Buscar", height=34, width=220, radius=None):
        tk.Canvas.__init__(self, parent, height=height, width=width, bd=0, highlightthickness=0, bg=Colors.BG_APP)
        self._ch = int(height)
        self._cw = int(width)
        self._r = (radius if radius is not None else 6)
        self._padx = 14
        self._placeholder = placeholder
        self._placeholder_on = True
        self._has_pil = None
        self._photo = None
        self._bg_tag = "pill_bg"

        # Cores
        self._fg_text = Colors.TEXT_MAIN
        self._fg_hint = Colors.TEXT_HINT
        self._caret_active = Colors.TEXT_MAIN
        self._caret_hint = self._fg_hint

        # ESTADO INICIAL: Habilitado = Branco
        self._fill = Colors.BG_INPUT

        self._bd_normal = Colors.BORDER
        self._bd_hover = Colors.BORDER
        self._bd_focus = Colors.BORDER_FOCUS
        self._state = "normal"

        self._var = tk.StringVar()

        # ENTRY INTERNO
        self._entry = tk.Entry(
            self,
            textvariable=self._var,
            bd=0,
            relief="flat",
            highlightthickness=0,
            highlightbackground=Colors.BORDER,
            highlightcolor=Colors.PRIMARY,
            bg=self._fill,  # Inicia Branco
            fg=self._fg_hint,
            font=("Segoe UI", 10),
            insertwidth=1,
            insertbackground=self._caret_hint,
            # Configurações para estado Disabled
            disabledbackground=Colors.BG_DISABLED,
            readonlybackground=Colors.BG_DISABLED,
            disabledforeground=Colors.TEXT_HINT
        )

        self._win = self.create_window(
            self._padx,
            self._ch // 2,
            window=self._entry,
            anchor="w",
            height=self._ch - 10,
            width=self._cw - (self._padx * 2)
        )

        self._setup_events()
        self._show_placeholder()
        self._draw()

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        if event.width < 10 or event.width == self._cw:
            return
        self._cw = event.width
        new_entry_w = max(10, self._cw - (self._padx * 2))
        self.itemconfigure(self._win, width=new_entry_w)
        self._draw()

    def _setup_events(self):
        # Correção: Usamos e=None para evitar o erro "missing argument"
        # e usamos self.bind direto ao invés de tk.Canvas.bind(self)
        self.bind("<Enter>", lambda e=None: self._set_state("hover"))

        self.bind("<Leave>",
                  lambda e=None: self._set_state("focus" if self._entry.focus_get() is self._entry else "normal"))

        self.bind("<Button-1>", lambda e=None: (
            self._entry.focus_set(),
            self._entry.icursor(0 if self._placeholder_on else "end"),
            self._set_state("focus")
        ))

        self._entry.bind("<FocusIn>", lambda e=None: self._on_focus_in())
        self._entry.bind("<FocusOut>", lambda e=None: self._on_focus_out())

        # O restante continua igual, apenas adicione o add="+" por segurança
        self._entry.bind("<KeyPress>", self._on_keypress, add="+")
        self._entry.bind("<KeyRelease>", self._on_keyrelease, add="+")

        # Eventos de mouse padrão do Entry
        self._entry.bind("<Button-1>", self._on_entry_click, add="+")
        self._entry.bind("<B1-Motion>", self._on_entry_drag, add="+")
        self._entry.bind("<Double-1>", self._on_entry_click, add="+")
        self._entry.bind("<Triple-1>", self._on_entry_click, add="+")
        self._entry.bind("<Control-a>", self._on_ctrl_a, add="+")
        self._entry.bind("<Control-A>", self._on_ctrl_a, add="+")
        self._entry.bind("<Control-c>", self._on_ctrl_c, add="+")
        self._entry.bind("<Control-C>", self._on_ctrl_c, add="+")
        self._entry.bind("<Control-x>", self._on_ctrl_x, add="+")
        self._entry.bind("<Control-X>", self._on_ctrl_x, add="+")

        self.after(10, lambda: self.winfo_toplevel().bind("<Button-1>", self._on_global_click, add="+"))

    def _on_entry_click(self, e):
        if self._placeholder_on:
            try:
                self._entry.focus_set()
                self._entry.icursor(0)
            except tk.TclError:
                pass
            return "break"

    def _on_entry_drag(self, e):
        if self._placeholder_on: return "break"

    def _on_ctrl_a(self, e):
        if self._placeholder_on: return "break"

    def _on_ctrl_c(self, e):
        if self._placeholder_on: return "break"

    def _on_ctrl_x(self, e):
        if self._placeholder_on: return "break"

    def _on_global_click(self, e):
        try:
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            x1, y1 = x0 + self._cw, y0 + self._ch
        except tk.TclError:
            return
        inside = (x0 <= e.x_root <= x1) and (y0 <= e.y_root <= y1)
        try:
            focused = self._entry.focus_get()
        except Exception:
            focused = None
        if not inside and (focused is self._entry):
            try:
                if hasattr(e, "widget") and e.widget not in (None, self):
                    e.widget.focus_set()
            except Exception:
                pass
            self._on_focus_out()

    def _on_keypress(self, ev):
        # --- NOVA LÓGICA: Corrigir sobrescrita de seleção ---
        # Se não é placeholder e tem texto selecionado (azul)
        if not self._placeholder_on and self._entry.selection_present():
            # Se for Backspace ou Delete, apaga a seleção e para (return "break")
            if ev.keysym in ("BackSpace", "Delete"):
                try:
                    self._entry.delete("sel.first", "sel.last")
                    return "break"
                except tk.TclError:
                    pass
            # Se for caractere digitável, apaga a seleção e DEIXA passar (para digitar a letra)
            elif len(ev.char) == 1 and ev.char >= " " and not (ev.state & 0x4):  # 0x4 é Control
                try:
                    self._entry.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass

        # --- LÓGICA ORIGINAL DO PLACEHOLDER ---
        if not self._placeholder_on: return

        if (ev.state & 0x4) and ev.keysym.lower() == "v":
            self._clear_placeholder()
            return
        if ev.keysym in ("BackSpace", "Delete", "Left", "Right", "Home", "End"): return "break"
        if ev.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Escape", "Tab"): return

        if len(ev.char) == 1 and ev.char >= " ":
            self._clear_placeholder()
            self._entry.insert("end", ev.char)
            return "break"

    def _on_keyrelease(self, _ev):
        if self._placeholder_on:
            try:
                self._entry.config(fg=self._fg_hint, insertbackground=self._caret_hint)
            except tk.TclError:
                pass
            if not self._entry.get():
                self._show_placeholder()
            return
        if not self._entry.get():
            self._show_placeholder()
        else:
            try:
                self._entry.config(insertbackground=self._caret_active, fg=self._fg_text)
            except tk.TclError:
                pass

    def _set_state(self, s):
        if s == "focus" and str(self._entry["state"]) == "disabled":
            return
        self._state = s
        self._draw()

    def _on_focus_in(self):
        self._entry.config(insertbackground=self._caret_hint if self._placeholder_on else self._caret_active)
        self._set_state("focus")

    def _on_focus_out(self):
        if not self._entry.get().strip() or self._placeholder_on:
            self._show_placeholder()
        self._set_state("normal")

    def _show_placeholder(self):
        try:
            self._entry.delete(0, "end")
        except tk.TclError:
            pass
        self._placeholder_on = True
        self._entry.config(fg=self._fg_hint, insertbackground=self._caret_hint)
        self._entry.insert(0, self._placeholder)
        try:
            self._entry.icursor(0)
        except tk.TclError:
            pass

    def _clear_placeholder(self):
        try:
            self._entry.delete(0, "end")
        except tk.TclError:
            pass
        self._placeholder_on = False
        self._entry.config(fg=self._fg_text, insertbackground=self._caret_active)

    def _draw(self):
        tk.Canvas.delete(self, self._bg_tag)
        if self._has_pil is None:
            try:
                import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk
                self._has_pil = True
            except Exception:
                self._has_pil = False

        bd = self._bd_normal
        if self._state == "hover": bd = self._bd_hover
        if self._state == "focus": bd = self._bd_focus

        if self._has_pil:
            from PIL import Image, ImageDraw, ImageTk
            ss = 3
            bg_app = Utils.hex_to_rgb(self["bg"])
            img = Image.new("RGBA", (self._cw * ss, self._ch * ss), (bg_app[0], bg_app[1], bg_app[2], 255))
            drw = ImageDraw.Draw(img)
            rr = self._r * ss
            bw = max(1, 1 * ss)
            drw.rounded_rectangle([0, 0, self._cw * ss - 1, self._ch * ss - 1], radius=rr, fill=bd)
            drw.rounded_rectangle([bw, bw, self._cw * ss - 1 - bw, self._ch * ss - 1 - bw], radius=max(1, rr - bw),
                                  fill=self._fill)
            img = img.resize((self._cw, self._ch), resample=Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._photo, anchor="nw", tags=(self._bg_tag,))
        else:
            r = self._r
            self.create_rectangle(r, 0, self._cw - r, self._ch, fill=bd, outline="", tags=(self._bg_tag,))
            self.create_oval(0, 0, r * 2, self._ch, fill=bd, outline="", tags=(self._bg_tag,))
            self.create_oval(self._cw - r * 2, 0, self._cw, self._ch, fill=bd, outline="", tags=(self._bg_tag,))
            inset = 1
            self.create_rectangle(r, inset, self._cw - r, self._ch - inset, fill=self._fill, outline="",
                                  tags=(self._bg_tag,))
            self.create_oval(inset, inset, r * 2 - inset, self._ch - inset, fill=self._fill, outline="",
                             tags=(self._bg_tag,))
            self.create_oval(self._cw - r * 2 + inset, inset, self._cw - inset, self._ch - inset, fill=self._fill,
                             outline="", tags=(self._bg_tag,))

        try:
            self.tag_lower(self._bg_tag, self._win)
        except tk.TclError:
            pass
        self.coords(self._win, self._padx, self._ch // 2)
        self.itemconfigure(self._win, width=self._cw - (self._padx * 2), height=self._ch - 10)

    def focus_set(self):
        return self._entry.focus_set()

    def get(self):
        return "" if self._placeholder_on else self._entry.get()

    def delete(self, *args):
        if len(args) == 1 and args[0] == "all": return tk.Canvas.delete(self, *args)
        try:
            self._entry.delete(0, "end")
        except tk.TclError:
            pass
        self._placeholder_on = False
        self._on_keyrelease(None)

    def insert(self, index, text):
        if not str(text) and self._placeholder_on:
            return

        if self._placeholder_on: self._clear_placeholder()
        self._entry.insert(index, text)

    def bind(self, seq=None, func=None, add=None):
        if seq == "<Configure>":
            return super().bind(seq, func, add)
        return self._entry.bind(seq, func, add)

    def configure(self, **kw):
        # --- FIX: Intercepta 'fg' e 'foreground' para aplicar no Entry interno ---
        # O Canvas (pai) não aceita 'fg', então aplicamos manualmente no self._entry
        if "fg" in kw:
            new_fg = kw.pop("fg")
            self._fg_text = new_fg  # Atualiza a cor padrão do texto
            # Só aplica visualmente se NÃO estiver mostrando o placeholder (para não sumir com o cinza do hint)
            if not self._placeholder_on:
                self._entry.configure(fg=new_fg)

        if "foreground" in kw:
            new_fg = kw.pop("foreground")
            self._fg_text = new_fg
            if not self._placeholder_on:
                self._entry.configure(fg=new_fg)
        # -------------------------------------------------------------------------

        # Se o comando mudar o estado (state), atualizamos a cor de fundo (_fill) e redesenhamos
        if "state" in kw:
            st = kw.pop("state")
            self._entry.configure(state=st)

            # Troca a cor do fundo arredondado
            self._fill = Colors.BG_DISABLED if st == "disabled" else Colors.BG_INPUT

            # Atualiza o fundo do canvas (recursivamente, mas sem o 'state' no kw, então passa direto pro Canvas na próxima)
            self.configure(bg=Colors.BG_DISABLED if st == "disabled" else Colors.BG_APP)

            # Força o redesenho imediato
            self._draw()

        if "width" in kw:
            self._cw = int(kw.pop("width") or self._cw)
            tk.Canvas.configure(self, width=self._cw)
            self._draw()

        return tk.Canvas.configure(self, **kw)

    def grid(self, **kwargs):
        # Padrão: 0 esq, 10 dir
        kwargs.setdefault("padx", (0, 10))

        # Padrão: Esticar horizontalmente
        kwargs.setdefault("sticky", "ew")

        super().grid(**kwargs)

TextField = PillEntry


class PillCombobox(tk.Canvas):
    def __init__(self, parent, values=None, placeholder="Selecione", height=34, width=200, justify="left", variable=None):
        tk.Canvas.__init__(self, parent, height=height, width=width, bd=0, highlightthickness=0, bg=Colors.BG_APP)

        # Dados
        self._values_full = values or []

        # Configurações Visuais
        self._ch = int(height)
        self._cw = int(width)
        self._radius = 6
        self._padx = 12

        self._bg_app = Colors.BG_APP
        self._bd_normal = Colors.BORDER
        self._bd_color = Colors.BORDER
        self._bd_focus = Colors.BORDER_FOCUS
        self._arrow_color = "#6B7280"
        self._arrow_focus = Colors.PRIMARY

        self._fill = Colors.BG_INPUT

        # Cores de Texto
        self._text_color_normal = Colors.TEXT_MAIN
        self._text_color_placeholder = Colors.TEXT_HINT  # Cinza claro

        # Estado
        self._is_open = False
        self._placeholder_text = placeholder
        self._is_placeholder_on = True

        self._dropdown_frame = None
        self._listbox = None
        self._var = variable if variable is not None else tk.StringVar()

        # Configuração do Entry
        self._entry = tk.Entry(
            self,
            textvariable=self._var,
            font=("Segoe UI", 10),
            justify=justify,
            bd=0,
            highlightthickness=0,
            insertwidth=1,
            # Cores Habilitado
            bg=self._fill,
            fg=self._text_color_placeholder,
            # Cores Desabilitado (AQUI ESTAVA O PROBLEMA DO BEGE)
            disabledbackground=Colors.BG_DISABLED,
            disabledforeground=Colors.TEXT_HINT
        )

        # Posicionamento
        inner_h = self._ch - 10
        self._win = self.create_window(
            self._padx,
            self._ch // 2,
            window=self._entry,
            anchor="w",
            width=self._cw - 35,
            height=inner_h
        )

        # --- BINDINGS ---
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out_validate)

        # Digitação
        self._entry.bind("<KeyPress>", self._on_key_press)
        self._entry.bind("<KeyRelease>", self._on_key_release)

        # Navegação via teclado
        self._entry.bind("<Down>", self._on_arrow_down)
        self._entry.bind("<Up>", self._on_arrow_up)
        self._entry.bind("<Return>", self._on_return_key)

        # --- BLOQUEIOS VISUAIS COMPLETOS ---
        self._entry.bind("<Button-1>", self._on_entry_click_down)
        self._entry.bind("<B1-Motion>", self._block_placeholder_interaction)
        self._entry.bind("<Double-Button-1>", self._block_placeholder_interaction)
        self._entry.bind("<Control-a>", self._block_placeholder_interaction)
        self._entry.bind("<Control-A>", self._block_placeholder_interaction)

        # Abertura do Dropdown
        self._entry.bind("<ButtonRelease-1>", self._on_entry_click_release)
        self.bind("<Button-1>", self._on_canvas_click)

        # Redimensionamento e Limpeza
        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", lambda e: self._close_dropdown())
        self.bind("<Unmap>", lambda e: self._close_dropdown())
        # Clique global para desfocar ao clicar fora da combobox
        self.after(10, lambda: self.winfo_toplevel().bind("<Button-1>", self._on_global_click, add="+"))

        self._check_pil()

        # Inicializa
        self._show_placeholder()
        self._draw(focus=False)

    # --- LÓGICA DE PLACEHOLDER ---
    def _show_placeholder(self):
        self._is_placeholder_on = True
        self._var.set(self._placeholder_text)
        self._entry.configure(fg=self._text_color_placeholder)
        try:
            self._entry.icursor(0)
        except:
            pass

    def _clear_placeholder(self):
        if self._is_placeholder_on:
            self._is_placeholder_on = False
            self._var.set("")
            self._entry.configure(fg=self._text_color_normal)

    # --- BLOQUEIOS VISUAIS ---
    def _block_placeholder_interaction(self, event):
        # Se for placeholder, bloqueia qualquer interação nativa
        if self._is_placeholder_on:
            return "break"

    def _on_entry_click_down(self, event):
        # --- CORREÇÃO AQUI ---
        # Se for placeholder, precisamos forçar o foco manualmente,
        # pois o "return break" impede o Tkinter de dar o foco nativamente.
        if self._is_placeholder_on:
            self._entry.focus_set()
            return "break"

    def _on_entry_click_release(self, event):
        # --- CORREÇÃO: Se estiver desabilitado, não faz nada ---
        if str(self._entry["state"]) == "disabled":
            return
        # -------------------------------------------------------

        if self._is_open: return

        # Se for placeholder, mantém comportamento padrão
        if self._is_placeholder_on:
            self._entry.focus_set()
            return "break"

        # Abre o dropdown
        self.after(10, self._open_dropdown)

        if not self._entry.selection_present():
            self._entry.select_range(0, "end")
        # ---------------------------

    def _on_canvas_click(self, event):
        if str(self._entry["state"]) == "disabled":
            return "break"
        # ----------------------------------------------------------

        self._entry.focus_force()
        if self._is_open:
            self._close_dropdown()
        else:
            self.after(10, lambda: self._open_dropdown(force_full=True))
        return "break"

    def _on_global_click(self, event):
        # Se o clique foi fora da área da combobox, força perda de foco
        try:
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            x1, y1 = x0 + self._cw, y0 + self._ch
        except tk.TclError:
            return

        inside = (x0 <= event.x_root <= x1) and (y0 <= event.y_root <= y1)

        if inside:
            return

        try:
            focused = self._entry.focus_get()
        except Exception:
            focused = None

        if focused is self._entry:
            moved = False
            try:
                if hasattr(event, "widget") and event.widget not in (None, self, self._entry):
                    event.widget.focus_set()
                    moved = True
            except Exception:
                pass

            if not moved:
                try:
                    self.winfo_toplevel().focus_set()
                except Exception:
                    pass

            self.after(10, self._handle_focus_loss)

    # --- EVENTOS DE DIGITAÇÃO ---
    def _on_key_press(self, event):
        if event.keysym in (
        'Tab', 'Escape', 'Return', 'Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Shift_L', 'Shift_R', 'Control_L',
        'Control_R', 'Alt_L', 'Alt_R'):
            return

        if event.keysym in ('BackSpace', 'Delete') and self._is_placeholder_on:
            return "break"

        if self._is_placeholder_on:
            self._clear_placeholder()

    def _on_key_release(self, event):
        if not self._is_placeholder_on and not self._var.get():
            self._show_placeholder()
            if self._is_open: self._open_dropdown()

        if not self._is_placeholder_on and self._is_open:
            self._close_dropdown()
            self._open_dropdown()

    # --- GET / SET ---
    def get(self):
        if self._is_placeholder_on:
            return ""

        val = self._var.get().strip()
        is_valid = any(str(v).lower() == val.lower() for v in self._values_full)
        if not is_valid:
            return ""

        return val

    def set(self, value):
        if not value:
            self._show_placeholder()
        else:
            self._is_placeholder_on = False
            self._var.set(value)
            self._entry.configure(fg=self._text_color_normal)

    def configure(self, **kwargs):
        if "values" in kwargs:
            raw = kwargs.pop("values")
            self._values_full = raw or []

        # Sincroniza cores ao mudar estado
        if "state" in kwargs:
            st = kwargs.pop("state")
            self._entry.configure(state=st)

            if st == "disabled":
                self._fill = Colors.BG_DISABLED
                self._arrow_color = Colors.TEXT_HINT
            else:
                self._fill = Colors.BG_INPUT
                self._arrow_color = "#6B7280"

            self._draw()

        super().configure(**kwargs)

    # --- VISUAL ---
    def _on_resize(self, event):
        if event.width > 1 and event.width != self._cw:
            self._cw = event.width
            self._update_inner_entry()
            self._draw(focus=(self.focus_get() == self._entry))
            if self._is_open: self._close_dropdown()

    def _update_inner_entry(self):
        new_inner_w = max(10, self._cw - 35)
        self.itemconfigure(self._win, width=new_inner_w)

    def _check_pil(self):
        try:
            import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk
            self._has_pil = True
        except ImportError:
            self._has_pil = False

    def _draw(self, focus=False):
        self.delete("pill_bg")
        self.delete("arrow")

        current_w = self.winfo_width()
        if current_w > self._cw: self._cw = current_w

        w_real, h_real = self._cw, self._ch
        bd = self._bd_focus if focus else self._bd_color
        bg = self._fill

        if self._has_pil:
            from PIL import Image, ImageDraw, ImageTk
            ss = 3
            w, h = w_real * ss, h_real * ss
            r = self._radius * ss
            bg_rgb = Utils.hex_to_rgb(self._bg_app)
            img = Image.new("RGBA", (w, h), bg_rgb + (255,))
            drw = ImageDraw.Draw(img)
            drw.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=bd)
            inset = 1 * ss
            drw.rounded_rectangle([inset, inset, w - 1 - inset, h - 1 - inset], radius=r - inset, fill=bg)
            img = img.resize((w_real, h_real), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._photo, anchor="nw", tags="pill_bg")
            self.tag_lower("pill_bg")
        else:
            self.create_rectangle(0, 0, w_real, h_real, fill=bd, outline="")
            inset = 1
            self.create_rectangle(inset, inset, w_real - inset, h_real - inset, fill=bg, outline="")

        ax = w_real - 16
        ay = h_real // 2
        arrow_c = self._arrow_focus if focus else self._arrow_color

        if self._is_open:
            self.create_line(ax - 4, ay + 2, ax, ay - 2, ax + 4, ay + 2, fill=arrow_c, width=2, capstyle="round",
                             tags="arrow")
        else:
            self.create_line(ax - 4, ay - 2, ax, ay + 2, ax + 4, ay - 2, fill=arrow_c, width=2, capstyle="round",
                             tags="arrow")

    def _on_focus_in(self, e):
        if self._is_placeholder_on:
            self._entry.select_clear()
            self._entry.icursor(0)
        else:
            self._entry.select_range(0, "end")
            self._entry.icursor("end")
            # ----------------------------------------------

        self._draw(focus=True)

    def _on_focus_out_validate(self, event):
        self.after(150, self._handle_focus_loss)

    def _handle_focus_loss(self):
        new_focus = self.focus_get()
        if self._dropdown_frame and new_focus and str(new_focus).startswith(str(self._dropdown_frame)):
            return
        if new_focus == self._entry:
            return

        if self._is_open:
            self._close_dropdown()

        val = self._var.get().strip()
        if not val:
            self._show_placeholder()
        else:
            self._validate_value()

        self._draw(focus=False)

    def _validate_value(self):
        if self._is_placeholder_on: return

        current = self._var.get().strip()
        if not current:
            self._show_placeholder()
            return

        match = None
        for v in self._values_full:
            if str(v).lower() == current.lower():
                match = v
                break

        if match:
            if current != str(match):
                self.set(match)
        else:
            self._show_placeholder()

        # Adicionamos o parâmetro 'force_full=False'
    def _open_dropdown(self, force_full=False):
        if self._is_open: return

        current_text = "" if self._is_placeholder_on else self._var.get()

        # --- LÓGICA ALTERADA (OPÇÃO 1: Setinha Soberana) ---
        # Se force_full for True (clique na seta) OU não tiver texto, mostra tudo.
        if force_full or not current_text:
            display_values = self._values_full
        else:
            # Caso contrário, filtra pelo que está digitado
            display_values = [v for v in self._values_full if current_text.lower() in str(v).lower()]
        # ---------------------------------------------------

        if not display_values: return

        self._is_open = True
        self._draw(focus=True)

        top_window = self.winfo_toplevel()
        top_window.update_idletasks()

        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        top_x = top_window.winfo_rootx()
        top_y = top_window.winfo_rooty()

        rel_x = root_x - top_x
        rel_y = (root_y - top_y) + self._ch + 2

        win_h = top_window.winfo_height()
        row_height = 26
        frame_padding = 4
        space_below = win_h - rel_y - 10

        rows_that_fit = int((space_below - frame_padding) // row_height)
        max_rows_limit = max(1, min(6, rows_that_fit))

        rows_visual = min(len(display_values), max_rows_limit)
        h_list = rows_visual * row_height + frame_padding

        self._dropdown_frame = tk.Frame(top_window, bg=Colors.BG_CARD, bd=1, relief="solid")
        self._dropdown_frame.place(x=rel_x, y=rel_y, width=self._cw, height=h_list)
        self._dropdown_frame.lift()

        self._listbox = tk.Listbox(
            self._dropdown_frame,
            bg=Colors.BG_INPUT,
            fg=Colors.TEXT_MAIN,
            bd=0,
            highlightthickness=0,
            relief="flat",
            font=("Segoe UI", 10),
            selectbackground=Colors.PRIMARY,
            selectforeground="#ffffff",
            activestyle="none",
            cursor="hand2",
            exportselection=False
        )
        self._listbox.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

        if len(display_values) > rows_visual:
            sb = MinimalScrollbar(self._dropdown_frame, orient="vertical", command=self._listbox.yview)
            sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
            self._listbox.config(yscrollcommand=sb.set)

        LIMIT_RENDER = 100
        count = 0
        for item in display_values:
            if count >= LIMIT_RENDER:
                self._listbox.insert("end", " ... Digite para filtrar ...")
                self._listbox.itemconfig("end", fg=Colors.TEXT_HINT, selectbackground="#ffffff",
                                         selectforeground=Colors.TEXT_HINT)
                break

            self._listbox.insert("end", f" {item}")
            count += 1

        self._listbox.bind("<Motion>", self._on_motion)
        self._listbox.bind("<ButtonRelease-1>", self._on_list_click_up)
        self._bind_close_id = top_window.bind("<Button-1>", self._check_close, add="+")

    def _close_dropdown(self):
        try:
            if self.winfo_exists():
                top = self.winfo_toplevel()
                if hasattr(self, '_bind_close_id'):
                    top.unbind("<Button-1>", self._bind_close_id)
        except Exception:
            pass

        if self._dropdown_frame:
            try:
                self._dropdown_frame.destroy()
            except:
                pass
            self._dropdown_frame = None
            self._listbox = None

        self._is_open = False
        if self.winfo_exists():
            self._draw(focus=(self.focus_get() == self._entry))

    def _check_close(self, event):
        if not self._is_open: return
        widget = event.widget
        if self._dropdown_frame and str(widget).startswith(str(self._dropdown_frame)): return
        if str(widget).startswith(str(self)): return

        self._close_dropdown()

        if not self._var.get().strip():
            self._show_placeholder()
        else:
            self._validate_value()

    def _on_list_click_up(self, event):
        try:
            index = self._listbox.nearest(event.y)
            if 0 <= index < self._listbox.size():
                val = self._listbox.get(index).strip()
                self.set(val)
                self._entry.icursor("end")
                self._close_dropdown()

                def force_refocus():
                    try:
                        self.winfo_toplevel().focus_force()
                        self._entry.focus_force()
                    except:
                        pass

                self.after(50, force_refocus)
        except Exception:
            self._close_dropdown()

    def _on_motion(self, event):
        try:
            index = self._listbox.nearest(event.y)
            if index != self._listbox.curselection():
                self._listbox.selection_clear(0, "end")
                self._listbox.selection_set(index)
                self._listbox.activate(index)
        except Exception:
            pass

    def _on_arrow_down(self, event):
        # --- CORREÇÃO ---
        if str(self._entry["state"]) == "disabled":
            return "break"
        # ----------------

        if not self._is_open:
            self._open_dropdown()
            return "break"
        if self._listbox:
            current = self._listbox.curselection()
            idx = min(current[0] + 1, self._listbox.size() - 1) if current else 0
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
        return "break"

    def _on_arrow_up(self, event):
        # --- CORREÇÃO ---
        if str(self._entry["state"]) == "disabled":
            return "break"
        # ----------------

        if not self._is_open:
            self._open_dropdown()
            return "break"
        if self._listbox:
            current = self._listbox.curselection()
            idx = max(current[0] - 1, 0) if current else 0
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
        return "break"

    def _on_return_key(self, event):
        if self._is_open and self._listbox:
            current = self._listbox.curselection()
            if current:
                val = self._listbox.get(current[0]).strip()
                self.set(val)
                self._entry.icursor("end")
            self._close_dropdown()
            return "break"
        else:
            self._validate_value()
            return "break"

    def grid(self, **kwargs):
        kwargs.setdefault("padx", (0, 10))
        kwargs.setdefault("sticky", "ew")
        super().grid(**kwargs)

class MinimalScrollbar(tk.Canvas):
    def __init__(self, parent, orient, command=None):
        size = 12
        super().__init__(parent, width=size if orient == "vertical" else 100,
                         height=size if orient == "horizontal" else 100,
                         bd=0, highlightthickness=0, bg=Colors.BG_APP)
        self.orient = orient
        self.command = command
        self.first = 0.0
        self.last = 1.0

        # Cores
        self.track = "#F1F5F9"
        self.thumb = "#CBD5E1"
        self.thumb_hover = "#94A3B8"

        self.radius = 6

        # Controle de estado para arrastar
        self._drag_data = None
        self._hovering = False

        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def configure(self, **kwargs):
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        super().configure(**kwargs)

    config = configure

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._redraw()

    def _on_enter(self, e):
        self._hovering = True
        self._redraw()

    def _on_leave(self, e):
        self._hovering = False
        self._redraw()

    def _redraw(self):
        if not self.winfo_exists(): return
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()

        current_thumb = self.thumb_hover if self._hovering else self.thumb

        # Desenha fundo
        self._rounded_rect(0, 0, w, h, self.radius, self.track, "")

        # Calcula posição da barra (Thumb) em pixels
        if self.orient == "horizontal":
            avail = max(1, w)
            px_start = avail * self.first
            px_end = avail * self.last
            length = px_end - px_start

            # Garante tamanho mínimo visual para conseguir clicar
            if length < 10:
                center = (px_start + px_end) / 2
                px_start = center - 5
                px_end = center + 5

            self._rounded_rect(px_start, 2, px_end, h - 2, self.radius - 2, current_thumb, "")

        else:  # vertical
            avail = max(1, h)
            px_start = avail * self.first
            px_end = avail * self.last
            length = px_end - px_start

            if length < 10:
                center = (px_start + px_end) / 2
                px_start = center - 5
                px_end = center + 5

            self._rounded_rect(2, px_start, w - 2, px_end, self.radius - 2, current_thumb, "")

    def _rounded_rect(self, x0, y0, x1, y1, r, fill, outline):
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0
        ]
        return self.create_polygon(points, smooth=True, fill=fill, outline=outline)

    def _get_thumb_coords(self):
        w, h = self.winfo_width(), self.winfo_height()
        if self.orient == "horizontal":
            avail = max(1, w)
            return (avail * self.first, avail * self.last)
        else:
            avail = max(1, h)
            return (avail * self.first, avail * self.last)

    def _on_click(self, e):
        if not self.command: return

        start_px, end_px = self._get_thumb_coords()
        mouse_pos = e.x if self.orient == "horizontal" else e.y

        # Lógica 1: Clique fora da barra (Paginação)
        if mouse_pos < start_px:
            self.command("scroll", -1, "pages")
            return
        elif mouse_pos > end_px:
            self.command("scroll", 1, "pages")
            return

        # Lógica 2: Clique na barra (Iniciar arrasto)
        self._drag_data = {
            "x": e.x,
            "y": e.y,
            "initial_first": self.first
        }

    def _on_drag(self, e):
        if self._drag_data is None: return
        if not self.command: return

        w, h = self.winfo_width(), self.winfo_height()

        if self.orient == "horizontal":
            total = max(1, w)
            delta = e.x - self._drag_data["x"]
        else:
            total = max(1, h)
            delta = e.y - self._drag_data["y"]

        # Calcula a variação percentual
        delta_frac = delta / total

        # Nova posição = Posição inicial do clique + quanto moveu
        new_first = self._drag_data["initial_first"] + delta_frac

        # Limites de segurança
        new_first = max(0.0, min(1.0, new_first))

        self.command("moveto", new_first)

    def _on_release(self, e):
        self._drag_data = None


class ScrollableFrame(tk.Frame):
    def __init__(self, parent, bg=Colors.BG_APP, padding=(20, 20, 0, 20)):
        super().__init__(parent, bg=bg)

        # Configuração do Grid do Container Principal
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)  # Coluna da scrollbar
        self.rowconfigure(0, weight=1)

        # 1. Scrollbar (Instanciada, mas não exibida imediatamente)
        self.scrollbar = MinimalScrollbar(self, orient="vertical")

        # 2. Canvas
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.configure(command=self.canvas.yview)

        pad_l, pad_t, pad_r, pad_b = padding
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(pad_l, pad_r), pady=(pad_t, pad_b))

        # 3. Frame Interno
        self.scroll_node = tk.Frame(self.canvas, bg=bg)
        self.window_id = self.canvas.create_window((0, 0), window=self.scroll_node, anchor="nw")

        # 4. Binds de redimensionamento e mouse
        self.scroll_node.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind("<Enter>", self._bound_to_mousewheel)
        self.canvas.bind("<Leave>", self._unbound_to_mousewheel)
        self.bind("<Destroy>", self._unbound_to_mousewheel)

    def _bound_to_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        # Só rola se a scrollbar estiver visível (mapped)
        if self.canvas.winfo_exists() and self.scrollbar.winfo_ismapped():
            step = 4
            if event.num == 5 or event.delta < 0:
                self.canvas.yview_scroll(step, "units")
            elif event.num == 4 or event.delta > 0:
                self.canvas.yview_scroll(-step, "units")
            return "break"

    def _on_content_configure(self, event):
        # Atualiza a área de rolagem baseada no tamanho do conteúdo
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._check_scroll_needed()

    def _on_canvas_configure(self, event):
        # Ajusta a largura do frame interno para acompanhar o canvas
        canvas_width = event.width
        self.canvas.itemconfig(self.window_id, width=canvas_width)
        self._check_scroll_needed()

    def _check_scroll_needed(self):
        # Verifica se precisa mostrar ou esconder a barra
        try:
            bbox = self.canvas.bbox("all")
            if not bbox: return

            content_height = bbox[3]  # Altura total do conteúdo
            canvas_height = self.canvas.winfo_height()  # Altura visível

            # Se o conteúdo for maior que a área visível -> Mostra Scroll
            if content_height > canvas_height:
                if not self.scrollbar.winfo_ismapped():
                    self.scrollbar.grid(row=0, column=1, sticky="ns", padx=0, pady=0)

            # Se couber tudo -> Esconde Scroll
            else:
                if self.scrollbar.winfo_ismapped():
                    self.scrollbar.grid_remove()
                    # Reseta posição para o topo para evitar que fique "rolado" no vazio
                    self.canvas.yview_moveto(0)

        except Exception:
            pass

    @property
    def content(self):
        return self.scroll_node


class RoundedCard(tk.Canvas):
    def __init__(self, parent, padding=(16, 12, 16, 16), radius=10, bg=Colors.BG_CARD, **kw):
        tk.Canvas.__init__(self, parent, bd=0, highlightthickness=0, bg=Colors.BG_APP, **kw)

        self._radius = int(radius)
        self._padding = tuple(padding) if isinstance(padding, (list, tuple)) and len(padding) == 4 else (16, 12, 16, 16)
        self._fill = bg
        self._border = Colors.BORDER
        self._bg_tag = "card_bg"
        self._has_pil = None

        # --- CONFIGURAÇÃO SAAS ULTRA-SMOOTH ---
        # Receita refinada: Mais camadas, opacidade (alpha) muito baixa e expansão progressiva.
        # (Offset X, Offset Y, Alpha 0-255, Expansão/Blur simulado)
        self._shadow_layers = [
            (0, 1, 8, 0),  # 1. Contorno leve (quase imperceptível)
            (0, 2, 6, 1),  # 2. Difusão curta
            (0, 4, 5, 2),  # 3. Difusão média
            (0, 8, 4, 4),  # 4. Difusão média-longa
            (0, 12, 3, 7),  # 5. Difusão longa (ambiente)
            (0, 20, 2, 12)  # 6. Atmosfera (muito expandida e transparente)
        ]
        # Margem de segurança aumentada para a sombra expandida não cortar
        self._shadow_margin = 25

        pl, pt, pr, pb = self._padding
        self.content = tk.Frame(self, bg=self._fill)
        self._win = self.create_window(pl, pt, window=self.content, anchor="nw")

        self.bind("<Configure>", self._on_configure)
        self.after(20, self._size_to_content)

    def _on_configure(self, event=None):
        if event:
            pl, pt, pr, pb = self._padding
            w_inner = max(1, event.width - (pl + pr))
            self.itemconfigure(self._win, width=w_inner)
        self._draw_bg()

    def _size_to_content(self):
        try:
            self.update_idletasks()
            pl, pt, pr, pb = self._padding
            cw = self.content.winfo_reqwidth()
            ch = self.content.winfo_reqheight()

            # Adiciona margem suficiente para a sombra mais larga (layer 6: expand 12 + offset 20)
            total_w = cw + pl + pr
            total_h = ch + pt + pb

            self.configure(width=total_w, height=total_h)
            self._draw_bg()
        except Exception:
            pass

    def _draw_bg(self):
        w = self.winfo_width()
        h = self.winfo_height()
        self.delete(self._bg_tag)
        if w <= 2 or h <= 2: return

        if self._has_pil is None:
            try:
                import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageTk
                self._has_pil = True
            except:
                self._has_pil = False

        if self._has_pil:
            from PIL import Image, ImageDraw, ImageTk

            ss = 2  # Super-sampling

            bg_app = Utils.hex_to_rgb(Colors.BG_APP)
            # Imagem 100% transparente no fundo
            img = Image.new("RGBA", (w * ss, h * ss), (bg_app[0], bg_app[1], bg_app[2], 0))
            drw = ImageDraw.Draw(img)

            rr = self._radius * ss

            # Margem base (considerando que o card não encosta na borda do canvas)
            margin = 2 * ss

            # Dimensões do card (subtraindo margem para dar espaço à sombra)
            card_w = (w * ss) - margin
            card_h = (h * ss) - margin

            # Desenha as camadas de sombra (do fundo para a frente)
            for off_x, off_y, alpha, expand in self._shadow_layers:
                ox = off_x * ss
                oy = off_y * ss
                exp = expand * ss

                # Cor: Preto com Alpha variável
                shadow_color = (0, 0, 0, alpha)

                # A expansão cresce para fora, suavizando a borda
                drw.rounded_rectangle(
                    [
                        margin - exp + ox,
                        margin - exp + oy,
                        card_w + exp - margin + ox,
                        card_h + exp - margin + oy
                    ],
                    radius=rr + exp,
                    fill=shadow_color
                )

            # Desenha o Card Principal (Sólido) por cima
            drw.rounded_rectangle(
                [margin, margin, card_w - margin, card_h - margin],
                radius=rr,
                fill=self._fill,
                outline=self._border
            )

            img = img.resize((w, h), resample=Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._photo, anchor="nw", tags=(self._bg_tag,))
            self.tag_lower(self._bg_tag, self._win)
        else:
            self.create_rectangle(0, 0, w, h, fill=self._border, outline="", tags=(self._bg_tag,))

class CardSectionTitle(ttk.Label):
    # Título de seção dentro do card (um pouco menor que o título principal)
    def __init__(self, parent, text, **kwargs):
        kwargs.setdefault("style", "CardSectionTitle.TLabel")
        ttk.Label.__init__(self, parent, text=text, **kwargs)


class CardSectionSeparator(tk.Frame):
    # Linha suave que separa seções dentro do card
    def __init__(self, parent, color=Colors.BORDER, height=1, pady=(12, 8), **kwargs):
        kwargs.setdefault("bg", color)
        kwargs.setdefault("height", height)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(self, parent, **kwargs)
        self._default_pady = pady

    def grid(self, *args, **kwargs):
        if "sticky" not in kwargs:
            kwargs["sticky"] = "ew"
        if "pady" not in kwargs:
            kwargs["pady"] = self._default_pady
        return tk.Frame.grid(self, *args, **kwargs)

class Page(ttk.Frame):
    destroy_on_hide = False

    def on_show(self, **kwargs):
        pass

    def on_hide(self):
        pass

    def alert(self, title, message, type="warning", focus_widget=None, pre_focus_action=None, width=420, height=260):
        icon = "alert"
        if type == "error": icon = "alert_red"
        elif type == "info": icon = "alert"

        dlg = SaaSDialog(self, title, message, icon_name=icon,
                         buttons=[("OK", True, "primary")],
                         width=width, height=height)
        self.wait_window(dlg)

        if pre_focus_action: pre_focus_action()
        self.update_idletasks()

        target = None
        if focus_widget:
            target = getattr(focus_widget, "_entry", focus_widget)
        elif self.focus_get():
            target = self.focus_get()

        if target:
            self.after(50, lambda: target.focus_force())

    def ask_yes_no(self, title, message, on_yes, on_no=None, width=420, height=260):
        dlg = SaaSDialog(self, title, message, icon_name="caution",
                         buttons=[("Não", False, "outline"), ("Sim", True, "primary")],
                         width=width, height=height)
        self.wait_window(dlg)

        resposta = dlg.result

        if resposta:
            if callable(on_yes): self.after(50, on_yes)
        else:
            if callable(on_no): self.after(50, on_no)
        return resposta

    def create_standard_toolbar(self, row_idx, on_add, on_edit, on_del):
        toolbar = ttk.Frame(self, style="Main.TFrame")
        toolbar.grid(row=row_idx, column=0, sticky="ew", padx=16, pady=(6, 6))
        toolbar.columnconfigure(4, weight=1)

        # Botão Adicionar: AZUL (primary) e QUADRADO (padx=9)
        self.btn_add = PillButton(toolbar, text="", icon=load_icon("add", 16), command=on_add,
                                  variant="primary", padx=9)
        ToolTip(self.btn_add, "Cadastrar")
        self.btn_add.grid(row=0, column=0, padx=(0, 10))

        # Botão Editar: QUADRADO (padx=9)
        self.btn_edit = PillButton(toolbar, text="", icon=load_icon("edit", 16), command=on_edit,
                                   variant="outline", padx=9)
        ToolTip(self.btn_edit, "Editar")
        self.btn_edit.grid(row=0, column=1, padx=(0, 10))

        # Botão Excluir: QUADRADO (padx=9)
        self.btn_del = PillButton(toolbar, text="", icon=load_icon("delete", 16), command=on_del,
                                  variant="outline", padx=9)
        ToolTip(self.btn_del, "Excluir")
        self.btn_del.grid(row=0, column=2, padx=(0, 10))

        # Estado inicial
        self.btn_edit.state(["disabled"])
        self.btn_del.state(["disabled"])

        return toolbar

# ====== Barra de paginação reutilizável ======
class PaginatorBar(ttk.Frame):
    def __init__(self, parent, on_first, on_prev, on_next, on_last, autohide=True):
        super().__init__(parent, style="Main.TFrame")
        self._visible = True
        self.autohide = autohide

        self.btn_first = PillButton(self, text="Primeiro", command=on_first, variant="outline",
                                    icon=load_icon("primeiro", 16))
        self.btn_prev = PillButton(self, text="Anterior", command=on_prev, variant="outline",
                                   icon=load_icon("anterior", 16))
        self.btn_next = PillButton(self, text="Próximo", command=on_next, variant="outline", icon=load_icon("proximo", 16))
        self.btn_last = PillButton(self, text="Último", command=on_last, variant="outline", icon=load_icon("ultimo", 16))
        self.lbl_info  = ttk.Label(self, text="")

        self.btn_first.grid(row=0, column=0)
        self.btn_prev.grid(row=0, column=1)
        self.btn_next.grid(row=0, column=2)

        # Último botão da fila -> padx=0
        self.btn_last.grid(row=0, column=3, padx=0)

        # Label info
        self.lbl_info.grid(row=0, column=4, padx=(12, 0))
        self.columnconfigure(4, weight=1)

        for b in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
            b.state(["disabled"])

    def update_state(self, total: int, page: int, page_size: int):
        try:
            if not self.winfo_exists(): return
        except Exception:
            return
        tem_paginacao = total > page_size
        need_show = tem_paginacao or (not self.autohide)
        if need_show and not self._visible:
            self.grid()
            self._visible = True
        elif not need_show and self._visible:
            self.grid_remove()
            self._visible = False

        if total <= 0:
            self.lbl_info.configure(text="Nenhum registro.")
            for b in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
                b.state(["disabled"])
            return

        max_page = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, max_page))

        start = (page - 1) * page_size + 1
        end   = min(start + page_size - 1, total)
        self.lbl_info.configure(text=f"Exibindo {start}-{end} de {total}")

        if page <= 1:
            self.btn_first.state(["disabled"])
            self.btn_prev.state(["disabled"])
        else:
            self.btn_first.state(["!disabled"])
            self.btn_prev.state(["!disabled"])

        if page >= max_page:
            self.btn_next.state(["disabled"])
            self.btn_last.state(["disabled"])
        else:
            self.btn_next.state(["!disabled"])
            self.btn_last.state(["!disabled"])


class ToolTip:
    def __init__(self, widget, text=None, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.id_schedule = None
        self.tip_label = None

        if self.text:
            self.widget.bind("<Enter>", self.schedule, add="+")
            self.widget.bind("<Leave>", self.hide, add="+")
            self.widget.bind("<ButtonPress>", self.hide, add="+")
            self.widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, event=None):
        self.unschedule()
        self.id_schedule = self.widget.after(self.delay, self.show)

    def unschedule(self):
        if self.id_schedule:
            self.widget.after_cancel(self.id_schedule)
            self.id_schedule = None

    def show(self, text=None, x=None, y=None):
        """
        Cria ou atualiza o Label flutuante.
        Permite atualização dinâmica de texto e posição (para seguir o mouse).
        """
        val_text = text or self.text
        if not val_text:
            return

        # Flag para saber se precisamos recalcular dimensões (otimização)
        needs_resize = False

        if not self.tip_label:
            try:
                top_window = self.widget.winfo_toplevel()
                self.tip_label = tk.Label(
                    top_window,
                    text=val_text,
                    justify='left',
                    background="#ffffe0",
                    relief='solid',
                    borderwidth=1,
                    font=("Segoe UI", 9),
                    fg="#000000",
                    padx=4,
                    pady=2
                )
                needs_resize = True
            except Exception:
                return
        else:
            # Se já existe, verificamos se o texto mudou
            current_text = self.tip_label.cget("text")
            if current_text != val_text:
                self.tip_label.configure(text=val_text)
                needs_resize = True

        # Só força atualização do layout se o conteúdo mudou (evita lag ao mover mouse)
        if needs_resize:
            self.tip_label.update_idletasks()

        # --- CÁLCULO DE POSIÇÃO ---
        try:
            top_window = self.tip_label.winfo_toplevel()

            tip_w = self.tip_label.winfo_reqwidth()
            tip_h = self.tip_label.winfo_reqheight()

            win_x = top_window.winfo_rootx()
            win_y = top_window.winfo_rooty()
            win_w = top_window.winfo_width()
            win_h = top_window.winfo_height()

            if x is not None and y is not None:
                # MODO SEGUIR MOUSE (Tabelas)
                # Posição relativa ao topo da janela
                rel_x = x - win_x
                rel_y = y - win_y

                # Ajuste borda direita
                if rel_x + tip_w > win_w:
                    rel_x = win_w - tip_w - 5

                # Ajuste borda inferior (se não couber, joga para cima do mouse)
                if rel_y + tip_h > win_h:
                    rel_y = rel_y - tip_h - 20
            else:
                # MODO ESTÁTICO (Botões)
                btn_x = self.widget.winfo_rootx()
                btn_y = self.widget.winfo_rooty()
                btn_h = self.widget.winfo_height()
                btn_w = self.widget.winfo_width()

                rel_x = btn_x - win_x
                rel_y = (btn_y - win_y) + btn_h + 2

                if rel_x + tip_w > win_w:
                    rel_x = (btn_x - win_x) + btn_w - tip_w

                if rel_y + tip_h > win_h:
                    rel_y = (btn_y - win_y) - tip_h - 2

            # Proteção contra coordenadas negativas
            if rel_x < 0: rel_x = 0
            if rel_y < 0: rel_y = 0

            self.tip_label.place(x=rel_x, y=rel_y)
            self.tip_label.lift()

        except Exception:
            self.hide()

    def hide(self, event=None):
        self.unschedule()
        if self.tip_label:
            try:
                self.tip_label.destroy()
            except:
                pass
            self.tip_label = None


class StandardTable(tk.Frame):
    def __init__(self, parent, columns, fetch_fn, page_size=PAGE_SIZE_DEFAULT, inner_padx=16,
                 minimal=False, filter_columns=None, checkboxes=False, autohide_pagination=True):
        super().__init__(parent, bg=Colors.BG_APP)
        self.columns = columns
        self.fetch_fn = fetch_fn
        self.page_size = page_size
        self.page = 1
        self.filters = []
        self.inner_padx = int(inner_padx)
        self.minimal = minimal
        self.autohide_pagination = autohide_pagination
        self.checkboxes = checkboxes
        self.chk_width = 30 if checkboxes else 0

        # Mapa de Seleção por ID {id: row_data}
        self._selection_map = {}
        self._last_click_id = None

        self.filter_definitions = filter_columns or []
        self.active_filters = {}
        self._search_timer = None
        self._current_rows = []
        self._pending_resize_id = None

        self.row_height = 30
        self.header_height = 36
        self.header_bg = Colors.HEADER_TABLE
        self.header_line = Colors.BORDER
        self.body_bg = Colors.BG_CARD
        self.cell_line = Colors.BORDER
        self.sel_bg = Colors.ROW_SELECTED
        self.sel_fg = "#000000"

        self._ids_cols = [c["id"] for c in self.columns if c.get("hidden", False)]
        self._ids_visible = False

        self._col_defs = []
        self._col_x = [0]
        self._total_w = 0
        self._last_ratio = 1.0

        self.columnconfigure(0, weight=1)
        if self.minimal:
            self.rowconfigure(0, weight=1)
        else:
            self.rowconfigure(1, weight=1)

        # --- BARRA DE FERRAMENTAS ---
        self.toolbar = None
        self.left_actions = None  # Container para botões à esquerda (Adicionar, etc)
        self.right_actions = None  # Container para botões à direita (Exportar, etc)

        if not self.minimal:
            self.toolbar = ttk.Frame(self, style="Main.TFrame")
            self.toolbar.grid(row=0, column=0, sticky="ew", padx=self.inner_padx, pady=(8, 4))

            self.toolbar.columnconfigure(4, weight=1)

            # 0. Container de Ações Customizadas (Esquerda)
            self.left_actions = tk.Frame(self.toolbar, bg=Colors.BG_APP)
            self.left_actions.grid(row=0, column=0, sticky="w", padx=(0, 10))

            # Busca (Col 1)
            self.ent_quick = PillEntry(self.toolbar, placeholder="Buscar", height=34, width=240)
            self.ent_quick.grid(row=0, column=1, padx=(0, 5))
            self.ent_quick.bind("<KeyRelease>", self._on_search_keypress)

            # 1. FILTRO (Col 2)
            self.btn_filters = PillButton(self.toolbar, text="", padx=9, command=self._open_filter_dialog,
                                          variant="outline", icon=load_icon("filter", 16))
            self.btn_filters.grid(row=0, column=2, padx=(0, 5))

            self._tt_filter = ToolTip(self.btn_filters)
            self.btn_filters.bind("<Enter>",
                                  lambda e: self._tt_filter.show("Filtros", e.x_root, e.y_root + 25), add="+")
            self.btn_filters.bind("<Leave>", lambda e: self._tt_filter.hide(), add="+")

            # 2. LIMPAR (Col 3)
            self.btn_clear = PillButton(self.toolbar, text="", padx=9, command=self._clear_filters,
                                        variant="outline", icon=load_icon("clear", 16))
            self.btn_clear.grid(row=0, column=3, padx=0)

            self._tt_clear = ToolTip(self.btn_clear)
            self.btn_clear.bind("<Enter>", lambda e: self._tt_clear.show("Limpar Filtros", e.x_root, e.y_root + 25),
                                add="+")
            self.btn_clear.bind("<Leave>", lambda e: self._tt_clear.hide(), add="+")

            # Spacer está na Col 4

            # 5. Container de Ações Customizadas (Direita) - Antes do Refresh
            self.right_actions = tk.Frame(self.toolbar, bg=Colors.BG_APP)
            self.right_actions.grid(row=0, column=5, sticky="e", padx=(0, 5))

            # 3. ATUALIZAR (Col 6)
            self.btn_refresh = PillButton(self.toolbar, text="", padx=9, command=self._refresh,
                                          variant="outline", icon=load_icon("refresh", 16))
            self.btn_refresh.grid(row=0, column=6, sticky="e", padx=(0, 5))  # Padrao

            self._tt_refresh = ToolTip(self.btn_refresh)
            self.btn_refresh.bind("<Enter>",
                                  lambda e: self._tt_refresh.show("Atualizar", e.x_root, e.y_root + 25), add="+")
            self.btn_refresh.bind("<Leave>", lambda e: self._tt_refresh.hide(), add="+")

            # 4. AUDITORIA (Col 7)
            self.btn_toggle_ids = None
            if self._ids_cols:
                self.btn_toggle_ids = PillButton(self.toolbar, text="", padx=9, command=self._toggle_id_cols,
                                                 variant="outline", icon=load_icon("eye", 16))

                # Ajuste de grid se houver auditoria
                self.btn_refresh.grid(row=0, column=6, sticky="e", padx=(0, 5))
                self.btn_toggle_ids.grid(row=0, column=7, sticky="e", padx=0)

                self._tt_audit = ToolTip(self.btn_toggle_ids)
                self.btn_toggle_ids.bind("<Enter>",
                                         lambda e: self._tt_audit.show("Auditoria", e.x_root, e.y_root + 25), add="+")
                self.btn_toggle_ids.bind("<Leave>", lambda e: self._tt_audit.hide(), add="+")
            else:
                self.btn_refresh.grid(row=0, column=6, sticky="e", padx=0)

        # Resto da inicialização (Canvas, Scrollbars, etc) continua igual...
        self.container = tk.Frame(
            self, bd=0, highlightthickness=1,
            highlightbackground=self.header_line, highlightcolor=self.header_line
        )
        row_idx = 0 if self.minimal else 1
        self.container.grid(row=row_idx, column=0, sticky="nsew", padx=self.inner_padx)
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(1, weight=1)

        self.header_canvas = tk.Canvas(self.container, height=self.header_height, highlightthickness=0,
                                       bg=Colors.BG_APP)
        self.body_canvas = tk.Canvas(self.container, highlightthickness=0, bg=Colors.BG_APP, confine=True)
        self.hbar = MinimalScrollbar(self.container, orient="horizontal", command=self._xview)

        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.body_canvas.grid(row=1, column=0, sticky="nsew")
        self.hbar.grid(row=2, column=0, sticky="ew")
        self.hbar.grid_remove()

        self.body_canvas.configure(xscrollcommand=self.hbar.set)
        self.bind("<Configure>", self._on_frame_configure)

        self._tooltip_manager = ToolTip(self.body_canvas)
        self.body_canvas.bind("<Motion>", self._on_mouse_motion)
        self.body_canvas.bind("<Leave>", lambda e: self._tooltip_manager.hide())

        self.body_canvas.bind("<Button-1>", self._on_text_select_start)
        self.body_canvas.bind("<B1-Motion>", self._on_text_select_drag)
        self.body_canvas.bind("<ButtonRelease-1>", self._on_text_select_end)
        self.body_canvas.bind("<Double-Button-1>", self._on_double_click)
        self.body_canvas.bind("<Triple-Button-1>", self._on_double_click)
        self.body_canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        self.header_canvas.bind("<Button-1>", self._on_header_click)

        # O bind do Ctrl+C precisa ser no próprio body_canvas, que é quem recebe o foco!
        self.body_canvas.bind("<Control-c>", self._copy_selected_text)
        self.body_canvas.bind("<Control-C>", self._copy_selected_text)

        self._text_sel_start = None
        self._selected_text_items = []

        self.body_canvas.bind("<Up>", self._on_arrow_up)
        self.body_canvas.bind("<Down>", self._on_arrow_down)
        self.body_canvas.bind("<Left>", self._on_arrow_left)
        self.body_canvas.bind("<Right>", self._on_arrow_right)
        self.body_canvas.bind("<Return>", self._on_return_key)

        if not self.minimal:
            self.nav = PaginatorBar(
                self,
                on_first=lambda: self.load_page(1),
                on_prev=lambda: self.load_page(self.page - 1),
                on_next=lambda: self.load_page(self.page + 1),
                on_last=self._go_last,
                autohide=self.autohide_pagination
            )
            self.nav.grid(row=3, column=0, sticky="ew", padx=self.inner_padx, pady=(6, 12))

        self.after(100, lambda: self.load_page(1))
        self.after(200, lambda: self.winfo_toplevel().bind("<Button-1>", self._safe_global_deselect, add="+"))

    def add_overflow_menu_action(self, label, command, icon_name=None):
        # Adiciona uma ação ao menu 'Mais Opções' (...) na barra de ferramentas.
        # Cria o botão de menu automaticamente se ele ainda não existir.
        if self.minimal or not self.toolbar:
            return

        # Se o menu ainda não existe, cria ele no container da direita
        if not hasattr(self, "_overflow_btn"):
            self._overflow_menu = tk.Menu(self, tearoff=0, bg=Colors.BG_APP, fg=Colors.TEXT_MAIN)

            # Botão que abre o menu (ícone de 3 pontos verticais ou engrenagem)
            # Usaremos 'settings' ou 'conf' como ícone genérico
            self._overflow_btn = PillButton(
                self.right_actions,
                text="",
                variant="outline",
                icon=load_icon("settings", 16),  # Ou use um icone de 'more_vert' se tiver
                padx=9,
                command=lambda: self._show_overflow_menu()
            )
            # Pack à direita (depois dos outros botões da direita)
            self._overflow_btn.pack(side="right", padx=(5, 0))

            # Tooltip
            self._tt_overflow = ToolTip(self._overflow_btn)
            self._overflow_btn.bind("<Enter>", lambda e: self._tt_overflow.show("Mais Opções", e.x_root, e.y_root + 25),
                                    add="+")
            self._overflow_btn.bind("<Leave>", lambda e: self._tt_overflow.hide(), add="+")

        # Adiciona o item ao menu
        # Nota: Tkinter menus nativos não suportam ícones facilmente em todas as plataformas,
        # vamos usar texto simples por compatibilidade e robustez.
        self._overflow_menu.add_command(label=label, command=command)

    def _show_overflow_menu(self):
        if hasattr(self, "_overflow_menu"):
            x = self._overflow_btn.winfo_rootx()
            y = self._overflow_btn.winfo_rooty() + self._overflow_btn.winfo_height()
            self._overflow_menu.tk_popup(x, y)

    def _get_row_id(self, row_data):
        # Tenta obter um ID único para rastrear a linha independente da página
        return str(row_data.get("Id")) if "Id" in row_data else str(id(row_data))

    def _recalc_columns(self, available_width=None):
        self._col_defs = [c for c in self.columns if not c.get("hidden", False)]

        # 1. Largura "ideal" somando os width das colunas visíveis
        base_total_w = sum(c.get("width", 120) for c in self._col_defs)
        if base_total_w <= 0:
            base_total_w = 1

        # 2. Largura da área visível
        if available_width:
            view_w = available_width - 2
            if view_w < 1:
                view_w = 1
        else:
            view_w = base_total_w

        # 3. Ratio ideal (quanto deveríamos esticar se fosse permitir encolher)
        if view_w < base_total_w:
            ratio_ideal = 1.0
        else:
            ratio_ideal = view_w / base_total_w

        # 4. Nunca deixar as colunas encolherem:
        #    o ratio nunca pode ser menor que o último já aplicado
        if not hasattr(self, "_last_ratio"):
            self._last_ratio = 1.0

        ratio = max(1.0, self._last_ratio, ratio_ideal)
        self._last_ratio = ratio

        target_w = int(round(base_total_w * ratio))

        # 5. Recalcula posições das colunas com o novo ratio
        start_x = self.chk_width
        self._col_x = [start_x]
        current_x = start_x
        num_cols = len(self._col_defs)

        for i, c in enumerate(self._col_defs):
            base_w = c.get("width", 120)
            final_w = int(base_w * ratio)

            # Ajuste fino para o último fechar a conta de pixels
            if i == num_cols - 1:
                remaining = target_w - current_x
                if remaining > 0:
                    final_w = max(final_w, remaining)

            current_x += final_w
            self._col_x.append(current_x)

        self._total_w = self._col_x[-1]

        # 6. Controle da scrollbar horizontal
        if available_width and self._total_w > available_width:
            self.hbar.grid()
            # Cabeçalho e corpo com a mesma scrollregion
            self.header_canvas.config(scrollregion=(0, 0, self._total_w, self.header_height))
            self.body_canvas.config(scrollregion=(0, 0, self._total_w, self.body_canvas.winfo_reqheight()))
        else:
            self.hbar.grid_remove()
            # Reseta posição se não tiver scroll
            self.header_canvas.xview_moveto(0)
            self.body_canvas.xview_moveto(0)

    # MUDANÇA: Lógica do botão Dados Técnicos
    def _toggle_id_cols(self):
        if not getattr(self, "_ids_cols", None): return
        self._ids_visible = not getattr(self, "_ids_visible", False)

        for c in self.columns:
            if c["id"] in self._ids_cols:
                c["hidden"] = not self._ids_visible

        self._perform_resize(self.winfo_width() - (self.inner_padx * 2))
        self._draw_grid()

        if hasattr(self, "btn_toggle_ids") and self.btn_toggle_ids:
            icon_name = "eye_off" if self._ids_visible else "eye"
            self.btn_toggle_ids.configure(icon=load_icon(icon_name, 16), variant="outline")

    def _on_frame_configure(self, event):
        # 1. Proteção contra Loop: Se a largura for igual a anterior, não faz nada.
        # Isso quebra o ciclo vicioso de redesenho.
        if getattr(self, "_last_width_cache", None) == event.width:
            return
        self._last_width_cache = event.width

        # 2. Debounce: Cancela agendamento anterior
        if self._pending_resize_id:
            self.after_cancel(self._pending_resize_id)

        available_w = event.width - (self.inner_padx * 2)

        # 3. Aumenta levemente o tempo (10 -> 50ms) para aliviar a CPU
        self._pending_resize_id = self.after(50, lambda w=available_w: self._perform_resize(w))

    def _perform_resize(self, width):
        self._recalc_columns(available_width=width)
        self._draw_grid()

    def _draw_chk(self, canvas, x, y, checked, is_header=False):
        # Tamanho do ícone (18 fica ótimo na linha padrão)
        size = 18

        # 1. Reutiliza a lógica visual exata do BlueCheckButton (incluindo cache)
        # Isso garante que a tabela tenha EXATAMENTE a mesma aparência dos widgets
        # e resolve o serrilhado (anti-aliasing)
        img = BlueCheckButton._get_image(size, checked)

        # Cálculos de posicionamento (Centralizar na coluna de checkbox)
        h_area = self.header_height if is_header else self.row_height
        center_x = x + (self.chk_width // 2)
        center_y = y + h_area // 2

        if img:
            # Desenha a imagem gerada (Suave e idêntica ao resto do sistema)
            canvas.create_image(center_x, center_y, image=img, anchor="center")
        else:
            # Fallback de segurança (caso o PIL falhe)
            # Desenho manual simples
            s = 14
            x0 = center_x - s // 2
            y0 = center_y - s // 2
            canvas.create_rectangle(x0, y0, x0 + s, y0 + s, outline="#C6CDDD", width=1)
            if checked:
                canvas.create_text(center_x, center_y, text="✓", fill=Colors.PRIMARY, font=("Segoe UI", 10, "bold"))

    def _draw_grid(self):
        self.header_canvas.delete("all")
        self.body_canvas.delete("all")
        if self.winfo_width() < 20: return

        rows_count = len(self._current_rows)
        content_height = max(1, rows_count) * self.row_height

        self.body_canvas.configure(height=content_height)
        self.header_canvas.config(scrollregion=(0, 0, self._total_w, self.header_height))
        self.body_canvas.config(scrollregion=(0, 0, self._total_w, content_height))

        # Fundo base e linha final
        self.body_canvas.create_rectangle(0, 0, self._total_w, content_height, fill=self.body_bg, outline="")
        self.body_canvas.create_line(0, content_height, self._total_w, content_height, fill=self.header_line)

        # --- CABEÇALHO ---
        self.header_canvas.create_rectangle(0, 0, self._total_w, self.header_height, fill=self.header_line, outline="")
        self.header_canvas.create_line(0, self.header_height - 1, self._total_w, self.header_height - 1, fill=self.header_line)

        if self.checkboxes:
            visible_selected_count = sum(1 for r in self._current_rows if self._get_row_id(r) in self._selection_map)
            all_visible_selected = (visible_selected_count == rows_count and rows_count > 0)
            self._draw_chk(self.header_canvas, 0, 0, all_visible_selected, is_header=True)
            self.header_canvas.create_line(self.chk_width, 0, self.chk_width, self.header_height, fill=self.header_line)

        for i, col in enumerate(self._col_defs):
            x0, x1 = self._col_x[i], self._col_x[i + 1]
            self.header_canvas.create_line(x1 - 1, 0, x1 - 1, self.header_height, fill=self.header_line, width=1)
            tx = (x0 + x1) // 2
            self.header_canvas.create_text(tx, self.header_height // 2, text=col["title"], anchor="center",
                                           font=("Segoe UI", 9, "bold"), fill=Colors.TEXT_MAIN)

        for r, row_data in enumerate(self._current_rows):
            self._draw_single_row(r, row_data)

    def _xview(self, *args):
        self.body_canvas.xview(*args)
        self.header_canvas.xview(*args)

    def _on_shift_wheel(self, event):
        self.body_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        self.header_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def _canvas_y_to_row(self, y):
        return int(self.body_canvas.canvasy(y) // self.row_height)

    def _on_header_click(self, event):
        if not self.checkboxes: return
        if self.header_canvas.canvasx(event.x) < self.chk_width:
            # Verifica se tudo VISÍVEL já está selecionado
            all_visible_selected = True
            for r in self._current_rows:
                if self._get_row_id(r) not in self._selection_map:
                    all_visible_selected = False
                    break

            if all_visible_selected:
                # Desmarca apenas os visíveis (mantém os de outras páginas)
                for r in self._current_rows:
                    rid = self._get_row_id(r)
                    self._selection_map.pop(rid, None)
                    if self._last_click_id == rid: self._last_click_id = None
            else:
                # Marca todos os visíveis
                for r in self._current_rows:
                    rid = self._get_row_id(r)
                    self._selection_map[rid] = r

            self._draw_grid()
            self.event_generate("<<TableSelect>>")

    def _on_text_select_start(self, event):
        self.body_canvas.focus_set()
        click_x = self.body_canvas.canvasx(event.x)
        click_y = self.body_canvas.canvasy(event.y)

        # Mantém clique do checkbox intacto
        if self.checkboxes and click_x < self.chk_width:
            self._on_click(event)
            self._text_sel_start = None
            return

        self._text_sel_start = (click_x, click_y)
        self.body_canvas.delete("text_sel_hl")
        self._selected_text_items = []

    def _on_text_select_drag(self, event):
        if not self._text_sel_start: return
        cur_x = self.body_canvas.canvasx(event.x)
        cur_y = self.body_canvas.canvasy(event.y)

        start_x, start_y = self._text_sel_start

        # 1. Determina a ordem de leitura lógica (Ponto 1 sempre antes do Ponto 2)
        row_start = self._canvas_y_to_row(start_y)
        row_cur = self._canvas_y_to_row(cur_y)

        if row_start < row_cur:
            p1_x, p1_y = start_x, start_y
            p2_x, p2_y = cur_x, cur_y
        elif row_start > row_cur:
            p1_x, p1_y = cur_x, cur_y
            p2_x, p2_y = start_x, start_y
        else:
            # Estão na mesma linha, definimos o menor X primeiro
            p1_y = p2_y = start_y
            p1_x = min(start_x, cur_x)
            p2_x = max(start_x, cur_x)

        row1 = self._canvas_y_to_row(p1_y)
        row2 = self._canvas_y_to_row(p2_y)

        # 2. Limpa o azulzinho anterior a cada movimento do mouse em tempo real
        self.body_canvas.delete("text_sel_hl")
        self._selected_text_items = []

        # 3. Busca TODOS os textos na faixa vertical (da largura inteira 0 a _total_w)
        largura_tabela = getattr(self, "_total_w", 9999)
        items = self.body_canvas.find_overlapping(0, p1_y - self.row_height, largura_tabela, p2_y + self.row_height)

        from tkinter import font as tkfont
        f_obj = tkfont.Font(family="Segoe UI", size=10)

        for item in items:
            if self.body_canvas.type(item) == "text":
                coords = self.body_canvas.coords(item)
                if not coords: continue
                cx, cy = coords[0], coords[1]
                item_row = self._canvas_y_to_row(cy)

                # Ignora itens que estão fisicamente no canvas mas fora da nossa seleção lógica de linhas
                if item_row < row1 or item_row > row2:
                    continue

                txt = self.body_canvas.itemcget(item, "text")
                txt_len = len(txt)

                # 4. Lógica de seleção fluida (Estilo texto de parágrafo)
                if row1 == row2:
                    # Seleção em uma única linha
                    idx_start = self.body_canvas.index(item, f"@{int(p1_x)},{int(cy)}")
                    idx_end = self.body_canvas.index(item, f"@{int(p2_x)},{int(cy)}")
                else:
                    if item_row == row1:
                        # Primeira linha: seleciona do ponto X do mouse até o fim do texto
                        idx_start = self.body_canvas.index(item, f"@{int(p1_x)},{int(cy)}")
                        idx_end = txt_len
                    elif item_row == row2:
                        # Última linha: seleciona do início do texto até o ponto X do mouse
                        idx_start = 0
                        idx_end = self.body_canvas.index(item, f"@{int(p2_x)},{int(cy)}")
                    else:
                        # Linhas intermediárias: seleciona a célula inteira
                        idx_start = 0
                        idx_end = txt_len

                idx_start, idx_end = sorted([idx_start, idx_end])

                # Se o mouse não pegou nenhum caractere dessa célula, pula para a próxima
                if idx_start == idx_end:
                    continue

                # 5. Calcula as medidas do highlight em Pixels
                txt_w = f_obj.measure(txt)
                start_x_text = cx - (txt_w / 2)

                px1 = start_x_text + f_obj.measure(txt[:idx_start])
                px2 = start_x_text + f_obj.measure(txt[:idx_end])

                bbox = self.body_canvas.bbox(item)
                if bbox:
                    # Pinta APENAS os caracteres selecionados de azulzinho
                    hl = self.body_canvas.create_rectangle(
                        px1, bbox[1] - 2, px2, bbox[3] + 2,
                        fill="#B4D7FF", outline="", tags="text_sel_hl"
                    )
                    self.body_canvas.tag_lower(hl, item)

                    # Salva o item e os limites exatos para que o Ctrl+C copie corretamente
                    self._selected_text_items.append((item, idx_start, idx_end))

    def _on_text_select_end(self, event):
        if not self._text_sel_start: return
        end_x = self.body_canvas.canvasx(event.x)
        end_y = self.body_canvas.canvasy(event.y)

        x1, x2 = sorted([self._text_sel_start[0], end_x])
        y1, y2 = sorted([self._text_sel_start[1], end_y])

        # Se foi apenas clique (não arrastou), processa o clique natural da tabela
        if abs(x2 - x1) < 5 and abs(y2 - y1) < 5:
            self.body_canvas.delete("text_sel_hl")
            self._selected_text_items = []
            self._on_click(event)

        self._text_sel_start = None

    def _copy_selected_text(self, event=None):
        if not self._selected_text_items: return "break"

        # Agrupa os itens selecionados por Linha e Coluna
        texts_by_row = {}
        for item_data in self._selected_text_items:
            item, idx_start, idx_end = item_data

            coords = self.body_canvas.coords(item)
            if not coords: continue
            cx, cy = coords[0], coords[1]
            row_idx = int(cy // self.row_height)

            if row_idx not in texts_by_row:
                texts_by_row[row_idx] = []

            val = self.body_canvas.itemcget(item, "text")

            # Corta apenas as letras que o usuário selecionou!
            val = val[idx_start:idx_end]

            texts_by_row[row_idx].append((cx, val))

        # Monta o texto formatado para o clipboard
        lines = []
        for row_idx in sorted(texts_by_row.keys()):
            row_items = sorted(texts_by_row[row_idx], key=lambda x: x[0])
            lines.append("\t".join([str(txt) for _, txt in row_items]))

        final_text = "\n".join(lines)
        if final_text:
            self.clipboard_clear()
            self.clipboard_append(final_text)

        return "break"  # Impede que a tecla faça o comportamento nativo indesejado

    def _handle_click_focus(self, event):
        self.body_canvas.focus_set()
        self._on_click(event)

    def _on_click(self, event):
        row_idx = self._canvas_y_to_row(event.y)
        click_x = self.body_canvas.canvasx(event.x)

        # Clicou fora (fundo branco): Limpa tudo
        if not (0 <= row_idx < len(self._current_rows)):
            self._selection_map.clear()
            self._last_click_id = None
            self._draw_grid()
            self.event_generate("<<TableSelect>>")
            return

        # --- NOVO: LÓGICA SHIFT + CLICK (Seleção em Intervalo) ---
        # 0x1 verifica se a tecla SHIFT está pressionada
        if (event.state & 0x1) and self._last_click_id:
            start_idx = self._get_current_index()  # Pega o índice do último item clicado

            # CORREÇÃO: Se não encontrou o último clique na página atual (retornou -1),
            # define o próprio clique atual como ponto de partida para não bugar a seleção.
            if start_idx == -1:
                start_idx = row_idx

            if start_idx != -1:
                # Define o intervalo (do menor para o maior)
                low = min(start_idx, row_idx)
                high = max(start_idx, row_idx)

                # Se for índice negativo (bug de wrap), ajusta para 0
                if low < 0: low = 0

                # Opcional: Se quiser que o Shift limpe seleções anteriores fora do range
                # self._selection_map.clear()

                for i in range(low, high + 1):
                    # Proteção extra para não estourar lista
                    if 0 <= i < len(self._current_rows):
                        r_data = self._current_rows[i]
                        rid = self._get_row_id(r_data)
                        self._selection_map[rid] = r_data

                self._draw_grid()
                self.event_generate("<<TableSelect>>")
                return
        # ---------------------------------------------------------

        row_data = self._current_rows[row_idx]
        rid = self._get_row_id(row_data)

        # --- COMPORTAMENTO QUANDO HÁ CHECKBOXES ---
        # Agora só faz TOGGLE se o clique for no quadrado do checkbox (coluna esquerda).
        if self.checkboxes:
            if click_x < self.chk_width:
                # Toggle (adiciona/remove)
                if rid in self._selection_map:
                    del self._selection_map[rid]
                    if self._last_click_id == rid:
                        self._last_click_id = None
                else:
                    self._selection_map[rid] = row_data
                    self._last_click_id = rid
            else:
                # Cliques fora do checkbox agem como seleção única (limpam as anteriores)
                self._selection_map.clear()
                self._selection_map[rid] = row_data
                self._last_click_id = rid

            self._draw_grid()
            self.event_generate("<<TableSelect>>")
            return

        # --- COMPORTAMENTO ANTIGO (SEM CHECKBOXES): clique limpa anteriores ---
        self._selection_map.clear()
        self._selection_map[rid] = row_data
        self._last_click_id = rid

        self._draw_grid()
        self.event_generate("<<TableSelect>>")

    def _on_mouse_motion(self, event):
        # Descobre em qual linha o mouse está
        row_idx = self._canvas_y_to_row(event.y)

        if 0 <= row_idx < len(self._current_rows):
            row_data = self._current_rows[row_idx]

            # Verifica se essa linha tem uma mensagem de tooltip escondida (chave "_tooltip")
            msg = row_data.get("_tooltip")

            if msg:
                # Mostra o balão um pouco abaixo e à direita do mouse
                x_root = event.x_root + 15
                y_root = event.y_root + 10
                self._tooltip_manager.show(msg, x_root, y_root)
            else:
                self._tooltip_manager.hide()
        else:
            self._tooltip_manager.hide()

    def _safe_global_deselect(self, event):
        if not self._selection_map: return
        if event.widget == self.body_canvas: return

        w = event.widget
        # Adicionei classes extras aqui para evitar bugs de deseleção
        if isinstance(w, (PillButton, BlueRadioButton, BlueCheckButton, ToggleSwitch,
                          MinimalScrollbar, PillEntry, PillCombobox,
                          tk.Entry, tk.Button, ttk.Button, tk.Listbox, tk.Canvas)):
            return

        self._selection_map.clear()
        self._last_click_id = None
        self._draw_grid()
        self.event_generate("<<TableSelect>>")
        self.event_generate("<<TreeviewSelect>>")

    def _on_double_click(self, event):
        if self.checkboxes:
            click_x = self.body_canvas.canvasx(event.x)

            # --- CORREÇÃO DO SPAM CLICK ---
            # Se clicou no checkbox, NÃO ignore.
            # Ao contrário: force a execução do clique normal (_on_click).
            # Isso faz com que o 2º e 3º cliques rápidos funcionem como toggles.
            if click_x < self.chk_width:
                self._on_click(event)
                return "break"

        # Se foi no texto, comportamento padrão (abrir edição)
        self._on_click(event)
        self.event_generate("<<TableDoubleClick>>")

    def get_selected(self):
        # Retorna UM item selecionado (o último clicado ou o primeiro do mapa)
        if self._last_click_id and self._last_click_id in self._selection_map:
            return self._selection_map[self._last_click_id]

        if self._selection_map:
            return list(self._selection_map.values())[0]
        return None

    def get_all_selected(self):
        # Retorna TODOS os itens selecionados (incluindo os de outras páginas)
        return list(self._selection_map.values())

    # --- MÉTODOS DE NAVEGAÇÃO POR TECLADO ---
    def _get_current_index(self):
        # Retorna o índice da linha focada atualmente, ou -1 se nenhuma.
        if not self._last_click_id or not self._current_rows:
            return -1

        # Procura o índice visual da linha que tem o ID do último clique
        for i, row in enumerate(self._current_rows):
            if self._get_row_id(row) == self._last_click_id:
                return i
        return -1

    def _select_by_index(self, index):
        """Seleciona linha e garante limpeza visual completa das anteriores."""
        if not self._current_rows: return

        # 1. Identifica TODAS as linhas que precisam ser redesenhadas (limpas)
        #    Isso evita o "rastro" de seleções antigas
        rows_to_refresh = set()

        # Adiciona a linha que estava com o foco do teclado
        old_focus = self._get_current_index()
        if old_focus != -1: rows_to_refresh.add(old_focus)

        # Adiciona todas as linhas que estão visualmente selecionadas na tela agora
        for i, row in enumerate(self._current_rows):
            if self._get_row_id(row) in self._selection_map:
                rows_to_refresh.add(i)

        # 2. Limpa a seleção lógica
        self._selection_map.clear()

        # 3. Define a nova seleção
        if index < 0: index = 0
        if index >= len(self._current_rows): index = len(self._current_rows) - 1

        row_data = self._current_rows[index]
        rid = self._get_row_id(row_data)
        self._selection_map[rid] = row_data
        self._last_click_id = rid

        # Adiciona a nova linha para ser desenhada (pintada de azul)
        rows_to_refresh.add(index)

        # 4. Redesenha APENAS as linhas afetadas (limpa as velhas, pinta a nova)
        for r_idx in rows_to_refresh:
            if 0 <= r_idx < len(self._current_rows):
                self._draw_single_row(r_idx, self._current_rows[r_idx])

        # Eventos
        self.event_generate("<<TableSelect>>")
        self.event_generate("<<TreeviewSelect>>")

        # 5. Auto-Scroll (Mantido igual)
        row_y_top = index * self.row_height
        row_y_bottom = row_y_top + self.row_height

        vis_top = self.body_canvas.canvasy(0)
        vis_height = self.body_canvas.winfo_height()
        vis_bottom = vis_top + vis_height

        if row_y_top < vis_top:
            self.body_canvas.yview_moveto(row_y_top / self.body_canvas.bbox("all")[3])
        elif row_y_bottom > vis_bottom:
            total_h = self.body_canvas.bbox("all")[3]
            target = (row_y_bottom - vis_height) / total_h
            self.body_canvas.yview_moveto(target)

    def _draw_single_row(self, r, row_data):
        # Desenha apenas uma linha específica, sem limpar o resto da tabela.
        # Tag única para identificar todos os elementos desta linha
        row_tag = f"row_{r}"

        # Remove apenas os elementos visuais desta linha antiga para redesenhar
        self.body_canvas.delete(row_tag)

        y0 = r * self.row_height
        y1 = y0 + self.row_height

        rid = self._get_row_id(row_data)
        is_sel = (rid in self._selection_map)

        # --- CORREÇÃO: Desenha o fundo da linha se estiver selecionada ---
        if is_sel:
            self.body_canvas.create_rectangle(
                0, y0, self._total_w, y1,
                fill=self.sel_bg, outline="", tags=(row_tag,)
            )

        if self.checkboxes:
            # Recalcula centro do checkbox
            center_x = self.chk_width // 2
            center_y = y0 + self.row_height // 2

            img = BlueCheckButton._get_image(18, is_sel)
            if img:
                self.body_canvas.create_image(center_x, center_y, image=img, anchor="center", tags=(row_tag,))
            else:
                # Fallback
                s = 14
                self.body_canvas.create_rectangle(center_x - s // 2, center_y - s // 2, center_x + s // 2,
                                                  center_y + s // 2,
                                                  outline="#C6CDDD", tags=(row_tag,))

            self.body_canvas.create_line(self.chk_width, y0, self.chk_width, y1,
                                         fill=self.cell_line, tags=(row_tag,))

        # 3. Colunas de Texto
        for i, col in enumerate(self._col_defs):
            x0, x1 = self._col_x[i], self._col_x[i + 1]

            # Linhas de grade
            self.body_canvas.create_line(x0, y1 - 1, x1, y1 - 1, fill=self.cell_line, width=1, tags=(row_tag,))
            self.body_canvas.create_line(x1 - 1, y0, x1 - 1, y1, fill=self.cell_line, width=1, tags=(row_tag,))

            # Texto
            raw_val = row_data.get(col["id"])
            val = str(raw_val) if raw_val is not None else "-"
            font_obj = tkfont.Font(family="Segoe UI", size=10)
            col_w = x1 - x0
            max_w = max(1, col_w - 12)

            final_text = val
            if font_obj.measure(val) > max_w:
                chars = len(val)
                # Vai reduzindo a string até que o texto + "..." caiba na largura máxima
                while chars > 0 and font_obj.measure(val[:chars] + "...") > max_w:
                    chars -= 1
                final_text = val[:chars] + "..."

            # Centralização forçada padrão (ignora configurações de 'anchor' externas)
            tx = (x0 + x1) // 2
            text_color = row_data.get("_text_color", "#374151")

            self.body_canvas.create_text(tx, (y0 + y1) // 2, text=final_text, anchor="center",
                                         font=("Segoe UI", 10), fill=text_color, tags=(row_tag,))

    def _on_arrow_down(self, event):
        if not self._current_rows: return "break"

        curr = self._get_current_index()
        total = len(self._current_rows)

        if curr == -1:
            # Nenhuma seleção -> Vai para o primeiro
            new_idx = 0
        else:
            # Loop: Se for o último (total-1), (curr+1)%total vira 0
            new_idx = (curr + 1) % total

        self._select_by_index(new_idx)
        return "break"  # Impede scroll nativo do canvas para controlar manualmente

    def _on_arrow_up(self, event):
        if not self._current_rows: return "break"

        curr = self._get_current_index()
        total = len(self._current_rows)

        if curr == -1:
            # Nenhuma seleção -> Vai para o último
            new_idx = total - 1
        else:
            # Loop: Se for o primeiro (0), (0-1)%total vira o último
            new_idx = (curr - 1) % total

        self._select_by_index(new_idx)
        return "break"

    def _on_arrow_left(self, event):
        # Página Anterior: Só vai se página > 1
        if self.page > 1:
            self.load_page(self.page - 1)
        return "break"

    def _on_arrow_right(self, event):
        # Próxima Página: Calcula o limite matemático real
        if hasattr(self, '_last_total'):
            max_page = max(1, (self._last_total + self.page_size - 1) // self.page_size)
            if self.page < max_page:
                self.load_page(self.page + 1)
        return "break"

    def _on_return_key(self, event):
        # Enter abre edição (Simula Double Click)
        if self._last_click_id:
            self.event_generate("<<TableDoubleClick>>")
        return "break"

    def load_page(self, page):
        # Busca dados (seguro)
        try:
            total, rows = self.fetch_fn(page, self.page_size, self.filters)
        except Exception:
            return

        self._last_total = total
        self.page = page
        self._current_rows = rows

        for r in rows:
            rid = self._get_row_id(r)
            if rid in self._selection_map:
                self._selection_map[rid] = r

        # UI Blindada
        try:
            if not self.winfo_exists(): return

            if not self.minimal and hasattr(self, 'nav'):
                if self.nav.winfo_exists():
                    self.nav.update_state(total=total, page=self.page, page_size=self.page_size)

            self.event_generate("<<TableSelect>>")
            self.event_generate("<<TreeviewSelect>>")

            self._perform_resize(self.winfo_width() - (self.inner_padx * 2))
            self.body_canvas.yview_moveto(0)

        except (tk.TclError, RuntimeError):
            pass
        except Exception:
            pass

    def _refresh(self):
        # Ao atualizar explicitamente (botão Atualizar), limpamos a seleção para evitar IDs fantasmas
        self._selection_map.clear()
        self._last_click_id = None
        self.load_page(self.page)

    def _on_search_keypress(self, event):
        # Ignora teclas de navegação para não refazer a busca enquanto o usuário apenas anda pelo texto
        if event.keysym in ("Up", "Down", "Left", "Right", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return

        # 1. Se já existe um timer agendado (usuário digitou outra letra rápido), cancela ele
        if self._search_timer:
            self.after_cancel(self._search_timer)

        # 2. Agenda uma nova busca para daqui a 400 milissegundos
        # Se o usuário digitar de novo antes disso, este timer será cancelado no passo 1
        self._search_timer = self.after(400, self._perform_auto_search)

    def _perform_auto_search(self):
        # Chama a função de busca original
        self._on_quick_enter()

    # ----------------------------------------

    def _open_filter_dialog(self):
        if not self.filter_definitions:
            self.alert("Filtro", "Nenhum campo de filtro configurado para esta tabela.", type="warning")
            return

        # 1. Ajuste a altura se quiser, mas agora com Scrollbar não é obrigatório
        top = SaaSModal(self, title="Filtros Avançados", width=420, height=550)

        # 2. SEPARAÇÃO DO LAYOUT:
        # Parte A: Área de Scroll (ocupa todo o espaço que sobrar)
        # Usamos o seu ScrollableFrame já existente
        scroll_area = ScrollableFrame(top.content, padding=(20, 20, 0, 20))
        scroll_area.pack(side="top", fill="both", expand=True)

        # O frame onde vamos colocar os inputs é o .content do scroll_area
        frm_inputs = scroll_area.content

        # Parte B: Área dos Botões (Fixa no rodapé)
        btn_box = ttk.Frame(top.content, style="Main.TFrame")
        btn_box.pack(side="bottom", fill="x", padx=20, pady=20)

        # Dicionário temporário para guardar as entradas desse modal
        input_vars = {}

        # 3. CRIAÇÃO DOS CAMPOS (Agora dentro de frm_inputs)
        for i, f_def in enumerate(self.filter_definitions):
            key = f_def['key']
            label = f_def['label']

            ttk.Label(frm_inputs, text=label, style="TLabel").pack(anchor="w", pady=(0, 4))

            ent = TextField(frm_inputs, height=34)
            ent.pack(fill="x", pady=(0, 12))

            # Preenche com valor atual se já existir filtro ativo
            current_val = self.active_filters.get(key, "")
            if current_val:
                ent.insert(0, current_val)

            input_vars[key] = ent

        # 4. LÓGICA DOS BOTÕES (Mesma de antes)
        def _apply():
            new_filters = {}
            for key, ent_widget in input_vars.items():
                val = ent_widget.get().strip()
                if val:
                    new_filters[key] = val

            self.active_filters = new_filters

            combined_filters = []
            q = self.ent_quick.get().strip()
            if q: combined_filters.append({"type": "quick", "value": q})

            for k, v in self.active_filters.items():
                combined_filters.append({"type": "advanced", "key": k, "value": v})

            self.filters = combined_filters
            self.load_page(1)

            if self.active_filters:
                self.btn_filters.configure(variant="primary")
            else:
                self.btn_filters.configure(variant="outline")

            top.close()

        def _clear_modal():
            for ent in input_vars.values():
                ent.delete(0, "end")

        # Os botões são adicionados no btn_box (rodapé fixo)
        PillButton(btn_box, text="Aplicar", variant="success", command=_apply).pack(side="right")
        PillButton(btn_box, text="Limpar Campos", variant="outline", command=_clear_modal).pack(side="right", padx=10)

    def _clear_filters(self):
        # Limpa tudo (Busca Rápida + Avançada)
        self.filters = []
        self.active_filters = {}
        self.ent_quick.delete(0, "end")
        self.btn_filters.configure(variant="outline")  # Volta a cor normal
        self.load_page(1)

    def _on_quick_enter(self):
        # Atualiza apenas a parte 'quick' dos filtros, mantendo os avançados
        q = self.ent_quick.get().strip()

        combined_filters = []
        if q: combined_filters.append({"type": "quick", "value": q})

        for k, v in self.active_filters.items():
            combined_filters.append({"type": "advanced", "key": k, "value": v})

        self.filters = combined_filters
        self.load_page(1)

    def _go_last(self):
        total, _ = self.fetch_fn(1, 1, self.filters)
        last = max(1, (total + self.page_size - 1) // self.page_size)
        self.load_page(last)


class SaaSModal(tk.Toplevel):
    # Pilha para controle de ordem (Stack)
    _stack = []

    def __init__(self, parent, title, width=500, height=600):
        super().__init__(parent)
        self.withdraw()

        SaaSModal._stack.append(self)

        # Define quem é o pai imediato (para posicionamento e overlay)
        self.top_parent = parent.winfo_toplevel()

        # --- BUSCA A RAIZ DO APLICATIVO (O "Chefe" Supremo) ---
        # Precisamos dela para detectar o Alt+Tab corretamente,
        # mesmo se formos um diálogo filho de outro modal.
        self.app_root = self.top_parent
        while hasattr(self.app_root, "master") and self.app_root.master:
            self.app_root = self.app_root.master
        self.app_root = self.app_root.winfo_toplevel()
        # ------------------------------------------------------

        # Configuração Visual
        self.overrideredirect(True)
        self.configure(bg=Colors.BG_APP, bd=1, relief="solid")

        try:
            self.transient(self.top_parent)
        except:
            pass

        # Overlay (Fundo Escuro) aplicado no pai imediato
        self.top_parent.update_idletasks()
        self.bg_image = self._create_screenshot_overlay()

        self.overlay = tk.Canvas(self.top_parent, highlightthickness=0, bd=0)
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)

        if self.bg_image:
            self.overlay.create_image(0, 0, image=self.bg_image, anchor="nw")
        else:
            self.overlay.configure(bg="#1e1e1e")

        tk.Misc.tkraise(self.overlay)
        self.overlay.bind("<Button-1>", lambda e: self._on_overlay_click())

        self._drag_data = {}
        self._setup_ui(title)
        self._center_window(width, height)

        # --- EVENTOS DE RECUPERAÇÃO GLOBAL ---
        # Monitoramos a RAIZ DO APP. Se ela acordar, todos acordam.
        # Usamos binds únicos para não duplicar eventos desnecessariamente
        self._bind_map = self.app_root.bind("<Map>", self._on_app_restore, add="+")
        self._bind_focus = self.app_root.bind("<FocusIn>", self._on_app_restore, add="+")

        self.header.bind("<Button-1>", self._start_move)
        self.header.bind("<B1-Motion>", self._do_move)
        self.protocol("WM_DELETE_WINDOW", self.close)

        # Exibição Inicial
        self.deiconify()

        # Força organização inicial da pilha
        SaaSModal.bring_all_to_front()

    def _on_app_restore(self, event):
        # Se o evento veio da janela raiz (ex: Alt+Tab), reorganiza a casa.
        if event.widget == self.app_root:
            self.after(10, SaaSModal.bring_all_to_front)

    @classmethod
    def bring_all_to_front(cls):
        # Método Mágico: Percorre a pilha inteira e levanta um por um.
        # Isso garante a ordem: Root -> Modal 1 -> Modal 2 (Dialog)

        for win in cls._stack:
            try:
                if win.winfo_exists():
                    win.lift()
            except:
                pass

        # Foca no último (o topo da pilha)
        if cls._stack:
            try:
                cls._stack[-1].focus_force()
            except:
                pass

    def _on_overlay_click(self):
        # Clicar no fundo escuro tenta trazer o modal correspondente para frente
        # Mas por segurança, trazemos todos na ordem certa.
        SaaSModal.bring_all_to_front()

    def _create_screenshot_overlay(self):
        try:
            try:
                from PIL import ImageGrab, ImageEnhance, ImageTk
            except ImportError:
                return None
            x = self.top_parent.winfo_rootx()
            y = self.top_parent.winfo_rooty()
            w = self.top_parent.winfo_width()
            h = self.top_parent.winfo_height()
            if w <= 1 or h <= 1: return None
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            enhancer = ImageEnhance.Brightness(shot)
            dark_shot = enhancer.enhance(0.6)
            return ImageTk.PhotoImage(dark_shot)
        except:
            return None

    def _center_window(self, w, h):
        try:
            root_w = self.top_parent.winfo_width()
            root_h = self.top_parent.winfo_height()
            root_x = self.top_parent.winfo_rootx()
            root_y = self.top_parent.winfo_rooty()
            x = root_x + (root_w - w) // 2
            y = root_y + (root_h - h) // 2
            self.geometry(f"{w}x{h}+{x}+{y}")
        except:
            self.geometry(f"{w}x{h}+100+100")

    def _setup_ui(self, title):
        self.header = tk.Frame(self, bg=Colors.BG_SIDEBAR, height=48)
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)

        lbl_title = tk.Label(self.header, text=title, font=("Segoe UI", 12, "bold"),
                             bg=Colors.BG_SIDEBAR, fg="#ffffff")
        lbl_title.pack(side="left", padx=24)
        lbl_title.bind("<Button-1>", self._start_move)
        lbl_title.bind("<B1-Motion>", self._do_move)

        sq_size = 34
        self.btn_close = tk.Canvas(self.header, width=sq_size, height=sq_size,
                                   bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0, cursor="hand2")
        self.btn_close.pack(side="right", padx=(0, 6), pady=7)
        center = sq_size / 2
        self.btn_close.create_text(center, 16, text="✕", fill="#ffffff", font=("Segoe UI", 12))
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(bg="#C42B1C"))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(bg=Colors.BG_SIDEBAR))
        self.btn_close.bind("<Button-1>", self.close)

        self.content = tk.Frame(self, bg=Colors.BG_APP)
        self.content.pack(side="top", fill="both", expand=True)

    def _start_move(self, event):
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root
        self._drag_data["win_x"] = self.winfo_x()
        self._drag_data["win_y"] = self.winfo_y()

    def _do_move(self, event):
        if not self._drag_data: return
        dx = event.x_root - self._drag_data["x"]
        dy = event.y_root - self._drag_data["y"]
        self.geometry(f"+{self._drag_data['win_x'] + dx}+{self._drag_data['win_y'] + dy}")

    def close(self, event=None):
        if self in SaaSModal._stack:
            SaaSModal._stack.remove(self)

        # Limpeza de eventos da Raiz (Importante para não acumular lixo na memória)
        try:
            self.app_root.unbind("<Map>", self._bind_map)
            self.app_root.unbind("<FocusIn>", self._bind_focus)
        except:
            pass

        # Destrói Overlay
        if hasattr(self, 'overlay') and self.overlay:
            try:
                self.overlay.destroy()
            except:
                pass

        try:
            self.grab_release()
        except:
            pass
        try:
            self.destroy()
        except:
            pass

        # Ao fechar, garante que quem sobrou na pilha (se houver) receba o foco
        # Se sobrou um modal pai, ele volta pro topo. Se não, a raiz.
        SaaSModal.bring_all_to_front()
        if not SaaSModal._stack:
            try:
                self.app_root.focus_force()
            except:
                pass

    # --- DIÁLOGOS ---
    def alert(self, title, message, type="warning", focus_widget=None, pre_focus_action=None, width=420, height=260):
        icon = "alert"
        if type == "error": icon = "alert_red"
        elif type == "info": icon = "alert"

        # Passa width/height para o SaaSDialog
        dlg = SaaSDialog(self, title, message, icon_name=icon,
                         buttons=[("OK", True, "primary")],
                         width=width, height=height)
        self.wait_window(dlg)

        if pre_focus_action:
            try: pre_focus_action()
            except: pass

        if focus_widget:
            try:
                target = getattr(focus_widget, "_entry", focus_widget)
                self.after(50, lambda: target.focus_force())
            except: pass
        else:
            self.after(50, lambda: self.focus_force())

    def ask_yes_no(self, title, message, on_yes=None, on_no=None, width=420, height=260):
        # Passa width/height para o SaaSDialog
        dlg = SaaSDialog(self, title, message, icon_name="caution",
                         buttons=[("Não", False, "outline"), ("Sim", True, "primary")],
                         width=width, height=height)
        self.wait_window(dlg)

        if dlg.result is True:
            if callable(on_yes): self.after(50, on_yes)
            return True
        else:
            if callable(on_no): self.after(50, on_no)
            self.after(50, lambda: self.focus_force())
            return False


class SaaSDialog(SaaSModal):
    # DEFAULT seguro aumentado para 420x260, mas agora é sobrescritível
    def __init__(self, parent, title, message, icon_name="alert", buttons=None, width=420, height=260):
        super().__init__(parent, title, width=width, height=height)
        self.result = None

        # --- ORDEM CORRIGIDA: Botões primeiro (Rodapé) ---
        btn_box = ttk.Frame(self.content, style="Main.TFrame", padding=(20, 0, 20, 20))
        btn_box.pack(side="bottom", fill="x")

        # Container Principal ocupa o resto
        container = ttk.Frame(self.content, style="Main.TFrame", padding=(20, 20, 20, 10))
        container.pack(side="top", fill="both", expand=True)

        body = tk.Frame(container, bg=Colors.BG_APP)
        body.pack(fill="both", expand=True)

        try:
            safe_icon = icon_name
            if "error" in icon_name: safe_icon = "alert_red"
            elif "warning" in icon_name: safe_icon = "alert_yellow"
            elif "info" in icon_name: safe_icon = "alert"

            img = load_icon(safe_icon, 32)
            lbl_ico = tk.Label(body, image=img, bg=Colors.BG_APP)
            lbl_ico.image = img
            lbl_ico.pack(side="left", anchor="n", padx=(0, 15))
        except:
            pass

        # Calcula a altura estimada para o texto ficar perfeitamente centralizado na vertical
        linhas = message.split('\n')
        altura_estimada = sum(max(1, len(linha) // 45 + 1) for linha in linhas)

        txt_msg = tk.Text(body, font=("Segoe UI", 11), bg=Colors.BG_APP, fg=Colors.TEXT_MAIN,
                          bd=0, highlightthickness=0, wrap="word", width=10, height=altura_estimada)

        txt_msg.pack(side="left", anchor="center", fill="x", expand=True, padx=(0, 10))

        # --- ALINHAMENTO CONDICIONAL ---
        # Se a mensagem tem mais de uma linha (contém \n), alinha à esquerda.
        # Se for uma mensagem curta (uma linha só), centraliza no meio.
        if len(linhas) > 1:
            txt_msg.tag_configure("formato", justify="left")
        else:
            txt_msg.tag_configure("formato", justify="center")

        txt_msg.insert("1.0", message, "formato")
        # --------------------------------------------

        # Trava o widget para não permitir digitação, apenas seleção
        txt_msg.configure(state="disabled")

        # Garante que o atalho Ctrl+C funcione nativamente
        def _copy_text(event):
            try:
                self.clipboard_clear()
                self.clipboard_append(txt_msg.selection_get())
            except tk.TclError:
                pass  # Ignora se tentar copiar sem ter nada selecionado
            return "break"

        txt_msg.bind("<Control-c>", _copy_text)
        txt_msg.bind("<Control-C>", _copy_text)

        if not buttons:
            buttons = [("OK", True, "primary")]

        for text, val, variant in buttons:
            cmd = lambda v=val: self._on_btn_click(v)
            btn = PillButton(btn_box, text=text, variant=variant, width=80, command=cmd)
            btn.pack(side="right", padx=(5, 0))
            if variant == "primary":
                self.bind("<Return>", lambda e, v=val: self._on_btn_click(v))

        self.bind("<Escape>", lambda e: self.close())

    def _on_btn_click(self, value):
        self.result = value
        self.close()


class ConferenciaModal(SaaSModal):
    def __init__(self, parent, pr_code, on_close=None):
        super().__init__(parent, title=f"Conferência - {pr_code}", width=520, height=590)
        self.pr_code = pr_code
        self.on_close_cb = on_close

        # --- NOVO: Flag para controlar se precisa atualizar a tela de trás ---
        self._houve_mudanca = False
        # -------------------------------------------------------------------

        # Carrega itens do PR
        self.items = recebimento_repo.list_itens_por_pr(pr_code)
        self.current_idx = 0
        self.current_lpn = None

        self.content.configure(bg=Colors.BG_APP)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.main_container = ttk.Frame(self.content, style="Main.TFrame", padding=20)
        self.main_container.grid(row=0, column=0, sticky="nsew")

        self.footer = ttk.Frame(self.content, style="Main.TFrame", padding=(20, 15, 20, 20))
        self.footer.grid(row=1, column=0, sticky="ew")

        self._show_stage_lpn()

    def _show_stage_lpn(self):
        self._qtd_original_edicao = 0.0  # Reseta a memória de edição
        for w in self.main_container.winfo_children(): w.destroy()
        for w in self.footer.winfo_children(): w.destroy()

        center_box = tk.Frame(self.main_container, bg=Colors.BG_APP)
        center_box.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9)

        tk.Label(center_box, text="Bipe ou digite um NOVO LPN para iniciar.",
                 font=("Segoe UI", 10), bg=Colors.BG_APP, fg="#6B7280").pack(pady=(0, 20))

        # --- INPUT ---
        self.ent_lpn_input = TextField(center_box, placeholder="", height=45)
        self.ent_lpn_input.pack(fill="x", pady=(0, 5))

        self.ent_lpn_input._entry.bind("<Return>", self._validate_lpn)
        self.ent_lpn_input._entry.bind("<Key>", self._reset_error_state, add="+")

        self.lbl_erro = tk.Label(center_box, text="", font=("Segoe UI", 9),
                                 fg="#EF4444", bg=Colors.BG_APP)
        self.lbl_erro.pack(pady=(0, 15))

        self.ent_lpn_input.focus_set()

        # Botão Centralizado
        btn_continue = PillButton(center_box, text="Continuar", variant="primary",
                                  command=self._validate_lpn, height=40, width=140)
        btn_continue.pack(anchor="center")

        # ==========================================================
        # NOVO: SEÇÃO DE RECUPERAÇÃO DE LPNs EXISTENTES
        # ==========================================================
        item_id = self.items[self.current_idx]["Id"]

        # 1. Busca LPNs salvos no banco
        sql_lpns = "SELECT Lpn FROM RecebimentoLeituras WHERE RecebimentoItemId=? AND Lpn IS NOT NULL AND Estornado = 0 GROUP BY Lpn ORDER BY MIN(DataHora)"
        res_lpns = recebimento_repo.execute_query(sql_lpns, (item_id,))
        lpns_banco = [r['Lpn'] for r in res_lpns if r['Lpn']]

        # 2. Resgata os LPNs da memória (caso algum LPN novo ainda não tenha ido pro banco)
        lpns_memoria = getattr(self, "lpns_do_item", []) if getattr(self, "_lpn_list_item_id", None) == item_id else []

        # 3. Combina e remove duplicatas
        self.lpns_do_item = []
        for lpn in lpns_banco + lpns_memoria:
            if lpn not in self.lpns_do_item:
                self.lpns_do_item.append(lpn)

        # Se já houver LPNs na caixa, exibe a opção de selecioná-los
        if self.lpns_do_item:
            # Linha separadora discreta
            tk.Frame(center_box, bg=Colors.BORDER, height=1).pack(fill="x", pady=25)

            tk.Label(center_box, text="Ou continue em um LPN já conferido:",
                     font=("Segoe UI", 10), bg=Colors.BG_APP, fg="#6B7280").pack(pady=(0, 20))

            # Substituído para PillCombobox para manter o padrão visual do sistema
            self.cb_lpns_existentes = PillCombobox(center_box, values=self.lpns_do_item)
            self.cb_lpns_existentes.pack(fill="x", pady=(0, 15))

            # Deixa o último LPN pré-selecionado para facilitar
            self.cb_lpns_existentes.set(self.lpns_do_item[-1])

            btn_abrir = PillButton(center_box, text="Abrir LPN", variant="outline", command=self._abrir_lpn_existente,
                                   height=40, width=140)
            btn_abrir.pack(anchor="center")
        # ==========================================================
        PillButton(self.footer, text="Voltar", variant="outline", command=self._voltar_para_form).pack(side="right")

    def _abrir_lpn_existente(self):
        if not hasattr(self, "cb_lpns_existentes"): return

        lpn_selecionado = self.cb_lpns_existentes.get()
        if lpn_selecionado and lpn_selecionado in self.lpns_do_item:
            self.current_lpn = lpn_selecionado
            self.current_lpn_idx = self.lpns_do_item.index(lpn_selecionado)

            # Chama a mesma função mágica que as setinhas usam para repopular a tela!
            self._carregar_lpn_selecionado()

    def _voltar_para_form(self):
        # Se houver um estado de formulário salvo, restaura para a tela anterior
        if hasattr(self, "_last_form_state") and self._last_form_state:
            self.current_lpn = self._last_form_state.get("lpn")
            self._qtd_original_edicao = self._last_form_state.get("qtd_convertida", 0.0)
            self._show_stage_form()

            # --- CORREÇÃO: Destrava o campo EAN antes de preencher ---
            self.ent_ean.configure(state="normal")

            # Repopula TODOS os campos com os dados cacheados perfeitamente
            self.ent_ean.delete(0, "end")
            val_ean = self._last_form_state.get("ean", "")
            self.ent_ean.insert(0, val_ean)

            if val_ean == "SEM GTIN":
                self.ent_ean.configure(state="disabled")

            self.ent_lote.delete(0, "end")
            self.ent_lote.insert(0, self._last_form_state.get("lote", ""))

            self.ent_fab.delete(0, "end")
            self.ent_fab.insert(0, self._last_form_state.get("fab", ""))

            self.ent_val.delete(0, "end")
            self.ent_val.insert(0, self._last_form_state.get("val", ""))

            self.ent_qtd.delete(0, "end")
            self.ent_qtd.insert(0, self._last_form_state.get("qtd", ""))

            self.cb_und.set(self._last_form_state.get("und", "UN"))
            self.cb_emb.set(self._last_form_state.get("emb", "Sim"))
            self.cb_mat.set(self._last_form_state.get("mat", "Sim"))
            self.cb_id.set(self._last_form_state.get("id", "Sim"))
            self.cb_cert.set(self._last_form_state.get("cert", "Sim"))
            self.cb_status.set(self._last_form_state.get("status", "Aprovado"))

            self.temp_desc_visual = self._last_form_state.get("desc_visual", "")

            # Limpa o cache após restaurar
            self._last_form_state = None
        else:
            self.close()

    def _reset_error_state(self, event=None):
        # Restaura as cores originais do componente (Azul/Cinza)
        self.ent_lpn_input._bd_normal = Colors.BORDER
        self.ent_lpn_input._bd_focus = Colors.BORDER_FOCUS

        # CORREÇÃO: Removemos o argumento "focus=True"
        self.ent_lpn_input._draw()

        # Limpa o texto de erro
        self.lbl_erro.config(text="")

    def _validate_lpn(self, _event=None):
        # 1. Pega o que está escrito (pode vir sujo do scanner)
        raw_text = self.ent_lpn_input.get().strip()

        # 2. Sanitização: Remove tudo que NÃO for dígito (hifens, espaços, letras)
        # Ex: "1234567-8" vira "12345678"
        digits_only = "".join(filter(str.isdigit, raw_text))

        # --- VALIDAÇÃO 1: VAZIO ---
        if not digits_only:
            # Pinta de vermelho e avisa
            self.ent_lpn_input._bd_normal = "#EF4444"
            self.ent_lpn_input._bd_focus = "#EF4444"
            self.ent_lpn_input._draw()

            self.lbl_erro.config(text="⚠ LPN obrigatório")
            self.ent_lpn_input.focus_set()
            return

        # --- VALIDAÇÃO 2: TAMANHO (Deve ter exatamente 8 números) ---
        if len(digits_only) != 8:
            # Pinta de vermelho e avisa o erro de tamanho
            self.ent_lpn_input._bd_normal = "#EF4444"
            self.ent_lpn_input._bd_focus = "#EF4444"
            self.ent_lpn_input._draw()

            self.lbl_erro.config(text=f"O LPN deve ter 8 números")
            self.ent_lpn_input.focus_set()
            # Seleciona o texto para facilitar a correção
            self.ent_lpn_input._entry.select_range(0, "end")
            return

        # Se passou pelas validações visuais, limpa o erro
        self._reset_error_state()

        # 3. Formatação Automática (O "Hífen Mágico")
        # Transforma "12345678" em "1234567-8"
        formatted_lpn = f"{digits_only[:7]}-{digits_only[7]}"

        # Atualiza o campo visualmente para o usuário ver o formato correto
        self.ent_lpn_input.delete(0, "end")
        self.ent_lpn_input.insert(0, formatted_lpn)

        # 4. Validação de Negócio (Existe no banco? É virgem?)
        ok, msg = lpn_repo.validar_lpn_virgem(formatted_lpn)
        if not ok:
            # Erro de negócio -> Modal de Alerta
            self.alert("LPN Inválido", msg, type="error", focus_widget=self.ent_lpn_input)
            return

        # 4.1 Validação Extra: LPN já usado neste recebimento?
        # Verifica se este LPN já foi atribuído a OUTRO item da lista (que não seja o atual)
        for i, it in enumerate(self.items):
            if i == self.current_idx: continue  # Pula o item atual

            lpn_outro = it.get("dados_qualidade", {}).get("lpn_vinculado")
            if lpn_outro == formatted_lpn:
                self.alert("LPN Duplicado",
                           f"Este LPN já foi usado no item {i + 1} ({it['sku']}).\nUse um LPN novo.")
                self.ent_lpn_input.delete(0, "end")
                return

        # 5. Sucesso: Atualiza status do Recebimento se necessário
        header = recebimento_repo.get_by_pr(self.pr_code)

        if header:
            status_atual = header.get("Status")
            ok, msg = recebimento_repo.iniciar_conferencia(self.pr_code, usuario="Conferente")

            if ok:
                self._houve_mudanca = True

        self.current_lpn = formatted_lpn
        self._last_form_state = None  # Limpa qualquer estado de fallback
        self._show_stage_form()

    def _on_fab_change(self, event=None):
        # 1. Aplica Máscara na Fabricação
        self._apply_date_mask(self.ent_fab, event)

        fab_txt = self.ent_fab.get()

        # Só executa se a data estiver completa (10 chars: dd/mm/aaaa)
        if len(fab_txt) == 10:

            # Tenta calcular (Se tiver cadastro)
            sku = self.items[self.current_idx]["Sku"]
            prod = products_repo.get_by_sku(sku)

            vida_util = None
            unidade = "Meses"

            if prod:
                # 1. Tenta do Produto
                if prod.get("VidaUtil") is not None:
                    vida_util = prod.get("VidaUtil")
                    unidade = "Dias"
                else:
                    # 2. Tenta da Família (Herança)
                    fam = families_repo.get_by_nome(prod.get("Familia"))
                    if fam and fam.get("VidaUtil") is not None:
                        vida_util = fam.get("VidaUtil")
                        unidade = "Dias"

            if vida_util:
                nova_val = Utils.calcular_vencimento(fab_txt, vida_util, unidade)
                if nova_val:
                    self.ent_val.delete(0, "end")
                    self.ent_val.insert(0, nova_val)

            # --- FOCO E SELEÇÃO ---
            # Pula para o campo validade IMEDIATAMENTE após completar a data
            self.ent_val.focus_set()

            self.ent_val._entry.select_range(0, "end")

            # Validação imediata (exibe alerta se venceu)
            self.after(100, self._validar_regras_validade_instantaneo)

    def _apply_date_mask(self, widget, event):
        if event.keysym in ("BackSpace", "Delete"):
            return

        raw = widget.get()
        digits = "".join(filter(str.isdigit, raw))[:8]
        fmt = digits
        if len(digits) >= 2: fmt = f"{digits[:2]}/{digits[2:]}"
        if len(digits) >= 4: fmt = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
        if fmt != raw:
            widget.delete(0, "end")
            widget.insert(0, fmt)

    def _format_date_mask(self, event=None):
        # Chama a função genérica aplicando ao campo de Validade (self.ent_val)
        self._apply_date_mask(self.ent_val, event)

    def _validar_regras_validade_instantaneo(self):
        val_str = self.ent_val.get().strip()
        if len(val_str) != 10: return

        try:
            dt_val = datetime.strptime(val_str, "%d/%m/%Y")
            hoje = datetime.now()

            # Resetamos o foco para o campo de Fabricação caso haja erro,
            # para forçar o conferente a corrigir a data de origem.

            # 1. Regra: Vencido
            if dt_val < hoje:
                msg = f"ATENÇÃO: Produto VENCIDO (Venc: {val_str})."

                if getattr(global_policies, "bloquear_vencido", False):
                    self.alert("BLOQUEADO", f"{msg}\nRecebimento de vencidos proibido por política.", type="error")
                    self.ent_fab.focus_set()  # Devolve o foco para ele corrigir a Fab
                    self.ent_val.delete(0, "end")  # Limpa a validade inválida
                else:
                    self.alert("Atenção", f"{msg}\nVerifique se a Data de Fabricação está correta.", type="warning")
                    self.ent_fab.focus_set()
                return

            # 2. Regra: Validade Mínima (Shelf Life Crítico)
            item_atual = self.items[self.current_idx]
            sku = item_atual["Sku"]
            prod = products_repo.get_by_sku(sku)

            # Determina dias mínimos (Produto > Família > Global)
            min_days = None
            if prod and prod.get("ValidadeMinimaDias") is not None:
                min_days = int(prod.get("ValidadeMinimaDias"))
            else:
                if prod:
                    fam = families_repo.get_by_nome(prod.get("Familia"))
                    if fam and fam.get("ValidadeMinimaDias") is not None:
                        min_days = int(fam.get("ValidadeMinimaDias"))

            if min_days is None:
                min_days = global_policies.validade_minima_dias

            if min_days is not None:
                restante = (dt_val - hoje).days
                if restante < min_days:
                    self.alert("Validade Curta",
                               f"ALERTA: Restam apenas {restante} dias.\n"
                               f"O mínimo exigido é {min_days} dias.\n\n"
                               "Confira a data de fabricação.", type="warning")
                    self.ent_fab.focus_set()

        except ValueError:
            # Se a data calculada for inválida (ex: 30/02)
            pass

    def _show_stage_form(self):
        # Limpa a tela anterior
        for w in self.main_container.winfo_children(): w.destroy()
        for w in self.footer.winfo_children(): w.destroy()

        if not self.items:
            tk.Label(self.main_container, text="Não há itens.", bg=Colors.BG_APP).pack(pady=20)
            return

        item = self.items[self.current_idx]

        # --- NOVO: Reset da descrição visual para o item atual ---
        self.temp_desc_visual = ""

        # ==============================================================================
        # 1. CABEÇALHO DO LPN E ITEM
        # ==============================================================================
        hdr = tk.Frame(self.main_container, bg=Colors.BG_APP)
        hdr.pack(fill="x", pady=(0, 10))

        # --- LÓGICA DE LISTAGEM DE LPNS DO ITEM ---
        item_id = item["Id"]

        # 1. Busca LPNs salvos no banco
        sql_lpns = "SELECT Lpn FROM RecebimentoLeituras WHERE RecebimentoItemId=? AND Lpn IS NOT NULL AND Estornado = 0 GROUP BY Lpn ORDER BY MIN(DataHora)"
        res_lpns = recebimento_repo.execute_query(sql_lpns, (item_id,))
        lpns_banco = [r['Lpn'] for r in res_lpns if r['Lpn']]

        # 2. Resgata os LPNs que já estavam na memória (ex: Novos que ainda não foram salvos)
        if getattr(self, "_lpn_list_item_id", None) != item_id:
            self._lpn_list_item_id = item_id
            lpns_memoria = []
        else:
            lpns_memoria = getattr(self, "lpns_do_item", [])

        # 3. Combina Banco + Memória sem perder ninguém
        self.lpns_do_item = []
        for lpn in lpns_banco:
            if lpn not in self.lpns_do_item:
                self.lpns_do_item.append(lpn)

        for lpn in lpns_memoria:
            if lpn not in self.lpns_do_item:
                self.lpns_do_item.append(lpn)

        # 4. Garante o atual
        if self.current_lpn and self.current_lpn not in self.lpns_do_item:
            self.lpns_do_item.append(self.current_lpn)

        if self.current_lpn in self.lpns_do_item:
            self.current_lpn_idx = self.lpns_do_item.index(self.current_lpn)
        else:
            self.current_lpn_idx = 0

        # --- NAVEGAÇÃO CENTRALIZADA DO LPN ---
        nav_box = tk.Frame(hdr, bg=Colors.BG_APP)
        nav_box.pack(fill="x", pady=(0, 15))

        # Grid para centralizar o LPN e jogar as setas para as laterais dele
        nav_box.columnconfigure(0, weight=1)
        nav_box.columnconfigure(1, weight=0)
        nav_box.columnconfigure(2, weight=0)
        nav_box.columnconfigure(3, weight=0)
        nav_box.columnconfigure(4, weight=1)

        btn_prev = PillButton(nav_box, text="", icon=load_icon("anterior", 16),
                              variant="outline", width=34, command=self._nav_prev)
        btn_prev.grid(row=0, column=1, padx=15)
        # Desabilita seta Esquerda se for o primeiro LPN
        if self.current_lpn_idx <= 0: btn_prev.state(["disabled"])

        lpn_display = self.current_lpn if self.current_lpn else "NOVO LPN"
        tk.Label(nav_box, text=lpn_display, font=("Segoe UI", 18, "bold"),
                 bg=Colors.BG_APP, fg=Colors.PRIMARY).grid(row=0, column=2)

        btn_next = PillButton(nav_box, text="", icon=load_icon("proximo", 16),
                              variant="outline", width=34, command=self._nav_next)
        btn_next.grid(row=0, column=3, padx=15)
        # Desabilita seta Direita se for o último LPN
        if self.current_lpn_idx >= len(self.lpns_do_item) - 1: btn_next.state(["disabled"])

        # Título (SKU)
        tk.Label(hdr, text=item["Sku"], font=("Segoe UI", 14, "bold"),
                 bg=Colors.BG_APP, fg=Colors.TEXT_MAIN).pack(anchor="w")

        # --- LÓGICA DE TRUNCAMENTO (ADICIONAR "...") ---
        full_desc = item["Descricao"]
        font_desc = tkfont.Font(family="Segoe UI", size=10)

        # Largura máxima disponível (520 do modal - 40 de padding - margem de segurança)
        max_w_desc = 460

        display_desc = full_desc
        if font_desc.measure(full_desc) > max_w_desc:
            avg_char = font_desc.measure("a")
            # Calcula quantos caracteres cabem, reservando espaço para o "..."
            chars_fit = int((max_w_desc - font_desc.measure("...")) / avg_char)
            display_desc = full_desc[:chars_fit] + "..."

        # Label Descrição (Sem wraplength, pois agora cortamos o texto)
        lbl_desc = tk.Label(hdr, text=display_desc, font=("Segoe UI", 10),
                            bg=Colors.BG_APP, fg="#6B7280", anchor="w")
        lbl_desc.pack(anchor="w")

        # Opcional: Adiciona Tooltip nativo simples para mostrar o nome completo ao parar o mouse
        if display_desc != full_desc:
            self._add_simple_tooltip(lbl_desc, full_desc)

        # ==============================================================================
        # 2. ÁREA DE FORMULÁRIO
        # ==============================================================================
        frm = tk.Frame(self.main_container, bg=Colors.BG_APP)
        frm.pack(fill="both", expand=True)

        def _lbl(parent, text):
            tk.Label(parent, text=text, font=("Segoe UI", 9, "bold"),
                     bg=Colors.BG_APP, fg="#374151").pack(anchor="w", pady=(0, 2))

        # --- LINHA 1: IDENTIFICAÇÃO ---
        row1 = tk.Frame(frm, bg=Colors.BG_APP)
        row1.pack(fill="x", pady=(0, 10))
        row1.columnconfigure(0, weight=3)
        row1.columnconfigure(1, weight=1)

        # Coluna EAN
        c1 = tk.Frame(row1, bg=Colors.BG_APP)
        c1.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        _lbl(c1, "Código de Barras")

        f_ean = tk.Frame(c1, bg=Colors.BG_APP)
        f_ean.pack(fill="x")

        # --- ALTERAÇÃO NO BOTÃO SEM GTIN ---
        # Agora ele chama o método _ask_visual_description
        PillButton(f_ean, text="Sem GTIN", variant="outline", height=34, width=100,
                   command=self._ask_visual_description).pack(side="right", padx=(5, 0))

        self.ent_ean = TextField(f_ean, height=34, placeholder="Escaneie ou digite...")
        self.ent_ean.pack(side="left", fill="x", expand=True)

        # --- NOVO: Binds para automação da unidade ---
        # <Return>: Acionado pelo leitor de código de barras
        self.ent_ean._entry.bind("<Return>", self._ao_bipar_ean)
        # <KeyRelease>: Acionado quando o usuário digita ou apaga manualmente
        self.ent_ean._entry.bind("<KeyRelease>", self._ao_alterar_ean)
        # ---------------------------------------------

        # Garante que começa destravado (caso tenha travado no anterior)
        self.ent_ean.configure(state="normal")
        # ----------------------------------------------------

        # Coluna Lote
        c2 = tk.Frame(row1, bg=Colors.BG_APP)
        c2.grid(row=0, column=1, sticky="ew")
        _lbl(c2, "Lote")

        prod_db = products_repo.get_by_sku(item["Sku"])
        eff_lote = "Lote opcional"
        if prod_db:
            eff_lote = getattr(global_policies, "modo_lote", "Lote opcional")
            fam_name = prod_db.get("Familia")
            fam_db = families_repo.get_by_nome(fam_name)
            if fam_db:
                l_fam = fam_db.get("LoteModo")
                if l_fam and l_fam not in ("Herdar", "None"): eff_lote = l_fam
            l_prod = prod_db.get("LoteModo")
            if l_prod and l_prod not in ("Herdar", "None"): eff_lote = l_prod

        self.ent_lote = TextField(c2, height=34, placeholder="")
        self.ent_lote.pack(fill="x")

        # --- LINHA 2: QUALIDADE ---
        tk.Label(frm, text="INSPEÇÃO DE QUALIDADE", font=("Segoe UI", 8, "bold"),
                 fg="#9CA3AF", bg=Colors.BG_APP).pack(anchor="w", pady=(5, 2))

        qc_box = tk.Frame(frm, bg="#F9FAFB", bd=1, relief="solid")
        qc_box.pack(fill="x", pady=(0, 10), ipady=4)

        qc_box.columnconfigure(0, weight=1)
        qc_box.columnconfigure(1, weight=1)

        # Função auxiliar simples para criar o layout (sem setattr dinâmico)
        def _criar_campo_qc(parent, r, c, label):
            f = tk.Frame(parent, bg="#F9FAFB")
            f.grid(row=r, column=c, sticky="ew", padx=10, pady=3)
            tk.Label(f, text=label, bg="#F9FAFB", fg="#374151", font=("Segoe UI", 9)).pack(side="left")
            cb = PillCombobox(f, values=["Sim", "Não"], height=26, width=60)
            cb.set("Sim")
            cb.pack(side="right")
            return cb

        # Declaração EXPLÍCITA dos atributos (Remove o aviso do PyCharm)
        self.cb_emb = _criar_campo_qc(qc_box, 0, 0, "Embalagem Íntegra?")
        self.cb_mat = _criar_campo_qc(qc_box, 0, 1, "Material Íntegro?")
        self.cb_id = _criar_campo_qc(qc_box, 1, 0, "Identificação Correta?")
        self.cb_cert = _criar_campo_qc(qc_box, 1, 1, "Certificado Qualidade?")

        # --- LINHA 3: DATAS E CONTAGEM ---
        row3 = tk.Frame(frm, bg=Colors.BG_APP)
        row3.pack(fill="x", pady=(0, 5))
        row3.columnconfigure(0, weight=1)
        row3.columnconfigure(1, weight=1)

        f_dates = tk.Frame(row3, bg=Colors.BG_APP)
        f_dates.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        f_dates.columnconfigure(0, weight=1)
        f_dates.columnconfigure(1, weight=1)

        # Fab
        fd1 = tk.Frame(f_dates, bg=Colors.BG_APP)
        fd1.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        _lbl(fd1, "Fab:")
        self.ent_fab = TextField(fd1, height=34, placeholder="__/__/____")
        self.ent_fab._entry.bind("<KeyRelease>", self._on_fab_change)
        self.ent_fab.pack(fill="x")

        # Val
        fd2 = tk.Frame(f_dates, bg=Colors.BG_APP)
        fd2.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        _lbl(fd2, "Val:")
        self.ent_val = TextField(fd2, height=34, placeholder="__/__/____")
        self.ent_val._entry.bind("<KeyRelease>", self._format_date_mask)
        self.ent_val.pack(fill="x")

        # Status
        f_st = tk.Frame(f_dates, bg=Colors.BG_APP)
        f_st.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        _lbl(f_st, "Situação")
        self.cb_status = PillCombobox(f_st, values=["Aprovado", "Reprovado"], height=34)
        self.cb_status.set("Aprovado")
        self.cb_status.pack(fill="x")

        # Quantidade
        f_qtd_area = tk.Frame(row3, bg=Colors.BG_APP)
        f_qtd_area.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0))

        _lbl(f_qtd_area, "Quantidade")

        self.ent_qtd = TextField(f_qtd_area, height=40, placeholder="0")
        self.ent_qtd.pack(fill="x")
        self.ent_qtd._entry.config(font=("Segoe UI", 14, "bold"))

        prod = products_repo.get_by_sku(item["Sku"])
        units_list = ["UN"]
        if prod:
            units_list = [prod.get("Unidade", "UN")]
            for cam in prod.get("Camadas", []):
                if cam.get("Unidade"): units_list.append(cam.get("Unidade"))

        f_und = tk.Frame(f_qtd_area, bg=Colors.BG_APP)
        f_und.pack(fill="x", pady=(5, 0))
        tk.Label(f_und, text="Unidade:", font=("Segoe UI", 8), bg=Colors.BG_APP, fg="#6B7280").pack(side="left")
        self.cb_und = PillCombobox(f_und, values=list(set(units_list)), width=80, height=28)
        if units_list: self.cb_und.set(units_list[0])
        self.cb_und.pack(side="right")

        # ==============================================================================
        # 3. RODAPÉ
        # ==============================================================================
        # A navegação (Setinhas) foi movida para o topo da tela, abraçando o LPN

        f_act = tk.Frame(self.footer, bg=Colors.BG_APP)
        f_act.pack(side="right")

        PillButton(f_act, text="Novo LPN", variant="outline", width=80,
                   command=lambda: self._save_and_action("new_lpn")).pack(side="left", padx=(0, 10))

        # =========================================================
        # BOTÃO DINÂMICO: "Confirmar Item" vs "Finalizar"
        # =========================================================
        is_ultimo_item = (self.current_idx == len(self.items) - 1)

        if is_ultimo_item:
            texto_botao = "Finalizar"
            acao_botao = "finish"
        else:
            texto_botao = "Confirmar Item"
            acao_botao = "next_item"

        PillButton(f_act, text=texto_botao, variant="primary", width=140,
                   command=lambda a=acao_botao: self._save_and_action(a)).pack(side="left")

        # 1. EAN -> Lote (Já tratado no bind específico do scanner, mas reforçamos para digitação manual)
        # Nota: O _ao_bipar_ean já cuida do Enter no EAN, vamos ajustar ele abaixo.

        # 2. Lote -> Fabricação
        self.ent_lote._entry.bind("<Return>", lambda e: self.ent_fab.focus_set())

        # 3. Fabricação -> Validade
        # (Já existe o salto automático ao completar a data, mas adicionamos Enter por garantia)
        self.ent_fab._entry.bind("<Return>", lambda e: self.ent_val.focus_set())

        # 4. Validade -> Quantidade
        self.ent_val._entry.bind("<Return>", lambda e: self.ent_qtd.focus_set())

        # 5. Quantidade -> Salvar (Opcional, agiliza o processo)
        self.ent_qtd._entry.bind("<Return>", lambda e: self._save_and_action("new_lpn"))

        # Foco Inicial: Sempre no Código de Barras
        self.ent_ean.focus_set()

    def _add_simple_tooltip(self, widget, text):
        def enter(event):
            self._tooltip_w = tk.Toplevel(widget)
            self._tooltip_w.wm_overrideredirect(True)
            self._tooltip_w.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
            lbl = tk.Label(self._tooltip_w, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                           font=("Segoe UI", 9))
            lbl.pack()

        def leave(event):
            if hasattr(self, '_tooltip_w'):
                self._tooltip_w.destroy()
                del self._tooltip_w

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _ask_visual_description(self):
        # Modal menor e mais limpo
        top = SaaSModal(self, title="Descrição Visual", width=420, height=300)

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # Instrução curta e direta
        tk.Label(frm, text="Descreva o produto:", font=("Segoe UI", 10, "bold"),
                 bg=Colors.BG_APP, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        # Área de Texto (Visual de Input grande)
        # Borda manual para parecer com os outros campos
        txt_frame = tk.Frame(frm, bg=Colors.BG_INPUT, bd=1, relief="solid")
        txt_frame.pack(fill="both", expand=True, pady=(0, 20))

        # Widget de texto
        self.txt_desc_input = tk.Text(txt_frame, height=5, font=("Segoe UI", 10),
                                      bd=0, bg=Colors.BG_INPUT, highlightthickness=0,
                                      padx=10, pady=10)
        self.txt_desc_input.pack(fill="both", expand=True)
        self.txt_desc_input.focus_set()

        def _confirmar():
            desc = self.txt_desc_input.get("1.0", "end").strip()

            if not desc:
                top.alert("Atenção", "Descrição visual obrigatória", focus_widget=self.txt_desc_input)
                return

            item_atual = self.items[self.current_idx]

            # Chama o repositório novo
            recebimento_repo.registrar_divergencia_visual(
                pr_code=self.pr_code,
                sku_selecionado=item_atual['Sku'],
                ean_lido="",
                descricao_visual=desc,
                qtd=0,
                usuario="Conferente"
            )

            self.temp_desc_visual = desc

            self.ent_ean.delete(0, "end")
            self.ent_ean.insert(0, "SEM GTIN")
            self.ent_ean.configure(state="disabled")

            top.close()

            # --- CORREÇÃO: Foco vai para o LOTE ---
            self.ent_lote.focus_set()

        # Botões Rodapé
        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(side="bottom", fill="x")

        PillButton(btn_box, text="Salvar", variant="success", command=_confirmar).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _save_and_action(self, action):
        val_ean = self.ent_ean.get().strip()
        val_qtd = self.ent_qtd.get().strip()
        usuario_atual = getattr(self, "usuario_atual", "Conferente")

        # 1. Validações Básicas de Input
        if not val_qtd or Utils.safe_float(val_qtd) <= 0:
            self.alert("Erro", "Informe uma quantidade válida.", focus_widget=self.ent_qtd)
            return

        qtd_digitada = Utils.safe_float(val_qtd)
        und_digitada = self.cb_und.get().strip().upper()

        item_atual = self.items[self.current_idx]
        qtd_nota = float(item_atual.get("Qtd", 0))
        und_nota = str(item_atual.get("Und", "")).strip().upper()
        sku_item = item_atual["Sku"]

        # --- VALIDACAO DE PRODUTO (EAN) ---
        if val_ean != "SEM GTIN":
            ean_xml = str(item_atual.get("EanNota") or "").strip().upper()
            prod_db = products_repo.get_by_sku(sku_item)
            ean_db = str(prod_db.get("Ean", "")).strip().upper() if prod_db else ""
            ean_bipado = val_ean.upper()

            if not ((ean_xml and ean_bipado == ean_xml) or (ean_db and ean_bipado == ean_db)):
                self.alert("Produto Incorreto", "Código bipado não corresponde ao item.", type="error",
                           focus_widget=self.ent_ean)
                return

        # --- VALIDAÇÃO DE DATAS ---
        val_str = self.ent_val.get().strip()
        if len(val_str) == 10:
            try:
                dt_val = datetime.strptime(val_str, "%d/%m/%Y")
                hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                if dt_val < hoje:
                    if getattr(global_policies, "bloquear_vencido", False):
                        self.alert("Bloqueio", "Produto VENCIDO.", type="error")
                        return
            except:
                pass

        # ====================================================================
        # LÓGICA DE CONFERÊNCIA CEGA (COM CONVERSÃO DE UNIDADES)
        # ====================================================================

        res_conv = products_repo.converter_unidades(
            sku=sku_item,
            qtd=qtd_digitada,
            und_origem=und_digitada,
            und_destino=und_nota
        )

        if not res_conv['sucesso']:
            self.alert("Erro Conversão", f"Falha ao converter unidades: {res_conv.get('erro')}", type="error")
            return

        qtd_digitada_convertida = res_conv['qtd_convertida']

        # 1. Busca a quantidade que JÁ FOI salva no banco (de outros LPNs deste item)
        itens_banco = recebimento_repo.list_itens_por_pr(self.pr_code)
        item_fresco = next((i for i in itens_banco if i["Id"] == item_atual["Id"]), item_atual)

        qtd_ja_coletada = float(item_fresco.get("QtdColetada", 0))

        # Desconta a quantidade caso o usuário esteja reeditando este mesmo LPN
        # (evita somar em duplicidade se ele corrigir a quantidade de um LPN atual)
        dados_db = item_fresco.get("dados_qualidade", {})
        if isinstance(dados_db, str):
            try:
                import json
                dados_db = json.loads(dados_db)
            except:
                dados_db = {}

        qtd_lpn_antigo = 0.0
        if dados_db.get("lpn_vinculado") == self.current_lpn:
            qtd_lpn_antigo = float(dados_db.get("qtd", 0))

        # REPARO: Se o banco não trouxe o LPN (comum em salvamento parcial), puxamos da memória de edição do Voltar
        if qtd_lpn_antigo == 0.0 and getattr(self, "_qtd_original_edicao", 0.0) > 0:
            qtd_lpn_antigo = self._qtd_original_edicao

        # Calcula a soma acumulada de todos os LPNs
        qtd_total_acumulada = (qtd_ja_coletada - qtd_lpn_antigo) + qtd_digitada_convertida

        # 2. SE FOR "CONFIRMAR ITEM" -> Valida rigorosamente se o total bateu com a nota
        if action in ["finish", "next_item"]:
            diferenca = abs(qtd_total_acumulada - qtd_nota)

            if diferenca > 0.001:
                # ERRO NA CONTAGEM
                tentativa_atual = recebimento_repo.incrementar_erro_contagem(
                    item_id=item_atual["Id"],
                    qtd_errada=qtd_digitada,
                    usuario=usuario_atual,
                    ean_lido=val_ean,
                    lpn=self.current_lpn
                )

                if tentativa_atual < 3:
                    msg_erro = f"Quantidade total não confere com a nota. Tentativa {tentativa_atual}/3."
                    self.alert("Divergência", msg_erro, type="warning", focus_widget=self.ent_qtd)
                    self.ent_qtd._entry.select_range(0, "end")
                    return
                else:
                    self.alert("Bloqueio Fiscal",
                               "Divergência persistente após 3 tentativas.\n\n"
                               "Item bloqueado para análise",
                               type="error")
                    obs_visual = getattr(self, "temp_desc_visual", "")

                    # ====================================================================
                    # CORREÇÃO DEFINITIVA: SALVAR O LPN ANTES DE BLOQUEAR O ITEM
                    # Como a quantidade é menor, o sistema caía aqui e pulava o salvamento,
                    # deixando o LPN vazio. Agora forçamos a gravação do LPN e de seus
                    # respectivos Lote e Validade antes de aplicar o bloqueio fiscal.
                    # ====================================================================
                    recebimento_repo.salvar_item_conferencia(
                        item_id=item_atual["Id"],
                        dados_conferencia={
                            "lpn": self.current_lpn,
                            "ean_lido": val_ean,
                            "lote": self.ent_lote.get(),
                            "emb_integra": self.cb_emb.get(),
                            "mat_integro": self.cb_mat.get(),
                            "ident_correta": self.cb_id.get(),
                            "fabricacao": self.ent_fab.get(),
                            "tem_certificado": self.cb_cert.get(),
                            "validade": self.ent_val.get(),
                            "status_qual": self.cb_status.get(),
                            "qtd": 0,
                            "unidade": und_digitada,
                            "usuario": usuario_atual,
                            "obs_visual": obs_visual,
                            "eh_parcial": False
                        }
                    )

                    # Após o LPN estar salvo fisicamente, registra o erro no log e bloqueia
                    recebimento_repo.registrar_erro_tentativa(
                        self.pr_code,
                        item_atual["Id"],
                        qtd_total_acumulada,
                        usuario_atual,
                        obs_texto=obs_visual,
                        ean_lido=val_ean,
                        lpn=self.current_lpn
                    )

                    self._houve_mudanca = True
                    self.close()
                    return

        # 3. SE FOR "NOVO LPN" -> Apenas acumula, mas impede que passe da quantidade máxima da NF sem querer
        else:
            if qtd_total_acumulada > qtd_nota + 0.001:
                self.alert("Excesso de Quantidade",
                           "A soma dos LPNs informados ultrapassa o total esperado da nota fiscal.",
                           type="warning", focus_widget=self.ent_qtd)
                self.ent_qtd._entry.select_range(0, "end")
                return

        # ====================================================================
        # SUCESSO (Quantidade Bateu)
        # ====================================================================
        item_atual["TentativasErro"] = 0

        # Salva as informações no Banco de Dados
        sucesso, msg = recebimento_repo.salvar_item_conferencia(
            item_id=item_atual["Id"],
            dados_conferencia={
                "lpn": self.current_lpn,
                "ean_lido": val_ean,
                "lote": self.ent_lote.get(),
                "emb_integra": self.cb_emb.get(),
                "mat_integro": self.cb_mat.get(),
                "ident_correta": self.cb_id.get(),
                "fabricacao": self.ent_fab.get(),
                "tem_certificado": self.cb_cert.get(),
                "validade": self.ent_val.get(),
                "status_qual": self.cb_status.get(),
                "qtd": qtd_digitada,
                "unidade": und_digitada,
                "usuario": usuario_atual,
                "obs_visual": getattr(self, "temp_desc_visual", ""),
                "eh_parcial": (action == "new_lpn")
            }
        )

        if not sucesso:
            self.alert("Erro", f"Falha ao salvar dados:\n{msg}", type="error")
            return

        novo_status, _ = recebimento_repo.recalcular_status_geral(self.pr_code)
        self._houve_mudanca = True

        # ====================================================================
        # 1. DISPARA EVENTOS (Dados Salvos)
        # Executamos isso ANTES da interface. Assim, se o usuário fechar a tela
        # bruscamente, o recebimento já estará garantido e salvo no sistema.
        # ====================================================================
        if recebimento_repo.event_bus:
            pr_seguro = self.pr_code

            recebimento_repo.event_bus.publish("pr_atualizado", {"pr": pr_seguro})
            if novo_status == StatusPR.CONCLUIDO:
                recebimento_repo.event_bus.publish("recebimento_concluido", {
                    "pr": pr_seguro,
                    "usuario": usuario_atual,
                    "data_conclusao": datetime.now()
                })

        # ====================================================================
        # 2. ROTEADOR DE TELA E ALERTAS (Blindado contra cliques duplos)
        # ====================================================================
        try:
            if not self.winfo_exists():
                return

            if hasattr(self, "_salvar_estado_temporario"):
                self._salvar_estado_temporario()

            if action == "new_lpn":
                self._last_form_state = {
                    "ean": val_ean,
                    "lote": self.ent_lote.get(),
                    "fab": self.ent_fab.get(),
                    "val": self.ent_val.get(),
                    "qtd": self.ent_qtd.get(),
                    "qtd_convertida": qtd_digitada_convertida,
                    "und": und_digitada,
                    "emb": self.cb_emb.get(),
                    "mat": self.cb_mat.get(),
                    "id": self.cb_id.get(),
                    "cert": self.cb_cert.get(),
                    "status": self.cb_status.get(),
                    "lpn": self.current_lpn,
                    "desc_visual": getattr(self, "temp_desc_visual", "")
                }

                self.current_lpn = None
                self.alert("LPN Salvo", "LPN registrado.",
                           type="info")
                if self.winfo_exists():
                    self._show_stage_lpn()

            elif action == "next_item":
                self.alert("Sucesso", "Item conferido com sucesso!", type="info")
                if self.winfo_exists():
                    self.current_idx += 1
                    self.current_lpn = None
                    self._decide_flow()

            elif action == "finish":
                self.alert("Sucesso", "Último item conferido com sucesso!", type="success")
                if self.winfo_exists():
                    self.close()

        except Exception:
            pass

    def _decide_flow(self):
        self._last_form_state = None

        item = self.items[self.current_idx]

        # Verifica se já existe dados de qualidade/LPN salvos neste item
        dados_salvos = item.get("dados_qualidade", {})
        lpn_vinculado = dados_salvos.get("lpn_vinculado")

        if lpn_vinculado:
            # Se já tem LPN, carrega ele e vai direto pro formulário (Modo Edição/Visualização)
            self.current_lpn = lpn_vinculado
            self._qtd_original_edicao = float(dados_salvos.get("qtd", item.get("QtdColetada", 0)))
            self._show_stage_form()

            # Preenche os campos visualmente puxando PRIMEIRO o que o usuário digitou, e não a Nota
            self.ent_ean.configure(state="normal")
            self.ent_ean.delete(0, "end")
            ean_salvo = dados_salvos.get("ean_lido", item.get("EanNota", ""))
            self.ent_ean.insert(0, ean_salvo)

            # Trava o campo caso tenha sido descrição visual
            if ean_salvo == "SEM GTIN":
                self.ent_ean.configure(state="disabled")

            self.ent_lote.delete(0, "end")
            self.ent_lote.insert(0, dados_salvos.get("lote", item.get("Lote", "")))

            self.ent_val.delete(0, "end")
            self.ent_val.insert(0, dados_salvos.get("validade", item.get("Val", "")))

            self.ent_qtd.delete(0, "end")
            self.ent_qtd.insert(0, str(float(item.get("QtdColetada", 0))))

            # Restaura comboboxes de qualidade
            if "embalagem_integra" in dados_salvos: self.cb_emb.set(dados_salvos["embalagem_integra"])
            if "material_integro" in dados_salvos: self.cb_mat.set(dados_salvos["material_integro"])
            if "identificacao_correta" in dados_salvos: self.cb_id.set(dados_salvos["identificacao_correta"])
            if "certificado" in dados_salvos: self.cb_cert.set(dados_salvos["certificado"])
            if "status_qualidade" in dados_salvos: self.cb_status.set(dados_salvos["status_qualidade"])

        else:
            # Se não tem LPN, limpa a memória temporária e pede LPN novo
            self.current_lpn = None
            self._show_stage_lpn()

    def _carregar_lpn_selecionado(self):
        item_id = self.items[self.current_idx]["Id"]

        # --- NOVO: VERIFICA SE TEMOS UM CACHE TEMPORÁRIO (LPN DIGITADO, MAS NÃO SALVO) ---
        cache = getattr(self, "_lpn_cache", {}).get(self.current_lpn)
        if cache:
            self._last_form_state = {
                "ean": cache["ean"],
                "lote": cache["lote"],
                "fab": cache["fab"],
                "val": cache["val"],
                "qtd": cache["qtd"],
                "qtd_convertida": Utils.safe_float(cache["qtd"]),
                "und": cache["und"],
                "emb": cache["emb"],
                "mat": cache["mat"],
                "id": cache["id"],
                "cert": cache["cert"],
                "status": cache["status"],
                "lpn": self.current_lpn,
                "desc_visual": cache["desc_visual"]
            }
            self._voltar_para_form()
            return

        # 1. Busca a QTD e o EAN exatos daquele LPN na tabela de Leituras
        # CORREÇÃO: Agora buscamos também o EanLido específico deste LPN
        sql_leitura = "SELECT ISNULL(SUM(Qtd), 0) as Qtd, MAX(EanLido) as EanLido FROM RecebimentoLeituras WHERE RecebimentoItemId=? AND Lpn=? AND Estornado = 0"
        res_leitura = recebimento_repo.execute_query(sql_leitura, (item_id, self.current_lpn))

        qtd_base = float(res_leitura[0]['Qtd']) if res_leitura else 0.0
        ean_lido_db = res_leitura[0]['EanLido'] if res_leitura and res_leitura[0].get('EanLido') else None

        # Converte para a unidade da tela
        und_nota = str(self.items[self.current_idx].get("Und", "")).strip().upper()
        prod_db = products_repo.get_by_sku(self.items[self.current_idx]["Sku"])
        und_base = prod_db.get("Unidade", "UN") if prod_db else "UN"

        if qtd_base > 0:
            res_conv = products_repo.converter_unidades(self.items[self.current_idx]["Sku"], qtd_base, und_base,
                                                        und_nota)
            qtd_tela = res_conv['qtd_convertida'] if res_conv['sucesso'] else qtd_base
        else:
            qtd_tela = 0.0

        # 2. Busca Lote e Validade específicos na tabela Lpns
        sql_lpn = "SELECT Lote, Validade FROM Lpns WHERE Lpn=?"
        res_lpn = recebimento_repo.execute_query(sql_lpn, (self.current_lpn,))

        dados_item = self.items[self.current_idx].get("dados_qualidade", {})

        lote = ""
        val = ""
        if res_lpn:
            lote = res_lpn[0].get("Lote") or ""
            val = res_lpn[0].get("Validade") or ""
            if hasattr(val, "strftime"): val = val.strftime("%d/%m/%Y")

        # Fallback de segurança: se o banco falhar ou trouxer vazio, resgata da memória do item
        if not lote:
            lote = dados_item.get("lote", self.items[self.current_idx].get("Lote", ""))
        if not val:
            val = dados_item.get("validade", self.items[self.current_idx].get("Val", ""))

        # --- CORREÇÃO: Define qual EAN mostrar ---
        # Prioridade 1: O EAN salvo no banco para este LPN específico (incluindo "SEM GTIN")
        # Prioridade 2: Fallback para a Nota Fiscal (caso seja um item muito antigo/órfão)
        ean_final = ean_lido_db if ean_lido_db else dados_item.get("ean_lido",
                                                                   self.items[self.current_idx].get("EanNota", ""))

        # 3. Monta o estado temporário e invoca a função de Voltar para repopular a tela perfeitamente
        self._last_form_state = {
            "ean": ean_final,
            "lote": lote,
            "fab": dados_item.get("fabricacao", ""),
            "val": val,
            "qtd": str(qtd_tela),
            "qtd_convertida": qtd_tela,
            "und": und_nota,
            "emb": dados_item.get("embalagem_integra", "Sim"),
            "mat": dados_item.get("material_integro", "Sim"),
            "id": dados_item.get("identificacao_correta", "Sim"),
            "cert": dados_item.get("possui_certificado", "Sim"),
            "status": dados_item.get("status_qualidade", "Aprovado"),
            "lpn": self.current_lpn,
            "desc_visual": dados_item.get("obs_visual", "")
        }
        self._voltar_para_form()

    def _salvar_estado_temporario(self):
        if not getattr(self, "current_lpn", None): return
        if not hasattr(self, "_lpn_cache"): self._lpn_cache = {}

        if hasattr(self, "ent_qtd") and self.ent_qtd.winfo_exists():
            self._lpn_cache[self.current_lpn] = {
                "ean": self.ent_ean.get(),
                "lote": self.ent_lote.get(),
                "fab": self.ent_fab.get(),
                "val": self.ent_val.get(),
                "qtd": self.ent_qtd.get(),
                "und": self.cb_und.get(),
                "emb": self.cb_emb.get(),
                "mat": self.cb_mat.get(),
                "id": self.cb_id.get(),
                "cert": self.cb_cert.get(),
                "status": self.cb_status.get(),
                "desc_visual": getattr(self, "temp_desc_visual", "")
            }

    def _nav_prev(self):
        if hasattr(self, "lpns_do_item") and self.current_lpn_idx > 0:
            self._salvar_estado_temporario()
            self.current_lpn_idx -= 1
            self.current_lpn = self.lpns_do_item[self.current_lpn_idx]
            self._carregar_lpn_selecionado()

    def _nav_next(self):
        if hasattr(self, "lpns_do_item") and self.current_lpn_idx < len(self.lpns_do_item) - 1:
            self._salvar_estado_temporario()
            self.current_lpn_idx += 1
            self.current_lpn = self.lpns_do_item[self.current_lpn_idx]
            self._carregar_lpn_selecionado()

    def _ao_bipar_ean(self, event):
        # Quando o scanner dá "Enter", validamos e travamos a unidade se for caixa
        self._verificar_e_travar_unidade()

        self.ent_lote.focus_set()
        self.ent_lote._entry.select_range(0, "end") # Seleciona caso já tenha algo escrito

    def _ao_alterar_ean(self, event):
        # Se o usuário apagou o texto (campo vazio), destrava a combo
        texto = self.ent_ean.get().strip()
        if not texto:
            self.cb_und.configure(state="normal")
            # Opcional: Volta para a unidade padrão se quiser
            # self.cb_und.set("UN")
        else:
            # Se ele digitou algo, verifica se já formou um código válido
            self._verificar_e_travar_unidade()

    def _verificar_e_travar_unidade(self):
        sku_atual = self.items[self.current_idx]["Sku"]
        gtin_digitado = self.ent_ean.get().strip()

        # Chama o cérebro (Repo)
        unidade_detectada = None

        prod_bipado, dados_emb = products_repo.identificar_por_codigo(gtin_digitado)

        # Trava de segurança: Garante que o código de barras bipado
        # realmente pertence ao SKU que está aberto na tela de conferência
        if prod_bipado and prod_bipado.get("Sku") == sku_atual:
            if dados_emb:
                unidade_detectada = dados_emb.get("Unidade")

        if unidade_detectada:
            # SUCESSO: Encontrou vínculo!

            # 1. Muda a combobox para a unidade certa (ex: CX)
            self.cb_und.set(unidade_detectada)

            # 2. TRAVA a combobox (Read-only)
            # O usuário não pode mudar porque o sistema TEM CERTEZA que é uma caixa
            self.cb_und.configure(state="disabled")

            # (Opcional) Feedback visual: Piscar verde ou algo sutil poderia vir aqui

        else:
            # Se não reconheceu o código (ex: etiqueta nova),
            # DESTRAVA para o usuário escolher manualmente
            self.cb_und.configure(state="normal")

    def close(self, event=None):
        # Só chama o callback se passar True ou False (dependendo da mudança)
        if self.on_close_cb:
            self.on_close_cb(self._houve_mudanca)

        # Chama o fechamento visual (sem chamar o cb do pai para não duplicar)
        self.grab_release()
        self.overlay.destroy()
        self.destroy()
        self.top_parent.focus_force()


class SupervisorAuthDialog(SaaSModal):
    def __init__(self, parent, on_success):
        super().__init__(parent, title="Autorização de Supervisor", width=350, height=220)
        self.on_success = on_success

        frm = ttk.Frame(self.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Esta ação requer permissão elevada.",
                 fg="#DC2626", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 10))

        ttk.Label(frm, text="Senha do Supervisor:", style="TLabel").pack(anchor="w")

        self.ent_pass = TextField(frm, height=34)
        self.ent_pass._entry.config(show="●")
        self.ent_pass.pack(fill="x", pady=(5, 15))
        self.ent_pass.focus_set()

        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(fill="x")

        PillButton(btn_box, text="Confirmar", variant="primary", command=self._check).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

        self.bind("<Return>", lambda e: self._check())

    def _check(self):
        senha_digitada = self.ent_pass.get()

        # Vai buscar a senha correta ao cofre (.env) de forma segura
        import os
        senha_correta = os.getenv("SUPERVISOR_PASS", "admin")  # Mantém admin como fallback em desenvolvimento

        # O ideal num sistema final é comparar usando a biblioteca 'bcrypt',
        # mas comparando strings limpas provindas do .env já mitiga o risco de código exposto.
        if senha_digitada == senha_correta:
            self.on_success()
            self.close()
        else:
            self.alert("Acesso Negado", "Senha incorreta.", type="error", focus_widget=self.ent_pass)

class ActivityCard(RoundedCard):
    def __init__(self, parent, data, on_action=None):
        super().__init__(parent, radius=10, padding=(15, 15, 15, 15))

        self.data = data
        self.on_action = on_action

        status = data.get("Status")

        # Configuração Padrão
        self.accent_color = Colors.PRIMARY
        self.activity_type = "ATIVIDADE"
        self.status_detail = status
        self.btn_text = "ABRIR"
        self.btn_variant = "primary"

        # --- REGRAS VISUAIS COM CONSTANTES ---

        # 1. EM ANDAMENTO (Amarelo)
        if status == StatusPR.EM_CONFERENCIA:
            self.accent_color = "#F59E0B"
            self.activity_type = "CONFERÊNCIA"
            self.status_detail = "Em Andamento"
            self.btn_text = "CONTINUAR"
            self.btn_variant = "outline"

        # 2. PROBLEMAS / BLOQUEIOS (Vermelho)
        # Agrupamos todos os status ruins aqui
        elif status in [StatusPR.DIVERGENCIA, StatusPR.BLOQUEADO_FISCAL, StatusPR.AGUARDANDO_DECISAO]:
            self.accent_color = "#EF4444"
            self.activity_type = "DIVERGÊNCIA"
            self.status_detail = "Bloqueado Fiscal"
            self.btn_text = "RESOLVER"
            self.btn_variant = "outline"

        # 3. AGUARDANDO (Azul)
        elif status == StatusPR.AGUARDANDO_CONF:
            self.accent_color = Colors.PRIMARY
            self.activity_type = "CONFERÊNCIA"
            self.status_detail = "Aguardando Início"
            self.btn_text = "CONFERIR"
            self.btn_variant = "primary"

        body = self.content
        body.columnconfigure(2, weight=1)

        # 1. Faixa Lateral
        strip = tk.Frame(body, bg=self.accent_color, width=4)
        strip.grid(row=0, column=0, sticky="ns", padx=(0, 0))

        # 2. Identificação (Esquerda)
        id_box = tk.Frame(body, bg=Colors.BG_CARD)
        id_box.grid(row=0, column=1, sticky="w", padx=(12, 15))

        lbl_type = tk.Label(
            id_box, text=self.activity_type, font=("Segoe UI", 10, "bold"),
            fg=self.accent_color, bg=Colors.BG_CARD, anchor="w"
        )
        lbl_type.pack(anchor="w")

        lbl_status = tk.Label(
            id_box, text=self.status_detail.upper(), font=("Segoe UI", 8, "bold"),
            fg=Colors.TEXT_HINT, bg=Colors.BG_CARD, anchor="w"
        )
        lbl_status.pack(anchor="w", pady=(2, 0))

        # 3. Informações (Centro)
        info_frame = tk.Frame(body, bg=Colors.BG_CARD)
        info_frame.grid(row=0, column=2, sticky="nsew")

        lbl_title = tk.Label(info_frame, text=data["Fornecedor"],
                             font=("Segoe UI", 11, "bold"),
                             fg=Colors.TEXT_MAIN, bg=Colors.BG_CARD, anchor="w")
        lbl_title.pack(fill="x")

        docs_text = f"NF: {data['Nfe']}  •  OC: {data['Oc']}"
        lbl_sub = tk.Label(info_frame, text=docs_text,
                           font=("Segoe UI", 9),
                           fg="#6B7280", bg=Colors.BG_CARD, anchor="w")
        lbl_sub.pack(fill="x", pady=(2, 6))

        raw_date = data.get('DataChegada', '-')
        display_date = raw_date if raw_date and raw_date != "-" else "Pendente"

        stats_text = f"{int(data['QtdSkus'])} Itens  •  Início: {display_date}"

        lbl_stats = tk.Label(info_frame, text=stats_text,
                             font=("Segoe UI", 9),
                             fg=Colors.TEXT_MAIN, bg=Colors.BG_CARD, anchor="w")
        lbl_stats.pack(fill="x")

        # 4. Container de Ações (Direita)
        btn_frame = tk.Frame(body, bg=Colors.BG_CARD)
        btn_frame.grid(row=0, column=3, sticky="e", padx=(10, 0))

        self.btn = PillButton(btn_frame, text=self.btn_text,
                              variant=self.btn_variant,
                              command=self._on_click,
                              height=36)
        self.btn.pack(side="left")

    def _on_click(self):
        if self.on_action:
            self.on_action(self.data, action_type="main")

    def _on_cancel_click(self):
        if self.on_action:
            self.on_action(self.data, action_type="cancel")


class SegmentedButton(tk.Canvas):
    def __init__(self, parent, variable, options, command=None, height=34, width=None, **kw):
        """
        options: Lista de tuplas [("Texto", "Valor"), ("Texto2", "Valor2")]
        """
        self._btn_options = options
        self._var = variable
        self._cmd = command

        self._bg_off = Colors.BG_INPUT
        self._bg_on = Colors.PRIMARY
        self._fg_off = Colors.TEXT_MAIN
        self._fg_on = "#ffffff"
        self._border = Colors.BORDER

        n_opts = len(options) if options else 1
        self._h = int(height)
        self._fixed_w = int(width) if width else (n_opts * 90)
        self._radius = 6

        super().__init__(parent, height=self._h, width=self._fixed_w, bd=0, highlightthickness=0, bg=Colors.BG_APP,
                         **kw)

        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._draw)

        self._trace_id = self._var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def set_options(self, new_options):
        self._btn_options = new_options
        self._draw()

    def destroy(self):
        if self._trace_id:
            try:
                self._var.trace_remove("write", self._trace_id)
            except Exception:
                pass
        super().destroy()

    def _draw(self, _event=None):
        if not self.winfo_exists(): return

        self.delete("all")
        w = self.winfo_width()
        if w <= 1: w = self._fixed_w
        h = self._h

        n = len(self._btn_options)
        if n == 0: return

        seg_w = w / n
        current_val = self._var.get()

        self._rounded_rect(0, 0, w, h, self._radius, self._border, "")

        for i, (label, val) in enumerate(self._btn_options):
            x0 = i * seg_w
            x1 = x0 + seg_w

            is_selected = (str(val) == str(current_val))

            bg = self._bg_on if is_selected else self._bg_off
            fg = self._fg_on if is_selected else self._fg_off

            pad = 1
            self.create_rectangle(x0 + pad, pad, x1 - pad, h - pad, fill=bg, outline="", width=0)

            if i < n - 1 and not is_selected and str(self._btn_options[i + 1][1]) != str(current_val):
                self.create_line(x1, 4, x1, h - 4, fill=self._border, width=1)

            font_w = "bold" if is_selected else "normal"
            self.create_text((x0 + x1) / 2, h / 2, text=label, fill=fg,
                             font=("Segoe UI", 9, font_w))

    def _rounded_rect(self, x0, y0, x1, y1, r, fill, outline):
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0
        ]
        return self.create_polygon(points, smooth=True, fill=fill, outline=outline)

    def _on_click(self, event):
        if not self.winfo_exists(): return
        w = self.winfo_width()
        if w <= 1: w = self._fixed_w
        n = len(self._btn_options)
        if n == 0: return

        seg_w = w / n
        idx = int(event.x // seg_w)
        if 0 <= idx < n:
            val = self._btn_options[idx][1]
            self._var.set(val)
            if self._cmd:
                self._cmd()


def render_kardex_modal(parent, sku):
    # 1. Busca dados
    repo = MovementsRepo()
    movimentos = repo.get_kardex_sku(sku)

    if not movimentos:
        dlg = SaaSDialog(
            parent,
            "Extrato",
            f"Nenhuma movimentação para {sku}.",
            buttons=[("OK", True, "primary")],
            icon_name="alert"  # ou 'alert_yellow' se preferir
        )
        parent.wait_window(dlg)  # Pausa até o usuário fechar
        return

    # 2. Cria o Modal
    top = SaaSModal(parent, title=f"Extrato: {sku}", width=800, height=600)

    # 3. Processa o Saldo Acumulado (Matemática Pura, sem Pandas)
    saldo_atual = 0.0
    rows_view = []

    for mov in movimentos:
        qtd = float(mov.get("QtdMovimentada", 0))
        saldo_atual += qtd

        # Formata Data
        dt = mov.get("DataMovimento")
        try:
            if hasattr(dt, "strftime"):
                dt_fmt = dt.strftime("%d/%m/%Y %H:%M")
            else:
                # Caso venha string do banco
                dt_obj = datetime.strptime(str(dt)[:19], "%Y-%m-%d %H:%M:%S")
                dt_fmt = dt_obj.strftime("%d/%m/%Y %H:%M")
        except:
            dt_fmt = str(dt)

        # Ícone Visual (Texto)
        if qtd > 0:
            op_icon = "🟢 Entrada"
            cor_qtd = Colors.SUCCESS
        elif qtd < 0:
            op_icon = "🔴 Saída"
            cor_qtd = Colors.DANGER
        else:
            op_icon = "🔵 Ajuste"
            cor_qtd = Colors.PRIMARY

        rows_view.append({
            "data": dt_fmt,
            "operacao": op_icon,
            "qtd": f"{qtd:+.2f}",  # Formata com sinal (+10 ou -10)
            "saldo": f"{saldo_atual:.2f}",
            "usuario": mov.get("Usuario", ""),
            "doc": mov.get("DocumentoRef", "") or "-",
            "lpn": mov.get("Lpn", "") or "-",
            "_text_color": cor_qtd  # Dica visual para sua StandardTable pintar o texto se quiser
        })

    # 4. Define Colunas da Tabela
    cols = [
        {"id": "data", "title": "Data/Hora", "width": 130, "anchor": "center"},
        {"id": "operacao", "title": "Operação", "width": 100, "anchor": "w"},
        {"id": "doc", "title": "Documento", "width": 120, "anchor": "w"},
        {"id": "lpn", "title": "LPN / Caixa", "width": 100, "anchor": "center"},
        {"id": "qtd", "title": "Movimento", "width": 80, "anchor": "e"},
        {"id": "saldo", "title": "Saldo", "width": 80, "anchor": "e"},
        {"id": "usuario", "title": "Usuário", "width": 100, "anchor": "w"},
    ]

    # 5. Renderiza a Tabela
    # Usamos uma função fake de fetch pois já temos os dados em memória
    def _fetch_local(p, s, f):
        return len(rows_view), rows_view

    # Cabeçalho com Saldo Final
    hdr = tk.Frame(top.content, bg=Colors.BG_APP, pady=10, padx=20)
    hdr.pack(fill="x")

    lbl_saldo = tk.Label(hdr, text=f"Saldo Atual: {saldo_atual:.2f}",
                         font=("Segoe UI", 16, "bold"), bg=Colors.BG_APP, fg=Colors.PRIMARY)
    lbl_saldo.pack(side="right")

    tk.Label(hdr, text=f"Histórico de Movimentações ({len(rows_view)} registros)",
             font=("Segoe UI", 10), bg=Colors.BG_APP, fg=Colors.TEXT_HINT).pack(side="left")

    # Tabela
    tbl_frame = tk.Frame(top.content, bg=Colors.BG_APP)
    tbl_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # Reutiliza sua StandardTable (que é ótima)
    tbl = StandardTable(tbl_frame, columns=cols, fetch_fn=_fetch_local,
                        page_size=1000, minimal=True, autohide_pagination=True)
    tbl.pack(fill="both", expand=True)

    # Botão Fechar
    btn_box = tk.Frame(top.content, bg=Colors.BG_APP, pady=10, padx=20)
    btn_box.pack(fill="x", side="bottom")
    PillButton(btn_box, text="Fechar", variant="outline", command=top.close).pack(side="right")