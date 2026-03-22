import logging
import math
import tkinter as tk
import traceback
from tkinter import font as tkfont
from tkinter import ttk

from ui.pages.atividades import AtividadesPage
from ui.pages.configuracoes import (
    FamiliasPage, UnidadesMedidaPage, LocaisEstoquePage,
    ProductAliasPage, LpnPage, PrintersPage, PoliticasValidadeLotePage
)
from ui.pages.enderecos import EnderecosPage
from ui.pages.home import HomePage
from ui.pages.produtos import CadastroProdutosPage
from ui.pages.recebimento import RecebimentoPage
from ui.pages.perfis import PerfisPage
from ui.pages.usuarios import UsuariosPage
from ui.pages.login import LoginWindow
from utils.constants import (
    Colors,
    FONT_BTN, ARROW_FONT, SUB_FONT, GAP_Y, TOP_PAD, MARKER_W
)
from utils.helpers import log_exception, load_icon
from ui.components import SaaSDialog, SaaSModal
from database.repositories import usuarios_repo

# Menus principais (Configurações antes de Home)
BUTTONS = [
    ("settings_white", "Configurações"),
    ("home", "Home"),
    ("gestao_produtos", "Gestão de Produtos"),
    ("pedidos", "Pedidos"),
    ("rotina", "Rotina de Estoque"),
    ("recebimento", "Recebimento"),
    ("expedicao", "Expedição"),
    ("atividades", "Atividades"),
    ("relatorios", "Relatórios"),
]

# Sub-menus
SUBTABS = {
    "Configurações": [
        "Acessos", # Funciona apenas como um título (não-clicável)
        "- Usuários", # O traço indica que é sub-subpágina (será recuado)
        "- Perfis",
        "Locais de Estoque",
        "Endereços",
        "Unidades de Medida",
        "Conversões",
        "Políticas Globais",
        "Impressão",
    ],
    "Gestão de Produtos": ["Cadastro de Produtos", "Famílias", "Vínculos de Fornecedores"],
    "Rotina de Estoque": ["LPNs"],
}

