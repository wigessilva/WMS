import tkinter as tk
from tkinter import ttk

from ui.components import (
    Page, PillButton, StandardTable, SaaSModal, TextField,
    BlueCheckButton, RoundedCard, MinimalScrollbar
)
from utils.constants import Colors, PAGE_SIZE_DEFAULT
from utils.helpers import load_icon

import json
from database.repositories import perfis_repo

# =====================================================================
# Dicionário Hierárquico de Permissões (Estrutura Achatada)
# =====================================================================
MOCK_HIERARQUIA_PERMISSOES = {
    "recebimento": {
        "titulo": "Recebimento",
        "itens": {
            "rec_vis": {"nome": "Visualizar página de recebimento"},
            "rec_vis_qtd": {"nome": "Visualizar quantidades de itens a receber"},
            "rec_painel": {"nome": "Acessar painel de controle"},
            "rec_painel_edit": {"nome": "Editar dados principais"},
            "rec_painel_liberar": {"nome": "Liberar conferência"},
            "rec_painel_desfazer": {"nome": "Desfazer liberação"},
            "rec_painel_cancelar": {"nome": "Cancelar recebimento"},
            "rec_painel_concluir": {"nome": "Concluir recebimento"},
            "rec_painel_reconferencia": {"nome": "Solicitar reconferência"},
            "rec_alt_destino": {"nome": "Alterar destino de itens"},
            "rec_conf_pasta": {"nome": "Configurar pasta XMLs"},
            "rec_vinc_sku": {"nome": "Vincular SKU"}
        }
    },
    "produtos": {
        "titulo": "Gestão de Produtos",
        "itens": {
            "prod_vis": {"nome": "Visualizar página de produtos"},
            "prod_edit_cad_codfor": {"nome": "Editar cód. fornecedor"},
            "prod_edit_cad_ref": {"nome": "Editar referência"},
            "prod_edit_cad_emb_dim": {"nome": "Editar dimensões"},
            "prod_edit_cad_emb_peso": {"nome": "Editar peso"},
            "prod_edit_cad_emb_gtin": {"nome": "Editar GTIN"},
            "prod_edit_pol": {"nome": "Editar políticas"},
            "prod_fam_vis": {"nome": "Visualizar página de famílias"},
            "prod_fam_edit": {"nome": "Criar e editar famílias"},
            "prod_fam_del": {"nome": "Excluir famílias"},
            "prod_vinc_vis": {"nome": "Visualizar página de vínculos de fornecedores"},
            "prod_vinc_del": {"nome": "Excluir vínculo"}
        }
    },
    "estoque": {
        "titulo": "Estoque",
        "itens": {
            "est_lpn_vis": {"nome": "Visualizar página de LPNs"},
            "est_lpn_gerar": {"nome": "Gerar LPNs"},
            "est_lpn_edit": {"nome": "Editar LPNs"},
            "est_lpn_del": {"nome": "Excluir LPNs"},
            "est_lpn_print": {"nome": "Reimprimir etiquetas"}
        }
    },
    "atividades": {
        "titulo": "Atividades",
        "itens": {
            "ativ_conferir": {"nome": "Conferir"}
        }
    },
    "configuracoes": {
        "titulo": "Configurações",
        "itens": {
            "conf_acessos_usu_vis": {"nome": "Visualizar página de usuários"},
            "conf_acessos_usu_edit": {"nome": "Criar e editar usuários"},
            "conf_acessos_perfis_vis": {"nome": "Visualizar página de perfis"},
            "conf_acessos_perfis_edit": {"nome": "Criar e editar perfis"},
            "conf_locais_vis": {"nome": "Visualizar página de locais de estoque"},
            "conf_locais_edit": {"nome": "Criar e editar locais de estoque"},
            "conf_enderecos_vis": {"nome": "Visualizar página de endereços"},
            "conf_enderecos_edit": {"nome": "Criar e editar endereços"},
            "conf_enderecos_del": {"nome": "Excluir endereços"},
            "conf_enderecos_print": {"nome": "Imprimir etiquetas de endereços"},
            "conf_enderecos_areas": {"nome": "Criar e editar áreas"},
            "conf_unidades_vis": {"nome": "Visualizar página de unidades de medida"},
            "conf_unidades_edit": {"nome": "Criar e editar unidades de medida"},
            "conf_unidades_sinonimos": {"nome": "Configurar sinônimos XMLs"},
            "conf_politicas_vis": {"nome": "Visualizar página de políticas globais"},
            "conf_politicas_excecoes": {"nome": "Visualizar tabela de exceções"},
            "conf_politicas_config": {"nome": "Configurar políticas"},
            "conf_impressao_vis": {"nome": "Visualizar página de impressão"},
            "conf_impressao_edit": {"nome": "Criar e editar impressoras"},
            "conf_impressao_del": {"nome": "Excluir impressoras"}
        }
    }
}


