import tkinter as tk
from tkinter import ttk
from datetime import datetime

from database.repositories import areas_repo
# --- 5. Repositórios (recebimento_repo) ---
from database.repositories import (
    families_repo, units_repo, unit_alias_repo, locations_repo,
    product_alias_repo, lpn_repo, printers_repo, global_policies,
    printer_config, products_repo,
    recebimento_repo
)
from ui.components import (
    Page, PillButton, StandardTable, SaaSModal,
    TextField, PillCombobox, ToggleSwitch,
    BlueCheckButton, BlueRadioButton,
    CardSectionTitle, CardSectionSeparator,
    ScrollableFrame,
    RoundedCard,
    ToolTip,
    SegmentedButton
)
from utils.constants import Colors, PAGE_SIZE_DEFAULT
from utils.helpers import load_icon, _tint_icon, AuditManager
from utils.printing import get_windows_printers, imprimir_etiqueta_lpn

try:
    from ui.pages.recebimento import ExcecoesEstoqueDialog, RecebimentoExcecoesDialog
except ImportError:
    # Fallback caso haja erro de ciclo (importa apenas na hora do uso)
    ExcecoesEstoqueDialog = None
    RecebimentoExcecoesDialog = None


class PolicyDialogBase(tk.Toplevel):
    def __init__(self, parent, title, resizable=True):
        tk.Toplevel.__init__(self, parent)

        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=Colors.BG_APP)
        self.resizable(True if resizable else False,
                       True if resizable else False)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # corpo padrão com padding
        body = ttk.Frame(self, style="Main.TFrame", padding=(16, 12, 16, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # header (barra superior da janela) e área de conteúdo
        self.header = ttk.Frame(body, style="Main.TFrame")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.header.columnconfigure(0, weight=1)

        self.content = ttk.Frame(body, style="Main.TFrame")
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(0, lambda: self._center_on_parent(parent))

    # hook para subclasses
    def on_close(self):
        # sobrescreva nas janelas de política que precisarem de callback
        pass

    def _close(self):
        try:
            self.on_close()
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _center_on_parent(self, parent):
        try:
            self.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            ww = self.winfo_width()
            wh = self.winfo_height()
            x = px + (pw - ww) // 2
            y = py + (ph - wh) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass


class FamiliasPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self._f5_bound = False

        # --- Definição das Colunas ---
        cols = [
                   {"id": "Nome", "title": "Família", "type": "text", "width": 220, "anchor": "w"},
                   {"id": "Descricao", "title": "Descrição", "type": "text", "width": 350, "anchor": "w"},

                   # Colunas de Política (Visão Rápida)
                   {"id": "validade_show", "title": "Validade", "type": "text", "width": 120, "anchor": "center"},
                   {"id": "lote_show", "title": "Lote", "type": "text", "width": 120, "anchor": "center"},
                   {"id": "giro_show", "title": "Giro", "type": "text", "width": 80, "anchor": "center"},
               ] + AuditManager.get_columns()

        def _fetch(page: int, page_size: int, filters: list):
            total, rows = families_repo.list(page, page_size, filters)
            processed_rows = []

            for r in rows:
                # 1. Normaliza chaves
                row_raw = dict(r)
                row_view = row_raw.copy()

                # 2. AUDITORIA AUTOMÁTICA (Substitui o mapeamento manual)
                row_view.update(AuditManager.process_row(r))

                # 3. Garante mapeamento para snake_case (Campos específicos da Família)
                row_view.update({
                    "validade_modo": row_raw.get("ValidadeModo"),
                    "lote_modo": row_raw.get("LoteModo"),
                    "giro_modo": row_raw.get("GiroModo"),
                    "variavel_consumo": row_raw.get("VariavelConsumo"),
                    "vida_util": row_raw.get("VidaUtil"),
                    "validade_minima_dias": row_raw.get("ValidadeMinimaDias"),
                    "block_vencido": row_raw.get("BlockVencido"),
                    "block_sem_validade": row_raw.get("BlockSemValidade"),
                    "block_sem_lote": row_raw.get("BlockSemLote"),
                    "block_rep_qualidade": row_raw.get("BlockRepQualidade"),
                })

                # --- LÓGICA DE NEGÓCIO (Calcula o que exibir nas colunas calculadas) ---
                def resolver_fam(campo_view, campo_global_attr, valor_default_global):
                    val = row_view.get(campo_view)
                    if val == "Herdar" or val is None:
                        val = getattr(global_policies, campo_global_attr, valor_default_global)
                    return str(val)

                # Validade
                v = resolver_fam("validade_modo", "modo_validade", "Validade opcional")
                if v == "Validade obrigatória":
                    row_view["validade_show"] = "Obrigatória"
                elif v == "Validade opcional":
                    row_view["validade_show"] = "Opcional"
                else:
                    row_view["validade_show"] = "-"

                # Lote
                l = resolver_fam("lote_modo", "modo_lote", "Lote opcional")
                if l == "Lote obrigatório":
                    row_view["lote_show"] = "Obrigatório"
                elif l == "Lote opcional":
                    row_view["lote_show"] = "Opcional"
                else:
                    row_view["lote_show"] = "-"

                # Giro
                g = resolver_fam("giro_modo", "modelo_giro", "FEFO")
                if g in ("None", "", "None"):
                    row_view["giro_show"] = "-"
                else:
                    row_view["giro_show"] = g.upper()

                # Limpeza final de Nones (para campos não auditados)
                for k, v in row_view.items():
                    if v is None: row_view[k] = "-"

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
        self._open_family_dialog(mode="add")

    def _open_edit_dialog(self):
        nome = self._selected_nome()
        if not nome:
            return
        row = families_repo.get_by_nome(nome)
        if not row:
            self.alert("Atenção", "Registro não encontrado.", type="warning")
            return
        self._open_family_dialog(mode="edit", initial=row)

    def _open_family_dialog(self, mode="add", initial=None):
        import tkinter as tk
        from tkinter import ttk

        titulo = "Nova Família" if mode == "add" else "Editar Família"
        top = SaaSModal(self, title=titulo, width=780, height=720)
        top.attributes("-alpha", 0.0)

        # --- ESTRUTURA PRINCIPAL ---
        main_container = ttk.Frame(top.content, style="Main.TFrame", padding=0)
        main_container.pack(fill="both", expand=True)

        # 1. RODAPÉ (Botões)
        footer = ttk.Frame(main_container, style="Main.TFrame")
        footer.pack(side="bottom", fill="x", pady=(16, 20), padx=20)

        # 2. TOPO (Identificação)
        frm_ident = ttk.Frame(main_container, style="Main.TFrame")
        frm_ident.pack(side="top", fill="x", pady=(20, 10), padx=20)

        ent_nome = TextField(frm_ident, placeholder="Nome da Família", height=34, width=220)
        ent_nome.pack(side="left", padx=(0, 12))

        ent_desc = TextField(frm_ident, placeholder="Descrição (Opcional)", height=34)
        ent_desc.pack(side="left", fill="x", expand=True)

        # --- VARIÁVEIS ---
        self.var_val = tk.StringVar(value="Herdar")
        self.var_lote = tk.StringVar(value="Herdar")
        self.var_giro = tk.StringVar(value="Herdar")
        self.var_cons = tk.StringVar(value="Herdar")

        # REMOVIDO: self.var_area = tk.StringVar(value="Herdar") (Não usamos mais var para controle de herança aqui)

        # Shelf Life & Minimo
        self.var_min_mode = tk.StringVar(value="Herdar")
        self.var_min_val = tk.StringVar()
        self.var_min_und = tk.StringVar(value="Dias")

        self.var_vida_val = tk.StringVar()
        self.var_vida_und = tk.StringVar(value="Meses")

        # Bloqueios
        self.var_blk_mode = tk.StringVar(value="Herdar")
        self.var_bv = tk.BooleanVar()
        self.var_bs = tk.BooleanVar()
        self.var_bl = tk.BooleanVar()
        self.var_bq = tk.BooleanVar()

        # --- HELPER: Verifica Validade Efetiva ---
        def _get_eff_validade():
            # Retorna "Sem", "Opcional" ou "Obrigatória" considerando a herança
            val = self.var_val.get()
            if val == "Herdar":
                return global_policies.modo_validade or "Validade opcional"
            return val

        # --- HELPER: Inheritance Field Modificado ---
        # Adicionei 'block_check' para permitir o bloqueio condicional
        def _create_inheritance_field(parent, label, variable, global_getter, options,
                                      custom_start_val=None, custom_display_text=None, block_check=None):
            container = tk.Frame(parent, bg="#ffffff")
            container.pack(fill="x", pady=(0, 15))

            tk.Label(container, text=label, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#374151").pack(anchor="w",
                                                                                                           pady=(0, 4))
            f_dyn = tk.Frame(container, bg="#ffffff")
            f_dyn.pack(fill="x")

            def _render(*args):
                if not f_dyn.winfo_exists(): return
                for w in f_dyn.winfo_children(): w.destroy()

                # >> LÓGICA DE BLOQUEIO NOVO <<
                if block_check:
                    should_block, msg_block = block_check()
                    if should_block:
                        tk.Label(f_dyn, text=msg_block, font=("Segoe UI", 9, "italic"),
                                 fg=Colors.TEXT_HINT, bg="#ffffff").pack(anchor="w")
                        top.update_idletasks()
                        return
                # >> FIM LÓGICA BLOQUEIO <<

                val = variable.get()

                if val == "Herdar":
                    g_val = global_getter()

                    if custom_display_text:
                        disp = custom_display_text
                    else:
                        disp = next((k for k, v in options if v == g_val), str(g_val))

                    box = tk.Frame(f_dyn, bg="#F3F4F6", padx=10, pady=8)
                    box.pack(fill="x")

                    tk.Label(box, text="↳", font=("Segoe UI", 12), bg="#F3F4F6", fg="#9CA3AF").pack(side="left",
                                                                                                    padx=(0, 8))
                    tk.Label(box, text="Padrão Global: ", font=("Segoe UI", 9), bg="#F3F4F6", fg="#6B7280").pack(
                        side="left")
                    tk.Label(box, text=disp, font=("Segoe UI", 9, "bold"), bg="#F3F4F6", fg="#374151").pack(side="left")

                    btn = tk.Label(box, text="Personalizar", font=("Segoe UI", 9, "bold"), bg="#F3F4F6",
                                   fg=Colors.PRIMARY, cursor="hand2")
                    btn.pack(side="right")

                    target_val = custom_start_val if custom_start_val else g_val
                    btn.bind("<Button-1>", lambda e: variable.set(target_val))
                else:
                    head = tk.Frame(f_dyn, bg="#ffffff")
                    head.pack(fill="x", pady=(0, 4))
                    tk.Label(head, text="Personalizado", font=("Segoe UI", 8, "bold"), bg="#ffffff",
                             fg=Colors.PRIMARY).pack(side="left")
                    rst = tk.Label(head, text="× Voltar ao Padrão", font=("Segoe UI", 8), bg="#ffffff", fg="#EF4444",
                                   cursor="hand2")
                    rst.pack(side="right")
                    rst.bind("<Button-1>", lambda e: variable.set("Herdar"))

                    if len(options) > 1:
                        seg = SegmentedButton(f_dyn, variable=variable, options=options)
                        seg.pack(fill="x")

                top.update_idletasks()

            variable.trace_add("write", _render)
            # Retornamos o render para poder chamá-lo externamente se necessário
            return _render

        # --- SCROLL AREA ---
        scroll_area = ScrollableFrame(main_container, padding=(20, 0, 0, 20))
        scroll_area.pack(fill="both", expand=True)

        card = RoundedCard(scroll_area.content, padding=(24, 24, 24, 24), radius=8)
        card.pack(fill="x", expand=True, padx=(0, 20), pady=2)
        body = card.content
        body.columnconfigure(0, weight=1, uniform="cols")
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1, uniform="cols")

        # === ESQUERDA ===
        left = tk.Frame(body, bg="#ffffff")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        # --- SEÇÃO UNIFICADA: VALIDADE ---
        # Armazenamos o render para chamar quando a validade mudar
        _render_validade_field = _create_inheritance_field(
            left, "Validade", self.var_val,
            lambda: global_policies.modo_validade or "Validade opcional",
            [("Sem val", "Sem validade"), ("Opcional", "Validade opcional"), ("Obrigatória", "Validade obrigatória")]
        )
        # Inicializa
        _render_validade_field()

        # Shelf Life (Prazo de Validade)
        # Esse campo não usa herança (é definição direta), mas precisa sumir se for "Sem validade"
        tk.Label(left, text="Prazo de Validade (Padrão):", font=("Segoe UI", 9, "bold"), bg="#ffffff",
                 fg="#374151").pack(anchor="w", pady=(8, 4))
        f_shelf_container = tk.Frame(left, bg="#ffffff")
        f_shelf_container.pack(anchor="w", fill="x", pady=(0, 15))

        def _render_shelf_life(*args):
            for w in f_shelf_container.winfo_children(): w.destroy()

            # Checagem de Bloqueio
            eff_v = _get_eff_validade()
            if eff_v == "Sem" or eff_v == "Sem validade":
                tk.Label(f_shelf_container, text="Não aplicável",
                         font=("Segoe UI", 9, "italic"), fg=Colors.TEXT_HINT, bg="#ffffff").pack(anchor="w")
                top.update_idletasks()
                return

            ent_vida = TextField(f_shelf_container, width=60, height=30)
            ent_vida._entry.config(textvariable=self.var_vida_val, justify="center")
            ent_vida.pack(side="left")

            tk.Label(f_shelf_container, text="dias", font=("Segoe UI", 9), bg="#ffffff").pack(side="left", padx=8)
            top.update_idletasks()

        # Vencimento Mínimo
        g_min = global_policies.validade_minima_dias
        txt_global_min = f"{g_min} dias" if g_min else "Inativo"

        # Função de check para o Vencimento Mínimo
        def _check_validade_block():
            eff = _get_eff_validade()
            if eff == "Sem" or eff == "Sem validade":
                return True, "Não aplicável"
            return False, ""

        _render_min_inheritance = _create_inheritance_field(
            left, "Vencimento Mínimo (Recebimento)", self.var_min_mode,
            lambda: "Personalizar" if global_policies.validade_minima_dias else "Herdar",
            [("Personalizar", "Personalizar")],
            custom_start_val="Personalizar",
            custom_display_text=txt_global_min,
            block_check=_check_validade_block  # Passamos a regra de bloqueio
        )

        f_min = tk.Frame(left, bg="#ffffff")
        f_min.pack(fill="x", pady=(0, 0))

        def _render_min_inputs(*args):
            if not f_min.winfo_exists(): return
            for w in f_min.winfo_children(): w.destroy()

            # Se estiver bloqueado (Sem validade), não renderiza inputs
            blocked, _ = _check_validade_block()
            if blocked:
                top.update_idletasks()
                return

            if self.var_min_mode.get() == "Personalizar":
                ent = TextField(f_min, width=80, height=30)
                ent._entry.config(textvariable=self.var_min_val, justify="center")
                ent.pack(side="left")

                tk.Label(f_min, text="dias", font=("Segoe UI", 9), bg="#ffffff").pack(side="left", padx=8)

            top.update_idletasks()

        self.var_min_mode.trace_add("write", _render_min_inputs)

        # --- GATILHOS CRUZADOS ---
        # Quando a validade mudar, redesenha Shelf Life e Vencimento Mínimo
        def _recalc_dependencies(*args):
            _render_shelf_life()
            _render_min_inheritance()  # Redesenha o toggle (herdado/personalizado)
            _render_min_inputs()  # Redesenha os inputs (se personalizado)

        self.var_val.trace_add("write", _recalc_dependencies)

        # Inicialização
        _recalc_dependencies()

        CardSectionSeparator(left).pack(fill="x", pady=(20, 15))

        # Variável de Consumo
        _render_cons = _create_inheritance_field(left, "Variável de Consumo", self.var_cons,
                                                 lambda: "Padrão",
                                                 [("Und", "Padrão"), ("Larg", "Largura"),
                                                  ("Comp", "Comprimento"), ("Peso", "Peso")]
                                                 )
        _render_cons()

        # --- NOVO: ÁREA DE ARMAZENAGEM (Segmented Button) ---
        tk.Frame(left, height=15, bg="#ffffff").pack(fill="x")  # Espaçamento

        tk.Label(left, text="Área de Armazenagem Preferencial", font=("Segoe UI", 9, "bold"), bg="#ffffff",
                 fg="#374151").pack(anchor="w", pady=(0, 4))

        # Busca áreas e cria a combobox direta
        lista_areas = [a['Nome'] for a in areas_repo.get_all() if a['Ativo']]

        # Combobox direta
        self.cmb_area = PillCombobox(left, values=lista_areas, placeholder="Selecione...", height=34)
        self.cmb_area.pack(fill="x")

        tk.Frame(left, height=30, bg="#ffffff").pack(fill="x")

        # === SEPARADOR VERTICAL ===
        tk.Frame(body, width=1, bg=Colors.BORDER).grid(row=0, column=1, sticky="ns", padx=24)

        # === DIREITA ===
        right = tk.Frame(body, bg="#ffffff")
        right.grid(row=0, column=2, sticky="nsew")

        # LOTE
        _render_lote = _create_inheritance_field(right, "Controle de Lote", self.var_lote,
                                                 lambda: getattr(global_policies, "modo_lote", "Lote opcional"),
                                                 [("Sem Lote", "Sem lote"), ("Opcional", "Lote opcional"),
                                                  ("Obrigatório", "Lote obrigatório")]
                                                 )
        _render_lote()

        # GIRO
        _render_giro = _create_inheritance_field(right, "Giro de Estoque", self.var_giro,
                                                 lambda: getattr(global_policies, "modelo_giro", "FEFO"),
                                                 [("FEFO", "FEFO"), ("FIFO", "FIFO"), ("LIFO", "LIFO")]
                                                 )
        _render_giro()

        CardSectionSeparator(right).pack(fill="x", pady=(10, 20))

        # BLOQUEIOS
        _render_blk = _create_inheritance_field(right, "Bloqueios Automáticos", self.var_blk_mode,
                                                lambda: "Padrão",
                                                [("Manual", "Personalizar")],
                                                custom_start_val="Personalizar",
                                                custom_display_text="Padrão do Sistema"
                                                )
        _render_blk()

        f_blk_opts = tk.Frame(right, bg="#ffffff")
        f_blk_opts.pack(fill="x", pady=(0, 20))

        def _render_blk_opts(*args):
            if not f_blk_opts.winfo_exists(): return
            for w in f_blk_opts.winfo_children(): w.destroy()

            if self.var_blk_mode.get() == "Personalizar":
                items = [
                    ("Produto vencido", self.var_bv),
                    ("Sem validade (se obrigatório)", self.var_bs),
                    ("Sem lote (se obrigatório)", self.var_bl),
                    ("Reprovado qualidade", self.var_bq)
                ]
                for lbl, var in items:
                    BlueCheckButton(f_blk_opts, text=lbl, variable=var, bg="#ffffff").pack(anchor="w", pady=3)

            top.update_idletasks()

        self.var_blk_mode.trace_add("write", _render_blk_opts)
        _render_blk_opts()

        tk.Frame(body, height=40, bg="#ffffff").grid(row=99, column=0, columnspan=3)

        # --- CARREGAR DADOS ---
        if mode == "edit" and initial:
            raw = dict(initial)
            val_area_db = raw.get("AreaPreferencial")
            if val_area_db:
                self.cmb_area.set(val_area_db)

            # --- Preenchimento direto (Sem dicionário intermediário) ---
            ent_nome.insert(0, raw.get("Nome") or "")
            ent_desc.insert(0, raw.get("Descricao") or "")

            if raw.get("ValidadeModo"): self.var_val.set(raw.get("ValidadeModo"))
            if raw.get("LoteModo"): self.var_lote.set(raw.get("LoteModo"))
            if raw.get("GiroModo"): self.var_giro.set(raw.get("GiroModo"))
            if raw.get("VariavelConsumo"): self.var_cons.set(raw.get("VariavelConsumo"))

            # Vida Útil
            vu = raw.get("VidaUtil")
            if vu is not None:
                self.var_vida_val.set(str(vu))

            # Validade Mínima
            val_raw = raw.get("ValidadeMinimaDias")
            if val_raw is not None:
                val_min = int(val_raw)
                self.var_min_mode.set("Personalizar")
                self.var_min_val.set(str(val_min))
                self.var_min_und.set("Dias")

            # Bloqueios (Usando as chaves TitleCase do banco)
            bk_keys = ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]
            if any(raw.get(k) is not None for k in bk_keys):
                self.var_blk_mode.set("Personalizar")
                self.var_bv.set(bool(raw.get("BlockVencido")))
                self.var_bs.set(bool(raw.get("BlockSemValidade")))
                self.var_bl.set(bool(raw.get("BlockSemLote")))
                self.var_bq.set(bool(raw.get("BlockRepQualidade")))

        # --- SALVAR ---
        def _save():
            nome = ent_nome.get().strip()
            if not nome: return

            # SALVAMENTO DA COMBOBOX SIMPLES
            val_area_save = self.cmb_area.get()
            if not val_area_save: val_area_save = None

            data = {
                "Descricao": ent_desc.get(),
                "ValidadeModo": self.var_val.get(),
                "LoteModo": self.var_lote.get(),
                "GiroModo": self.var_giro.get(),
                "VariavelConsumo": self.var_cons.get(),
                "AreaPreferencial": val_area_save
            }

            # Vida Útil
            life = self.var_vida_val.get().strip()
            data["VidaUtil"] = int(life) if life.isdigit() else None

            # Validade Mínima
            # Lógica simplificada: Se preenchido e "Personalizar", salva. Senão None.
            eff_v = _get_eff_validade()
            if eff_v in ["Sem", "Sem validade"] or self.var_min_mode.get() != "Personalizar":
                data["ValidadeMinimaDias"] = None
            else:
                m = self.var_min_val.get().strip()
                data["ValidadeMinimaDias"] = int(m) if m.isdigit() else 0

            # Bloqueios
            if self.var_blk_mode.get() == "Personalizar":
                data["BlockVencido"] = self.var_bv.get()
                data["BlockSemValidade"] = self.var_bs.get()
                data["BlockSemLote"] = self.var_bl.get()
                data["BlockRepQualidade"] = self.var_bq.get()
            else:
                # CORRIGIDO: Chaves em TitleCase na lista também
                for k in ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]:
                    data[k] = None

            try:
                if mode == "add":
                    families_repo.add(nome=nome, **data)
                else:
                    old_name = initial.get("Nome")

                    if not old_name:
                        pass

                    families_repo.update(old_nome=old_name, new_nome=nome, **data)

                # Atualiza tela e fecha
                self.table.load_page(1)
                top.close()
                self.alert("Sucesso", "Dados salvos com sucesso!", type="info")

            except Exception as e:
                # Mostra o erro real agora
                top.alert("Erro", str(e))

        PillButton(footer, text="Salvar", command=_save, variant="success").pack(side="right")
        PillButton(footer, text="Cancelar", command=top.close, variant="outline").pack(side="right", padx=10)

        if mode == "add": ent_nome.focus_set()

        top.update_idletasks()
        def _revelar_janela_pronta():
            try:
                # Verifica se a janela ainda existe (caso o usuário tenha fechado muito rápido)
                if top.winfo_exists():
                    top.attributes("-alpha", 1.0)
            except tk.TclError:
                pass

        top.after(270, _revelar_janela_pronta)

    def _delete_selected(self):
        
        nome = self._selected_nome()
        if not nome:
            return

        def _confirmar():
            try:
                families_repo.delete(nome)
                self.table.load_page(self.table.page)
            except ValueError as e:
                self.alert("Atenção", str(e), type="warning")

        self.ask_yes_no(
            title="Confirmar exclusão",
            message=f"Excluir a família “{nome}”?\nEsta ação não pode ser desfeita.",
            on_yes=_confirmar
        )

    def _selected_nome(self):
        
        row = self.table.get_selected()
        if not row:
            self.alert("Atenção", "Selecione um registro.", type="info")
            return None
        return row.get("Nome")