REF_LABEL = "Gestão de Produtos"
ARROW_LEFT = "˂"  # U+02C2
ARROW_DOWN = "˅"  # U+02C5


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=0, style="Main.TFrame")
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        # --- ROTEADOR DE ATALHOS GLOBAIS ---
        # Vincula na raiz (root). Funciona sempre que a janela estiver ativa.
        # Usamos bind_all no master para garantir captura global sem bloquear widgets.
        master.bind_all("<F2>", self._handle_global_f2)  # Adicionar
        master.bind_all("<F3>", self._handle_global_f3)  # Editar
        master.bind_all("<F5>", self._handle_global_f5)  # Atualizar
        # -----------------------------------

        # Indicador (triângulo/página atual)
        self.selected_row = None
        self.selected_widgets = ()
        self.selected_marker = None
        self.active_triangle_fill = Colors.BG_APP

        # Roteador / páginas
        self.pages = {}
        self.page_factories = {}
        self.current_page_name = None

        # Mapas para triângulo/grupos
        self.page_to_menuitem = {}
        self.groups = {}

        # Registro das páginas
        self.register_page("Home", HomePage)
        self.register_page("Cadastro de Produtos", CadastroProdutosPage)
        self.register_page("Famílias", FamiliasPage)
        self.register_page("Usuários", UsuariosPage)
        self.register_page("Perfis", PerfisPage)
        self.register_page("Vínculos de Fornecedores", ProductAliasPage)
        self.register_page("Unidades de Medida", UnidadesMedidaPage)
        self.register_page("Locais de Estoque", LocaisEstoquePage)
        self.register_page("Endereços", EnderecosPage)
        self.register_page("Políticas Globais", PoliticasValidadeLotePage)
        self.register_page("Impressão", PrintersPage)
        self.register_page("LPNs", LpnPage)
        self.register_page("Recebimento", RecebimentoPage)
        self.register_page("Atividades", AtividadesPage)

        font_btn = tkfont.Font(root=master, font=FONT_BTN)
        font_arrow = tkfont.Font(root=master, font=ARROW_FONT)

        ROW_H_STD = {"px": None}

        ref_tuple = next(((ico, txt) for ico, txt in BUTTONS if txt == REF_LABEL), BUTTONS[0])
        ref_text = f"  {ref_tuple[1]}"
        text_px = font_btn.measure(ref_text) + 16  # Soma os 16 pixels do ícone
        char_px = max(1, font_btn.measure("0"))
        self.btn_width_chars = math.ceil(text_px / char_px) + 2

        arrow_px = font_arrow.measure(ARROW_LEFT) + 12
        self.sidebar_min_px = text_px + 20 + 24 + arrow_px + MARKER_W

        self.grid_columnconfigure(0, minsize=self.sidebar_min_px)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(0, 0))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)

        LEFT_TEXT_PAD = 8

        def sub_left_pad_for_icon(icon_name: str) -> int:
            # Largura base (Padding E + 16px da Imagem + Espaçamento)
            return int(LEFT_TEXT_PAD + 16 + font_btn.measure("  "))

        self.is_sidebar_collapsed = False
        self.sidebar_buttons = []
        self.sidebar_arrows = []

        # Pré-carregar ícones da sidebar na memória para não sumirem (Garbage Collector)
        self.sidebar_icons = {}
        for icon_name, _ in BUTTONS:
            self.sidebar_icons[icon_name] = load_icon(icon_name, 16)

        # Botão Hamburger
        self.icon_hamburguer = load_icon("hamburguer", 16)

        self.btn_toggle_sidebar = tk.Button(
            sidebar, image=self.icon_hamburguer, text=" ", compound="left",  # <-- Adicionado texto e compound
            bg=Colors.BG_SIDEBAR, activebackground=Colors.ROW_HOVER_SB,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            anchor="w", padx=8, pady=10
        )
        self.btn_toggle_sidebar.grid(row=0, column=0, sticky="ew")
        self.btn_toggle_sidebar.configure(command=self.toggle_sidebar)

        # helpers visuais
        def paint_widgets(widgets, color):
            for w in widgets:
                try:
                    w.configure(bg=color)
                except tk.TclError:
                    pass

        def draw_marker(canvas, height, fill_color):
            canvas.delete("all")
            w, h = MARKER_W, max(1, height)
            o = 2
            pts = (w + o, -o, -o, h / 2, w + o, h + o)
            canvas.create_polygon(pts, fill=fill_color, outline="")

        def is_selected(row):
            return self.selected_row is row

        def on_enter(row, widgets, marker):
            paint_widgets(widgets, Colors.ROW_HOVER_SB)
            if marker and not is_selected(row):
                marker.configure(bg=Colors.ROW_HOVER_SB)

        def on_leave(row, widgets, marker):
            paint_widgets(widgets, Colors.ROW_HOVER_SB if is_selected(row) else Colors.BG_SIDEBAR)
            if marker:
                marker.configure(bg=Colors.ROW_HOVER_SB if is_selected(row) else Colors.BG_SIDEBAR)

        def redraw_current_marker(height=None):
            if self.selected_marker and self.selected_row:
                h = height if height is not None else self.selected_row.winfo_height()
                draw_marker(self.selected_marker, h, self.active_triangle_fill)

        # Render da sidebar
        current_row = 1
        self.nested_info = {}
        for idx, (icon_name, text) in enumerate(BUTTONS):
            header = tk.Frame(sidebar, bg=Colors.BG_SIDEBAR)
            header.grid(row=current_row, column=0, sticky="ew",
                        padx=0, pady=(TOP_PAD if idx == 0 else GAP_Y, 0))
            header.columnconfigure(0, weight=1)
            header.columnconfigure(1, weight=0)
            header.columnconfigure(2, weight=0)

            # Pega a referência da imagem salva em memória
            img = self.sidebar_icons[icon_name]

            btn = tk.Button(
                header, text=f"  {text}", image=img, compound="left", font=FONT_BTN,
                fg=Colors.TEXT_SIDEBAR, bg=Colors.BG_SIDEBAR,
                activeforeground=Colors.TEXT_SIDEBAR, activebackground=Colors.ROW_HOVER_SB,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                anchor="w", padx=LEFT_TEXT_PAD
            )
            btn.grid(row=0, column=0, sticky="w", padx=0, ipady=2)

            # Salva o botão (com o objeto da imagem) para podermos alterá-lo depois
            self.sidebar_buttons.append((btn, img, text))

            if ROW_H_STD["px"] is None:
                header.update_idletasks()
                ROW_H_STD["px"] = header.winfo_height()

            header.rowconfigure(0, minsize=ROW_H_STD["px"])

            marker = tk.Canvas(header, width=MARKER_W, height=1,
                               bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0)

            sub_list = SUBTABS.get(text, [])

            # Home (tem conteúdo)
            if text == "Home":
                marker.grid(row=0, column=2, sticky="ns", padx=(0, 0))
                widgets = (header, btn, marker)
                self.page_to_menuitem["Home"] = (header, widgets, marker)

                btn.bind("<Enter>", lambda e, r=header, w=widgets, m=marker: on_enter(r, w, m))
                btn.bind("<Leave>", lambda e, r=header, w=widgets, m=marker: on_leave(r, w, m))
                btn.configure(command=lambda: self.show_page("Home"))
                header.bind("<Configure>", lambda e, m=marker, r=header:
                (self.selected_marker is m) and redraw_current_marker(r.winfo_height()))
                current_row += 1
                continue

            # seta
            arrow_btn = tk.Button(
                header, text=ARROW_LEFT, font=ARROW_FONT,
                fg=Colors.TEXT_SIDEBAR, bg=Colors.BG_SIDEBAR,
                activeforeground=Colors.TEXT_SIDEBAR, activebackground=Colors.ROW_HOVER_SB,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                width=2, anchor="e", padx=0
            )
            arrow_btn.grid(row=0, column=1, sticky="e", padx=(6, 6))
            arrow_btn.grid(row=0, column=1, sticky="e", padx=(6, 6))
            self.sidebar_arrows.append(arrow_btn)  # NOVO: Rastreia a seta
            marker.grid(row=0, column=2, sticky="ns", padx=(0, 0))
            header_widgets = (header, btn, arrow_btn, marker)

            for w in (btn, arrow_btn):
                w.bind("<Enter>", lambda e, r=header, ws=header_widgets, m=marker: on_enter(r, ws, m))
                w.bind("<Leave>", lambda e, r=header, ws=header_widgets, m=marker: on_leave(r, ws, m))

            header.bind("<Configure>", lambda e, m=marker, r=header:
            (self.selected_marker is m) and redraw_current_marker(r.winfo_height()))

            if sub_list:
                sub_container = tk.Frame(sidebar, bg=Colors.BG_SIDEBAR)
                sub_container.grid(row=current_row + 1, column=0, sticky="ew")
                sub_container.columnconfigure(0, weight=1)
                sub_container.grid_remove()
                SUB_LEFT_PAD = sub_left_pad_for_icon(icon_name)

                group_markers = []
                # Removida a linha "nested_info = {}" daqui
                last_parent_text = None

                for si, sub in enumerate(sub_list):
                    # Verifica se é uma sub-subpágina pelo prefixo
                    is_nested = sub.startswith("- ")
                    display_text = sub[2:] if is_nested else sub

                    sub_row = tk.Frame(sub_container, bg=Colors.BG_SIDEBAR)

                    if is_nested:
                        sub_row.grid(row=si, column=0, sticky="ew")
                        sub_row.grid_remove()  # NASCE FECHADO
                        if last_parent_text and last_parent_text in self.nested_info:
                            self.nested_info[last_parent_text]['rows'].append(sub_row)
                    else:
                        sub_row.grid(row=si, column=0, sticky="ew")
                        # Verifica se o próximo item da lista é um filho deste item
                        has_children = (si + 1 < len(sub_list) and sub_list[si + 1].startswith("- "))
                        if has_children:
                            last_parent_text = display_text
                            self.nested_info[display_text] = {'rows': [], 'open': False, 'arrow': None}
                        else:
                            last_parent_text = None

                    if ROW_H_STD["px"]:
                        sub_row.configure(height=ROW_H_STD["px"])
                        sub_row.grid_propagate(False)
                        sub_row.rowconfigure(0, weight=1)

                    sub_row.columnconfigure(0, weight=1)
                    sub_row.columnconfigure(1, weight=0)
                    sub_row.columnconfigure(2, weight=0)

                    # Aumenta o recuo (padding) se for uma sub-subpágina
                    current_pad = SUB_LEFT_PAD + 16 if is_nested else SUB_LEFT_PAD

                    # É o título de um grupo (ex: "Acessos")
                    is_parent = (not is_nested and last_parent_text == display_text)

                    # Define cursor
                    cursor_type = "hand2" if (display_text in self.page_factories or is_parent) else "arrow"

                    sub_btn = tk.Button(
                        sub_row, text=display_text, font=SUB_FONT,
                        fg=Colors.TEXT_SIDEBAR, bg=Colors.BG_SIDEBAR,
                        activeforeground=Colors.TEXT_SIDEBAR, activebackground=Colors.ROW_HOVER_SB,
                        relief="flat", bd=0, highlightthickness=0, cursor=cursor_type,
                        anchor="w", padx=current_pad
                    )
                    sub_btn.grid(row=0, column=0, sticky="nsew", padx=0, ipady=2)

                    sub_arrow_btn = None
                    if is_parent:
                        sub_arrow_btn = tk.Button(
                            sub_row, text=ARROW_LEFT, font=ARROW_FONT,
                            fg=Colors.TEXT_SIDEBAR, bg=Colors.BG_SIDEBAR,
                            activeforeground=Colors.TEXT_SIDEBAR, activebackground=Colors.ROW_HOVER_SB,
                            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                            width=2, anchor="e", padx=0
                        )
                        sub_arrow_btn.grid(row=0, column=1, sticky="e", padx=(6, 6))
                        self.nested_info[display_text]['arrow'] = sub_arrow_btn

                        # Função de clique para abrir/fechar o submenu aninhado
                        def toggle_nested(p_text=display_text):
                            info = self.nested_info[p_text]
                            if info['open']:
                                info['arrow'].configure(text=ARROW_LEFT)
                                for r in info['rows']: r.grid_remove()
                                info['open'] = False
                            else:
                                info['arrow'].configure(text=ARROW_DOWN)
                                for r in info['rows']: r.grid()
                                info['open'] = True

                        sub_btn.configure(command=toggle_nested)
                        sub_arrow_btn.configure(command=toggle_nested)

                    sub_marker = tk.Canvas(sub_row, width=MARKER_W, height=1,
                                           bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0)
                    col_marker = 2 if is_parent else 1
                    sub_marker.grid(row=0, column=col_marker, sticky="ns", padx=(0, 0))
                    group_markers.append(sub_marker)

                    if is_parent:
                        sub_widgets = (sub_row, sub_btn, sub_arrow_btn, sub_marker)
                    else:
                        sub_widgets = (sub_row, sub_btn, sub_marker)

                    # Aplica hover e clique APENAS se a página estiver registrada ou se for Pai (Acessos)
                    if display_text in self.page_factories:
                        sub_btn.bind("<Enter>", lambda e, r=sub_row, ws=sub_widgets, m=sub_marker: on_enter(r, ws, m))
                        sub_btn.bind("<Leave>", lambda e, r=sub_row, ws=sub_widgets, m=sub_marker: on_leave(r, ws, m))

                        def open_sub(name=display_text, r=sub_row, ws=sub_widgets, m=sub_marker, header_text=text):
                            if name in self.page_factories:
                                self._set_group_state(header_text, True)
                                self.show_page(name)

                        sub_btn.configure(command=open_sub)
                    elif is_parent:
                        for w in (sub_btn, sub_arrow_btn):
                            w.bind("<Enter>", lambda e, r=sub_row, ws=sub_widgets, m=sub_marker: on_enter(r, ws, m))
                            w.bind("<Leave>", lambda e, r=sub_row, ws=sub_widgets, m=sub_marker: on_leave(r, ws, m))
                    else:
                        # Tira o efeito de fundo no hover para itens que funcionam apenas como separador
                        sub_btn.configure(activebackground=Colors.BG_SIDEBAR)

                    sub_row.bind("<Configure>", lambda e, m=sub_marker, r=sub_row:
                    (self.selected_marker is m) and redraw_current_marker(r.winfo_height()))

                    self.page_to_menuitem[display_text] = (sub_row, sub_widgets, sub_marker)

                self.groups[text] = {"container": sub_container, "arrow": arrow_btn, "markers": set(group_markers),
                                     "open": False}

                def toggle(header_text=text):
                    if self.is_sidebar_collapsed:
                        self.toggle_sidebar()  # Abre a sidebar se estiver fechada

                    info = self.groups.get(header_text, {})
                    open_now = bool(info.get("open"))
                    if open_now:
                        if self.selected_marker in info.get("markers", set()):
                            self._set_group_state(header_text, True)
                            return
                        self._set_group_state(header_text, False)
                    else:
                        self._set_group_state(header_text, True)

                btn.configure(command=toggle)
                arrow_btn.configure(command=toggle)
                current_row += 2
            else:
                header_widgets = (header, btn, arrow_btn, marker)

                def open_header_page(name=text, r=header, ws=header_widgets, m=marker, a=arrow_btn):
                    if self.is_sidebar_collapsed:
                        self.toggle_sidebar()  # Abre a sidebar se estiver fechada

                    if name in self.page_factories:
                        self.show_page(name)
                    a.configure(text=(ARROW_DOWN if a.cget("text") == ARROW_LEFT else ARROW_LEFT))

                btn.configure(command=open_header_page)
                arrow_btn.configure(command=open_header_page)

                if text in self.page_factories:
                    self.page_to_menuitem[text] = (header, header_widgets, marker)

                current_row += 1

        self.main = ttk.Frame(self, style="Main.TFrame")
        self.main.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main.rowconfigure(0, weight=1)
        self.main.columnconfigure(0, weight=1)
        self._page_container = self.main

        self.after(0, lambda: self.show_page("Home"))

    # --- MÉTODOS DE ATALHO GLOBAL ---
        # 1. Adicione/Verifique se este método está alinhado com os outros (indentação correta)
    def _can_handle_shortcut(self):
        # Verifica se há algum modal bloqueante aberto
        try:
            focused = self.focus_get()
            if focused:
                # Se a janela focada não for a janela principal (App), é um modal
                if focused.winfo_toplevel() != self.winfo_toplevel():
                    return False
        except Exception:
            pass
        return True

        # 2. Atualize os handlers para usar a nova função:
    def _handle_global_f2(self, event):
        # AQUI: A chamada faz o aviso sumir
        if not self._can_handle_shortcut(): return "break"

        if not self.current_page_name: return

        page = self.pages.get(self.current_page_name)
        if page:
            if hasattr(page, "_open_add_dialog"):
                page._open_add_dialog()
                return "break"
            if hasattr(page, "btn_add"):
                try:
                    if str(page.btn_add["state"]) != "disabled":
                        if hasattr(page.btn_add, "_on_click"): page.btn_add._on_click()
                        return "break"
                except:
                    pass

    def _handle_global_f3(self, event):
        if not self._can_handle_shortcut(): return "break"

        if not self.current_page_name: return

        page = self.pages.get(self.current_page_name)
        if page:
            if hasattr(page, "_open_edit_dialog"):
                page._open_edit_dialog()
                return "break"
            if hasattr(page, "btn_edit") and page.btn_edit.winfo_ismapped():
                try:
                    if str(page.btn_edit["state"]) != "disabled":
                        if hasattr(page.btn_edit, "_on_click"): page.btn_edit._on_click()
                        return "break"
                except:
                    pass

    def _handle_global_f5(self, event):
        if not self._can_handle_shortcut(): return "break"

        if not self.current_page_name: return

        page = self.pages.get(self.current_page_name)
        if page and hasattr(page, "table") and hasattr(page.table, "refresh"):
            page.table.refresh()
            return "break"

    # --------------------------------

    def toggle_sidebar(self):
        self.is_sidebar_collapsed = not self.is_sidebar_collapsed

        if self.is_sidebar_collapsed:
            # Estado Recolhido (Sidebar fininha)
            self.grid_columnconfigure(0, minsize=46)

            self.btn_toggle_sidebar.grid_configure(sticky="ew")
            self.btn_toggle_sidebar.configure(anchor="center", padx=0, text=" ", compound="center")

            # Esconde as setinhas de submenu corretamente
            for arrow in self.sidebar_arrows:
                arrow.grid_remove()

            # Fecha todos os submenus
            for g_name in self.groups:
                self._set_group_state(g_name, False)

            # Ícones do menu principal
            for btn, img, header_text in self.sidebar_buttons:
                btn.grid_configure(sticky="ew")
                btn.configure(text=" ", image=img, compound="center", anchor="center", padx=0)

                # LÓGICA INTELIGENTE: Pular o triângulo pro Pai se um submenu estiver ativo
                info = self.groups.get(header_text)
                if info and self.selected_marker in info.get("markers", set()):
                    parent_marker = next((c for c in btn.master.winfo_children() if isinstance(c, tk.Canvas)), None)
                    if parent_marker:
                        # Desliga o marcador do submenu atual
                        self.selected_marker.delete("all")
                        self.selected_marker.configure(bg=Colors.BG_SIDEBAR)
                        self.selected_row.configure(bg=Colors.BG_SIDEBAR)
                        for c in self.selected_row.winfo_children():
                            try:
                                c.configure(bg=Colors.BG_SIDEBAR)
                            except tk.TclError:
                                pass

                        # Ativa o marcador do Pai
                        self.selected_marker = parent_marker
                        self.selected_row = btn.master
                        self.selected_marker.configure(bg=Colors.ROW_HOVER_SB)
                        self.selected_row.configure(bg=Colors.ROW_HOVER_SB)
                        for c in self.selected_row.winfo_children():
                            try:
                                c.configure(bg=Colors.ROW_HOVER_SB)
                            except tk.TclError:
                                pass

        else:
            # Estado Expandido
            self.grid_columnconfigure(0, minsize=self.sidebar_min_px)

            self.btn_toggle_sidebar.grid_configure(sticky="ew")
            self.btn_toggle_sidebar.configure(anchor="w", padx=14, text=" ", compound="left")

            # Devolve as setinhas de submenu
            for arrow in self.sidebar_arrows:
                arrow.grid()

            for btn, img, header_text in self.sidebar_buttons:
                btn.grid_configure(sticky="w")
                btn.configure(text=f"  {header_text}", image=img, compound="left", anchor="w", padx=8)

            # LÓGICA INTELIGENTE: Devolver o triângulo pro submenu ao abrir a barra
            if self.current_page_name:
                item = self.page_to_menuitem.get(self.current_page_name)
                if item:
                    row, widgets, marker = item
                    # Se o marcador visual estiver no Pai, nós o devolvemos pro Submenu
                    if self.selected_marker != marker:
                        # Limpa o Pai
                        self.selected_marker.delete("all")
                        self.selected_marker.configure(bg=Colors.BG_SIDEBAR)
                        self.selected_row.configure(bg=Colors.BG_SIDEBAR)
                        for c in self.selected_row.winfo_children():
                            try:
                                c.configure(bg=Colors.BG_SIDEBAR)
                            except tk.TclError:
                                pass

                        # Devolve pro Submenu
                        self.selected_marker = marker
                        self.selected_row = row
                        self.selected_marker.configure(bg=Colors.ROW_HOVER_SB)
                        self.selected_row.configure(bg=Colors.ROW_HOVER_SB)
                        for w in widgets:
                            try:
                                w.configure(bg=Colors.ROW_HOVER_SB)
                            except tk.TclError:
                                pass

                    # Reabre o submenu automaticamente se ele contém a tela ativa
                    for g_name, info in self.groups.items():
                        if marker in info.get("markers", set()):
                            self._set_group_state(g_name, True)

        # FORÇA O REDESENHO DO TRIÂNGULO (Corrige o bug do sumiço visual do Tkinter)
        self.update_idletasks()
        if self.selected_marker and self.selected_row:
            self.selected_marker.delete("all")
            h = max(1, self.selected_row.winfo_height())
            o = 2
            pts = (MARKER_W + o, -o, -o, h / 2, MARKER_W + o, h + o)
            self.selected_marker.create_polygon(pts, fill=self.active_triangle_fill, outline="")

    def register_page(self, name: str, factory):
        self.page_factories[name] = factory

    def _set_group_state(self, header_text, open_flag: bool):
        info = self.groups.get(header_text)
        if not info: return
        if open_flag:
            try:
                info["container"].grid()
                info["arrow"].configure(text=ARROW_DOWN)
            except tk.TclError:
                pass
            info["open"] = True
        else:
            try:
                info["container"].grid_remove()
                info["arrow"].configure(text=ARROW_LEFT)
            except tk.TclError:
                pass
            info["open"] = False

    def _page_bg_color(self, page: ttk.Frame) -> str:
        try:
            style = ttk.Style()
            style_name = page.cget("style") or page.winfo_class()
            bg = style.lookup(style_name, "background")
            if not bg: bg = page.cget("background")
            return bg or Colors.BG_APP
        except Exception:
            return Colors.BG_APP

    def show_page(self, name: str, **kwargs):
        if name not in self.page_factories: return
        if self.current_page_name:
            cur = self.pages.get(self.current_page_name)
            if cur:
                cur.on_hide()
                if getattr(cur, "destroy_on_hide", False):
                    try:
                        cur.destroy()
                    finally:
                        self.pages.pop(self.current_page_name, None)
                else:
                    cur.grid_remove()

        page = self.pages.get(name)
        if page is None:
            page = self.page_factories[name](self._page_container)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = page
        else:
            page.grid()

        self.current_page_name = name
        page.tkraise()
        page.on_show(**kwargs)

        self.active_triangle_fill = self._page_bg_color(page)

        item = self.page_to_menuitem.get(name)
        if item:
            row, widgets, marker = item
            owning_group = None
            for g_name, info in self.groups.items():
                if marker in info.get("markers", set()):
                    owning_group = g_name
                    break
            if owning_group:
                self._set_group_state(owning_group, True)

            if hasattr(self, "selected_row") and self.selected_row and self.selected_widgets:
                for w in self.selected_widgets:
                    try:
                        w.configure(bg=Colors.BG_SIDEBAR)
                    except tk.TclError:
                        pass
            if hasattr(self, "selected_marker") and self.selected_marker:
                self.selected_marker.delete("all")
            self.selected_row = row
            self.selected_widgets = widgets
            self.selected_marker = marker
            for w in widgets:
                try:
                    w.configure(bg=Colors.ROW_HOVER_SB)
                except tk.TclError:
                    pass
            marker.configure(bg=Colors.ROW_HOVER_SB)
            row.update_idletasks()
            h = row.winfo_height()
            cw = MARKER_W
            o = 2
            pts = (cw + o, -o, -o, h / 2, cw + o, h + o)
            marker.create_polygon(pts, fill=self.active_triangle_fill, outline="")