# =====================================================================
# Componente: Nó de Árvore Colapsável
# =====================================================================
class CollapsiblePermissionNode(tk.Frame):
    def __init__(self, parent, text, is_leaf=False, is_card_level=False, bg_color=Colors.BG_APP, perm_vars_dict=None,
                 perm_key=None, on_toggle_callback=None, state="normal"):
        super().__init__(parent, bg=bg_color)
        self.expanded = False
        self.is_leaf = is_leaf
        self.child_nodes = []

        self.on_toggle_callback = on_toggle_callback

        self.var = tk.BooleanVar()
        if perm_key and perm_vars_dict is not None:
            perm_vars_dict[perm_key] = self.var

        self.header = tk.Frame(self, bg=bg_color)
        self.header.pack(fill="x")

        if not is_leaf:
            self.canvas_icon = tk.Canvas(self.header, width=20, height=20, bg=bg_color, highlightthickness=0,
                                         cursor="hand2")
            self.canvas_icon.pack(side="left", padx=(0, 4))
            self.canvas_icon.bind("<Button-1>", self.toggle)
            self._draw_arrow()

        # O block else foi removido para tirar a indentação de 24px em nós folha, já que a estrutura agora é plana.

        self.chk = BlueCheckButton(self.header, text=text, variable=self.var, bg=bg_color, command=self._on_check)

        # Bloqueia a caixinha se o estado for disabled
        if state == "disabled":
            self.chk.state(["disabled"])

        self.chk.pack(side="left", pady=4)

        if is_card_level:
            self.chk.itemconfigure(self.chk.find_withtag("text"), font=("Segoe UI", 11, "bold"))
        elif not is_leaf:
            self.chk.itemconfigure(self.chk.find_withtag("text"), font=("Segoe UI", 10, "bold"))
        else:
            self.chk.itemconfigure(self.chk.find_withtag("text"), font=("Segoe UI", 10))

        if not is_leaf:
            self.header.bind("<Button-1>", self.toggle)

            self.content = tk.Frame(self, bg=bg_color)

            indent_frame = tk.Frame(self.content, bg=bg_color, width=28)
            indent_frame.pack(side="left", fill="y")
            tk.Frame(indent_frame, bg=Colors.BORDER, width=1).pack(side="right", fill="y", pady=2, padx=10)

            self.content_inner = tk.Frame(self.content, bg=bg_color)
            self.content_inner.pack(side="left", fill="both", expand=True)

    def _draw_arrow(self):
        self.canvas_icon.delete("all")
        if self.expanded:
            # Seta para baixo, outline aplicado para suavizar os contornos
            self.canvas_icon.create_polygon(4, 7, 16, 7, 10, 15, fill=Colors.PRIMARY, outline=Colors.PRIMARY, width=1)
        else:
            # Seta para a direita com outline para suavizar
            self.canvas_icon.create_polygon(7, 4, 7, 16, 15, 10, fill=Colors.TEXT_HINT, outline=Colors.TEXT_HINT,
                                            width=1)

    def add_child(self, child_node):
        self.child_nodes.append(child_node)
        child_node.pack(fill="x")

    def toggle(self, event=None):
        if self.is_leaf: return
        self.expanded = not self.expanded

        self._draw_arrow()

        if self.expanded:
            self.content.pack(fill="both", expand=True, after=self.header)
        else:
            self.content.pack_forget()

        if self.on_toggle_callback:
            self.on_toggle_callback()

    def _on_check(self):
        state = self.var.get()
        self._set_children_state(state)

    def _set_children_state(self, state):
        for child in self.child_nodes:
            child.var.set(state)
            child._set_children_state(state)