class UnidadesMedidaPage(Page):
    # destrói ao sair; ao voltar recarrega do repositório
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        # flag simples só para controle interno (não é obrigatório)
        self._f5_bound = False

        cols = [
                   # --- DADOS DE NEGÓCIO (Visíveis) ---
                   {"id": "Sigla", "title": "Sigla", "type": "text", "width": 120, "anchor": "w"},
                   {"id": "Descricao", "title": "Descrição", "type": "text", "width": 360, "anchor": "w"},
                   {"id": "Decimais", "title": "Decimais", "type": "text", "width": 100, "anchor": "center"},

               ] + AuditManager.get_columns()

        def _fetch(page: int, page_size: int, filters: list):
            total, rows = units_repo.list(page, page_size, filters)
            processed_rows = []

            for r in rows:
                row_raw = dict(r)
                row_view = row_raw.copy()

                # AUDITORIA
                row_view.update(AuditManager.process_row(r))

                # TRATAMENTO VISUAL: Decimais
                if row_view.get("Decimais"):
                    row_view["Decimais"] = "Sim"
                else:
                    row_view["Decimais"] = "Não"

                # Limpeza
                for k, v in row_view.items():
                    if v is None: row_view[k] = "-"

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

        # Mantendo o botão de Alias
        self.btn_alias = PillButton(left_box, text="Sinônimos XML", variant="outline", icon=load_icon("link", 16),
                                    command=self._open_alias_dialog)
        self.btn_alias.pack(side="left", padx=(0, 10))

        self.table.bind("<<TableSelect>>", self._on_selection_change)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._open_edit_dialog())
        self.table.bind("<Return>", lambda e: self._open_edit_dialog())
        self.table.bind("<Delete>", lambda e: self._delete_selected())

    # ----- habilitar/desabilitar botões conforme seleção -----
    def _on_selection_change(self, _e=None):
        has_sel = (self.table.get_selected() is not None)
        if has_sel:
            self.btn_edit.state(["!disabled"])
            self.btn_del.state(["!disabled"])
        else:
            self.btn_edit.state(["disabled"])
            self.btn_del.state(["disabled"])

    # ----- ciclo de vida da página -----
    def on_show(self, **kwargs):
        # Apenas carrega os dados
        self.table.load_page(1)

    def on_hide(self):
        pass

    # ----- diálogos de inclusão/edição -----
    def _open_add_dialog(self):
        self._open_unit_dialog(mode="add")

    def _open_edit_dialog(self):
        sigla = self._selected_sigla()
        if not sigla:
            return
        row = units_repo.get_by_sigla(sigla)
        if not row:
            self.alert("Atenção", "Registro não encontrado.", type="warning")
            return
        self._open_unit_dialog(mode="edit", initial=row)

    def _open_unit_dialog(self, mode="add", initial=None):
        # Pode remover os imports locais se já estiverem no topo
        titulo = "Nova Unidade de Medida" if mode == "add" else "Editar Unidade de Medida"

        # USE O SEU COMPONENTE
        top = SaaSModal(self, title=titulo, width=320, height=280)

        # O SaaSModal já configura bg, transient e grab_set, não precisa repetir.

        # Ajuste o container para usar top.content
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=(16, 12, 16, 16))
        frm.pack(fill="both", expand=True)

        ent_sigla = TextField(frm, placeholder="Sigla", height=32, width=260)
        ent_sigla.grid(row=0, column=0, columnspan=2, pady=(0, 6), padx=0)

        ent_desc = TextField(frm, placeholder="Descrição", height=32, width=260)
        ent_desc.grid(row=1, column=0, columnspan=2, pady=6, padx=0)

        ttk.Label(frm, text="Decimais:").grid(row=2, column=0, sticky="w", pady=6)
        cmb_dec = PillCombobox(
            frm,
            values=["SIM", "NÃO"],
            width=100,  # Ajuste a largura conforme necessário
            height=32
        )
        cmb_dec.grid(row=2, column=1, sticky="w", pady=6, padx=0)

        old_sigla = None
        if mode == "edit" and initial:
            old_sigla = initial.get("Sigla", "")
            ent_sigla.insert(0, initial.get("Sigla", ""))
            ent_desc.insert(0, initial.get("Descricao", ""))
            cmb_dec.set(initial.get("Decimais", "NÃO") or "NÃO")

        btns = ttk.Frame(frm, style="Main.TFrame")
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))

        def save():
            sigla = ent_sigla.get().strip()
            desc = ent_desc.get().strip()
            dec = cmb_dec.get().strip()

            if not sigla:
                self.alert("Atenção", "Informe a sigla.", type="warning")
                ent_sigla.focus_set()
                return
            if not desc:
                top.alert("Atenção", "Informe a descrição.", type="warning")
                ent_desc.focus_set()
                return

            if not dec:
                top.alert("Atenção", "Seleção obrigatória", type="warning")
                cmb_dec._entry.focus_set()
                return
            # --------------------------------------------

            try:
                if mode == "add":
                    units_repo.add(sigla=sigla, descricao=desc, decimais_sim_nao=dec)
                else:
                    units_repo.update(old_sigla=old_sigla, new_sigla=sigla, descricao=desc, decimais_sim_nao=dec)
            except ValueError as e:
                self.alert("Atenção", str(e), type="warning")
                return
            self.table.load_page(self.table.page)
            top.close()
            self.after(100, lambda: self.alert("Sucesso", "Unidade salva com sucesso!", type="info"))

        btn_salvar = PillButton(btns, text="Salvar", command=save, variant="success")
        btn_cancel = PillButton(btns, text="Cancelar", command=top.destroy, variant="outline")
        btn_salvar.grid(row=0, column=0)
        btn_cancel.grid(row=0, column=1, padx=0)

        top.bind("<Return>", lambda _e: save())

        top.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width() - top.winfo_width()) // 2
        py = self.winfo_rooty() + (self.winfo_height() - top.winfo_height()) // 2
        top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

        if mode == "add":
            ent_sigla.focus_set()
        else:
            ent_desc.focus_set()

    def _open_alias_dialog(self):
        # Modal para gerenciar o De/Para
        top = SaaSModal(self, title="Mapeamento de Unidades (XML)", width=600, height=500)

        # Fundo cinza para combinar com o app
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # --- ÁREA DE CADASTRO ---
        box_add = ttk.Frame(frm, style="Main.TFrame")
        box_add.pack(fill="x", pady=(0, 15))

        # Labels na Linha 0
        ttk.Label(box_add, text="Se na nota vier:", style="TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(box_add, text="Converter para:", style="TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Inputs na Linha 1
        ent_from = TextField(box_add, placeholder="Ex: UND, CXS, PÇ...", width=160, height=34)
        ent_from.grid(row=1, column=0, sticky="w")

        # Pega nossas unidades cadastradas
        # CORREÇÃO: units_repo.get_all() em vez de _rows
        my_units = [u["Sigla"] for u in units_repo.get_all()]
        cmb_to = PillCombobox(box_add, values=my_units, width=140, height=34)
        cmb_to.grid(row=1, column=1, sticky="w", padx=(10, 0))

        def _add_map():
            u_ext = ent_from.get().strip()
            u_int = cmb_to.get().strip()

            if not u_ext or not u_int:
                top.alert("Atenção", "Preencha os dois campos.")
                return

            unit_alias_repo.add_alias(u_ext, u_int)
            ent_from.delete(0, "end")
            _refresh_list()

        # Botão na Linha 1 (Mesma dos inputs)
        # CORREÇÃO 1: Removido pady vertical excessivo. Adicionado apenas padx lateral.
        btn_save = PillButton(box_add, text="Adicionar", variant="primary", command=_add_map, icon=load_icon("add", 16))
        btn_save.grid(row=1, column=2, sticky="w", padx=(10, 0))

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=10)

        # --- LISTA DE MAPEAMENTOS ---
        # CORREÇÃO 2: Usar tk.Label direto para forçar a cor de fundo cinza (BG_APP)
        # O estilo anterior CardSectionTitle forçava fundo branco.
        lbl_title = tk.Label(
            frm,
            text="Mapeamentos Ativos:",
            font=("Segoe UI", 11, "bold"),
            bg=Colors.BG_APP,
            fg=Colors.TEXT_MAIN
        )
        lbl_title.pack(anchor="w", pady=(0, 10))

        list_frame = ScrollableFrame(frm, padding=(0, 0, 0, 0))
        list_frame.pack(fill="both", expand=True)

        inner = list_frame.content

        # Configura colunas do grid interno para garantir alinhamento
        inner.columnconfigure(0, weight=1)  # Coluna Origem
        inner.columnconfigure(1, weight=1)  # Coluna Destino
        inner.columnconfigure(2, weight=0)  # Coluna Botão X

        def _refresh_list():
            for w in inner.winfo_children(): w.destroy()

            # CORREÇÃO: unit_alias_repo.get_all() em vez de _rows
            rows = unit_alias_repo.get_all()
            if not rows:
                ttk.Label(inner, text="Nenhum mapeamento cadastrado.", foreground=Colors.TEXT_HINT).pack(pady=20)
                return

            # CORREÇÃO 3: Usar GRID para cabeçalho e linhas

            # Cabeçalho
            h_origem = ttk.Label(inner, text="XML (Origem)", font=("Segoe UI", 9, "bold"))
            h_origem.grid(row=0, column=0, sticky="w", padx=10, pady=(0, 8))

            h_destino = ttk.Label(inner, text="Interno (Destino)", font=("Segoe UI", 9, "bold"))
            h_destino.grid(row=0, column=1, sticky="w", padx=10, pady=(0, 8))

            # Linhas
            for i, r in enumerate(rows):
                row_idx = i + 1  # Começa na linha 1

                # Borda inferior suave (opcional, simulada com frame ou apenas espaçamento)
                # Vamos simplificar mantendo apenas os textos alinhados

                lbl_from = ttk.Label(inner, text=r["UXml"])
                lbl_from.grid(row=row_idx, column=0, sticky="w", padx=10, pady=4)

                lbl_to = ttk.Label(inner, text=r["UInterna"], foreground=Colors.PRIMARY)
                lbl_to.grid(row=row_idx, column=1, sticky="w", padx=10, pady=4)

                def _del(aid=r["Id"]):
                    unit_alias_repo.delete(aid)
                    _refresh_list()

                btn_del = PillButton(inner, text="X", width=30, height=24, variant="outline", command=_del)
                btn_del.grid(row=row_idx, column=2, sticky="e", padx=10, pady=4)

        _refresh_list()

    def _delete_selected(self):
        
        sigla = self._selected_sigla()
        if not sigla:
            return

        # --- VERIFICAÇÃO DE DEPENDÊNCIA (INTEGRIDADE REFERENCIAL) ---

        # 1. Verifica se algum PRODUTO usa essa unidade
        # (normalizamos para maiúsculo para garantir)
        # CORREÇÃO: products_repo.get_all()
        all_products = products_repo.get_all()

        prod_em_uso = any(
            str(p.get("Unidade", "")).upper() == sigla.upper()
            for p in all_products
        )

        if prod_em_uso:
            self.alert(
                "Ação Bloqueada",
                f"A unidade '{sigla}' não pode ser excluída pois está vinculada a um ou mais PRODUTOS.\n\n"
                "Altere os produtos que usam esta unidade antes de excluir.", type="warning"
            )
            return

        # 2. Verifica se alguma CAMADA de embalagem usa essa unidade
        # (Isso é mais profundo, varre as camadas dentro dos produtos)
        camada_em_uso = False
        for p in all_products:
            # Precisa decodificar o JSON das camadas
            import json
            try:
                camadas = json.loads(p.get("camadasjson") or "[]")
            except:
                camadas = []

            for layer in camadas:
                if str(layer.get("Unidade", "")).upper() == sigla.upper():
                    camada_em_uso = True
                    break
            if camada_em_uso: break

        if camada_em_uso:
            self.alert(
                "Ação Bloqueada",
                f"A unidade '{sigla}' está sendo usada em uma Conversão/Embalagem de produto.\n\n"
                "Remova a embalagem do produto antes de excluir a unidade.", type="warning"
            )
            return

        def _confirmar():
            try:
                units_repo.delete(sigla)
                self.table.load_page(self.table.page)
                self.alert("Sucesso", "Unidade excluída.", type="info")
            except ValueError as e:
                self.alert("Atenção", str(e), type="warning")

        self.ask_yes_no(
            title="Confirmar exclusão",
            message=f"Excluir a unidade “{sigla}”?\nEsta ação não pode ser desfeita.",
            on_yes=_confirmar
        )

    def _selected_sigla(self):
        
        # A StandardTable retorna o dicionário de dados da linha, ou None
        row = self.table.get_selected()

        if not row:
            self.alert("Atenção", "Selecione um registro.", type="info")
            return None

        # Acesso direto à chave 'sigla' do dicionário
        return row.get("Sigla")


