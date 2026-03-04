import tkinter as tk
from tkinter import ttk

from database.repositories import (
    products_repo, families_repo, units_repo, global_policies, addresses_repo, areas_repo
)
from ui.components import (
    Page, PillButton, StandardTable, SaaSModal, TabButton, ToggleSwitch,
    TextField, PillCombobox, BlueCheckButton, RoundedCard, CardSectionSeparator,
    ScrollableFrame, SegmentedButton, ToolTip, SaaSDialog
)
from utils.constants import Colors, PAGE_SIZE_DEFAULT
from utils.helpers import Utils, load_icon, AuditManager


class CadastroProdutosPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self._f5_bound = False

        cols = [
                   # 1. Colunas Principais (Ordem Visual)
                   {"id": "Sku", "title": "SKU", "type": "text", "width": 100, "anchor": "w"},
                   {"id": "Ean", "title": "EAN/GTIN", "type": "text", "width": 120, "anchor": "center"},
                   {"id": "Descricao", "title": "Descrição", "type": "text", "width": 380, "anchor": "w"},
                   {"id": "Familia", "title": "Família", "type": "text", "width": 200, "anchor": "w"},
                   {"id": "Picking", "title": "Picking", "type": "text", "width": 100, "anchor": "center"},
                   {"id": "validade_show", "title": "Validade", "type": "text", "width": 140, "anchor": "center"},
                   {"id": "status_show", "title": "Status", "type": "text", "width": 80, "anchor": "center"},

               ] + AuditManager.get_columns()

        def _fetch(page: int, page_size: int, filters: list):
            total, rows = products_repo.list(page, page_size, filters)
            processed_rows = []

            fam_map = {f["Nome"]: f for f in families_repo.get_all()}

            # --- BUSCA O MAPA DE PICKING UMA ÚNICA VEZ ---
            mapa_picking = addresses_repo.get_skus_with_fixed_address()

            for r in rows:
                row_view = dict(r)

                row_view.update(AuditManager.process_row(r))

                # --- PREENCHE A COLUNA PICKING ---
                sku_atual = r.get("Sku")
                row_view["Picking"] = mapa_picking.get(sku_atual, "-")

                # ... (resto da lógica de família e status mantida igual)
                fam_name = r.get("Familia")
                fam_row = fam_map.get(fam_name)

                def resolver_valor(campo_prod, campo_global_attr):
                    val = r.get(campo_prod, "Herdar")

                    if val == "Herdar":
                        if fam_row:
                            val = fam_row.get(campo_prod, "Herdar")
                        else:
                            val = "Herdar"

                    if val == "Herdar" or val is None:
                        val = getattr(global_policies, campo_global_attr, None)

                    return str(val)

                # Lógica visual (Validade)
                v_final = resolver_valor("validade_modo", "modo_validade")
                if v_final == "Validade obrigatória":
                    row_view["validade_show"] = "Obrigatória"
                elif v_final == "Validade opcional":
                    row_view["validade_show"] = "Opcional"
                else:
                    row_view["validade_show"] = "-"

                is_active = r.get("Ativo", True)
                is_blocked = r.get("Bloqueado", False)

                if is_blocked:
                    row_view["status_show"] = "BLOQUEADO"
                    row_view["_text_color"] = Colors.DANGER
                elif not is_active:
                    row_view["status_show"] = "Inativo"
                    row_view["_text_color"] = Colors.TEXT_HINT
                else:
                    row_view["status_show"] = "Ativo"

                for k, v in row_view.items():
                    if v is None:
                        row_view[k] = "-"

                processed_rows.append(row_view)

            return total, processed_rows

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="new")

        # --- BOTÕES NA BARRA DA TABELA ---
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
        self.table.bind("<Return>", lambda e: self._open_edit_dialog())
        self.table.bind("<Delete>", lambda e: self._delete_selected())

    def _on_selection_change(self, _e=None):
        has_sel = (self.table.get_selected() is not None)
        if has_sel:
            self.btn_edit.state(["!disabled"])
            self.btn_del.state(["!disabled"])
        else:
            self.btn_edit.state(["disabled"])
            self.btn_del.state(["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)

    def on_hide(self):
        pass

    def _open_add_dialog(self):
        self._open_product_dialog(mode="add")

    def _open_edit_dialog(self):
        sku = self._selected_sku()
        if not sku:
            return
        row = products_repo.get_by_sku(sku)
        if not row:
            self.alert("Atenção", "Registro não encontrado.", type="warning")
            return
        self._open_product_dialog(mode="edit", initial=row)

    def _open_product_dialog(self, mode="add", initial=None):
        from datetime import datetime

        # --- 1. Variáveis e Configurações Iniciais ---
        GAP = 10
        titulo = "Novo Produto" if mode == "add" else "Editar Produto"
        top = SaaSModal(self, title=titulo, width=930, height=720)

        # --- VARIÁVEIS PRINCIPAIS (Definidas no início para acesso global) ---
        self.var_manual_block = tk.BooleanVar(value=False)
        self.var_block_reason = tk.StringVar()
        self.var_block_obs = tk.StringVar()

        var_ativo = tk.BooleanVar(value=True)
        var_texto_ativo = tk.StringVar()

        def upd_st(*a):
            var_texto_ativo.set("Ativo" if var_ativo.get() else "Inativo")

        upd_st()
        var_ativo.trace_add("write", upd_st)

        # --- 2. Limpeza e Criação do Header com Abas ---
        children = top.header.winfo_children()
        if children:
            for widget in children:
                if isinstance(widget, tk.Label) and widget is not top.btn_close:
                    widget.destroy()

        tabs_container = tk.Frame(top.header, bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0)
        tabs_container.pack(side="left", padx=(24, 0), fill="y")

        self._tab_frames = {}
        self.current_tab_var = tk.StringVar(value=None)
        self._tab_buttons = {}

        tab_defs = [("cadastro", "cadastro"), ("parametros", "políticas")]

        def _switch_tab(tab_id):
            if self.current_tab_var.get() == tab_id: return
            old = self.current_tab_var.get()
            if old in self._tab_frames: self._tab_frames[old].grid_remove()
            self.current_tab_var.set(tab_id)
            for t, btn in self._tab_buttons.items():
                btn.configure(variant="tab_selected" if t == tab_id else "tab_unselected")
            if tab_id in self._tab_frames:
                self._tab_frames[tab_id].grid()
                if tab_id == "parametros": top.update_idletasks()
            if tab_id == "cadastro":
                try:
                    ent_sku.focus_set()
                except:
                    pass

        for i, (tab_id, label) in enumerate(tab_defs):
            btn = TabButton(tabs_container, text=label, command=lambda t=tab_id: _switch_tab(t), height=32)
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0), pady=(8, 0))
            self._tab_buttons[tab_id] = btn

        # --- 3. Layout Principal do Corpo ---
        top.content.columnconfigure(0, weight=1)
        top.content.rowconfigure(0, weight=1)

        body = ttk.Frame(top.content, style="Main.TFrame", padding=0)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        content_stack = ttk.Frame(body, style="Main.TFrame")
        content_stack.grid(row=0, column=0, sticky="nsew")
        content_stack.columnconfigure(0, weight=1)
        content_stack.rowconfigure(0, weight=1)

        cadastro_frame = ttk.Frame(content_stack, style="Main.TFrame", padding=(16, 12, 16, 16))
        params_frame = ttk.Frame(content_stack, style="Main.TFrame", padding=0)

        cadastro_frame.grid(row=0, column=0, sticky="nsew")

        params_frame.grid(row=0, column=0, sticky="nsew")
        params_frame.grid_remove()

        self._tab_frames["cadastro"] = cadastro_frame
        self._tab_frames["parametros"] = params_frame

        # ==============================================================================
        # ABA 1: CADASTRO
        # ==============================================================================
        cadastro_frame.columnconfigure(0, weight=1)
        cadastro_frame.rowconfigure(4, weight=1)

        var_ativo = tk.BooleanVar(value=True)
        var_texto_ativo = tk.StringVar()

        def upd_st(*a):
            var_texto_ativo.set("Ativo" if var_ativo.get() else "Inativo")

        upd_st()
        var_ativo.trace_add("write", upd_st)

        # --- BARRA DE STATUS (Header da Aba) ---
        frm_status_row = ttk.Frame(cadastro_frame, style="Main.TFrame")
        frm_status_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Container ESQUERDO (Para o Botão de Bloqueio)
        frm_status_left = ttk.Frame(frm_status_row, style="Main.TFrame")
        frm_status_left.pack(side="left")

        # Container DIREITO (Para o Toggle Ativo/Inativo)
        frm_status_right = ttk.Frame(frm_status_row, style="Main.TFrame")
        frm_status_right.pack(side="right")

        # >>> Lógica do Modal de Bloqueio <<<
        def _open_block_modal():
            dlg = tk.Toplevel(top)
            dlg.title("Gerenciar Bloqueio")
            dlg.transient(top)
            dlg.grab_set()
            dlg.resizable(False, False)
            dlg.configure(bg=Colors.BG_APP)

            w_dlg, h_dlg = 400, 380
            px = top.winfo_x() + (top.winfo_width() - w_dlg) // 2
            py = top.winfo_y() + (top.winfo_height() - h_dlg) // 2
            dlg.geometry(f"{w_dlg}x{h_dlg}+{int(px)}+{int(py)}")

            cont = ttk.Frame(dlg, style="Main.TFrame", padding=20)
            cont.pack(fill="both", expand=True)

            is_blocked = self.var_manual_block.get()
            title_text = "Produto Bloqueado" if is_blocked else "Bloquear Produto"
            title_color = Colors.DANGER if is_blocked else Colors.TEXT_MAIN
            tk.Label(cont, text=title_text, font=("Segoe UI", 12, "bold"), fg=title_color, bg=Colors.BG_APP).pack(
                anchor="w", pady=(0, 10))

            # Campos (Usando interação direta para evitar bug de limpeza)
            reasons_list = ["Avaria", "Qualidade", "Inventário", "Recall", "Fiscal", "Devolução", "Outros"]

            ttk.Label(cont, text="Motivo:", style="TLabel").pack(anchor="w")
            cmb_r = PillCombobox(cont, values=reasons_list, height=32)
            cmb_r.pack(fill="x", pady=(0, 10))
            cmb_r.set(self.var_block_reason.get())  # Carrega valor inicial

            ttk.Label(cont, text="Observação:", style="TLabel").pack(anchor="w")
            ent_o = TextField(cont, height=80)
            ent_o.pack(fill="x", pady=(0, 20))
            ent_o.insert(0, self.var_block_obs.get())  # Carrega valor inicial

            btns = ttk.Frame(cont, style="Main.TFrame")
            btns.pack(fill="x", side="bottom")

            def _confirm_block():
                r = cmb_r.get().strip()
                o = ent_o.get().strip()
                if not r:
                    SaaSDialog(dlg, "Atenção", "Selecione um motivo.", icon_name="alert_yellow").wait_window()
                    return
                if r == "Outros" and not o:
                    SaaSDialog(dlg, "Atenção", "Observação obrigatória.", icon_name="alert_yellow").wait_window()
                    return

                self.var_manual_block.set(True)
                self.var_block_reason.set(r)
                self.var_block_obs.set(o)
                dlg.destroy()

            def _unlock():
                self.var_manual_block.set(False)
                self.var_block_reason.set("")
                self.var_block_obs.set("")
                dlg.destroy()

            if is_blocked:
                PillButton(btns, text="Desbloquear Produto", variant="success", command=_unlock).pack(side="left")
                PillButton(btns, text="Atualizar Motivo", variant="primary", command=_confirm_block).pack(side="right")
            else:
                PillButton(btns, text="Confirmar Bloqueio", variant="danger", command=_confirm_block).pack(side="right")
                PillButton(btns, text="Cancelar", variant="outline", command=dlg.destroy).pack(side="right", padx=10)

        # 1. BOTÃO DE AÇÃO (Fica na Esquerda)
        def _on_block_action():
            _open_block_modal()

        self.btn_block_action = PillButton(frm_status_left, text="Bloquear", variant="outline", command=_on_block_action,
                                           icon=load_icon("lock", 16))
        self.btn_block_action.pack(side="left")

        def _update_block_btn_visuals(*args):
            if self.var_manual_block.get():
                # Se BLOQUEADO -> Oferece DESBLOQUEAR
                # Agora o 'fg' funciona: Pinta texto E ícone de VERDE
                self.btn_block_action.configure(
                    text="Desbloquear",
                    variant="outline",
                    fg=None,
                    icon=load_icon("unlock", 16)
                )
            else:
                # Se DESBLOQUEADO -> Oferece BLOQUEAR
                # Removemos a cor forçada (fg=None) para voltar ao padrão da variante (Branco no Danger)
                self.btn_block_action.configure(
                    text="Bloquear",
                    variant="outline",
                    fg=None,
                    icon=load_icon("lock", 16)
                )

        self.var_manual_block.trace_add("write", _update_block_btn_visuals)

        # 2. TOGGLE ATIVO/INATIVO (Fica na Direita)
        tk.Label(frm_status_right, textvariable=var_texto_ativo, font=("Segoe UI", 10, "bold"), fg=Colors.TEXT_MAIN,
                 bg=Colors.BG_APP).pack(side="left", padx=(0, GAP))
        ToggleSwitch(frm_status_right, variable=var_ativo, on_color=Colors.SUCCESS).pack(side="left", pady=(1, 0))

        # --- FIM DO BLOCO DE STATUS ---

        frm_row1 = ttk.Frame(cadastro_frame, style="Main.TFrame")
        frm_row1.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        frm_row1.columnconfigure(0, weight=0)
        frm_row1.columnconfigure(1, weight=1)
        ent_sku = TextField(frm_row1, placeholder="SKU", height=32, width=130)
        ent_sku.grid(row=0, column=0, sticky="w", padx=(0, GAP))
        ent_desc = TextField(frm_row1, placeholder="Descrição", height=32, width=100)
        ent_desc.grid(row=0, column=1, sticky="ew", padx=0)

        frm_row2 = ttk.Frame(cadastro_frame, style="Main.TFrame")
        frm_row2.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        # Volta para 3 colunas
        frm_row2.columnconfigure(0, weight=1)
        frm_row2.columnconfigure(1, weight=1)
        frm_row2.columnconfigure(2, weight=1)

        ent_cod_fornec = TextField(frm_row2, placeholder="Cód. Fornecedor", height=32)
        ent_cod_fornec.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        ent_ref = TextField(frm_row2, placeholder="Referência", height=32)
        ent_ref.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        frm_fam_container = ttk.Frame(frm_row2, style="Main.TFrame")
        frm_fam_container.grid(row=0, column=2, sticky="ew", padx=0)
        frm_fam_container.columnconfigure(1, weight=1)

        ttk.Label(frm_fam_container, text="Família:", style="TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))

        fam_names = [r.get("Nome", "") for r in families_repo.get_all() if r.get("Nome")]
        cmb_familia = PillCombobox(frm_fam_container, values=fam_names, placeholder="Selecione", height=32)
        cmb_familia.grid(row=0, column=1, sticky="ew", padx=0)

        # --- 4. TABELA: DEFINIÇÃO ---
        import copy
        if mode == "edit" and initial:
            layer_rows = copy.deepcopy(initial.get("Camadas", []))
        else:
            layer_rows = []
        layer_cols = [
            {"id": "Camada", "title": "Emb.", "width": 50, "anchor": "center"},
            {"id": "Tipo", "title": "Tipo", "width": 90, "anchor": "center"},
            {"id": "Unidade", "title": "Unidade", "width": 90, "anchor": "center"},
            {"id": "FatorConversao", "title": "Fator", "width": 70, "anchor": "center"},
            {"id": "Largura", "title": "L", "width": 80, "anchor": "center"},
            {"id": "Comprimento", "title": "C", "width": 80, "anchor": "center"},
            {"id": "Altura", "title": "A", "width": 80, "anchor": "center"},
            {"id": "PesoBruto", "title": "P. Bruto (kg)", "width": 110, "anchor": "center"},
            {"id": "Ean", "title": "EAN/GTIN", "width": 150, "anchor": "w"},
            {"id": "CriadoPor", "title": "Criado por", "width": 100, "anchor": "center", "hidden": True},
            {"id": "Cadastro", "title": "Data Criação", "width": 130, "anchor": "center", "hidden": True},
            {"id": "AtualizadoPor", "title": "Atualizado por", "width": 100, "anchor": "center", "hidden": True},
            {"id": "Alteracao", "title": "Data Alteração", "width": 130, "anchor": "center", "hidden": True},
            {"id": "Id", "title": "ID", "width": 50, "anchor": "center", "hidden": True},
            {"id": "RowVersion", "title": "RowVersion", "width": 100, "anchor": "center", "hidden": True},
        ]

        def _fetch_layers(p, s, f):
            display_rows = []
            for r in layer_rows:
                cp = r.copy()

                def fmt_dim(val, unit):
                    if val is None or val == "" or float(val or 0) == 0: return "-"
                    return f"{float(val):g} {unit}"

                cp["Largura"] = fmt_dim(r.get("Largura"), r.get("LarguraUn", "mm"))
                cp["Comprimento"] = fmt_dim(r.get("Comprimento"), r.get("ComprimentoUn", "mm"))
                cp["Altura"] = fmt_dim(r.get("Altura"), r.get("AlturaUn", "mm"))
                p_val = r.get("PesoBruto")
                cp["PesoBruto"] = f"{float(p_val):g}" if (p_val and float(p_val) > 0) else "-"
                uni = cp.get("Unidade", "")
                if cp.get("EhPadrao"): uni += " (Padrão)"
                cp["unidade_show"] = uni
                for k, v in cp.items():
                    if v is None:
                        cp[k] = "-"
                display_rows.append(cp)
            return len(display_rows), display_rows

        frm_table_wrap = ttk.Frame(cadastro_frame, style="Main.TFrame")
        frm_table_wrap.grid(row=4, column=0, sticky="nsew")
        frm_table_wrap.grid_propagate(False)
        frm_table_wrap.columnconfigure(0, weight=1)
        frm_table_wrap.rowconfigure(0, weight=1)

        layer_table = StandardTable(frm_table_wrap, columns=layer_cols, fetch_fn=_fetch_layers, minimal=True,
                                    inner_padx=0)
        layer_table.configure(bg=Colors.BG_CARD)
        layer_table.container.configure(highlightbackground=Colors.BORDER, highlightcolor=Colors.BORDER)
        layer_table.header_canvas.configure(bg=Colors.BG_CARD)
        layer_table.body_canvas.configure(bg=Colors.BG_CARD)
        layer_table.grid(row=0, column=0, sticky="nsew")

        # --- Lógica de Camadas (Botões) ---
        btns_camadas = ttk.Frame(cadastro_frame, style="Main.TFrame")
        btns_camadas.grid(row=3, column=0, sticky="ew", pady=(12, 4))
        btns_camadas.columnconfigure(4, weight=1)

        def _recalc_camadas():
            for idx, r in enumerate(layer_rows, start=1):
                r["Camada"] = idx
            layer_table.load_page(layer_table.page)

        _recalc_camadas()

        def _open_layer_dialog(mode_layer="add", index=None):
            # 1. Trava os botões para evitar clique duplo
            btn_add_l.state(["disabled"])
            btn_edit_l.state(["disabled"])
            import threading

            # --- 1. CONFIGURAÇÃO DA JANELA (SaaSModal) ---
            lt = SaaSModal(top, title="Detalhes da Embalagem", width=350, height=540)

            # Pausa loop do pai para evitar congelamento
            if hasattr(top, "_loop_id") and top._loop_id:
                top.after_cancel(top._loop_id)

            original_close = lt.close

            def _close_layer(event=None):
                try:
                    btn_add_l.state(["!disabled"])
                    btn_edit_l.state(["!disabled"])
                except:
                    pass
                # Chama o fechamento padrão do SaaSModal (gerencia pilha e destroy)
                original_close(event)

            # Substitui o método do botão "X" e o protocolo do sistema
            lt.close = _close_layer
            lt.protocol("WM_DELETE_WINDOW", _close_layer)

            # Configura layout no lt.content (corpo do SaaSModal)
            lt.content.columnconfigure(0, weight=1)
            lt.content.rowconfigure(0, weight=1)

            frm = ttk.Frame(lt.content, style="Main.TFrame", padding=(20, 20, 20, 20))
            frm.grid(row=0, column=0, sticky="nsew")

            # Grid layout mais limpo
            frm.columnconfigure(0, weight=1)
            frm.columnconfigure(1, weight=1)

            # --- 2. TIPO DA EMBALAGEM (NOVO) ---
            ttk.Label(frm, text="Tipo de Embalagem:", style="TLabel").grid(row=0, column=0, sticky="w")

            # Os 3 Tipos que definimos
            tipos_validos = ["BASE", "PRODUTO", "RECIPIENTE"]
            cmb_tipo = PillCombobox(frm, values=tipos_validos, width=140, height=32)
            cmb_tipo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 15))
            cmb_tipo.set("RECIPIENTE")  # Default seguro

            # --- UNIDADE ---
            ttk.Label(frm, text="Unidade (Sigla):", style="TLabel").grid(row=0, column=1, sticky="w")
            cmb_uni = PillCombobox(frm, values=["Carregando..."], width=140, height=32)
            cmb_uni.grid(row=1, column=1, sticky="ew", padx=0, pady=(0, 15))
            cmb_uni.configure(state="disabled")

            # Thread para carregar unidades
            def _load_units_bg():
                def _worker():
                    try:
                        raw = units_repo.get_all()
                        data = [r.get("Sigla", "") for r in raw if r.get("Sigla")]
                    except:
                        data = []

                    def _update_ui():
                        if not lt.winfo_exists(): return
                        if data:
                            cmb_uni.configure(values=data, state="normal")
                            # Restaura valor se edição
                            if mode_layer == "edit" and index is not None:
                                cur = layer_rows[index].get("Unidade", "")
                                if cur in data: cmb_uni.set(cur)
                        else:
                            cmb_uni.configure(values=["Erro"], state="normal")

                    lt.after(0, _update_ui)

                threading.Thread(target=_worker, daemon=True).start()

            _load_units_bg()

            # --- FATOR ---
            nome_base = layer_rows[0].get("Unidade", "Base") if layer_rows else "..."
            lbl_fator = f"Fator de Conversão (Qtd em {nome_base}):"

            ttk.Label(frm, text=lbl_fator, style="TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
            ent_fator = TextField(frm, placeholder="1", height=32)
            ent_fator.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15))

            # Separação Visual
            ttk.Separator(frm, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(5, 15))

            # Label de Dimensões
            lbl_dim = ttk.Label(frm, text="Dimensões Físicas:", style="TLabel", font=("Segoe UI", 9, "bold"))
            lbl_dim.grid(row=5, column=0, sticky="w", pady=(0, 10))

            # --- CAMPOS DE DIMENSÃO ---
            def create_dim_field(parent, label_text, r, c):
                f = ttk.Frame(parent, style="Main.TFrame")
                f.grid(row=r, column=c, sticky="w", padx=(0, 10) if c == 0 else 0, pady=(0, 10))

                ttk.Label(f, text=label_text, style="TLabel").pack(anchor="w")
                box = ttk.Frame(f, style="Main.TFrame")
                box.pack(fill="x")

                entry = TextField(box, placeholder="0", height=32, width=80)
                entry.pack(side="left")

                combo = PillCombobox(box, values=["mm", "cm", "m"], width=50, height=32)
                combo.pack(side="left", padx=(4, 0))
                combo.set("mm")  # Default
                return entry, combo

            ent_larg, cmb_larg = create_dim_field(frm, "Largura:", 6, 0)
            ent_comp, cmb_comp = create_dim_field(frm, "Comprimento:", 6, 1)
            ent_alt, cmb_alt = create_dim_field(frm, "Altura:", 7, 0)

            # Peso
            f_peso = ttk.Frame(frm, style="Main.TFrame")
            f_peso.grid(row=7, column=1, sticky="w", pady=(0, 10))
            ttk.Label(f_peso, text="Peso Bruto (kg):", style="TLabel").pack(anchor="w")
            ent_peso = TextField(f_peso, placeholder="0.000", height=32, width=140)
            ent_peso.pack(fill="x")

            def _auto_calc_weight(event=None):
                try:
                    txt_f = ent_fator.get().replace(",", ".").strip()
                    if not txt_f: return
                    f_atual = float(txt_f)
                except ValueError:
                    return

                # Tenta achar uma proporção baseada em embalagens existentes
                ratio = 0
                for r in layer_rows:
                    w = float(r.get("PesoBruto") or 0)
                    f = float(r.get("FatorConversao") or 0)
                    if w > 0 and f > 0:
                        ratio = w / f
                        break

                if ratio > 0:
                    novo_peso = f_atual * ratio
                    ent_peso.delete(0, "end")
                    ent_peso.insert(0, f"{novo_peso:.4g}")

            ent_fator.bind("<KeyRelease>", _auto_calc_weight)

            # --- EAN ---
            ttk.Label(frm, text="EAN / GTIN (Código de Barras):", style="TLabel").grid(row=8, column=0, sticky="w")
            ent_ean = TextField(frm, placeholder="", height=32)
            ent_ean.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 5))

            var_eh_padrao = tk.BooleanVar(value=False)
            chk_padrao = BlueCheckButton(frm, text="Unidade Principal", variable=var_eh_padrao,
                                         bg=Colors.BG_APP)
            chk_padrao.grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 0))

            # --- LÓGICA DE INTERAÇÃO ---
            all_dim_widgets = [
                ent_larg, cmb_larg, ent_comp, cmb_comp,
                ent_alt, cmb_alt, ent_peso
            ]

            def _on_type_change(*args):
                tipo = cmb_tipo.get()

                # Se for BASE, desabilita dimensões
                if tipo == "BASE":
                    for w in all_dim_widgets:
                        if isinstance(w, PillCombobox):
                            w.configure(state="disabled")
                        else:
                            w._entry.config(state="disabled")  # TextField wrapper
                else:
                    # Se for PRODUTO ou RECIPIENTE, habilita
                    for w in all_dim_widgets:
                        if isinstance(w, PillCombobox):
                            w.configure(state="normal")
                        else:
                            w._entry.config(state="normal")

            # Vincula evento ao Combobox de Tipo
            cmb_tipo.bind("<<ComboboxSelected>>", _on_type_change)
            cmb_tipo.bind("<KeyRelease>", _on_type_change)  # Caso digite

            # --- CARREGAR DADOS (EDIT MODE) ---
            if mode_layer == "edit" and index is not None:
                row = layer_rows[index]

                # Carrega Tipo
                tipo_salvo = row.get("Tipo", "RECIPIENTE")
                if tipo_salvo not in tipos_validos: tipo_salvo = "RECIPIENTE"
                cmb_tipo.set(tipo_salvo)

                ent_fator.insert(0, str(row.get("FatorConversao", 1)))
                ent_ean.insert(0, str(row.get("Ean", "")))
                var_eh_padrao.set(row.get("EhPadrao", False))

                # Helper para carregar dimensões
                def load_d(k_val, k_un, ent_w, cmb_w):
                    if row.get(k_val): ent_w.insert(0, str(row.get(k_val)))
                    if row.get(k_un): cmb_w.set(row.get(k_un))

                load_d("Largura", "LarguraUn", ent_larg, cmb_larg)
                load_d("Comprimento", "ComprimentoUn", ent_comp, cmb_comp)
                load_d("Altura", "AlturaUn", ent_alt, cmb_alt)
                if row.get("PesoBruto"): ent_peso.insert(0, str(row.get("PesoBruto")))

                # Regra especial para a primeira linha (Unidade Base)
                if index == 0:
                    cmb_tipo.set("BASE")
                    cmb_tipo.configure(state="disabled")  # Não pode mudar o tipo da base
                    ent_fator.delete(0, "end")
                    ent_fator.insert(0, "1")
                    ent_fator._entry.config(state="disabled")
                    # Bloqueia dimensões
                    _on_type_change()

            elif mode_layer == "add":
                # Se for a primeira embalagem, força ser BASE
                if not layer_rows:
                    cmb_tipo.set("BASE")
                    cmb_tipo.configure(state="disabled")
                    ent_fator.insert(0, "1")
                    ent_fator._entry.config(state="disabled")
                    _on_type_change()
                else:
                    # Se já tem base, sugere RECIPIENTE ou PRODUTO
                    cmb_tipo.set("RECIPIENTE")
                    _on_type_change()

            # --- BOTÕES ---
            btns = ttk.Frame(frm, style="Main.TFrame")
            btns.grid(row=11, column=0, columnspan=2, sticky="e", pady=(20, 0))

            def _save_layer():
                # Validações Básicas
                u = cmb_uni.get().strip()
                t = cmb_tipo.get().strip()
                f_txt = ent_fator.get().strip()

                if u in ["Carregando...", "Erro", ""]:
                    self.alert("Atenção", "Selecione uma unidade válida.", type="warning")
                    return

                try:
                    f = float(f_txt.replace(",", "."))
                    if f <= 0: raise ValueError
                except:
                    self.alert("Atenção", "Fator inválido.", type="warning")
                    return

                # Captura de dados
                novo_dado = {
                    "Tipo": t,
                    "Unidade": u,
                    "FatorConversao": f,
                    "Ean": ent_ean.get().strip(),
                    "EhPadrao": var_eh_padrao.get(),

                    # Se for BASE, ignora dimensões (salva None ou 0)
                    "Largura": Utils.safe_float_or_none(ent_larg.get()) if t != "BASE" else None,
                    "LarguraUn": cmb_larg.get() if t != "BASE" else "mm",

                    "Comprimento": Utils.safe_float_or_none(ent_comp.get()) if t != "BASE" else None,
                    "ComprimentoUn": cmb_comp.get() if t != "BASE" else "mm",

                    "Altura": Utils.safe_float_or_none(ent_alt.get()) if t != "BASE" else None,
                    "AlturaUn": cmb_alt.get() if t != "BASE" else "mm",

                    "PesoBruto": Utils.safe_float_or_none(ent_peso.get()) if t != "BASE" else None,
                }

                # Lógica de ID e Update (Mantida igual ao seu original)
                curr_id = None
                curr_rv = 1
                agora = datetime.now().strftime("%d/%m/%Y %H:%M")

                if mode_layer == "edit" and index is not None:
                    existente = layer_rows[index]
                    existente.update(novo_dado)
                    existente["Alteracao"] = agora
                else:
                    # Novo ID fake para UI
                    ids = [int(r.get("Id", 0)) for r in layer_rows if str(r.get("Id", 0)).isdigit()]
                    novo_dado["Id"] = (max(ids) + 1) if ids else 1
                    novo_dado["RowVersion"] = 1
                    novo_dado["CriadoPor"] = "Admin"
                    novo_dado["Cadastro"] = agora
                    layer_rows.append(novo_dado)

                # Garante que só um seja padrão
                if novo_dado["EhPadrao"]:
                    for i, r in enumerate(layer_rows):
                        if (mode_layer == "add" and i != len(layer_rows) - 1) or \
                                (mode_layer == "edit" and i != index):
                            r["EhPadrao"] = False

                _recalc_camadas()
                _close_layer()

            PillButton(btns, text="Salvar", command=_save_layer, variant="success").pack(side="left", padx=(0, 10))
            PillButton(btns, text="Cancelar", command=_close_layer, variant="outline").pack(side="left")

            lt.protocol("WM_DELETE_WINDOW", _close_layer)
            lt.focus_force()

        def _add_layer():
            _open_layer_dialog("add", None)

        def _edit_layer():
            idx = layer_table._get_current_index()
            if idx != -1 and 0 <= idx < len(layer_rows):
                _open_layer_dialog("edit", idx)
            else:
                SaaSDialog(top, "Atenção", "Selecione uma embalagem.", icon_name="alert").wait_window()

        def _del_layer():
            idx = layer_table._get_current_index()
            if idx != -1 and 0 <= idx < len(layer_rows):
                if idx == 0 and len(layer_rows) > 1: top.alert("Ação Negada", "Não pode excluir Unidade Base.",
                                                               type="error"); return

                def _confirm_del():
                    layer_rows.pop(idx)
                    layer_table._selection_map.clear()
                    layer_table._last_click_id = None
                    _recalc_camadas()

                top.ask_yes_no(title="Excluir", message="Remover esta embalagem?", on_yes=_confirm_del)
            else:
                self.alert("Atenção", "Selecione uma embalagem.", type="warning")

        btn_add_l = PillButton(btns_camadas, text="", command=_add_layer, variant="primary", icon=load_icon("add", 16),
                               padx=9)
        btn_add_l.grid(row=0, column=0, padx=(0, GAP))
        ToolTip(btn_add_l, "Adicionar")

        btn_edit_l = PillButton(btns_camadas, text="", command=_edit_layer, variant="outline",
                                icon=load_icon("edit", 16),
                                padx=9)
        btn_edit_l.grid(row=0, column=1, padx=(0, GAP))
        ToolTip(btn_edit_l, "Editar")

        btn_del_l = PillButton(btns_camadas, text="", command=_del_layer, variant="outline",
                               icon=load_icon("delete", 16),
                               padx=9)
        btn_del_l.grid(row=0, column=2, padx=(0, GAP))
        ToolTip(btn_del_l, "Excluir")

        icon_eye = load_icon("eye", 16)
        icon_eye_off = load_icon("eye_off", 16)

        def _toggle_ids():
            layer_table._toggle_id_cols()
            is_showing = getattr(layer_table, "_ids_visible", False)
            btn_ids.configure(icon=icon_eye_off if is_showing else icon_eye)

        btn_ids = PillButton(btns_camadas, text="", command=_toggle_ids, variant="outline", icon=icon_eye,
                             height=34, padx=9)
        btn_ids.grid(row=0, column=4, sticky="e", padx=0)
        ToolTip(btn_ids, "Auditoria")

        # ==============================================================================
        # ABA 2: POLÍTICAS
        # ==============================================================================

        # Variáveis de Políticas
        var_pol_validade = tk.StringVar(value="Herdar")
        var_pol_lote = tk.StringVar(value="Herdar")
        var_pol_giro = tk.StringVar(value="Herdar")
        var_pol_consumo = tk.StringVar(value="Herdar")
        var_pol_area = tk.StringVar(value="Herdar")
        var_min_mode = tk.StringVar(value="Herdar")
        var_min_val = tk.StringVar()
        var_min_und = tk.StringVar(value="Dias")
        var_vida_mode = tk.StringVar(value="Herdar")
        var_vida_val = tk.StringVar()
        var_vida_und = tk.StringVar(value="Meses")
        var_blk_mode = tk.StringVar(value="Herdar")
        var_blk_vencido = tk.BooleanVar()
        var_blk_semval = tk.BooleanVar()
        var_blk_semlote = tk.BooleanVar()
        var_blk_qualidade = tk.BooleanVar()

        # Scroll e Layout
        params_frame.columnconfigure(0, weight=1)
        params_frame.rowconfigure(0, weight=1)
        scroll_area = ScrollableFrame(params_frame, padding=(20, 20, 0, 20))
        scroll_area.grid(row=0, column=0, sticky="nsew")
        merged_card = RoundedCard(scroll_area.content, padding=(24, 24, 24, 24), radius=8)
        merged_card.pack(fill="x", expand=True, padx=(0, 20), pady=2)
        mc_body = merged_card.content
        mc_body.columnconfigure(0, weight=1, uniform="cols")
        mc_body.columnconfigure(1, weight=0);
        mc_body.columnconfigure(2, weight=1, uniform="cols")

        left_col = tk.Frame(mc_body, bg="#ffffff")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        # --- FUNÇÃO AUXILIAR DE HERANÇA ---
        def _get_eff_value(attr_fam, attr_global, default_global):
            fam_name = cmb_familia.get().strip()
            if not fam_name or fam_name == "Selecione":
                return getattr(global_policies, attr_global, default_global), "Padrão Global"
            fam_row = families_repo.get_by_nome(fam_name)
            if not fam_row:
                return getattr(global_policies, attr_global, default_global), "Padrão Global"
            val_fam = fam_row.get(attr_fam, "Herdar")
            if val_fam == "Herdar" or val_fam is None:
                return getattr(global_policies, attr_global, default_global), f"Família '{fam_name}' (Global)"
            return val_fam, f"Família '{fam_name}'"

        def _create_inheritance_field(parent, label, variable, get_inherited_val, options, custom_start_val=None,
                                      custom_display_text=None, block_check=None, on_personalize=None):
            container = tk.Frame(parent, bg="#ffffff")
            container.pack(fill="x", pady=(0, 15))
            tk.Label(container, text=label, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#374151").pack(anchor="w",
                                                                                                           pady=(0, 4))
            f_dyn = tk.Frame(container, bg="#ffffff")
            f_dyn.pack(fill="x")

            def _render(*args):
                if not f_dyn.winfo_exists(): return
                for w in f_dyn.winfo_children(): w.destroy()
                if block_check:
                    blocked, msg = block_check()
                    if blocked:
                        tk.Label(f_dyn, text=msg, font=("Segoe UI", 9, "italic"), fg=Colors.TEXT_HINT,
                                 bg="#ffffff").pack(anchor="w")
                        top.update_idletasks()
                        return
                val = variable.get()
                inherited_val, origin_txt = get_inherited_val()
                if val == "Herdar":
                    disp = custom_display_text if custom_display_text else inherited_val
                    if not custom_display_text and options:
                        for k, v in options:
                            if v == inherited_val: disp = k; break
                    box = tk.Frame(f_dyn, bg="#F3F4F6", padx=10, pady=8);
                    box.pack(fill="x")
                    tk.Label(box, text="↳", font=("Segoe UI", 12), bg="#F3F4F6", fg="#9CA3AF").pack(side="left",
                                                                                                    padx=(0, 8))
                    tk.Label(box, text=f"{origin_txt}: ", font=("Segoe UI", 9), bg="#F3F4F6", fg="#6B7280").pack(
                        side="left")
                    tk.Label(box, text=disp, font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg="#374151").pack(side="left")
                    btn = tk.Label(box, text="Personalizar", font=("Segoe UI", 9, "bold"), bg="#F3F4F6",
                                   fg=Colors.PRIMARY, cursor="hand2")
                    btn.pack(side="right")
                    target = custom_start_val if custom_start_val else inherited_val

                    # --- ATUALIZAÇÃO: Executa callback ao personalizar ---
                    def _on_click(e):
                        if on_personalize: on_personalize()
                        variable.set(target)

                    btn.bind("<Button-1>", _on_click)
                else:
                    head = tk.Frame(f_dyn, bg="#ffffff")
                    head.pack(fill="x", pady=(0, 4))
                    tk.Label(head, text="Personalizado", font=("Segoe UI", 8, "bold"), bg="#ffffff",
                             fg=Colors.PRIMARY).pack(side="left")
                    rst = tk.Label(head, text="× Voltar ao Padrão", font=("Segoe UI", 8), bg="#ffffff", fg="#EF4444",
                                   cursor="hand2")
                    rst.pack(side="right")
                    rst.bind("<Button-1>", lambda e: variable.set("Herdar"))
                    if len(options) > 1: SegmentedButton(f_dyn, variable=variable, options=options).pack(fill="x")
                top.update_idletasks()

            variable.trace_add("write", _render)
            return _render

        # --- COLUNA ESQUERDA (Lógica da Validade que fizemos antes) ---
        _render_validade = _create_inheritance_field(
            left_col, "Validade", var_pol_validade,
            lambda: _get_eff_value("ValidadeModo", "modo_validade", "Validade opcional"),
            [("Sem val", "Sem validade"), ("Opcional", "Validade opcional"), ("Obrigatória", "Validade obrigatória")]
        )

        # Shelf Life e Mínimo (Lógica mantida)
        tk.Label(left_col, text="Prazo de Validade:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#374151").pack(
            anchor="w", pady=(8, 4))
        f_shelf = tk.Frame(left_col, bg="#ffffff")
        f_shelf.pack(anchor="w", fill="x", pady=(0, 15))

        def _render_shelf(*args):
            for w in f_shelf.winfo_children(): w.destroy()

            # 1. Verifica a regra efetiva (Herdada ou Direta)
            cur_v = var_pol_validade.get()
            if cur_v == "Herdar":
                eff_v, _ = _get_eff_value("ValidadeModo", "modo_validade", "Validade opcional")
            else:
                eff_v = cur_v

            # 2. BLOQUEIO ROBUSTO: Verifica se é "Sem" ou "Sem validade"
            if eff_v in ["Sem", "Sem validade"]:
                tk.Label(f_shelf, text="Não aplicável",
                         font=("Segoe UI", 9, "italic"), fg=Colors.TEXT_HINT, bg="#ffffff").pack(anchor="w")
                top.update_idletasks()
                return

            # 3. Se não for bloqueado, renderiza os campos normais
            # (Busca dados da família para mostrar como referência no modo Herdar)
            fam_name = cmb_familia.get().strip()
            fam_row = families_repo.get_by_nome(fam_name) if fam_name else None
            f_life = fam_row.get("VidaUtil") if fam_row else None
            f_unit = "Dias"

            txt_inherited = f"{f_life} {f_unit}" if f_life else "Não definido"
            origin = f"Família '{fam_name}'" if fam_row else "Padrão Global"

            if var_vida_mode.get() == "Herdar":
                box = tk.Frame(f_shelf, bg="#F3F4F6", padx=10, pady=8)
                box.pack(fill="x")
                tk.Label(box, text="↳", font=("Segoe UI", 12), bg="#F3F4F6", fg="#9CA3AF").pack(side="left",
                                                                                                padx=(0, 8))
                tk.Label(box, text=f"{origin}: ", font=("Segoe UI", 9), bg="#F3F4F6", fg="#6B7280").pack(
                    side="left")
                tk.Label(box, text=txt_inherited, font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg="#374151").pack(
                    side="left")
                btn = tk.Label(box, text="Personalizar", font=("Segoe UI", 9, "bold"), bg="#F3F4F6",
                               fg=Colors.PRIMARY,
                               cursor="hand2")
                btn.pack(side="right")
                btn.bind("<Button-1>", lambda e: var_vida_mode.set("Personalizar"))
            else:
                head = tk.Frame(f_shelf, bg="#ffffff")
                head.pack(fill="x", pady=(0, 4))
                tk.Label(head, text="Personalizado", font=("Segoe UI", 8, "bold"), bg="#ffffff",
                         fg=Colors.PRIMARY).pack(side="left")
                rst = tk.Label(head, text="× Voltar ao Padrão", font=("Segoe UI", 8), bg="#ffffff", fg="#EF4444",
                               cursor="hand2")
                rst.pack(side="right")
                rst.bind("<Button-1>", lambda e: var_vida_mode.set("Herdar"))

                row = tk.Frame(f_shelf, bg="#ffffff")
                row.pack(fill="x")
                ent = TextField(row, width=60, height=30)
                ent._entry.config(textvariable=var_vida_val, justify="center")
                ent.pack(side="left")

                # ALTERADO: Substituída a Combobox por Label fixo "dias"
                tk.Label(row, text="dias", font=("Segoe UI", 9), bg="#ffffff").pack(side="left", padx=8)

            top.update_idletasks()

        var_vida_mode.trace_add("write", _render_shelf)

        # Vencimento Mínimo
        f_min_container = tk.Frame(left_col, bg="#ffffff")
        f_min_container.pack(fill="x")

        def _render_min_custom(*args):
            for w in f_min_container.winfo_children(): w.destroy()

            tk.Label(f_min_container, text="Vencimento Mínimo (Recebimento)", font=("Segoe UI", 9, "bold"),
                     bg="#ffffff", fg="#374151").pack(anchor="w", pady=(0, 4))

            # 1. Verifica a regra efetiva (igual acima)
            cur_v = var_pol_validade.get()
            if cur_v == "Herdar":
                eff_v, _ = _get_eff_value("ValidadeModo", "modo_validade", "Validade opcional")
            else:
                eff_v = cur_v

            # 2. BLOQUEIO ROBUSTO
            if eff_v in ["Sem", "Sem validade"]:
                tk.Label(f_min_container, text="Não aplicável",
                         font=("Segoe UI", 9, "italic"), fg=Colors.TEXT_HINT, bg="#ffffff").pack(anchor="w",
                                                                                                 pady=(0, 15))
                top.update_idletasks()
                return

            # 3. Renderização normal
            val_inh, src_txt = _get_eff_value("ValidadeMinimaDias", "ValidadeMinimaDias", None)
            disp_txt = f"{val_inh} dias" if val_inh else "Não definido"

            if var_min_mode.get() == "Herdar":
                box = tk.Frame(f_min_container, bg="#F3F4F6", padx=10, pady=8)
                box.pack(fill="x", pady=(0, 15))
                tk.Label(box, text="↳", font=("Segoe UI", 12), bg="#F3F4F6", fg="#9CA3AF").pack(side="left",
                                                                                                padx=(0, 8))
                tk.Label(box, text=f"{src_txt}: ", font=("Segoe UI", 9), bg="#F3F4F6", fg="#6B7280").pack(
                    side="left")
                tk.Label(box, text=disp_txt, font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg="#374151").pack(
                    side="left")
                btn = tk.Label(box, text="Personalizar", font=("Segoe UI", 9, "bold"), bg="#F3F4F6",
                               fg=Colors.PRIMARY,
                               cursor="hand2")
                btn.pack(side="right")
                btn.bind("<Button-1>", lambda e: var_min_mode.set("Personalizar"))
            else:
                subhead = tk.Frame(f_min_container, bg="#ffffff")
                subhead.pack(fill="x", pady=(0, 4))
                tk.Label(subhead, text="Personalizado", font=("Segoe UI", 8, "bold"), bg="#ffffff",
                         fg=Colors.PRIMARY).pack(side="left")
                rst = tk.Label(subhead, text="× Voltar ao Padrão", font=("Segoe UI", 8), bg="#ffffff", fg="#EF4444",
                               cursor="hand2")
                rst.pack(side="right")
                rst.bind("<Button-1>", lambda e: var_min_mode.set("Herdar"))

                row = tk.Frame(f_min_container, bg="#ffffff")
                row.pack(fill="x", pady=(0, 15))
                ent = TextField(row, width=60, height=30)
                ent._entry.config(textvariable=var_min_val, justify="center")
                ent.pack(side="left")
                tk.Label(row, text="dias", font=("Segoe UI", 9), bg="#ffffff").pack(side="left", padx=8)

            top.update_idletasks()

        var_min_mode.trace_add("write", _render_min_custom)

        # GATILHOS EXTRAS
        var_pol_validade.trace_add("write", lambda *a: _render_shelf())
        var_pol_validade.trace_add("write", lambda *a: _render_min_custom())

        cmb_familia._var.trace_add("write", lambda *a: _render_shelf())
        cmb_familia._var.trace_add("write", lambda *a: _render_min_custom())

        CardSectionSeparator(left_col).pack(fill="x", pady=(20, 15))

        _render_cons = _create_inheritance_field(
            left_col, "Variável de Consumo", var_pol_consumo,
            lambda: _get_eff_value("VariavelConsumo", "VariavelConsumo", "Padrão"),
            [("Und", "Padrão"), ("Larg", "Largura"), ("Comp", "Comprimento"), ("Peso", "Peso")]
        )

        # --- ÁREA DE ARMAZENAGEM (Posicionada Fora do Loop) ---
        CardSectionSeparator(left_col).pack(fill="x", pady=(20, 15))

        container_area = tk.Frame(left_col, bg="#ffffff")
        container_area.pack(fill="x", pady=(0, 15))
        tk.Label(container_area, text="Área de Armazenagem", font=("Segoe UI", 9, "bold"), bg="#ffffff",
                 fg="#374151").pack(anchor="w", pady=(0, 4))
        f_dyn_area = tk.Frame(container_area, bg="#ffffff")
        f_dyn_area.pack(fill="x")

        lista_areas_prod = [a['Nome'] for a in areas_repo.get_all() if a['Ativo']]

        def _render_area_custom(*args):
            if not f_dyn_area.winfo_exists(): return

            val_atual = var_pol_area.get()

            # --- MODO A: HERDAR (Cascata: Família -> Global -> Indefinido) ---
            if val_atual == "Herdar":
                for w in f_dyn_area.winfo_children(): w.destroy()

                fam_name = cmb_familia.get().strip()

                # 1. Tenta pegar da Família
                inh_val = None
                inh_src = ""

                if fam_name and fam_name != "Selecione":
                    fam_row = families_repo.get_by_nome(fam_name)
                    if fam_row:
                        v_fam = fam_row.get("AreaPreferencial")
                        if v_fam and str(v_fam).strip():
                            inh_val = v_fam
                            inh_src = f"Família '{fam_name}'"

                # 2. Se não achou na família (ou não tem família), tenta no Global
                if not inh_val:
                    v_global = getattr(global_policies, "area_preferencial_padrao", None)
                    if v_global and str(v_global).strip():
                        inh_val = v_global
                        inh_src = "Padrão Global"
                    else:
                        inh_val = "Indefinido"
                        inh_src = "Sistema (Sem Padrão)"

                # Renderiza a caixa cinza informativa
                box = tk.Frame(f_dyn_area, bg="#F3F4F6", padx=10, pady=8)
                box.pack(fill="x")
                tk.Label(box, text="↳", font=("Segoe UI", 12), bg="#F3F4F6", fg="#9CA3AF").pack(side="left",
                                                                                                padx=(0, 8))

                # Texto de Origem (Ex: "Padrão Global: ")
                tk.Label(box, text=f"{inh_src}: ", font=("Segoe UI", 9), bg="#F3F4F6", fg="#6B7280").pack(side="left")

                # Valor Herdado (Ex: "Recepção A")
                tk.Label(box, text=inh_val, font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg="#374151").pack(side="left")

                btn = tk.Label(box, text="Personalizar", font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg=Colors.PRIMARY,
                               cursor="hand2")
                btn.pack(side="right")

                def _sw_custom(e):
                    # Ao clicar em personalizar, sugere o valor que estava sendo herdado
                    start_val = inh_val if inh_val in lista_areas_prod else (
                        lista_areas_prod[0] if lista_areas_prod else "")
                    f_dyn_area.after(50, lambda: var_pol_area.set(start_val))

                btn.bind("<Button-1>", _sw_custom)

            # --- MODO B: PERSONALIZADO ---
            else:
                # Verifica se já estamos exibindo a Combobox.
                children = f_dyn_area.winfo_children()
                combobox_existente = None

                for w in children:
                    if isinstance(w, PillCombobox):
                        combobox_existente = w
                        break

                # Se já existe a combobox, apenas sincroniza visualmente (se necessário) e retorna
                if combobox_existente:
                    if combobox_existente.get() != val_atual:
                        combobox_existente.set(val_atual)
                    return

                # Se não existe, limpa e desenha do zero
                for w in f_dyn_area.winfo_children(): w.destroy()

                head = tk.Frame(f_dyn_area, bg="#ffffff")
                head.pack(fill="x", pady=(0, 4))
                tk.Label(head, text="Personalizado", font=("Segoe UI", 8, "bold"), bg="#ffffff",
                         fg=Colors.PRIMARY).pack(side="left")

                rst = tk.Label(head, text="× Voltar ao Padrão", font=("Segoe UI", 8), bg="#ffffff", fg="#EF4444",
                               cursor="hand2")
                rst.pack(side="right")
                rst.bind("<Button-1>", lambda e: var_pol_area.set("Herdar"))

                # --- CORREÇÃO: Uso de variável ponte (bridge) ---
                bridge_var = tk.StringVar()

                # Instancia a Combobox passando a variável
                cmb_area_pol = PillCombobox(f_dyn_area, values=lista_areas_prod, height=34, variable=bridge_var)
                cmb_area_pol.pack(fill="x")
                cmb_area_pol.set(val_atual)

                # Mantém referência para evitar Garbage Collection
                cmb_area_pol._bridge = bridge_var

                def _sync_bridge(*args):
                    # Pega o valor usando .get() do componente, que já trata o placeholder
                    val = cmb_area_pol.get()
                    # Só atualiza se for diferente para evitar loop infinito
                    if val != var_pol_area.get():
                        var_pol_area.set(val)

                # Monitora mudanças na variável da combobox e reflete na variável principal
                bridge_var.trace_add("write", _sync_bridge)

            top.update_idletasks()

        var_pol_area.trace_add("write", _render_area_custom)
        cmb_familia._var.trace_add("write", lambda *a: _render_area_custom())

        # === SEPARADOR VERTICAL ===
        sep_vert = tk.Frame(mc_body, width=1, bg=Colors.BORDER, bd=0, highlightthickness=0)
        sep_vert.grid(row=0, column=1, sticky="ns", padx=24)

        # === DIREITA ===
        right_col = tk.Frame(mc_body, bg="#ffffff")
        right_col.grid(row=0, column=2, sticky="nsew")

        # LOTE
        _render_lote = _create_inheritance_field(
            right_col, "Controle de Lote", var_pol_lote,
            lambda: _get_eff_value("LoteModo", "modo_lote", "Lote opcional"),
            [("Sem Lote", "Sem lote"), ("Opcional", "Lote opcional"), ("Obrigatório", "Lote obrigatório")]
        )

        # GIRO
        _render_giro = _create_inheritance_field(
            right_col, "Giro de Estoque", var_pol_giro,
            lambda: _get_eff_value("GiroModo", "modelo_giro", "FEFO"),
            [("FEFO", "FEFO"), ("FIFO", "FIFO"), ("LIFO", "LIFO")]
        )

        CardSectionSeparator(right_col).pack(fill="x", pady=(10, 20))

        # BLOQUEIOS
        def _get_blk_inherited():
            fam_name = cmb_familia.get().strip()
            # Se não tem família, retorna Padrão Global
            if not fam_name or fam_name == "Selecione":
                return "Padrão do Sistema", "Padrão Global"

            fam_row = families_repo.get_by_nome(fam_name)
            if not fam_row:
                return "Padrão do Sistema", "Padrão Global"

            row_lower = {k.lower(): v for k, v in fam_row.items()}
            keys = ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade",
                    "block_vencido", "block_sem_validade", "block_sem_lote", "block_rep_qualidade"]

            has_explicit = False
            for k in keys:
                if row_lower.get(k) is not None:
                    has_explicit = True;
                    break

            if has_explicit: return "Regra da Família", f"Família '{fam_name}'"
            return "Padrão do Sistema", f"Família '{fam_name}'"

        # --- NOVA FUNÇÃO: Carrega valores da família para os checkboxes ---
        def _load_current_blocks_to_vars():
            fam_name = cmb_familia.get().strip()
            fam_row = families_repo.get_by_nome(fam_name) if fam_name and fam_name != "Selecione" else None

            row_lower = {k.lower(): v for k, v in fam_row.items()} if fam_row else {}

            def resolve(keys, global_attr):
                # 1. Tenta Família
                if row_lower:
                    for k in keys:
                        val = row_lower.get(k)
                        if val is not None: return bool(val)
                # 2. Tenta Global
                return bool(getattr(global_policies, global_attr, False))

            var_blk_vencido.set(resolve(["BlockVencido", "block_vencido"], "bloquear_vencido"))
            var_blk_semval.set(resolve(["BlockSemValidade", "block_sem_validade"], "bloquear_sem_validade_obrigatoria"))
            var_blk_semlote.set(resolve(["BlockSemLote", "block_sem_lote"], "bloquear_sem_lote_obrigatorio"))
            var_blk_qualidade.set(
                resolve(["BlockRepQualidade", "block_rep_qualidade"], "bloquear_reprovacao_qualidade"))

        f_blk_container = tk.Frame(right_col, bg="#ffffff")
        f_blk_container.pack(fill="x")

        # Passamos a nova função no on_personalize
        _render_blk = _create_inheritance_field(
            f_blk_container, "Bloqueios Automáticos", var_blk_mode,
            _get_blk_inherited,
            [("Manual", "Personalizar")],
            custom_start_val="Personalizar",
            on_personalize=_load_current_blocks_to_vars
        )

        f_blk_opts = tk.Frame(right_col, bg="#ffffff")
        f_blk_opts.pack(fill="x", pady=(0, 60))

        def _render_blk_custom(*args):
            for w in f_blk_opts.winfo_children(): w.destroy()
            if var_blk_mode.get() == "Personalizar":
                items = [
                    ("Produto vencido", var_blk_vencido),
                    ("Sem validade (se obrigatório)", var_blk_semval),
                    ("Sem lote (se obrigatório)", var_blk_semlote),
                    ("Reprovado qualidade", var_blk_qualidade)
                ]
                for lbl, var in items:
                    BlueCheckButton(f_blk_opts, text=lbl, variable=var, bg="#ffffff").pack(anchor="w", pady=3)
            top.update_idletasks()

        var_blk_mode.trace_add("write", _render_blk_custom)
        _render_blk_custom()

        # Espaçador Final
        tk.Frame(mc_body, height=40, bg="#ffffff").grid(row=99, column=0, columnspan=3)

        # --- TRIGGER DE RECALCULO GERAL ---
        def _recalc_all_inheritance(*args):
            _render_validade()
            _render_shelf()
            _render_min_custom()
            _render_cons()
            _render_area_custom()
            _render_lote()
            _render_giro()
            _render_blk()
            _render_blk_custom()
            _update_block_btn_visuals()

        cmb_familia._var.trace_add("write", _recalc_all_inheritance)

        # === RODAPÉ ===
        footer = ttk.Frame(body, style="Main.TFrame")
        footer.grid(row=1, column=0, sticky="e", padx=(0, 16), pady=(16, 16))

        def _save_product():
            sku_val = ent_sku.get().strip()
            if not sku_val:
                top.alert(title="Atenção", message="Informe o SKU.", focus_widget=ent_sku,
                          pre_focus_action=lambda: _switch_tab("cadastro"))
                return

            desc_val = ent_desc.get().strip()
            if not desc_val:
                top.alert(title="Atenção", message="A Descrição é obrigatória.", focus_widget=ent_desc,
                          pre_focus_action=lambda: _switch_tab("cadastro"))
                return

            if not layer_rows:
                top.alert(title="Atenção",
                          message="O produto deve ter uma embalagem cadastrada.",
                          pre_focus_action=lambda: _switch_tab("cadastro"))
                return

            # --- 2. LÓGICA EAN PRINCIPAL ---
            ean_val = ""
            layer_padrao = next((r for r in layer_rows if r.get("EhPadrao")), None)
            if layer_padrao:
                ean_val = layer_padrao.get("Ean", "").strip()
            elif layer_rows and len(layer_rows) == 1:
                ean_val = layer_rows[0].get("Ean", "").strip()
                layer_rows[0]["EhPadrao"] = True

            if ean_val and not Utils.is_valid_gtin(ean_val):
                top.alert(title="Erro", message=f"O EAN da unidade padrão ({ean_val}) é inválido.")
                return

            ean_clean = "".join(filter(str.isdigit, ean_val))
            if len(ean_clean) == 14 and ean_clean[0] in "12345678":
                top.alert(title="Código de Caixa Detectado",
                          message=f"O código {ean_val} é um GTIN-14 de Caixa.\n\nEste campo aceita apenas o código da UNIDADE.\nCadastre a caixa na tabela de 'Embalagens'.",
                          type="warning", pre_focus_action=lambda: _switch_tab("Cadastro"))
                return

            unidade_definida = ""
            found_std = False
            for layer in layer_rows:
                if layer.get("EhPadrao", False):
                    unidade_definida = layer.get("Unidade", "")
                    found_std = True
                    break
            if not found_std and layer_rows:
                first = layer_rows[0]
                unidade_definida = first.get("Unidade", "")
                first["EhPadrao"] = True

            # --- DADOS ---
            val_min_final = None
            if var_min_mode.get() == "Personalizar":
                m = var_min_val.get().strip()
                if m.isdigit():
                    val_min_final = int(m)
                else:
                    val_min_final = 0

            val_vida_util = None
            if var_vida_mode.get() == "Personalizar":
                raw_vida = var_vida_val.get().strip()
                if raw_vida and Utils.safe_float(raw_vida) > 0:
                    val_vida_util = int(float(raw_vida))

            val_area_ui = var_pol_area.get()
            modo_area_save = "Personalizar"
            val_area_save = val_area_ui

            if val_area_ui == "Herdar":
                modo_area_save = "Herdar"
                val_area_save = None  # Reset inicial

                # 1. Tenta Família
                fam_name = cmb_familia.get()
                if fam_name:
                    fam_row = families_repo.get_by_nome(fam_name)
                    if fam_row:
                        val_area_save = fam_row.get("AreaPreferencial")

                # 2. Se ainda for None, tenta Global
                if not val_area_save:
                    val_area_save = getattr(global_policies, "area_preferencial_padrao", None)

            data_to_save = {
                "Sku": sku_val,
                "Ean": ean_val,
                "CodFornecedor": ent_cod_fornec.get().strip(),
                "Referencia": ent_ref.get().strip(),
                "Descricao": ent_desc.get().strip(),
                "Familia": cmb_familia.get(),
                "Unidade": unidade_definida,
                "Ativo": var_ativo.get(),
                "ValidadeModo": var_pol_validade.get(),
                "ValidadeMinimaDias": val_min_final,
                "VidaUtil": val_vida_util,
                "LoteModo": var_pol_lote.get(),
                "GiroModo": var_pol_giro.get(),
                "VariavelConsumo": var_pol_consumo.get(),
                "Camadas": layer_rows,
                "Bloqueado": self.var_manual_block.get(),
                "MotivoBloqueio": self.var_block_reason.get(),
                "ObsBloqueio": self.var_block_obs.get(),
                "AreaPreferencial": val_area_save,
                "AreaPreferencialModo": modo_area_save,
            }

            if var_blk_mode.get() == "Personalizar":
                data_to_save["BlockVencido"] = var_blk_vencido.get()
                data_to_save["BlockSemValidade"] = var_blk_semval.get()
                data_to_save["BlockSemLote"] = var_blk_semlote.get()
                data_to_save["BlockRepQualidade"] = var_blk_qualidade.get()
            else:
                for k in ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]:
                    data_to_save[k] = None

            try:
                if mode == "add":
                    products_repo.add(**data_to_save)
                    r = products_repo.get_by_sku(data_to_save["Sku"])
                    if r: r.update(data_to_save)
                else:
                    products_repo.update(old_sku=initial.get("Sku"), new_sku=data_to_save["Sku"], **data_to_save)
                    r = products_repo.get_by_sku(data_to_save["Sku"])
                    if r: r.update(data_to_save)

                top.alert("Sucesso", "Produto salvo.", type="info")

                self.table.load_page(self.table.page)
                top.close()

            except ValueError as e:
                top.alert("Erro", str(e), type="error")

        PillButton(footer, text="Salvar", command=_save_product, variant="success").grid(row=0, column=0,
                                                                                         padx=(0, GAP))
        PillButton(footer, text="Cancelar", variant="outline", command=top.close).grid(row=0, column=1, padx=0)

        # Carregamento Inicial
        if mode == "edit" and initial:
            var_ativo.set(initial.get("Ativo", True))
            ent_sku.insert(0, initial.get("Sku", ""))
            ent_cod_fornec.insert(0, initial.get("CodFornecedor", ""))
            ent_ref.insert(0, initial.get("Referencia", ""))
            ent_desc.insert(0, initial.get("Descricao", ""))
            if initial.get("Familia"): cmb_familia.set(initial.get("Familia"))
            if initial.get("ValidadeModo"): var_pol_validade.set(initial.get("ValidadeModo"))
            if initial.get("LoteModo"): var_pol_lote.set(initial.get("LoteModo"))
            if initial.get("GiroModo"): var_pol_giro.set(initial.get("GiroModo"))
            if initial.get("VariavelConsumo"): var_pol_consumo.set(initial.get("VariavelConsumo"))
            mode_area = initial.get("AreaPreferencialModo", "Herdar")

            if mode_area == "Personalizar":
                var_pol_area.set(initial.get("AreaPreferencial") or "Herdar")
            else:
                var_pol_area.set("Herdar")

            has_blk = any(initial.get(k) is not None for k in
                          ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"])
            if has_blk:
                var_blk_mode.set("Personalizar")
                var_blk_vencido.set(bool(initial.get("BlockVencido")))
                var_blk_semval.set(bool(initial.get("BlockSemValidade")))
                var_blk_semlote.set(bool(initial.get("BlockSemLote")))
                var_blk_qualidade.set(bool(initial.get("BlockRepQualidade")))
            else:
                var_blk_mode.set("Herdar")

            v_life = initial.get("VidaUtil")
            if v_life is not None:
                var_vida_mode.set("Personalizar")
                var_vida_val.set(str(v_life))
            else:
                var_vida_mode.set("Herdar")

            # Carrega Vencimento Mínimo
            v_min = initial.get("ValidadeMinimaDias")
            if v_min is not None:
                var_min_mode.set("Personalizar")
                var_min_val.set(str(v_min))
                var_min_und.set("Dias")  # Default
            else:
                var_min_mode.set("Herdar")

            # BLOQUEIO MANUAL (Carregamento)
            self.var_manual_block.set(bool(initial.get("Bloqueado", False)))
            self.var_block_reason.set(initial.get("MotivoBloqueio", ""))
            self.var_block_obs.set(initial.get("ObsBloqueio", ""))

        # Força calculo inicial
        _recalc_all_inheritance()
        _update_block_btn_visuals()

        _switch_tab("cadastro")
        self._tab_buttons["cadastro"].configure(variant="tab_selected")
        self._tab_frames["parametros"].grid_remove()
        ent_sku.focus_set()

    def _delete_selected(self):

        sku = self._selected_sku()
        if not sku:
            return

        if products_repo.tem_movimentacao(sku):
            self.alert(
                "Ação bloqueada",
                f"Não é possível excluir o '{sku}' pois ele possui movimentações.\n\n"
                "Por favor, altere o status para Inativo.", type="warning"
            )
            return

        def _confirmar():
            try:
                products_repo.delete(sku)
                self.table.load_page(self.table.page)
                self.alert("Sucesso", "Produto excluído.", type="info")
            except ValueError as e:
                self.alert("Atenção", str(e), type="warning")

        # Chama a pergunta
        self.ask_yes_no(
            title="Confirmar exclusão",
            message=f"Excluir o produto “{sku}”?\nEsta ação não pode ser desfeita.",
            on_yes=_confirmar
        )

    def _selected_sku(self):

        row = self.table.get_selected()
        if not row:
            self.alert("Atenção", "Selecione um registro.", type="info")
            return None
        return row.get("Sku")