def setup_style(root):
    style = ttk.Style()
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=Colors.BG_APP)

    # Configurações Gerais
    style.configure("Main.TFrame", background=Colors.BG_APP)
    style.configure("Sidebar.TFrame", background=Colors.BG_SIDEBAR)
    style.configure("TFrame", background=Colors.BG_APP)
    style.configure("TLabelframe", background=Colors.BG_APP)
    style.configure("TLabel", background=Colors.BG_APP)
    style.configure("TNotebook", background=Colors.BG_APP)
    style.configure("TSeparator", background=Colors.BORDER)

    # Títulos
    style.configure("Title.TFrame", background=Colors.BG_APP)
    style.configure(
        "Title.TLabel",
        background=Colors.BG_APP,
        foreground=Colors.TEXT_MAIN,
        font=("Segoe UI", 18, "bold")
    )

    # Treeview (Tabela Nativa, se usada)
    style.configure(
        "Treeview",
        background=Colors.BG_CARD,
        fieldbackground=Colors.BG_CARD,
        bordercolor=Colors.BORDER,
        borderwidth=1
    )
    style.map(
        "Treeview",
        background=[("selected", Colors.ROW_SELECTED)],
        foreground=[("selected", Colors.TEXT_MAIN)]
    )
    style.configure(
        "Treeview.Heading",
        background=Colors.HEADER_TABLE,
        foreground=Colors.TEXT_MAIN,
        relief="flat"
    )
    style.map(
        "Treeview.Heading",
        background=[("active", Colors.BORDER_LIGHT)]
    )

    # Combobox Global
    style.configure(
        "Global.TCombobox",
        fieldbackground=Colors.BG_CARD,
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MAIN,
        bordercolor=Colors.BORDER,
        lightcolor=Colors.BORDER,
        darkcolor=Colors.BORDER,
        arrowcolor=Colors.PRIMARY,
        borderwidth=1,
        relief="flat",
        padding=4
    )
    style.map(
        "Global.TCombobox",
        fieldbackground=[("readonly", Colors.BG_CARD), ("!disabled", Colors.BG_CARD)],
        foreground=[("readonly", Colors.TEXT_MAIN), ("!disabled", Colors.TEXT_MAIN)],
        bordercolor=[("focus", Colors.PRIMARY), ("active", Colors.PRIMARY)],
        lightcolor=[("focus", Colors.PRIMARY), ("active", Colors.PRIMARY)],
        darkcolor=[("focus", Colors.PRIMARY), ("active", Colors.PRIMARY)],
        arrowcolor=[("pressed", Colors.PRIMARY), ("active", Colors.PRIMARY)]
    )

    # Estilos de Card
    style.configure(
        "Card.TFrame",
        background=Colors.BG_CARD,
        bordercolor=Colors.BORDER,
        relief="solid",
        borderwidth=1
    )
    style.configure(
        "RoundedCardInner.TFrame",
        background=Colors.BG_CARD
    )

    # Títulos dentro dos Cards
    style.configure(
        "CardTitle.TLabel",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MAIN,
        font=("Segoe UI", 12, "bold")
    )
    style.configure(
        "CardSectionTitle.TLabel",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MAIN,
        font=("Segoe UI", 11, "bold")
    )
    style.configure(
        "CardBody.TLabel",
        background=Colors.BG_CARD,
        foreground="#4B5563",
        font=("Segoe UI", 10)
    )

    # Radiobutton e Checkbutton dentro dos cards (Fundo branco)
    style.configure(
        "Card.TRadiobutton",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MAIN,
        font=("Segoe UI", 10)
    )
    style.configure(
        "Card.TCheckbutton",
        background=Colors.BG_CARD,
        foreground=Colors.TEXT_MAIN,
        font=("Segoe UI", 10)
    )
    style.map(
        "Card.TCheckbutton",
        background=[("active", Colors.BG_CARD), ("selected", Colors.BG_CARD)],
        foreground=[("disabled", Colors.TEXT_HINT)]
    )
    style.map(
        "Card.TRadiobutton",
        background=[("active", Colors.BG_CARD), ("selected", Colors.BG_CARD)],
        foreground=[("disabled", Colors.TEXT_HINT)]
    )