class LocaisEstoquePage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        cols = [
                   {"id": "Nome", "title": "Nome do Local", "type": "text", "width": 250, "anchor": "w"},
                   {"id": "Tipo", "title": "Tipo", "type": "text", "width": 120, "anchor": "center"},
                   {"id": "Cnpj", "title": "CNPJ / Identificação", "type": "text", "width": 150, "anchor": "center"},
                   {"id": "ativo_show", "title": "Status", "type": "text", "width": 80, "anchor": "center"},
                   {"id": "Obs", "title": "Observações", "type": "text", "width": 200, "anchor": "w"},
               ] + AuditManager.get_columns()

        def _fetch(page: int, page_size: int, filters: list):
            total, rows = locations_repo.list(page, page_size, filters)
            processed_rows = []

            for r in rows:
                row_raw = dict(r)
                row_view = row_raw.copy()
                row_view.update(AuditManager.process_row(r))

                row_view["ativo_show"] = "Ativo" if row_view.get("Ativo") else "Inativo"

                for k, v in row_view.items():
                    if v is None: row_view[k] = "-"

                processed_rows.append(row_view)

            return total, processed_rows

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=15)
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

        # Label de Local Padrão (Movemos para a barra da tabela)
        self.lbl_padrao = tk.Label(
            left_box,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg=Colors.BG_APP,
            fg=Colors.TEXT_HINT
        )
        self.lbl_padrao.pack(side="left", padx=(20, 0))

        self.table.bind("<<TableSelect>>", self._on_sel)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._open_edit_dialog())

    def _update_label_padrao(self):
        nome_padrao = locations_repo.get_padrao()

        cor_texto = Colors.TEXT_HINT

        if nome_padrao:
            self.lbl_padrao.config(
                text=f"Local de recebimento padrão: {nome_padrao}",
                fg=cor_texto
            )
        else:
            self.lbl_padrao.config(
                text="Nenhum local de recebimento padrão definido.",
                fg=cor_texto
            )

    def _on_sel(self, e):
        has = (self.table.get_selected() is not None)
        self.btn_edit.state(["!disabled"] if has else ["disabled"])
        self.btn_del.state(["!disabled"] if has else ["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)
        self._update_label_padrao()

    def _open_add_dialog(self):
        self._show_modal("add")

    def _open_edit_dialog(self):
        sel = self.table.get_selected()
        if not sel: return
        self._show_modal("edit", sel)

    def _show_modal(self, mode, initial=None):
        title = "Novo Local de Estoque" if mode == "add" else "Editar Local"
        top = SaaSModal(self, title=title, width=400, height=480)  # Aumentei um pouco a altura

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        frm_status_container = ttk.Frame(frm, style="Main.TFrame")
        frm_status_container.pack(anchor="e", pady=(0, 15))

        var_ativo = tk.BooleanVar(value=True)
        var_texto_ativo = tk.StringVar()

        def upd_st(*a):
            var_texto_ativo.set("Ativo" if var_ativo.get() else "Inativo")

        upd_st()
        var_ativo.trace_add("write", upd_st)

        tk.Label(frm_status_container, textvariable=var_texto_ativo, font=("Segoe UI", 10, "bold"),
                 fg=Colors.TEXT_MAIN, bg=Colors.BG_APP).pack(side="left", padx=(0, 10))

        ToggleSwitch(frm_status_container, variable=var_ativo, on_color=Colors.SUCCESS).pack(side="left", pady=(1, 0))

        # --- 2. CAMPOS ---

        ent_nome = TextField(frm, placeholder="Nome (Ex: Matriz, CD-SP)", height=34)
        ent_nome.pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text="Tipo de Instalação:", style="TLabel").pack(anchor="w")
        tipos = ["Matriz", "Filial", "Depósito Externo", "Loja", "Qualidade/Quarentena", "Virtual"]
        cmb_tipo = PillCombobox(frm, values=tipos, placeholder="Selecione ou digite...", height=34)
        cmb_tipo.pack(fill="x", pady=(0, 10))

        ent_cnpj = TextField(frm, placeholder="CNPJ (Opcional)", height=34)
        ent_cnpj.pack(fill="x", pady=(0, 10))

        ent_obs = TextField(frm, placeholder="Observações (Endereço físico, responsável...)", height=34)
        ent_obs.pack(fill="x", pady=(0, 10))

        # --- NOVO: Checkbox Padrão ---
        var_padrao = tk.BooleanVar(value=False)
        chk_padrao = BlueCheckButton(
            frm,
            text="Definir como local padrão de recebimento",
            variable=var_padrao,
            bg=Colors.BG_APP
        )
        chk_padrao.pack(anchor="w", pady=(5, 0))
        # -----------------------------

        if mode == "edit" and initial:
            ent_nome.insert(0, initial.get("nome", ""))
            cmb_tipo.set(initial.get("Tipo", ""))
            ent_cnpj.insert(0, initial.get("Cnpj", ""))
            ent_obs.insert(0, initial.get("Obs", ""))
            var_ativo.set(initial.get("Ativo", True))
            var_padrao.set(initial.get("EhPadrao", False))
            upd_st()

        def _save():
            nome = ent_nome.get().strip()
            tipo = cmb_tipo.get().strip()

            if not nome:
                top.alert("Atenção", "O nome é obrigatório.", focus_widget=ent_nome)
                return
            if not tipo:
                top.alert("Atenção", "Informe o tipo do local.", focus_widget=cmb_tipo)
                return

            # Dicionário Padronizado (TitleCase)
            data = {
                "Nome": nome,
                "Tipo": tipo,
                "Cnpj": ent_cnpj.get(),
                "Obs": ent_obs.get(),
                "EhPadrao": var_padrao.get(),
                "Ativo": var_ativo.get()
            }

            try:
                if mode == "add":
                    locations_repo.add(**data)
                else:
                    locations_repo.update(id_local=initial["Id"], **data)

                self.table.load_page(self.table.page)
                self._update_label_padrao()
                top.close()
            except ValueError as e:
                top.alert("Erro", str(e), type="error")

        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(fill="x", pady=20)
        PillButton(box, text="Salvar", variant="success", command=_save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _delete_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        def _confirm():
            try:
                locations_repo.delete(sel["Id"])
                self.table.load_page(1)
                self._update_label_padrao()
            except Exception as e:
                
                self.alert("Erro", str(e), type="error")

        self.ask_yes_no("Excluir", f"Deseja excluir o local '{sel['Nome']}'?", on_yes=_confirm)


class AreasPage(Page):
    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.create_standard_toolbar(1, self._add, self._edit, self._del)

        cols = [{"id": "Nome", "title": "Área", "width": 100, "anchor": "center"},
                {"id": "Descricao", "title": "Descrição", "width": 300, "anchor": "w"},
                {"id": "Ativo", "title": "Status", "width": 80, "anchor": "center"}]

        self.table = StandardTable(self, columns=cols, fetch_fn=self._fetch, page_size=15)

        self.table.grid(row=2, column=0, sticky="new")

        self.table.bind("<<TableSelect>>", self._on_sel)

    def _fetch(self, p, s, f):
        rows = areas_repo.list(p, s, f)[1]  # Pega lista do retorno
        for r in rows:
            r["ativo"] = "Ativo" if r["Ativo"] else "Inativo"
        return len(rows), rows

    def _on_sel(self, e):
        has = bool(self.table.get_selected())
        self.btn_edit.state(["!disabled"] if has else ["disabled"])
        self.btn_del.state(["!disabled"] if has else ["disabled"])

    def _add(self):
        self._modal("add")

    def _edit(self):
        sel = self.table.get_selected()
        if sel: self._modal("edit", sel)

    def _del(self):
        sel = self.table.get_selected()
        if sel:
            # Função interna que será executada apenas se o usuário clicar em SIM
            def _confirmar():
                try:
                    areas_repo.delete(sel['Id'])
                    self.table.load_page(1)
                except Exception as e:
                    self.alert("Erro", str(e))

            # Chamada correta passando a função _confirmar como argumento on_yes
            self.ask_yes_no(
                title="Excluir",
                message=f"Excluir Área {sel['Nome']}?",
                on_yes=_confirmar
            )

    def _modal(self, mode, data=None):
        top = SaaSModal(self, "Nova Área" if mode == "add" else "Editar Área", width=400, height=350)
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # --- 1. STATUS (ToggleSwitch no Topo Direito) ---
        f_top = tk.Frame(frm, bg=Colors.BG_APP)
        f_top.pack(fill="x", pady=(0, 15))

        f_status = tk.Frame(f_top, bg=Colors.BG_APP)
        f_status.pack(side="right")

        var_ativo = tk.BooleanVar(value=True)

        # Toggle Switch
        ToggleSwitch(f_status, variable=var_ativo, on_color=Colors.SUCCESS, bg=Colors.BG_APP).pack(side="left")

        # Label Dinâmico (Ativo/Inativo)
        lbl_status = tk.Label(f_status, text="Ativo", font=("Segoe UI", 9, "bold"),
                              bg=Colors.BG_APP, fg=Colors.SUCCESS)
        lbl_status.pack(side="left", padx=(8, 0))

        def _update_st(*args):
            if var_ativo.get():
                lbl_status.config(text="Ativo", fg=Colors.SUCCESS)
            else:
                lbl_status.config(text="Inativo", fg=Colors.TEXT_HINT)

        var_ativo.trace_add("write", _update_st)

        # --- 2. CAMPOS ---
        ent_nome = TextField(frm, placeholder="Nome (Ex: A, B, REF)", height=34)
        ent_nome.pack(fill="x", pady=(0, 15))

        ent_desc = TextField(frm, placeholder="Descrição (Opcional)", height=34)
        ent_desc.pack(fill="x", pady=(0, 15))

        # --- 3. CARREGAR DADOS (Se for edição) ---
        if mode == "edit":
            ent_nome.insert(0, data['Nome'])
            ent_desc.insert(0, data.get('Descricao', ''))
            var_ativo.set(data['Ativo'] == "Ativo")

            # Atualiza o label visualmente
            _update_st()

            # (Opcional) Se quiser manter a trava das áreas padrão, descomente abaixo:
            # if data['nome'] in ["A", "SEG"]: ent_nome._entry.config(state="disabled")

        # --- 4. SALVAR ---
        def _save():
            # >> VALIDAÇÃO DE NOME VAZIO <<
            nome = ent_nome.get().strip()
            if not nome:
                top.alert("Atenção", "O nome da Área é obrigatório.", focus_widget=ent_nome)
                return

            try:
                if mode == "add":
                    areas_repo.add(nome, ent_desc.get())
                else:
                    areas_repo.update(data['Id'], nome, ent_desc.get(), var_ativo.get())

                self.table.load_page(1)
                top.close()
            except Exception as e:
                top.alert("Erro", str(e))

        # Botão Salvar no rodapé
        PillButton(frm, text="Salvar", variant="success", command=_save).pack(side="bottom", anchor="e")


class ProductAliasPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        cols = [
            {"id": "SkuInterno", "title": "SKU Interno", "type": "text", "width": 120, "anchor": "w"},
            {"id": "DescInterna", "title": "Descrição Interna", "type": "text", "width": 250, "anchor": "w"},
            {"id": "CodFornecedor", "title": "Cód. no Fornecedor", "type": "text", "width": 150, "anchor": "center"},
            {"id": "Cnpj", "title": "CNPJ Fornecedor", "type": "text", "width": 140, "anchor": "center"},
            {"id": "CriadoPor", "title": "Vinculado Por", "type": "text", "width": 110, "anchor": "center"},
            {"id": "Cadastro", "title": "Vinculado Em", "type": "text", "width": 120, "anchor": "center"},
        ]

        def _fetch(page: int, page_size: int, filters: list):
            # CORREÇÃO: Usamos get_all() que é garantido e já traz a descrição (JOIN)
            # em vez de usar o .list() genérico que pode estar falhando no mapeamento.
            all_rows = product_alias_repo.get_all()

            # --- Filtragem em Memória (Busca Rápida) ---
            filtered_rows = []
            term = ""
            for f in filters:
                if f.get("type") == "quick":
                    term = str(f.get("value", "")).lower().strip()
                    break

            if term:
                for r in all_rows:
                    # Concatena os campos principais para busca
                    txt = f"{r.get('SkuInterno')} {r.get('CodFornecedor')} {r.get('DescricaoInterna')} {r.get('Cnpj')}".lower()
                    if term in txt:
                        filtered_rows.append(r)
            else:
                filtered_rows = all_rows

            # --- Paginação Manual ---
            total = len(filtered_rows)
            start = (page - 1) * page_size
            end = start + page_size
            page_rows = filtered_rows[start:end]

            processed = []
            for r in page_rows:
                # 1. Normaliza chaves para minúsculo
                r_low = dict(r)

                # 2. Mapeia os valores (Agora usando os campos vindos do get_all)
                sku_val = r_low.get("SkuInterno")
                cod_val = r_low.get("CodFornecedor")
                cnpj_val = r_low.get("Cnpj")

                # A descrição agora vem direto do SQL (alias 'DescricaoInterna')
                desc_val = r_low.get("DescricaoInterna") or "- Produto não encontrado -"

                row_view = {
                    "Id": r_low.get("Id"),
                    "SkuInterno": sku_val,
                    "CodFornecedor": cod_val,
                    "Cnpj": cnpj_val,
                    "DescInterna": desc_val
                }

                # 3. Formata Data (Cadastro)
                raw_date = r_low.get("Cadastro")
                if raw_date:
                    try:
                        if hasattr(raw_date, "strftime"):
                            row_view["Cadastro"] = raw_date.strftime("%d/%m/%Y %H:%M")
                        else:
                            # Tenta converter string ISO
                            from datetime import datetime
                            dt_str = str(raw_date).split('.')[0]
                            dt = datetime.fromisoformat(dt_str)
                            row_view["Cadastro"] = dt.strftime("%d/%m/%Y %H:%M")
                    except:
                        row_view["Cadastro"] = str(raw_date)
                else:
                    row_view["Cadastro"] = "-"

                row_view.update(AuditManager.process_row(r))
                processed.append(row_view)

            return total, processed

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=15)
        self.table.grid(row=0, column=0, sticky="new")

        # --- BOTÕES NA BARRA DA TABELA ---
        left_box = self.table.left_actions

        self.btn_del = PillButton(left_box, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._delete_selected)
        self.btn_del.pack(side="left", padx=(0, 10))
        self.btn_del.state(["disabled"])

        self.table.bind("<<TableSelect>>", self._on_sel)

    def on_show(self, **kwargs):
        # Atualiza a tabela sempre que a aba for aberta
        self.table.load_page(1)

    def _on_sel(self, _e=None):
        has = (self.table.get_selected() is not None)
        self.btn_del.state(["!disabled"] if has else ["disabled"])

    def _delete_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        # Pegamos apenas dados visuais para a pergunta
        sku = sel.get("SkuInterno")
        cod = sel.get("CodFornecedor")
        id_alias = sel.get("Id")

        def _confirm():
            try:
                # MUDANÇA PRINCIPAL:
                # Chamamos o delete passando o recebimento_repo.
                # Ele agora nos devolve se deu certo e quantos itens foram impactados.
                sucesso, qtd_afetada = product_alias_repo.delete(id_alias, recebimento_repo=recebimento_repo)

                self.table.load_page(self.table.page)

                # Monta a mensagem baseada no retorno do repositório
                msg = "Vínculo excluído com sucesso."
                if qtd_afetada > 0:
                    msg += f"\n\nATENÇÃO: {qtd_afetada} item(ns) em recebimentos pendentes foram revertidos"

                
                self.alert("Sucesso", msg, type="info")

            except Exception as e:
                
                self.alert("Erro", str(e), type="error")

        self.ask_yes_no(
            "Desvincular",
            f"Deseja remover o vínculo entre:\n\nSKU Interno: {sku}\nCódigo Fornecedor: {cod}?\n\nO sistema deixará de reconhecer este código automaticamente.",
            on_yes=_confirm, width=500, height=300
        )


class LpnPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        self.showing_history = False

        # --- DEFINIÇÃO DE COLUNAS ---
        cols = [
                   {"id": "Lpn", "title": "LPN", "type": "text", "width": 100, "anchor": "center"},
                   {"id": "Origem", "title": "Origem", "type": "text", "width": 110, "anchor": "center"},
                   {"id": "Sku", "title": "SKU", "type": "text", "width": 60, "anchor": "w"},
                   {"id": "Descricao", "title": "Descrição", "type": "text", "width": 250, "anchor": "w"},
                   {"id": "Lote", "title": "Lote", "type": "text", "width": 100, "anchor": "center"},
                   {"id": "Validade", "title": "Validade", "type": "text", "width": 90, "anchor": "center"},
                   {"id": "Local", "title": "Local", "type": "text", "width": 100, "anchor": "center"},
                   {"id": "Saldo", "title": "Qtd", "type": "text", "width": 80, "anchor": "center"},
                   {"id": "Unidade", "title": "Und", "type": "text", "width": 50, "anchor": "center"},
                   {"id": "Dimensoes", "title": "Dimensões", "type": "text", "width": 120, "anchor": "center"},
                   {"id": "Status", "title": "Status", "type": "text", "width": 160, "anchor": "center"},
                   {"id": "Obs", "title": "Observação", "type": "text", "width": 250, "anchor": "w",
                    "hidden": True},
               ] + AuditManager.get_columns()

        def _fetch(page: int, page_size: int, filters: list):
            total, rows = lpn_repo.list(page, page_size, filters)
            processed = []

            locais_virtuais = ["CANCELADOS", "CONSUMIDOS", "EXPEDIDOS", "PERDA"]
            prod_map = {p["Sku"]: p for p in products_repo.get_all()}

            for r in rows:
                endereco_atual = str(r.get("Endereco", "-")).upper()
                is_virtual = (endereco_atual in locais_virtuais)

                if self.showing_history:
                    if not is_virtual: continue
                else:
                    if is_virtual: continue

                prod = prod_map.get(r.get("Sku"), {})
                und_prod = prod.get("Unidade") or "UN"
                qtd = r.get("QtdAtual", 0)

                if r.get("Status") == "Cancelado":
                    qtd_show = "0"
                else:
                    qtd_show = f"{float(qtd):g}"

                larg = r.get('largura_atual', 0)
                comp = r.get('comprimento_atual', 0)

                dim_str = "-"
                if larg > 0 and comp > 0:
                    dim_str = f"{float(larg):g}mm x {float(comp):g}m"
                elif larg > 0:
                    dim_str = f"L: {float(larg):g}mm"
                elif comp > 0:
                    dim_str = f"C: {float(comp):g}m"

                origem_val = r.get("Origem") or r.get("PrRef") or "-"

                # Pega a data bruta do banco e tenta formatar para DD/MM/AAAA
                val_raw = r.get("Validade")
                val_formatada = "-"
                if val_raw:
                    try:
                        # Se já for objeto datetime
                        if hasattr(val_raw, "strftime"):
                            val_formatada = val_raw.strftime("%d/%m/%Y")
                        else:
                            # Se for string vinda do banco (ex: "2026-10-21 00:00:00.000")
                            val_str = str(val_raw).split()[0]  # Pega só a data
                            val_formatada = datetime.fromisoformat(val_str).strftime("%d/%m/%Y")
                    except:
                        val_formatada = str(val_raw).split()[0]  # Fallback de segurança

                cp = {
                    "Lpn": r.get("Lpn"),
                    "Origem": origem_val,
                    "Sku": r.get("Sku"),
                    "Descricao": prod.get("Descricao", "-"),
                    "Lote": r.get("Lote", "-"),
                    "Validade": val_formatada,  # << ADICIONAR ESTA LINHA
                    "Local": r.get("Endereco", "-"),
                    "Saldo": qtd_show,
                    "Unidade": und_prod,
                    "QtdRaw": qtd,
                    "Dimensoes": dim_str,
                    "Status": r.get("Status"),
                    "Obs": r.get("Obs", "")
                }

                cp.update(AuditManager.process_row(r))

                if r.get("Status") == "Cancelado":
                    cp["_text_color"] = "#9CA3AF"

                processed.append(cp)

            return len(processed), processed

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="new")

        # --- BOTÕES NA BARRA DA TABELA ---

        # ESQUERDA
        left_box = self.table.left_actions

        # Adicionar (Gerar)
        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16), padx=9,
                                  command=self._open_generate_dialog)
        self.btn_add.pack(side="left", padx=(0, 10))
        ToolTip(self.btn_add, "Gerar LPNs")

        # Excluir (Cancelar)
        self.btn_del = PillButton(left_box, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._delete_selected)
        self.btn_del.pack(side="left", padx=(0, 10))
        self.btn_del.state(["disabled"])
        ToolTip(self.btn_del, "Cancelar LPN")

        # Reimprimir (Mantemos texto pois é uma ação específica)
        self.btn_reprint = PillButton(left_box, text="Reimprimir", variant="outline", icon=load_icon("print", 16),
                                      command=self._reprint_selected)
        self.btn_reprint.pack(side="left", padx=(0, 10))
        self.btn_reprint.state(["disabled"])

        # Dividir (Mantemos texto)
        self.btn_split = PillButton(left_box, text="Dividir", variant="outline", icon=load_icon("link", 16),
                                    command=self._open_split_dialog)
        self.btn_split.pack(side="left", padx=(0, 10))
        self.btn_split.state(["disabled"])

        # DIREITA
        right_box = self.table.right_actions

        # Histórico
        self.btn_history = PillButton(right_box, text="Arquivo Morto", variant="outline", icon=None,
                                      command=self._toggle_history_mode)
        self.btn_history.pack(side="right", padx=(10, 0))

        self.table.bind("<<TableSelect>>", self._on_selection)

    def _toggle_history_mode(self):
        # Inverte o estado
        self.showing_history = not self.showing_history

        # --- MUDANÇA: Exibe/Oculta a coluna 'obs' dinamicamente ---
        for c in self.table.columns:
            if c["id"] == "Obs":
                c["hidden"] = not self.showing_history
                break

        # Força a tabela a recalcular as colunas imediatamente
        w_util = self.table.winfo_width() - (self.table.inner_padx * 2)
        self.table._perform_resize(w_util)
        # -----------------------------------------------------------

        if self.showing_history:
            # Modo Arquivo Morto
            icon_white = _tint_icon(load_icon("anterior", 16), "#ffffff")
            self.btn_history.configure(text="Voltar ao Estoque Físico", variant="primary", icon=icon_white)

            # Oculta botões de ação (usando pack_forget pois agora estão dentro do left_actions)
            self.btn_add.pack_forget()
            self.btn_del.pack_forget()
            self.btn_reprint.pack_forget()
            self.btn_split.pack_forget()

        else:
            # Modo Estoque
            self.btn_history.configure(text="Arquivo Morto", variant="outline", icon=None)

            # Restaura botões (re-empacota na ordem correta)
            self.btn_add.pack(side="left", padx=(0, 10), before=self.btn_reprint if self.btn_reprint.winfo_manager() else None)
            self.btn_del.pack(side="left", padx=(0, 10), after=self.btn_add)
            self.btn_reprint.pack(side="left", padx=(0, 10), after=self.btn_del)
            self.btn_split.pack(side="left", padx=(0, 10), after=self.btn_reprint)

        # Recarrega os dados
        self.table.load_page(1)

    def _on_selection(self, _e=None):
        has_sel = (self.table.get_selected() is not None)

        if not self.showing_history:
            self.btn_del.state(["!disabled"] if has_sel else ["disabled"])
            self.btn_reprint.state(["!disabled"] if has_sel else ["disabled"])
            self.btn_split.state(["!disabled"] if has_sel else ["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)

    def _open_generate_dialog(self):
        

        top = SaaSModal(self, title="Gerar LPNs", width=400, height=420)

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # --- SELEÇÃO DE IMPRESSORA ---
        ttk.Label(frm, text="Enviar para Impressora:", style="TLabel").pack(anchor="w", pady=(0, 6))

        all_printers = printers_repo.get_all()
        printer_map = {f"{p['Nome']} ({p['Caminho']})": p for p in all_printers}
        printer_labels = list(printer_map.keys())

        cmb_printer = PillCombobox(frm, values=printer_labels, placeholder="Selecione...", height=34)
        cmb_printer.pack(fill="x", pady=(0, 5))

        # --- OPÇÕES ---
        # Checkbox para salvar padrão
        var_save_default = tk.BooleanVar(value=False)
        chk_default = BlueCheckButton(frm, text="Salvar como padrão", variable=var_save_default, bg=Colors.BG_APP)
        chk_default.pack(anchor="w", pady=(0, 5))

        # --- NOVO: Checkbox para Imprimir ou Não ---
        var_imprimir = tk.BooleanVar(value=True)  # Padrão marcado

        def _toggle_printer_state(*args):
            state = "normal" if var_imprimir.get() else "disabled"
            cmb_printer.configure(state=state)
            chk_default.state((state,) if state == "disabled" else ("!disabled",))

        chk_imprimir = BlueCheckButton(frm, text="Imprimir etiquetas fisicamente", variable=var_imprimir,
                                       command=_toggle_printer_state, bg=Colors.BG_APP)
        chk_imprimir.pack(anchor="w", pady=(0, 15))

        # Lógica de carregamento de padrão
        saved_default_name = printer_config.get_default("Lpn")
        if saved_default_name:
            match = next((label for label, p in printer_map.items() if p["Nome"] == saved_default_name), None)
            if match:
                cmb_printer.set(match)
                var_save_default.set(True)
        elif printer_labels:
            cmb_printer.set(printer_labels[0])

        # --- QUANTIDADE ---
        ttk.Label(frm, text="Quantidade de etiquetas:", style="TLabel").pack(anchor="w", pady=(0, 6))
        ent_qtd = TextField(frm, placeholder="Ex: 1", height=34)  # Mudei o placeholder pra 1 pra facilitar teste
        ent_qtd.pack(fill="x", pady=(0, 20))
        ent_qtd.focus_set()

        def _confirmar():
            should_print = var_imprimir.get()
            dados_impressora = None

            # Validação apenas se for imprimir
            if should_print:
                label_selecionada = cmb_printer.get()
                if not label_selecionada or label_selecionada not in printer_map:
                    top.alert("Atenção", "Selecione uma impressora válida ou desmarque a impressão.")
                    return
                dados_impressora = printer_map[label_selecionada]

            valor = ent_qtd.get().strip()
            if not valor.isdigit() or int(valor) <= 0:
                top.alert("Erro", "Informe uma quantidade válida.", focus_widget=ent_qtd)
                return

            qtd = int(valor)
            if qtd > 500:
                top.alert("Atenção", "O limite máximo é de 500 etiquetas.")
                return

            # Salva preferência se marcado e se for imprimir
            if should_print and var_save_default.get():
                printer_config.set_default("Lpn", dados_impressora["Nome"])

            sucesso_count = 0
            erros = []
            gerados = []  # Lista para mostrar na tela se não imprimir

            try:
                for i in range(qtd):
                    # 1. Gera
                    novo_id = lpn_repo.create_blank_lpn()
                    gerados.append(novo_id)

                    # 2. Imprime (Se o usuário quiser)
                    if should_print:
                        try:
                            imprimir_etiqueta_lpn(dados_impressora, novo_id)
                            sucesso_count += 1
                        except Exception as e_print:
                            erros.append(f"Falha ao imprimir {novo_id}")
                            print(f"Erro de impressão: {e_print}")

                self.table.load_page(1)
                top.close()

                # FEEDBACK
                if not should_print:
                    # Mostra os códigos na tela para copiar/colar
                    lista_txt = "\n".join(gerados)
                    self.alert("LPNs Gerados (Modo Teste)",
                                        f"Foram gerados {len(gerados)} LPNs virtuais:\n\n{lista_txt}\n\n(Copie um deles para testar a conferência)",
                                        type="info")
                elif len(erros) == 0:
                    self.alert("Sucesso",
                                        f"{qtd} LPNs geradas e enviadas para impressão!", type="info")
                else:
                    self.alert("Atenção",
                                           f"{sucesso_count} etiquetas enviadas.\n{len(erros)} falharam.", type="warning")

            except Exception as e:
                top.alert("Erro Crítico", f"Erro ao gerar dados: {e}", type="error")

        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(fill="x", pady=10)

        PillButton(btn_box, text="Confirmar", variant="primary", command=_confirmar).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _reprint_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        lpn_codigo = sel.get("Lpn")

        # --- Modal de Escolha de Impressora ---
        top = SaaSModal(self, title=f"Reimprimir {lpn_codigo}", width=380, height=250)

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Selecione a Impressora:", style="TLabel").pack(anchor="w", pady=(0, 6))

        # Carrega impressoras
        all_printers = printers_repo.get_all()
        printer_map = {f"{p['Nome']} ({p['Caminho']})": p for p in all_printers}
        printer_labels = list(printer_map.keys())

        cmb_printer = PillCombobox(frm, values=printer_labels, placeholder="Selecione...", height=34)
        cmb_printer.pack(fill="x", pady=(0, 20))

        # Tenta carregar padrão
        saved_default = printer_config.get_default("Lpn")
        if saved_default:
            match = next((label for label, p in printer_map.items() if p["Nome"] == saved_default), None)
            if match: cmb_printer.set(match)
        elif printer_labels:
            cmb_printer.set(printer_labels[0])

        def _confirm_reprint():
            label_sel = cmb_printer.get()
            if not label_sel or label_sel not in printer_map:
                top.alert("Atenção", "Selecione uma impressora.")
                return

            p_data = printer_map[label_sel]

            try:
                # Chama a função de impressão que criamos anteriormente
                # Passa o ID que já existe na tabela (sel.get("lpn"))
                imprimir_etiqueta_lpn(p_data, lpn_codigo)

                top.close()
                self.alert("Sucesso", "Etiqueta enviada para reimpressão.", type="info")
            except Exception as e:
                top.alert("Erro", f"Falha na impressão: {e}", type="error")

        # Botões
        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(fill="x", pady=10)
        PillButton(btn_box, text="Imprimir", variant="primary", command=_confirm_reprint).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _delete_selected(self):
        sel = self.table.get_selected()
        if not sel: return

        lpn_codigo = sel.get("Lpn")
        status = sel.get("Status")

        # Se já estiver cancelado, não faz nada
        if status == "Cancelado":
            
            self.alert("Aviso", "Este LPN já está cancelado.", type="info")
            return

        # Função interna de confirmação
        def _confirm():
            try:
                # Chama o repo passando o motivo (pode vir de um input no futuro)
                lpn_repo.delete(lpn_codigo, motivo="Cancelamento via Interface")
                self.table.load_page(self.table.page)

                
                self.alert("Sucesso", f"LPN {lpn_codigo} cancelado e saldo zerado.", type="info")

            except ValueError as e:
                
                self.alert("Erro", str(e), type="error")

        self.ask_yes_no(
            title="Cancelar LPN",
            message=f"Deseja CANCELAR o LPN {lpn_codigo}?\n\nO saldo será zerado e o endereço liberado,\nmas o registro será mantido para histórico.",
            on_yes=_confirm
        )

    def _open_split_dialog(self):
        sel = self.table.get_selected()
        if not sel: return

        lpn_origem = sel['Lpn']
        sku_origem = sel['Sku']

        # Tenta pegar qtd bruta (float) ou da string
        qtd_total = sel.get('QtdRaw', 0)

        # Dados atuais para preencher os campos
        lote_atual = sel.get('Lote', '')
        # Se você tiver fabricação na tabela, pegue aqui. Senão vazio.
        fab_atual = sel.get('Fabricacao', '')
        val_atual = sel.get('Validade', '')

        

        top = SaaSModal(self, title=f"Dividir LPN: {lpn_origem}", width=450, height=520)
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # Header
        tk.Label(frm, text=f"Produto: {sku_origem}", font=("Segoe UI", 10, "bold"), bg=Colors.BG_APP).pack(anchor="w")
        tk.Label(frm, text=f"Saldo Disponível: {float(qtd_total):g}", font=("Segoe UI", 9), fg="#6B7280",
                 bg=Colors.BG_APP).pack(anchor="w", pady=(0, 15))

        # --- CAMPOS (Abertos para Edição) ---

        # 1. Quantidade
        ttk.Label(frm, text="Quantidade para o NOVO LPN:", style="TLabel").pack(anchor="w")
        ent_qtd = TextField(frm, placeholder="Ex: 10", height=34)
        ent_qtd.pack(fill="x", pady=(0, 10))
        ent_qtd.focus_set()

        # 2. Lote (Vem preenchido, user muda se quiser)
        ttk.Label(frm, text="Lote:", style="TLabel").pack(anchor="w")
        ent_lote = TextField(frm, placeholder="Lote", height=34)
        ent_lote.pack(fill="x", pady=(0, 10))
        ent_lote.insert(0, lote_atual)

        # 3. Fabricação
        ttk.Label(frm, text="Fabricação (AAAA-MM-DD):", style="TLabel").pack(anchor="w")
        ent_fab = TextField(frm, placeholder="Data Fabricação", height=34)
        ent_fab.pack(fill="x", pady=(0, 10))
        if fab_atual: ent_fab.insert(0, str(fab_atual))

        # 4. Validade
        ttk.Label(frm, text="Validade (AAAA-MM-DD):", style="TLabel").pack(anchor="w")
        ent_val = TextField(frm, placeholder="Data Validade", height=34)
        ent_val.pack(fill="x", pady=(0, 20))
        if val_atual: ent_val.insert(0, str(val_atual))

        def _confirmar():
            # A. Valida Quantidade
            raw_q = ent_qtd.get().strip()
            if not raw_q or not raw_q.replace('.', '', 1).isdigit():
                top.alert("Erro", "Quantidade inválida.")
                return

            q_sep = float(raw_q)
            if q_sep <= 0:
                top.alert("Erro", "Quantidade deve ser maior que zero.")
                return
            if q_sep >= qtd_total:
                top.alert("Atenção", "Para mover todo o saldo, use a função de Movimentação.")
                return

            # B. Coleta Dados (Se vazio, manda None para o backend tratar ou usar vazio)
            n_lote = ent_lote.get().strip()
            n_fab = ent_fab.get().strip()
            n_val = ent_val.get().strip()

            if not n_lote:
                top.alert("Atenção", "O Lote é obrigatório.")
                return

            # C. Chama Backend
            sucesso, msg = lpn_repo.desmembrar_lpn(
                lpn_origem, q_sep,
                novo_lote=n_lote,
                nova_fabricacao=n_fab,
                nova_validade=n_val,
                usuario="Admin"
            )

            if sucesso:
                self.table.load_page(self.table.page)
                top.close()

                # D. Impressão Automática
                novo_lpn = msg
                printer_name = printer_config.get_default("Lpn")

                # Busca objeto da impressora pelo nome salvo
                all_printers = printers_repo.get_all()
                printer_obj = next((p for p in all_printers if p['Nome'] == printer_name), None)

                if printer_obj:
                    try:
                        imprimir_etiqueta_lpn(printer_obj, novo_lpn)
                        self.alert("Sucesso",
                                            f"LPN {novo_lpn} gerado e enviado para impressão ({printer_name}).", type="info")
                    except Exception as e:
                        self.alert("Sucesso (Erro Impressão)",
                                               f"LPN {novo_lpn} gerado, mas falha ao imprimir: {e}", type="warning")
                else:
                    # 1. Criamos a função que define o que acontece no clique do "Sim"
                    def confirmar_configuracao():
                        self._open_print_modal_direct(novo_lpn)

                    # 2. Chamamos o ask_yes_no da classe Page (ou do modal)
                    self.ask_yes_no(
                        "Sucesso",
                        f"LPN {novo_lpn} gerado!\n\nNenhuma impressora padrão configurada.\nDeseja selecionar uma agora?",
                        on_yes=confirmar_configuracao
                    )

            else:
                top.alert("Erro", msg, type="error")

        # Botões
        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x")
        PillButton(box, text="Confirmar e Imprimir", variant="success", command=_confirmar).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _open_print_modal_direct(self, lpn_id):
        top = SaaSModal(self, title=f"Imprimir {lpn_id}", width=380, height=250)
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Selecione a Impressora:", style="TLabel").pack(anchor="w", pady=(0, 6))

        all_printers = printers_repo.get_all()
        printer_map = {f"{p['Nome']} ({p['Caminho']})": p for p in all_printers}
        cmb = PillCombobox(frm, values=list(printer_map.keys()), height=34)
        cmb.pack(fill="x")

        saved = printer_config.get_default("Lpn")
        if saved:
            match = next((l for l, p in printer_map.items() if p["Nome"] == saved), None)
            if match: cmb.set(match)
        elif printer_map:
            cmb.set(list(printer_map.keys())[0])

        def _do_print():
            if cmb.get() in printer_map:
                try:
                    imprimir_etiqueta_lpn(printer_map[cmb.get()], lpn_id)
                    top.close()
                except Exception as e:
                    top.alert("Erro", str(e))

        PillButton(frm, text="Imprimir", variant="primary", command=_do_print).pack(side="bottom", pady=20)


class PrintersPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        cols = [
            {"id": "Nome", "title": "Apelido", "type": "text", "width": 150, "anchor": "w"},
            {"id": "caminho_show", "title": "Destino", "type": "text", "width": 300, "anchor": "w"},
            {"id": "tipo_show", "title": "Tipo", "type": "text", "width": 100, "anchor": "center"},
        ]

        def _fetch(page, page_size, filters):
            rows = printers_repo.get_all()
            processed = []
            for r in rows:
                cp = dict(r)
                if r.get("Tipo") == "rede":
                    cp["caminho_show"] = f"{r.get('Caminho')}:{r.get('Porta')}"
                    cp["tipo_show"] = "Rede (IP)"
                else:
                    cp["caminho_show"] = r.get("caminho")
                    cp["tipo_show"] = "Windows"
                processed.append(cp)
            return len(processed), processed

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=15)
        self.table.grid(row=0, column=0, sticky="new")

        # --- BOTÕES NA BARRA DA TABELA ---
        left_box = self.table.left_actions

        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16), padx=9,
                                  command=self._open_modal)
        self.btn_add.pack(side="left", padx=(0, 10))

        self.btn_edit = PillButton(left_box, text="", variant="outline", icon=load_icon("edit", 16), padx=9,
                                   command=lambda: self._open_modal(edit=True))
        self.btn_edit.pack(side="left", padx=(0, 10))
        self.btn_edit.state(["disabled"])

        self.btn_del = PillButton(left_box, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._delete_selected)
        self.btn_del.pack(side="left", padx=(0, 10))
        self.btn_del.state(["disabled"])

        self.table.bind("<<TableSelect>>", self._on_sel)

    def _on_sel(self, e):
        has = (self.table.get_selected() is not None)
        self.btn_edit.state(["!disabled"] if has else ["disabled"])
        self.btn_del.state(["!disabled"] if has else ["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)

    def _open_modal(self, edit=False):
        sel = self.table.get_selected()
        if edit and not sel: return

        title = "Editar Impressora" if edit else "Nova Impressora"
        top = SaaSModal(self, title=title, width=450, height=450)  # Mais alto para caber opções

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x", pady=20)

        # 1. Apelido
        ent_nome = TextField(frm, placeholder="Apelido (Ex: Zebra 01)", height=34)
        ent_nome.pack(fill="x", pady=(0, 15))

        # 2. Tipo de Conexão (Radio Buttons)
        ttk.Label(frm, text="Tipo de Conexão:", style="TLabel").pack(anchor="w", pady=(0, 4))

        var_tipo = tk.StringVar(value="windows")
        frm_radios = ttk.Frame(frm, style="Main.TFrame")
        frm_radios.pack(anchor="w", fill="x", pady=(0, 15))

        BlueRadioButton(frm_radios, "Driver do Windows (USB/Rede)", var_tipo, "windows", bg=Colors.BG_APP).pack(
            side="left", padx=(0, 15))
        BlueRadioButton(frm_radios, "Direto via IP (Raw Socket)", var_tipo, "rede", bg=Colors.BG_APP).pack(side="left")

        # --- CONTAINER DINÂMICO ---
        # Vamos criar dois frames e alternar qual aparece
        frm_windows = ttk.Frame(frm, style="Main.TFrame")
        frm_rede = ttk.Frame(frm, style="Main.TFrame")

        # --> Conteúdo Windows
        ttk.Label(frm_windows, text="Selecione a Impressora:", style="TLabel").pack(anchor="w", pady=(0, 4))
        lista_printers = get_windows_printers()
        placeholder_txt = "Selecione..." if lista_printers else "Nenhuma detectada..."
        cmb_windows = PillCombobox(frm_windows, values=lista_printers, placeholder=placeholder_txt, height=34)
        cmb_windows.pack(fill="x")

        # --> Conteúdo Rede
        ttk.Label(frm_rede, text="Endereço IP:", style="TLabel").pack(anchor="w", pady=(0, 4))
        ent_ip = TextField(frm_rede, placeholder="Ex: 192.168.1.200", height=34)
        ent_ip.pack(fill="x", pady=(0, 10))

        ttk.Label(frm_rede, text="Porta (Padrão 9100):", style="TLabel").pack(anchor="w", pady=(0, 4))
        ent_porta = TextField(frm_rede, placeholder="9100", height=34)
        ent_porta.pack(fill="x")
        ent_porta.insert(0, "9100")

        # Lógica de troca
        def _toggle_ui(*args):
            t = var_tipo.get()
            if t == "windows":
                frm_rede.pack_forget()
                frm_windows.pack(fill="x", pady=(0, 15))
            else:
                frm_windows.pack_forget()
                frm_rede.pack(fill="x", pady=(0, 15))

        var_tipo.trace_add("write", _toggle_ui)

        # Preencher dados se edição
        if edit:
            ent_nome.insert(0, sel.get("Nome", ""))
            tipo_salvo = sel.get("Tipo", "windows")
            var_tipo.set(tipo_salvo)

            if tipo_salvo == "windows":
                cmb_windows.set(sel.get("Caminho", ""))
            else:
                ent_ip.insert(0, sel.get("Caminho", ""))
                ent_porta.delete(0, "end")
                ent_porta.insert(0, str(sel.get("Porta", 9100)))

        # Inicializa UI correta
        _toggle_ui()

        def _save():
            tipo = var_tipo.get()
            nome = ent_nome.get().strip()

            # Validação do Nome
            if not nome:
                top.alert("Atenção", "Informe um apelido para a impressora.", focus_widget=ent_nome)
                return

            # Inicializa variáveis para evitar erro de referência
            caminho_final = ""
            porta_final = 0

            if tipo == "windows":
                caminho_final = cmb_windows.get().strip()
                if not caminho_final:
                    top.alert("Atenção", "Selecione uma impressora do Windows.", focus_widget=cmb_windows)
                    return
                porta_final = 0
            else:
                # Lógica de Rede (IP + Porta)
                caminho_final = ent_ip.get().strip()
                porta_str = ent_porta.get().strip()

                if not caminho_final:
                    top.alert("Atenção", "Informe o endereço IP.", focus_widget=ent_ip)
                    return

                # --- VALIDAÇÃO DA PORTA (Correção do Erro) ---
                if not porta_str:
                    top.alert("Atenção", "Informe a porta (Ex: 9100).", focus_widget=ent_porta)
                    return
                if not porta_str.isdigit():
                    top.alert("Atenção", "A porta deve ser apenas números.", focus_widget=ent_porta)
                    return

                porta_final = int(porta_str)

            data = {
                "Nome": nome,
                "Caminho": caminho_final,
                "Tipo": tipo,
                "Porta": porta_final
            }

            try:
                if edit:
                    printers_repo.update(id_prt=sel["Id"], **data)
                else:
                    printers_repo.add(**data)

                self.table.load_page(1)
                top.close()
            except ValueError as e:
                top.alert("Erro", str(e), type="error")

        PillButton(box, text="Salvar", variant="success", command=_save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _delete_selected(self):
        sel = self.table.get_selected()
        if sel:
            printers_repo.delete(sel["Id"])
            self.table.load_page(1)


class PoliticasValidadeLotePage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        # Configuração básica: Scroll total na página
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.main_scroll = ScrollableFrame(self, padding=(0, 0, 0, 0), bg=Colors.BG_APP)
        self.main_scroll.grid(row=0, column=0, sticky="nsew")

        # Área centralizada (fixa em 960px para não "esparramar" na tela grande)
        content_area = self.main_scroll.content
        content_area.columnconfigure(0, weight=1)
        content_area.columnconfigure(1, weight=0)  # Centro Fixo
        content_area.columnconfigure(2, weight=1)

        self.center_frame = ttk.Frame(content_area, style="Main.TFrame", width=960)
        self.center_frame.grid(row=0, column=1, sticky="n", pady=30)
        self.center_frame.columnconfigure(0, weight=1)

        # 1. Inicializa variáveis (apenas declaração)
        self._init_vars_variables_only()

        # 2. Constrói o Layout Novo
        self._build_page_header()
        self._build_card_estoque()  # Card principal (2 colunas)
        self._build_card_recebimento()  # Card secundário
        self._build_card_separacao()  # Card placeholder
        self._build_footer_actions()  # Botão Salvar fixo

        # 3. Carrega os valores do banco
        self.on_show()
        self.update_idletasks()

    def _init_vars_variables_only(self):
        # Apenas declaração, sem carregar valores ainda
        self.var_modo = tk.StringVar()
        self.var_modo_lote = tk.StringVar()
        self.var_giro_modelo = tk.StringVar()

        # Bloqueios
        self.var_block_vencido = tk.BooleanVar()
        self.var_block_sem_validade = tk.BooleanVar()
        self.var_block_sem_lote = tk.BooleanVar()
        self.var_block_rep_qualidade = tk.BooleanVar()

        # Validade mínima e Unidade
        self.var_min_dias = tk.StringVar()
        self.var_min_und = tk.StringVar(value="Dias")

        self.var_tol_valor = tk.StringVar()
        self.var_tol_tipo = tk.StringVar(value="Valor")
        self.var_reset_all = tk.BooleanVar()
        self.var_reset_receb = tk.BooleanVar()

    def _build_page_header(self):
        h_frm = ttk.Frame(self.center_frame, style="Main.TFrame")
        h_frm.pack(fill="x", pady=(0, 25))
        tk.Label(h_frm, text="Políticas Globais", font=("Segoe UI", 22, "bold"), bg=Colors.BG_APP,
                 fg=Colors.TEXT_MAIN).pack(
            anchor="w")
        tk.Label(h_frm,
                 text="Defina as regras padrão do sistema. Produtos e famílias podem obedecer a estas configurações.",
                 font=("Segoe UI", 10), bg=Colors.BG_APP, fg="#6B7280").pack(anchor="w", pady=(4, 0))

    def _build_card_estoque(self):
        # Card com padding 0 para permitir elementos "Full Bleed" (como o Separator)
        card = RoundedCard(self.center_frame, radius=8, padding=0)
        card.pack(fill="x", pady=(0, 20))
        body = card.content

        # --- CONTEÚDO (Com Padding) ---
        # Criamos um frame interno para dar o recuo de 24px no conteúdo
        main_content = tk.Frame(body, bg="#ffffff")
        main_content.pack(fill="both", expand=True, padx=24, pady=(24, 0))

        tk.Label(main_content, text="Controle de Estoque", font=("Segoe UI", 12, "bold"), bg="#ffffff",
                 fg=Colors.PRIMARY).pack(anchor="w", pady=(0, 20))

        # Grid de 2 Colunas dentro do main_content
        grid = tk.Frame(main_content, bg="#ffffff")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # === COLUNA ESQUERDA ===
        c1 = tk.Frame(grid, bg="#ffffff")
        c1.grid(row=0, column=0, sticky="nsw", padx=(0, 30))

        # 1. Validade
        CardSectionTitle(c1, text="Validade").pack(anchor="w", pady=(0, 8))
        BlueRadioButton(c1, "Opcional", self.var_modo, "Validade opcional").pack(anchor="w", pady=2)
        BlueRadioButton(c1, "Obrigatória", self.var_modo, "Validade obrigatória").pack(anchor="w", pady=2)

        self.lbl_validade_excecoes = ttk.Label(c1, text="", style="CardBody.TLabel", foreground="#6B7280")
        self.lbl_validade_excecoes.pack(anchor="w", pady=(2, 15))

        # 2. Lote
        CardSectionTitle(c1, text="Controle de Lote").pack(anchor="w", pady=(0, 8))
        BlueRadioButton(c1, "Opcional", self.var_modo_lote, "Lote opcional").pack(anchor="w", pady=2)
        BlueRadioButton(c1, "Obrigatório", self.var_modo_lote, "Lote obrigatório").pack(anchor="w", pady=2)

        self.lbl_lote_excecoes = ttk.Label(c1, text="", style="CardBody.TLabel", foreground="#6B7280")
        self.lbl_lote_excecoes.pack(anchor="w", pady=(2, 15))

        # 3. Giro
        CardSectionTitle(c1, text="Modelo de Giro").pack(anchor="w", pady=(0, 8))
        f_giro = tk.Frame(c1, bg="#ffffff")
        f_giro.pack(anchor="w")
        BlueRadioButton(f_giro, "FEFO", self.var_giro_modelo, "FEFO").pack(side="left", padx=(0, 10))
        BlueRadioButton(f_giro, "FIFO", self.var_giro_modelo, "FIFO").pack(side="left", padx=(0, 10))
        BlueRadioButton(f_giro, "LIFO", self.var_giro_modelo, "LIFO").pack(side="left")

        self.lbl_giro_excecoes = ttk.Label(c1, text="", style="CardBody.TLabel", foreground="#6B7280")
        self.lbl_giro_excecoes.pack(anchor="w", pady=(4, 0))

        # === COLUNA DIREITA ===
        c2 = tk.Frame(grid, bg="#ffffff")
        c2.grid(row=0, column=1, sticky="nsew", padx=(30, 0))

        # 4. Bloqueios
        CardSectionTitle(c2, text="Bloqueios Automáticos").pack(anchor="w", pady=(0, 8))
        BlueCheckButton(c2, "Produtos vencidos", self.var_block_vencido).pack(anchor="w", pady=2)
        BlueCheckButton(c2, "Sem validade (se obrigatória)", self.var_block_sem_validade).pack(anchor="w", pady=2)
        BlueCheckButton(c2, "Sem lote (se obrigatório)", self.var_block_sem_lote).pack(anchor="w", pady=2)
        BlueCheckButton(c2, "Reprovados na qualidade", self.var_block_rep_qualidade).pack(anchor="w", pady=2)

        self.lbl_bloqueios_excecoes = ttk.Label(c2, text="", style="CardBody.TLabel", foreground="#6B7280")
        self.lbl_bloqueios_excecoes.pack(anchor="w", pady=(2, 0))

        # --- RODAPÉ DO CARD ---
        # Separador fora do main_content (direto no body) para ir de ponta a ponta
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(20, 0))

        # Botões com padding para alinhar visualmente com o conteúdo acima
        act_frm = tk.Frame(body, bg="#ffffff")
        act_frm.pack(fill="x", padx=24, pady=20)

        BlueCheckButton(act_frm, "Resetar exceções", self.var_reset_all).pack(side="left")

        # Botão alinhado à direita
        PillButton(act_frm, text="Ver Exceções", variant="outline", command=self._open_exceptions_dialog,
                   height=28).pack(side="right")

    def _build_card_recebimento(self):
        # Card Wrapper (Padding 0 para full bleed do separador)
        card = RoundedCard(self.center_frame, radius=8, padding=0)
        card.pack(fill="x", pady=(0, 20))
        body = card.content

        # --- CONTEÚDO (Com Padding) ---
        main_content = tk.Frame(body, bg="#ffffff")
        main_content.pack(fill="both", expand=True, padx=24, pady=(24, 0))

        # Título DENTRO do main_content (para alinhar com padding)
        tk.Label(main_content, text="Políticas de Recebimento", font=("Segoe UI", 12, "bold"), bg="#ffffff",
                 fg=Colors.PRIMARY).pack(anchor="w", pady=(0, 15))

        # Grid interno DENTRO do main_content
        grid = tk.Frame(main_content, bg="#ffffff")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)

        # === Coluna Única (Esquerda) ===
        c_main = tk.Frame(grid, bg="#ffffff")
        c_main.grid(row=0, column=0, sticky="nsw")

        # --- Vencimento Mínimo ---
        CardSectionTitle(c_main, text="Vencimento Mínimo").pack(anchor="w", pady=(0, 8))

        f_min = tk.Frame(c_main, bg="#ffffff")
        f_min.pack(anchor="w")

        ent = TextField(f_min, width=60, height=34)
        ent._entry.config(textvariable=self.var_min_dias, justify="center")
        ent.pack(side="left")

        tk.Label(f_min, text="dias", font=("Segoe UI", 10), bg="#ffffff", fg="#374151").pack(side="left", padx=8)

        # Espaçamento
        tk.Frame(c_main, height=20, bg="#ffffff").pack()

        # --- Tolerância Financeira ---
        CardSectionTitle(c_main, text="Tolerância Financeira").pack(anchor="w", pady=(0, 8))

        # 1. Seletor de Tipo (SegmentedButton)
        f_tol_opts = tk.Frame(c_main, bg="#ffffff")
        f_tol_opts.pack(anchor="w", pady=(0, 8))

        SegmentedButton(f_tol_opts, variable=self.var_tol_tipo,
                        options=[("Valor (R$)", "Valor"), ("Porcentagem (%)", "Porcentagem")],
                        width=240, height=30).pack(side="left")

        # 2. Campo de Valor com Símbolo Dinâmico
        f_tol = tk.Frame(c_main, bg="#ffffff")
        f_tol.pack(anchor="w")

        # Label dinâmico (R$ ou %)
        lbl_tol_symbol = tk.Label(f_tol, text="R$", bg="#ffffff", fg="#6B7280", font=("Segoe UI", 10, "bold"))
        lbl_tol_symbol.pack(side="left", padx=(0, 4))

        # --- MODIFICAÇÃO: TextField com placeholder padrão ---
        ent_tol = TextField(f_tol, width=80, height=34, placeholder="0.00")
        ent_tol._entry.config(textvariable=self.var_tol_valor, justify="center")
        ent_tol.pack(side="left")

        # --- LÓGICA DE ATUALIZAÇÃO UI (Placeholder e Símbolo) ---
        def _update_tol_ui(*args):
            # A. Atualiza o símbolo (R$ ou %)
            curr_type = self.var_tol_tipo.get()
            sym = "%" if curr_type == "Porcentagem" else "R$"
            lbl_tol_symbol.config(text=sym)

            # B. Lógica de Placeholder e Valor
            # Busca o estado "Salvo" no repositório para comparação
            saved_val = getattr(global_policies, "tolerancia_valor_recebimento", 0.00) or 0.00
            saved_type = getattr(global_policies, "tolerancia_tipo_recebimento", "Valor")

            has_definition = (saved_val > 0)

            if not has_definition:
                # Caso 1: Não há definição (0.00)
                # O placeholder deve ser "0.00" para ambas as opções.
                # Se o valor atual na entry for "0.00" (texto vindo do load), limpamos para mostrar o placeholder.
                val_atual = self.var_tol_valor.get()
                if val_atual in ["0.00", "0", "0.0"]:
                    self.var_tol_valor.set("")

                # Garante que o placeholder do componente seja 0.00
                if hasattr(ent_tol, 'placeholder'): ent_tol.placeholder = "0.00"

            else:
                # Caso 2: Usuário definiu um valor (ex: 5.00)
                if curr_type == saved_type:
                    # Estamos na aba que possui o valor salvo.
                    # Se a caixa estiver vazia (por troca de aba), repopula com o valor salvo.
                    if not self.var_tol_valor.get():
                        self.var_tol_valor.set(f"{saved_val:.2f}")

                    # Placeholder padrão (caso o usuário apague o texto)
                    if hasattr(ent_tol, 'placeholder'): ent_tol.placeholder = "0.00"
                else:
                    # Estamos na aba "não escolhida".
                    # Deve ficar "sem placeholder" (vazio) para indicar inatividade clara.
                    self.var_tol_valor.set("")
                    if hasattr(ent_tol, 'placeholder'): ent_tol.placeholder = ""

        # Vincula a função à mudança do tipo (trace)
        self.var_tol_tipo.trace_add("write", _update_tol_ui)

        # Chamada inicial para garantir consistência visual ao desenhar
        # (Obs: on_show chamará depois, mas isso define o estado inicial dos widgets)
        _update_tol_ui()
        # --------------------------------------------------------

        tk.Label(f_tol, text="Diferença máxima aceitável", bg="#ffffff", fg="#6B7280").pack(side="left", padx=8)

        # --- RODAPÉ DO CARD ---
        # Separador fora do main_content para ir de ponta a ponta
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(20, 0))

        # Botões com padding
        frm_act = tk.Frame(body, bg="#ffffff")
        frm_act.pack(fill="x", padx=24, pady=20)

        BlueCheckButton(frm_act, text="Resetar exceções", variable=self.var_reset_receb, bg="#ffffff").pack(side="left")

        # Label Exceções
        self.lbl_receb_excecoes = tk.Label(frm_act, text="", font=("Segoe UI", 9, "italic"),
                                           bg="#ffffff", fg="#6B7280")
        self.lbl_receb_excecoes.pack(side="left", padx=15)

        # Botão alinhado à direita
        PillButton(frm_act, text="Ver Exceções", variant="outline",
                   command=self._open_receb_exceptions_dialog, height=28).pack(side="right")

    def _build_card_separacao(self):
        # Placeholder visual
        card = RoundedCard(self.center_frame, radius=8, padding=(24, 24, 24, 24))
        card.pack(fill="x", pady=(0, 20))
        body = card.content

        tk.Label(body, text="Políticas de Separação", font=("Segoe UI", 12, "bold"), bg="#ffffff",
                 fg=Colors.PRIMARY).pack(anchor="w", pady=(0, 10))
        tk.Label(body, text="Configurações de picking, ondas e expedição em breve.", bg="#ffffff",
                 fg=Colors.TEXT_HINT).pack(
            anchor="w")

    def _build_footer_actions(self):
        f_frm = ttk.Frame(self.center_frame, style="Main.TFrame")
        f_frm.pack(fill="x", pady=(10, 60))  # Padding extra no fundo para scroll

        # Botão Salvar Grande e Verde
        self.btn_save = PillButton(f_frm, text="Salvar", variant="success",
                                   icon=load_icon("check_green", 16), command=self._apply_all_policies)
        self.btn_save.pack(side="right")

        tk.Label(f_frm, text="Alterações impactam o sistema imediatamente.", bg=Colors.BG_APP, fg="#6B7280").pack(
            side="right", padx=15)

    # --- LÓGICA DE NEGÓCIO ---

    def on_show(self, **kwargs):
        # 1. Carrega Validade
        try:
            self.var_modo.set(global_policies.modo_validade or "Validade opcional")
        except Exception:
            self.var_modo.set("Validade opcional")

        # 3. Carrega Bloqueios
        try:
            self.var_block_vencido.set(bool(getattr(global_policies, "bloquear_vencido", False)))
            self.var_block_sem_validade.set(bool(getattr(global_policies, "bloquear_sem_validade_obrigatoria", False)))
            self.var_block_sem_lote.set(bool(getattr(global_policies, "bloquear_sem_lote_obrigatorio", False)))
            self.var_block_rep_qualidade.set(bool(getattr(global_policies, "bloquear_reprovacao_qualidade", False)))
        except Exception:
            self.var_block_vencido.set(False)
            self.var_block_sem_validade.set(False)
            self.var_block_sem_lote.set(False)
            self.var_block_rep_qualidade.set(False)

        # 4. Carrega Giro e Lote
        try:
            self.var_giro_modelo.set(getattr(global_policies, "modelo_giro", "FEFO"))
        except Exception:
            self.var_giro_modelo.set("FEFO")

        try:
            self.var_modo_lote.set(getattr(global_policies, "modo_lote", "Lote opcional"))
        except Exception:
            self.var_modo_lote.set("Lote opcional")

        # 5. Carrega Validade Mínima
        val_salvo = global_policies.validade_minima_dias
        if val_salvo:
            self.var_min_dias.set(str(val_salvo))
            self.var_min_und.set("Dias")
        else:
            self.var_min_dias.set("")
            self.var_min_und.set("Dias")

        tol_salva = getattr(global_policies, "tolerancia_valor_recebimento", 0.00)
        self.var_tol_valor.set(f"{tol_salva:.2f}")

        tipo_salvo = getattr(global_policies, "tolerancia_tipo_recebimento", "Valor")
        self.var_tol_tipo.set(tipo_salvo)

        # 7. Reseta o checkbox de "Forçar Reset"
        self.var_reset_all.set(False)
        self.var_reset_receb.set(False)

        # 8. Atualiza a UI (sem _update_alerta_entry_state)
        self._refresh_summaries()
        self._refresh_receb_summary()

    def _refresh_summaries(self):
        # Conta exceções para exibir nos labels
        fam_counts = families_repo.count_exceptions(global_policies)
        prod_counts = products_repo.count_exceptions(global_policies, families_repo)

        def _fmt_resumo(fam, prod):
            fam_txt = "1 família" if fam == 1 else f"{fam} famílias"
            prod_txt = "1 produto" if prod == 1 else f"{prod} produtos"
            if fam == 0 and prod == 0: return ""
            return f"Exceções: {fam_txt} · {prod_txt}"

        try:
            self.lbl_validade_excecoes.configure(text=_fmt_resumo(fam_counts["validade"], prod_counts["validade"]))
            self.lbl_bloqueios_excecoes.configure(text=_fmt_resumo(fam_counts["bloqueio"], prod_counts["bloqueio"]))
            self.lbl_giro_excecoes.configure(text=_fmt_resumo(fam_counts["giro"], prod_counts["giro"]))
            self.lbl_lote_excecoes.configure(text=_fmt_resumo(fam_counts["lote"], prod_counts["lote"]))
        except Exception:
            pass

    def _refresh_receb_summary(self):
        # CORREÇÃO: families_repo.get_all()
        fam_count = sum(1 for r in families_repo.get_all() if r.get("ValidadeMinimaDias") is not None)
        # CORREÇÃO: products_repo.get_all()
        prod_count = sum(1 for r in products_repo.get_all() if r.get("ValidadeMinimaDias") is not None)

        txt = f"Exceções de Validade: {fam_count} famílias · {prod_count} produtos" if (
                                                                                               fam_count + prod_count) > 0 else ""

        try:
            # Tenta atualizar o label se ele ainda existir na sua interface
            self.lbl_receb_excecoes.configure(text=txt)
        except Exception:
            # Se você apagou o label visualmente no passo anterior, o código apenas ignora e não quebra
            pass

    def _open_exceptions_dialog(self):
        def _refresh(): self._refresh_summaries()

        ExcecoesEstoqueDialog(self, on_changed=_refresh)

    def _open_receb_exceptions_dialog(self):
        RecebimentoExcecoesDialog(self, on_close=self._refresh_receb_summary)

    def _apply_all_policies(self):
        import traceback

        try:
            # --- Validade Mínima (Recebimento) ---
            min_d = self.var_min_dias.get().strip()
            if not min_d:
                global_policies.validade_minima_dias = None
            else:
                if not min_d.isdigit() or int(min_d) < 0:
                    self.alert("Erro", "Validade mínima inválida.", type="warning")
                    return

                global_policies.validade_minima_dias = int(min_d)

            # --- Tolerância ---
            try:
                tol_txt = self.var_tol_valor.get().replace(",", ".").strip()
                if not tol_txt:
                    # Se vazio, assume 0.00
                    global_policies.tolerancia_valor_recebimento = 0.00
                else:
                    tol_float = float(tol_txt)
                    if tol_float < 0: raise ValueError

                    # Validação extra para porcentagem
                    if self.var_tol_tipo.get() == "Porcentagem" and tol_float > 100:
                        self.alert("Erro", "A porcentagem não pode ser maior que 100%.", type="warning")
                        return

                    global_policies.tolerancia_valor_recebimento = tol_float

                # Salva o tipo
                global_policies.tolerancia_tipo_recebimento = self.var_tol_tipo.get()

            except ValueError:
                self.alert("Erro", "Valor de tolerância inválido.", type="warning")
                return

            # --- Transferência de Valores Simples ---
            global_policies.modo_validade = self.var_modo.get()
            global_policies.modo_lote = self.var_modo_lote.get()
            global_policies.modelo_giro = self.var_giro_modelo.get()

            # --- Bloqueios ---
            global_policies.bloquear_vencido = self.var_block_vencido.get()
            global_policies.bloquear_sem_validade_obrigatoria = self.var_block_sem_validade.get()
            global_policies.bloquear_sem_lote_obrigatorio = self.var_block_sem_lote.get()
            global_policies.bloquear_reprovacao_qualidade = self.var_block_rep_qualidade.get()

            # --- Reset ---
            reset_estoque = self.var_reset_all.get()
            reset_receb = self.var_reset_receb.get()

            msg_reset = ""
            if reset_estoque and reset_receb:
                msg_reset = "Isso irá remover TODAS as regras personalizadas (Estoque e Recebimento)..."
            elif reset_estoque:
                msg_reset = "Isso irá remover as regras personalizadas de ESTOQUE"
            elif reset_receb:
                msg_reset = "Isso irá remover as regras personalizadas de RECEBIMENTO"

            if msg_reset:
                def processar_reset():
                    if reset_estoque:
                        self._reset_estoque_exceptions()
                    if reset_receb:
                        self._reset_receb_exceptions()

                self.ask_yes_no(
                    "Confirmar Reset",
                    msg_reset,
                    on_yes=processar_reset
                )

            global_policies.save()

            from database.repositories import recebimento_repo
            recebimento_repo.recalcular_todos_prs_abertos()

            if hasattr(self, '_refresh_summaries'): self._refresh_summaries()
            if hasattr(self, '_refresh_receb_summary'): self._refresh_receb_summary()

            from utils.helpers import bus
            bus.publish("policy_changed")

            self.alert("Sucesso", "Políticas globais atualizadas!", type="info")

        except Exception as e:
            traceback.print_exc()
            self.alert("Erro Crítico", f"Erro: {str(e)}", type="error")

    def _reset_all_exceptions(self):
        # Mantido para compatibilidade se chamado externamente, mas redireciona
        self._reset_estoque_exceptions()
        self._reset_receb_exceptions()

    def _reset_estoque_exceptions(self):
        # Limpa famílias (Estoque)
        for r in families_repo.get_all():
            r["ValidadeModo"] = "Herdar"
            r["LoteModo"] = "Herdar"
            r["GiroModo"] = "Herdar"
            # Não limpa validade_minima_dias aqui
            for k in ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]:
                r[k] = None

        # Limpa produtos (Estoque)
        for r in products_repo.get_all():
            r["ValidadeModo"] = "Herdar"
            r["LoteModo"] = "Herdar"
            r["GiroModo"] = "Herdar"
            for k in ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]:
                r[k] = None

        if hasattr(families_repo, "_save"): families_repo._save()
        if hasattr(products_repo, "_save"): products_repo._save()

    def _reset_receb_exceptions(self):
        # Limpa famílias (Recebimento)
        for r in families_repo.get_all():
            r["ValidadeMinimaDias"] = None

        # Limpa produtos (Recebimento)
        for r in products_repo.get_all():
            r["ValidadeMinimaDias"] = None

        if hasattr(families_repo, "_save"): families_repo._save()
        if hasattr(products_repo, "_save"): products_repo._save()