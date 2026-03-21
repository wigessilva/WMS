import tkinter as tk
from tkinter import ttk

from ui.components import (
    Page, PillButton, StandardTable, SaaSModal, TextField,
    BlueCheckButton, RoundedCard, CardSectionSeparator, MinimalScrollbar, ToggleSwitch
)
from utils.constants import Colors, PAGE_SIZE_DEFAULT
from utils.permissoes import DICIONARIO_PERMISSOES
from utils.helpers import load_icon


# Importar o repositório quando ele estiver pronto:
# from database.repos.usuarios import PerfisRepo

class PerfisPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        # --- 1. Definição da Tabela ---
        cols = [
            {"id": "Nome", "title": "Nome", "type": "text", "width": 250, "anchor": "w"},
            {"id": "Descricao", "title": "Descrição", "type": "text", "width": 400, "anchor": "w"},
            {"id": "ativo_show", "title": "Status", "type": "text", "width": 100, "anchor": "center"},
        ]

        # Função mockada para a tabela (Substitua por PerfisRepo().list() depois)
        def _fetch_mock(page: int, page_size: int, filters: list):
            # Apenas o Administrador hardcoded inicial, exatamente como combinado!
            rows = [
                {"Id": 1, "Nome": "Administrador", "Descricao": "Acesso total a todos os módulos",
                 "Ativo": True}
            ]

            processed = []
            for r in rows:
                r["ativo_show"] = "Ativo" if r["Ativo"] else "Inativo"
                processed.append(r)
            return len(processed), processed

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch_mock, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="new")

        # --- 2. Barra de Ferramentas ---
        left_box = self.table.left_actions

        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16), padx=9,
                                  command=self._open_add_dialog)
        self.btn_add.pack(side="left", padx=(0, 10))

        self.btn_edit = PillButton(left_box, text="", variant="outline", icon=load_icon("edit", 16), padx=9,
                                   command=self._open_edit_dialog)
        self.btn_edit.pack(side="left", padx=(0, 10))
        self.btn_edit.state(["disabled"])

        self.btn_del = PillButton(left_box, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._delete_selected)
        self.btn_del.pack(side="left", padx=(0, 10))
        self.btn_del.state(["disabled"])

        self.table.bind("<<TableSelect>>", self._on_selection_change)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._open_edit_dialog())

    def _on_selection_change(self, _e=None):
        has_sel = (self.table.get_selected() is not None)
        self.btn_edit.state(["!disabled"] if has_sel else ["disabled"])
        self.btn_del.state(["!disabled"] if has_sel else ["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)

    def _open_add_dialog(self):
        self._open_perfil_modal("add")

    def _open_edit_dialog(self):
        sel = self.table.get_selected()
        if not sel: return

        # Bloqueia a edição do perfil Administrador (ID 1 hardcoded)
        if sel.get("Id") == 1:
            self.alert("Acesso Negado", "O perfil Administrador padrão não pode ser editado.", type="warning")
            return

        self._open_perfil_modal("edit", sel)

    def _delete_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        if sel.get("Id") == 1:
            self.alert("Acesso Negado", "O perfil Administrador padrão não pode ser excluído.", type="warning")
            return

        def _confirmar():
            self.alert("Sucesso", f"Perfil {sel['Nome']} excluído (Mock)", type="info")

        self.ask_yes_no("Confirmar exclusão", f"Excluir o perfil '{sel['Nome']}'?", on_yes=_confirmar)

    # =========================================================================
    # MODAL DE CRIAÇÃO/EDIÇÃO E A ÁRVORE DE PERMISSÕES
    # =========================================================================
    def _open_perfil_modal(self, mode="add", initial=None):
        titulo = "Novo Perfil de Acesso" if mode == "add" else "Editar Perfil"
        top = SaaSModal(self, title=titulo, width=700, height=750)

        main_container = ttk.Frame(top.content, style="Main.TFrame")
        main_container.pack(fill="both", expand=True)

        # --- 1. CABEÇALHO DO PERFIL ---
        frm_header = tk.Frame(main_container, bg=Colors.BG_APP)
        frm_header.pack(side="top", fill="x", padx=20, pady=(20, 10))

        ent_nome = TextField(frm_header, placeholder="Nome", height=34, width=200)
        ent_nome.pack(side="left", padx=(0, 12))

        ent_desc = TextField(frm_header, placeholder="Descrição", height=34)
        ent_desc.pack(side="left", fill="x", expand=True)

        # --- 2. RODAPÉ COM BOTÃO SALVAR (Sempre empacotar o rodapé ANTES do Scroll!) ---
        frm_footer = ttk.Frame(main_container, style="Main.TFrame")
        frm_footer.pack(side="bottom", fill="x", padx=20, pady=20)

        def _save():
            nome = ent_nome.get().strip()
            if not nome:
                top.alert("Atenção", "O nome do perfil é obrigatório.", focus_widget=ent_nome)
                return

            permissoes_selecionadas = {}
            for k, var in self.perm_vars.items():
                if var.get():
                    permissoes_selecionadas[k] = True

            # PerfisRepo().criar_perfil(nome, ent_desc.get(), permissoes_selecionadas)
            self.alert("Sucesso", f"Perfil {nome} guardado com sucesso!", type="info")
            top.close()

        PillButton(frm_footer, text="Salvar Perfil", command=_save, variant="success").pack(side="right")
        PillButton(frm_footer, text="Cancelar", command=top.close, variant="outline").pack(side="right", padx=10)

        # --- 3. ÁREA DE SCROLL MANUAL COM MinimalScrollbar ---
        frm_scroll = tk.Frame(main_container, bg=Colors.BG_APP)
        frm_scroll.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 0))

        canvas = tk.Canvas(frm_scroll, bg=Colors.BG_APP, highlightthickness=0)
        scrollbar = MinimalScrollbar(frm_scroll, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_content = tk.Frame(canvas, bg=Colors.BG_APP)
        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scroll_content.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        canvas.bind("<Configure>", _on_canvas_configure)

        # Ativa o scroll pelo mouse nativo
        def _on_mousewheel(e):
            if e.num == 5 or getattr(e, "delta", 0) < 0:
                canvas.yview_scroll(1, "units")
            elif e.num == 4 or getattr(e, "delta", 0) > 0:
                canvas.yview_scroll(-1, "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        tk.Label(scroll_content, text="Permissões do Sistema", font=("Segoe UI", 12, "bold"),
                 bg=Colors.BG_APP, fg=Colors.PRIMARY).pack(anchor="w", pady=(0, 10))

        # --- 4. RENDERIZAÇÃO DA ÁRVORE DE PERMISSÕES ---
        self.perm_vars = {}

        def _toggle_all(var_master, vars_children):
            estado = var_master.get()
            for v_child in vars_children:
                v_child.set(estado)

        def _check_children(var_master, vars_children):
            todas_marcadas = all(v.get() for v in vars_children)
            var_master.set(todas_marcadas)

        for mod_key, mod_info in DICIONARIO_PERMISSOES.items():
            card = RoundedCard(scroll_content, padding=(16, 16, 16, 16), radius=8)
            card.pack(fill="x", pady=(0, 15))

            var_mod = tk.BooleanVar()
            acoes_vars = []

            # ATENÇÃO: O 'command' deve ser passado AQUI na criação do componente
            chk_mod = BlueCheckButton(
                card.content, text=mod_info["nome"], variable=var_mod, bg=Colors.BG_CARD,
                command=lambda v_m=var_mod, v_c=acoes_vars: _toggle_all(v_m, v_c)
            )
            chk_mod.pack(anchor="w", pady=(0, 8))
            chk_mod.itemconfigure(chk_mod.find_withtag("text"), font=("Segoe UI", 10, "bold"))

            CardSectionSeparator(card.content).pack(fill="x", pady=(0, 10))

            frm_acoes = tk.Frame(card.content, bg=Colors.BG_CARD)
            frm_acoes.pack(fill="x", padx=(28, 0))

            for acao_key, acao_nome in mod_info["acoes"].items():
                var_acao = tk.BooleanVar()
                self.perm_vars[acao_key] = var_acao
                acoes_vars.append(var_acao)

                chk_acao = BlueCheckButton(
                    frm_acoes, text=acao_nome, variable=var_acao, bg=Colors.BG_CARD,
                    command=lambda v_m=var_mod, v_c=acoes_vars: _check_children(v_m, v_c)
                )
                chk_acao.pack(anchor="w", pady=4)

            # FORÇA MÁGICA: Obriga o Canvas do Card a recalcular sua altura
            # logo após os itens serem colocados dentro dele, para não sumir.
            card.update_idletasks()
            card._size_to_content()

        # --- PREENCHIMENTO SE FOR EDIÇÃO ---
        if mode == "edit" and initial:
            ent_nome.insert(0, initial.get("Nome", ""))
            ent_desc.insert(0, initial.get("Descricao", ""))

        if mode == "add":
            ent_nome.focus_set()