# =====================================================================
# Tela Principal de Perfis
# =====================================================================
class PerfisPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        cols = [
            {"id": "Nome", "title": "Nome", "type": "text", "width": 250, "anchor": "w"},
            {"id": "Descricao", "title": "Descrição", "type": "text", "width": 500, "anchor": "w"},
        ]

        def _fetch_data(page: int, page_size: int, filters: list):
            total, rows = perfis_repo.list(page, page_size, filters)
            return total, rows

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch_data, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="new")

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

        self._open_perfil_modal("edit", sel)

    def _delete_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        perfil_id = sel.get("Id")
        nome_perfil = sel.get("Nome")

        if perfil_id == 1:
            self.alert("Acesso Negado", "O perfil Administrador padrão não pode ser excluído.", type="warning")
            return

        # 1. Verificação de Integridade: Impede excluir perfis em uso
        try:
            res = perfis_repo.execute_query("SELECT COUNT(Id) as Qtd FROM Usuarios WHERE PerfilId = ?", (perfil_id,))
            qtd_usuarios = res[0]["Qtd"] if res else 0

            if qtd_usuarios > 0:
                self.alert("Operação Bloqueada", "Não é possível excluir, há usuários utilizando este perfil.",
                           type="error")
                return
        except Exception as e:
            self.alert("Erro", f"Falha ao verificar vínculo com usuários:\n{str(e)}", type="error")
            return

        # 2. Exclusão Real
        def _confirmar():
            try:
                perfis_repo.delete(perfil_id)
                self.alert("Sucesso", f"Perfil '{nome_perfil}' excluído com sucesso!", type="success")

                # Desabilita os botões e recarrega a tabela
                self.btn_edit.state(["disabled"])
                self.btn_del.state(["disabled"])
                self.table.load_page(1)
            except Exception as e:
                self.alert("Erro de Sistema", f"Falha ao excluir o perfil:\n{str(e)}", type="error")

        self.ask_yes_no("Confirmar exclusão",
                        f"Deseja realmente excluir o perfil '{nome_perfil}'?\nEsta ação não pode ser desfeita.",
                        on_yes=_confirmar)

    # =========================================================================
    # MODAL DE CRIAÇÃO/EDIÇÃO COM LISTA DE PERMISSÕES PLANA
    # =========================================================================
    def _open_perfil_modal(self, mode="add", initial=None):
        # Identifica se é o perfil padrão do sistema (ID 1)
        is_readonly = (mode == "edit" and initial and initial.get("Id") == 1)

        if is_readonly:
            titulo = "Visualizar Perfil (Padrão do Sistema)"
        else:
            titulo = "Novo Perfil de Acesso" if mode == "add" else "Editar Perfil"

        top = SaaSModal(self, title=titulo, width=700, height=750)

        main_container = ttk.Frame(top.content, style="Main.TFrame")
        main_container.pack(fill="both", expand=True)

        frm_header = tk.Frame(main_container, bg=Colors.BG_APP)
        frm_header.pack(side="top", fill="x", padx=20, pady=(20, 10))

        ent_nome = TextField(frm_header, placeholder="Nome", height=34, width=200)
        ent_nome.pack(side="left", padx=(0, 12))

        ent_desc = TextField(frm_header, placeholder="Descrição", height=34)
        ent_desc.pack(side="left", fill="x", expand=True)

        # Bloqueia a digitação do nome e descrição
        if is_readonly:
            ent_nome.configure(state="disabled")
            ent_desc.configure(state="disabled")

        frm_footer = ttk.Frame(main_container, style="Main.TFrame")
        frm_footer.pack(side="bottom", fill="x", padx=20, pady=20)

        self.perm_vars = {}

        def _save():
            if is_readonly: return  # Trava de segurança extra

            nome = ent_nome.get().strip()
            descricao = ent_desc.get().strip()
            if not nome:
                top.alert("Atenção", "O nome do perfil é obrigatório.", focus_widget=ent_nome)
                return

            permissoes_selecionadas = {k: True for k, var in self.perm_vars.items() if var.get()}

            try:
                if mode == "add":
                    perfis_repo.criar_perfil(nome, descricao, permissoes_selecionadas)
                    msg_sucesso = f"Perfil '{nome}' guardado com sucesso!"
                else:
                    perfis_repo.update(uid=initial["Id"], Nome=nome, Descricao=descricao,
                                       Permissoes=json.dumps(permissoes_selecionadas))
                    msg_sucesso = f"Perfil '{nome}' atualizado com sucesso!"

                self.table.load_page(self.table.page)
                top.close()
                self.alert("Sucesso", msg_sucesso, type="success")

            except Exception as e:
                if "UNIQUE" in str(e).upper() or "DUPLICATE" in str(e).upper():
                    top.alert("Erro", "Já existe um perfil com este nome.", type="error")
                else:
                    top.alert("Erro de Sistema", f"Falha ao salvar:\n{str(e)}", type="error")

        # Muda o rodapé se for somente leitura
        if is_readonly:
            PillButton(frm_footer, text="Fechar", command=top.close, variant="primary").pack(side="right")
        else:
            PillButton(frm_footer, text="Salvar Perfil", command=_save, variant="success").pack(side="right")
            PillButton(frm_footer, text="Cancelar", command=top.close, variant="outline").pack(side="right", padx=10)

        frm_scroll = tk.Frame(main_container, bg=Colors.BG_APP)
        frm_scroll.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 0))

        canvas = tk.Canvas(frm_scroll, bg=Colors.BG_APP, highlightthickness=0)
        scrollbar = MinimalScrollbar(frm_scroll, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_content = tk.Frame(canvas, bg=Colors.BG_APP)
        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

        def _on_mousewheel(e):
            if canvas.yview() == (0.0, 1.0): return
            if e.num == 5 or getattr(e, "delta", 0) < 0:
                if canvas.yview()[1] < 1.0: canvas.yview_scroll(1, "units")
            elif e.num == 4 or getattr(e, "delta", 0) > 0:
                if canvas.yview()[0] > 0.0: canvas.yview_scroll(-1, "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        tk.Label(scroll_content, text="Permissões do Sistema", font=("Segoe UI", 12, "bold"), bg=Colors.BG_APP,
                 fg=Colors.PRIMARY).pack(anchor="w", pady=(0, 10))

        # Estado a ser repassado para a criação das caixinhas
        node_state = "disabled" if is_readonly else "normal"

        for mod_key, mod_info in MOCK_HIERARQUIA_PERMISSOES.items():

            # Subtítulo de seção fora do Card
            tk.Label(scroll_content, text=mod_info["titulo"], font=("Segoe UI", 11, "bold"),
                     bg=Colors.BG_APP, fg=Colors.TEXT_HINT).pack(anchor="w", pady=(10, 5), padx=5)

            card = RoundedCard(scroll_content, padding=(10, 10, 10, 10), radius=8)
            card.pack(fill="x", pady=(0, 10))

            # Montagem das checkboxes achatadas dentro do card
            for item_key, item_info in mod_info["itens"].items():
                node = CollapsiblePermissionNode(
                    card.content, text=item_info["nome"], is_leaf=True,
                    bg_color=Colors.BG_CARD, perm_vars_dict=self.perm_vars, perm_key=item_key,
                    state=node_state
                )
                node.pack(fill="x")

        if mode == "edit" and initial:
            # Usa tk.NORMAL momentaneamente só para injetar o texto antes de travar
            ent_nome.configure(state="normal")
            ent_nome.insert(0, initial.get("Nome", ""))
            if is_readonly: ent_nome.configure(state="disabled")

            desc = initial.get("Descricao")
            ent_desc.configure(state="normal")
            ent_desc.insert(0, desc if desc else "")
            if is_readonly: ent_desc.configure(state="disabled")

            # Se for o Administrador, força tudo a ficar checado visualmente
            if is_readonly:
                for var in self.perm_vars.values():
                    var.set(True)
            else:
                perms_salvas = perfis_repo.obter_permissoes(initial["Id"])
                for chave, var in self.perm_vars.items():
                    if perms_salvas.get(chave) is True:
                        var.set(True)

        if mode == "add":
            ent_nome.focus_set()