def main():
    try:
        root = tk.Tk()
        root.title("WMS")
        root.minsize(1024, 700)

        root.withdraw()
        setup_style(root)

        # ====================================================================
        # AUTO-SETUP: Cria o usuário admin se o banco estiver vazio
        # ====================================================================
        def verificar_primeiro_acesso():
            # Checa quantos usuários existem no banco
            total, _ = usuarios_repo.list(page=1, page_size=1)

            if total == 0:
                print("Primeiro acesso detectado. Configurando Administrador padrão...")

                # 1. Cria o perfil Administrador com acesso total
                permissoes_json = '{"recebimento": true, "produtos": true, "estoque": true, "atividades": true, "configuracoes": true}'
                usuarios_repo.execute_non_query(
                    "INSERT INTO Perfis (Nome, Descricao, Permissoes, Ativo) VALUES ('Administrador', 'Acesso total ao sistema', ?, 1)",
                    (permissoes_json,)
                )

                # Pega o ID do perfil que acabou de ser criado
                res = usuarios_repo.execute_query("SELECT TOP 1 Id FROM Perfis ORDER BY Id DESC")
                perfil_id = res[0]['Id'] if res else 1

                # 2. Cria o usuário Admin com a senha padrao (a função do repo já faz o bcrypt corretamente)
                # Passamos None para o usuario_logado_id pois é o sistema criando
                usuarios_repo.criar_usuario(perfil_id, "Administrador do Sistema", "admin", "123456", None)
                print("Setup concluído com sucesso!")

        # Executa a verificação ANTES de abrir a tela de login
        verificar_primeiro_acesso()

        # ====================================================================

        def iniciar_sistema():
            try:
                root.state("zoomed")
            except tk.TclError:
                root.update_idletasks()
                sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
                root.geometry(f"{sw}x{sh}+0+0")

            app = App(root)
            root.deiconify()

        def confirm_exit():
            dlg = SaaSDialog(
                root,
                "Sair",
                "Deseja realmente sair?",
                icon_name="caution",
                buttons=[("Não", False, "outline"), ("Sim", True, "primary")]
            )
            root.wait_window(dlg)

            if dlg.result:
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", confirm_exit)

        def handle_tkinter_error(*args):
            err_val = traceback.format_exc()
            logging.error(f"Erro de Interface (Tkinter):\n{err_val}")

            dlg = SaaSDialog(
                root,
                "Erro no Sistema",
                "Ocorreu um erro inesperado.\nO detalhe foi salvo em 'sistema_erros.log'.\n\nPor favor, contate o administrador.",
                icon_name="alert_red"
            )
            root.wait_window(dlg)

        root.report_callback_exception = handle_tkinter_error

        # Inicializa e mostra a tela de login
        LoginWindow(root, on_success=iniciar_sistema)

        root.mainloop()

    except Exception as e:
        log_exception(e, "Falha Fatal na Inicialização")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Erro fatal ao abrir sistema:\n{e}", "Erro Crítico", 16)
        except:
            pass


if __name__ == "__main__":
    main()