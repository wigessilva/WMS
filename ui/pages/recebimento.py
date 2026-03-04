import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog

from database.repositories import (
    recebimento_repo, oc_repo, products_repo, families_repo,
    lpn_repo,
    locations_repo,
    global_policies
)
from ui.components import (
    Page, PillButton, StandardTable, SaaSModal,
    TextField, PillCombobox, TabButton, RoundedCard, SplitButton
)
from utils.constants import Colors, StatusPR, PAGE_SIZE_DEFAULT
from utils.helpers import load_icon, AuditManager
from workflows.recebimento_workflow import RecebimentoWorkflow


class RecebimentoExcecoesDialog(SaaSModal):
    def __init__(self, parent, on_close=None):
        super().__init__(parent, title="Exceções de Recebimento", width=900, height=550)
        self._on_close_callback = on_close

        self.content.configure(bg=Colors.BG_APP)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)

        header_frm = ttk.Frame(self.content, style="Main.TFrame", padding=(16, 12, 16, 0))
        header_frm.grid(row=0, column=0, sticky="ew")

        self.mode = tk.StringVar(value="familias")
        self.icon_left = load_icon("anterior", 16)
        self.icon_right = load_icon("proximo", 16)

        self.btn_toggle = PillButton(
            header_frm,
            text="Produtos",
            command=self._toggle_mode,
            variant="outline",
            icon=self.icon_right
        )
        self.btn_toggle.pack(side="left")

        table_frm = ttk.Frame(self.content, style="Main.TFrame", padding=0)
        table_frm.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        table_frm.columnconfigure(0, weight=1)
        table_frm.rowconfigure(0, weight=1)

        self.table_container = table_frm
        self.table = None

        self._build_table()

    def _toggle_mode(self):
        if self.mode.get() == "familias":
            self.mode.set("produtos")
            self.btn_toggle.configure(text="Famílias", icon=self.icon_left)
        else:
            self.mode.set("familias")
            self.btn_toggle.configure(text="Produtos", icon=self.icon_right)
        self._build_table()

    def _build_table(self):
        if self.table:
            self.table.destroy()

        mode = self.mode.get()

        if mode == "familias":
            cols = [
                {"id": "Nome", "title": "Família", "width": 300, "anchor": "w"},
                {"id": "Validade", "title": "Val. Mínima (Dias)", "width": 180, "anchor": "center"},
            ]
            fetch = self._fetch_familias
        else:
            cols = [
                {"id": "Sku", "title": "SKU", "width": 100, "anchor": "w"},
                {"id": "Descricao", "title": "Descrição", "width": 280, "anchor": "w"},
                {"id": "Familia", "title": "Família", "width": 150, "anchor": "w"},
                {"id": "Validade", "title": "Val. Mínima (Dias)", "width": 140, "anchor": "center"},
            ]
            fetch = self._fetch_produtos

        self.table = StandardTable(self.table_container, columns=cols, fetch_fn=fetch, page_size=14)

        self.table.body_canvas.configure(bg=Colors.BG_CARD)
        self.table.header_canvas.configure(bg=Colors.BG_CARD)
        self.table.body_bg = Colors.BG_CARD

        self.table.grid(row=0, column=0, sticky="new")

    def _fetch_familias(self, page, page_size, filters):
        all_rows = []
        # CORREÇÃO: Usando get_all()
        for r in families_repo.get_all():
            val_min = r.get("ValidadeMinimaDias")
            has_min = (val_min is not None)

            if has_min:
                row = dict(r)
                row["Validade"] = f"{val_min}"
                all_rows.append(row)

        total = len(all_rows)
        start = (page - 1) * page_size
        end = start + page_size
        return total, all_rows[start:end]

    def _fetch_produtos(self, page, page_size, filters):
        all_rows = []
        # CORREÇÃO: Usando get_all()
        for r in products_repo.get_all():
            val_min = r.get("ValidadeMinimaDias")
            has_min = (val_min is not None)

            if has_min:
                row = dict(r)
                row["Validade"] = f"{val_min}"
                all_rows.append(row)

        total = len(all_rows)
        start = (page - 1) * page_size
        end = start + page_size
        return total, all_rows[start:end]

    def close(self, event=None):
        if self._on_close_callback:
            self._on_close_callback()
        super().close(event)


class ExcecoesEstoqueDialog(SaaSModal):
    def __init__(self, parent, on_changed=None):
        self._on_changed = on_changed
        super().__init__(parent, title="Exceções de Estoque", width=1000, height=600)

        self.content.configure(bg=Colors.BG_APP)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)

        self.mode = tk.StringVar(value="familias")
        self.current_tab = tk.StringVar(value="validade")

        self._icon_left = load_icon("anterior", 16)
        self._icon_right = load_icon("proximo", 16)

        children = self.header.winfo_children()
        if children:
            for widget in children:
                if isinstance(widget, tk.Label) and widget != self.btn_close:
                    widget.destroy()

        tabs_container = tk.Frame(self.header, bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0)
        tabs_container.pack(side="left", padx=(24, 0), fill="y")

        self._tab_buttons = {}
        tab_defs = [
            ("validade", "Validade"),
            ("lote", "Lote"),
            ("bloqueios", "Bloqueios"),
            ("giro", "Giro"),
            ("todas", "Todas"),
        ]

        for i, (tab_id, label) in enumerate(tab_defs):
            btn = TabButton(
                tabs_container,
                text=label,
                command=lambda t=tab_id: self._switch_tab(t),
                height=32,
            )
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0), pady=(8, 0))
            self._tab_buttons[tab_id] = btn

        header_toggle = ttk.Frame(self.content, style="Main.TFrame")
        header_toggle.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        self.btn_toggle = PillButton(
            header_toggle,
            text="Produtos",
            command=self._toggle_mode,
            variant="outline",
            icon=self._icon_right
        )
        self.btn_toggle.pack(side="left")

        tables_frame = ttk.Frame(self.content, style="Main.TFrame", padding=0)
        tables_frame.grid(row=1, column=0, sticky="nsew")
        tables_frame.columnconfigure(0, weight=1)
        tables_frame.rowconfigure(0, weight=1)
        self._tables_frame = tables_frame

        self.table = None
        self._update_tab_styles()
        self._build_table()

    def on_close(self):
        if self._on_changed:
            try:
                self._on_changed()
            except:
                pass
        super().close()

    def _switch_tab(self, tab_id):
        if self.current_tab.get() == tab_id: return
        self.current_tab.set(tab_id)
        self._update_tab_styles()
        self._build_table()

    def _update_tab_styles(self):
        current = self.current_tab.get()
        for tab_id, btn in self._tab_buttons.items():
            if tab_id == current:
                btn.configure(variant="tab_selected")
            else:
                btn.configure(variant="tab_unselected")

    def _toggle_mode(self):
        if self.mode.get() == "familias":
            self.mode.set("produtos")
            self.btn_toggle.configure(text="Famílias", icon=self._icon_left)
        else:
            self.mode.set("familias")
            self.btn_toggle.configure(text="Produtos", icon=self._icon_right)
        self._build_table()

    def _build_table(self):
        if self.table:
            try:
                self.table.destroy()
            except:
                pass
            self.table = None

        tab_id = self.current_tab.get()
        mode = self.mode.get()
        cols, fetch_fn = self._get_columns_and_fetch(tab_id, mode)

        self.table = StandardTable(
            self._tables_frame,
            columns=cols,
            fetch_fn=fetch_fn,
            page_size=PAGE_SIZE_DEFAULT,
            inner_padx=16
        )
        self.table.body_canvas.configure(bg=Colors.BG_CARD)
        self.table.header_canvas.configure(bg=Colors.BG_CARD)
        self.table.body_bg = Colors.BG_CARD
        self.table.grid(row=0, column=0, sticky="new")

        try:
            self.table.load_page(1)
        except:
            pass

    def _get_columns_and_fetch(self, tab_id, mode):
        if tab_id == "validade": return self._columns_validade(mode), self._fetch_validade(mode)
        if tab_id == "lote": return self._columns_lote(mode), self._fetch_lote(mode)
        if tab_id == "bloqueios": return self._columns_bloqueios(mode), self._fetch_bloqueios(mode)
        if tab_id == "giro": return self._columns_giro(mode), self._fetch_giro(mode)
        return self._columns_todas(mode), self._fetch_todas(mode)

    def _base_cols(self, mode):
        if mode == "familias":
            return [{"id": "Nome", "title": "Família", "width": 300, "anchor": "w"}]
        return [
            {"id": "Sku", "title": "SKU", "width": 100, "anchor": "w"},
            {"id": "Descricao", "title": "Descrição", "width": 300, "anchor": "w"},
            {"id": "Familia", "title": "Família", "width": 180, "anchor": "w"}
        ]

    def _columns_validade(self, mode):
        return self._base_cols(mode) + [
            {"id": "ValidadeModo", "title": "Validade", "type": "text", "width": 220, "anchor": "center"}]

    def _columns_lote(self, mode):
        return self._base_cols(mode) + [
            {"id": "LoteModo", "title": "Lote", "type": "text", "width": 220, "anchor": "center"}]

    def _columns_giro(self, mode):
        return self._base_cols(mode) + [
            {"id": "GiroModo", "title": "Modelo de giro", "type": "text", "width": 200, "anchor": "center"}]

    def _columns_bloqueios(self, mode):
        return self._base_cols(mode) + [
            {"id": "Vencimento", "title": "Vencimento", "width": 140, "anchor": "center"},
            {"id": "SemValidade", "title": "Sem Validade", "width": 140, "anchor": "center"},
            {"id": "SemLote", "title": "Sem Lote", "width": 140, "anchor": "center"},
            {"id": "RepQualidade", "title": "Rep. Qualidade", "width": 140, "anchor": "center"},
        ]

    def _columns_todas(self, mode):
        return self._base_cols(mode) + [
            {"id": "Validade", "title": "Validade", "width": 180, "anchor": "center"},
            {"id": "Lote", "title": "Lote", "width": 160, "anchor": "center"},
            {"id": "Vencimento", "title": "B. Vencido", "width": 130, "anchor": "center"},
            {"id": "SemValidade", "title": "B. Sem Validade", "width": 130, "anchor": "center"},
            {"id": "SemLote", "title": "B. Sem Lote", "width": 130, "anchor": "center"},
            {"id": "RepQualidade", "title": "B. Rep. Qual.", "width": 130, "anchor": "center"},
            {"id": "Giro", "title": "Giro", "width": 120, "anchor": "center"},
        ]

    def _fetch_validade(self, mode):
        def fetch(page, page_size, filters):
            exc_rows = []
            g_val = global_policies.modo_validade or "Validade opcional"

            def clean_val(txt):
                if not txt: return ""
                return str(txt).replace("Validade ", "").capitalize()

            if mode == "familias":
                _t, rows = families_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("ValidadeModo")
                    if not raw or raw == "Herdar" or raw == g_val: continue

                    cp = dict(r)
                    cp["ValidadeModo"] = clean_val(raw)
                    exc_rows.append(cp)
            else:
                # CORREÇÃO: get_all()
                fam_map = {f["Nome"]: f for f in families_repo.get_all()}
                _t, rows = products_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("ValidadeModo")
                    if not raw or raw == "Herdar": continue

                    parent_rule = g_val
                    f_row = fam_map.get(r.get("Familia"))
                    if f_row:
                        fr = f_row.get("ValidadeModo")
                        if fr and fr != "Herdar": parent_rule = fr

                    if raw != parent_rule:
                        cp = dict(r)
                        cp["ValidadeModo"] = clean_val(raw)
                        exc_rows.append(cp)

            return len(exc_rows), exc_rows[max(0, (page - 1) * page_size): max(0, (page - 1) * page_size) + page_size]

        return fetch

    def _fetch_lote(self, mode):
        def fetch(page, page_size, filters):
            exc_rows = []
            g_lote = getattr(global_policies, "ModoLote", "Lote opcional")

            def clean_val(txt):
                if not txt: return ""
                return str(txt).replace("Lote ", "").capitalize()

            if mode == "familias":
                _t, rows = families_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("LoteModo")
                    if not raw or raw == "Herdar" or raw == g_lote: continue

                    cp = dict(r)
                    cp["LoteModo"] = clean_val(raw)
                    exc_rows.append(cp)
            else:
                # CORREÇÃO: get_all()
                fam_map = {f["Nome"]: f for f in families_repo.get_all()}
                _t, rows = products_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("LoteModo")
                    if not raw or raw == "Herdar": continue

                    parent_rule = g_lote
                    f_row = fam_map.get(r.get("Familia"))
                    if f_row:
                        fr = f_row.get("LoteModo")
                        if fr and fr != "Herdar": parent_rule = fr

                    if raw != parent_rule:
                        cp = dict(r)
                        cp["LoteModo"] = clean_val(raw)
                        exc_rows.append(cp)
            return len(exc_rows), exc_rows[max(0, (page - 1) * page_size): max(0, (page - 1) * page_size) + page_size]

        return fetch

    def _fetch_giro(self, mode):
        def fetch(page, page_size, filters):
            exc_rows = []
            g_giro = getattr(global_policies, "ModeloGiro", "FEFO")

            if mode == "familias":
                _t, rows = families_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("GiroModo")
                    if not raw or raw in ("Herdar", "None", "") or raw == g_giro: continue

                    cp = dict(r)
                    cp["GiroModo"] = raw.upper()
                    exc_rows.append(cp)
            else:
                # CORREÇÃO: get_all()
                fam_map = {f["Nome"]: f for f in families_repo.get_all()}
                _t, rows = products_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    raw = r.get("GiroModo")
                    if not raw or raw in ("Herdar", "None", ""): continue

                    parent_rule = g_giro
                    f_row = fam_map.get(r.get("Familia"))
                    if f_row:
                        fr = f_row.get("GiroModo")
                        if fr and fr not in ("Herdar", "None", ""): parent_rule = fr

                    if raw != parent_rule:
                        cp = dict(r)
                        cp["GiroModo"] = raw.upper()
                        exc_rows.append(cp)
            return len(exc_rows), exc_rows[max(0, (page - 1) * page_size): max(0, (page - 1) * page_size) + page_size]

        return fetch

    def _fetch_bloqueios(self, mode):
        def fetch(page, page_size, filters):
            exc_rows = []

            gv = bool(getattr(global_policies, "bloquear_vencido", False))
            gs = bool(getattr(global_policies, "bloquear_sem_validade_obrigatoria", False))
            gl = bool(getattr(global_policies, "bloquear_sem_lote_obrigatorio", False))
            gq = bool(getattr(global_policies, "bloquear_reprovacao_qualidade", False))

            def fmt(val):
                return "Sim" if val else "Não"

            if mode == "familias":
                _t, rows = families_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    if all(r.get(k) is None for k in
                           ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]):
                        continue

                    rv = r.get("BlockVencido")
                    rs = r.get("BlockSemValidade")
                    rl = r.get("BlockSemLote")
                    rq = r.get("BlockRepQualidade")

                    diff = False
                    if rv is not None and bool(rv) != gv: diff = True
                    if rs is not None and bool(rs) != gs: diff = True
                    if rl is not None and bool(rl) != gl: diff = True
                    if rq is not None and bool(rq) != gq: diff = True

                    if diff:
                        cp = dict(r)
                        cp["Vencimento"] = fmt(rv) if (rv is not None and bool(rv) != gv) else "-"
                        cp["SemValidade"] = fmt(rs) if (rs is not None and bool(rs) != gs) else "-"
                        cp["SemLote"] = fmt(rl) if (rl is not None and bool(rl) != gl) else "-"
                        cp["RepQualidade"] = fmt(rq) if (rq is not None and bool(rq) != gq) else "-"
                        exc_rows.append(cp)
            else:
                # CORREÇÃO: get_all()
                fam_map = {f["Nome"]: f for f in families_repo.get_all()}
                _t, rows = products_repo.list(1, 10 ** 9, filters or [])
                for r in rows:
                    if all(r.get(k) is None for k in
                           ["BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"]):
                        continue

                    f_row = fam_map.get(r.get("Familia"))
                    pv = f_row.get("BlockVencido") if (f_row and f_row.get("BlockVencido") is not None) else gv
                    ps = f_row.get("BlockSemValidade") if (
                            f_row and f_row.get("BlockSemValidade") is not None) else gs
                    pl = f_row.get("BlockSemLote") if (f_row and f_row.get("BlockSemLote") is not None) else gl
                    pq = f_row.get("BlockRepQualidade") if (
                            f_row and f_row.get("BlockRepQualidade") is not None) else gq

                    rv, rs, rl, rq = r.get("BlockVencido"), r.get("BlockSemValidade"), r.get(
                        "BlockSemLote"), r.get("BlockRepQualidade")

                    diff = False
                    if rv is not None and bool(rv) != bool(pv): diff = True
                    if rs is not None and bool(rs) != bool(ps): diff = True
                    if rl is not None and bool(rl) != bool(pl): diff = True
                    if rq is not None and bool(rq) != bool(pq): diff = True

                    if diff:
                        cp = dict(r)
                        cp["Vencimento"] = fmt(rv) if (rv is not None and bool(rv) != bool(pv)) else "-"
                        cp["SemValidade"] = fmt(rs) if (rs is not None and bool(rs) != bool(ps)) else "-"
                        cp["SemLote"] = fmt(rl) if (rl is not None and bool(rl) != bool(pl)) else "-"
                        cp["RepQualidade"] = fmt(rq) if (rq is not None and bool(rq) != bool(pq)) else "-"
                        exc_rows.append(cp)

            return len(exc_rows), exc_rows[max(0, (page - 1) * page_size): max(0, (page - 1) * page_size) + page_size]

        return fetch

    def _fetch_todas(self, mode):
        def fetch(page, page_size, filters):
            if mode == "familias":
                all_data = families_repo.get_resolved_report(
                    global_policies=global_policies,
                    filter_exceptions_only=True
                )
            else:
                all_data = products_repo.get_resolved_report(
                    global_policies=global_policies,
                    families_repo_instance=families_repo,
                    filter_exceptions_only=True
                )

            total = len(all_data)
            start = (page - 1) * page_size
            end = start + page_size

            return total, all_data[start:end]

        return fetch


class RecebimentoControlPanel(SaaSModal):
    def __init__(self, parent, pr_code, on_close_callback=None):
        self.pr_code = pr_code
        self.on_close_callback = on_close_callback

        # Busca dados do Header para pré-preenchimento
        self.header_data = recebimento_repo.get_by_pr(pr_code) or {}

        super().__init__(parent, title="", width=950, height=650)

        for widget in self.header.winfo_children():
            if isinstance(widget, tk.Label):
                widget.destroy()

        self.content.configure(bg=Colors.BG_APP)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)

        # --- Abas ---
        tabs_container = tk.Frame(self.header, bg=Colors.BG_SIDEBAR, bd=0, highlightthickness=0)
        tabs_container.pack(side="left", padx=(24, 0), fill="y")

        # ALTERAÇÃO 2: Ações vem primeiro e é o default
        self.current_tab = tk.StringVar(value="acoes")
        self._tab_buttons = {}

        tabs_def = [
            ("acoes", "Ações"),
            ("conferencia", "Conferência")
        ]

        for i, (tid, label) in enumerate(tabs_def):
            btn = TabButton(tabs_container, text=label, command=lambda t=tid: self._switch_tab(t), height=32)
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0), pady=(8, 0))
            self._tab_buttons[tid] = btn

        # Área de Conteúdo das Abas
        self.tab_frame = ttk.Frame(self.content, style="Main.TFrame")
        self.tab_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        self._update_tab_styles()

        # ALTERAÇÃO 2: Constrói ações primeiro
        self._build_acoes()

    def _switch_tab(self, tab_id):
        if self.current_tab.get() == tab_id: return
        self.current_tab.set(tab_id)
        self._update_tab_styles()

        # Limpa conteúdo atual
        for widget in self.tab_frame.winfo_children():
            widget.destroy()

        if tab_id == "conferencia":
            self._build_conferencia()
        elif tab_id == "acoes":
            self._build_acoes()

    def _update_tab_styles(self):
        curr = self.current_tab.get()
        for tid, btn in self._tab_buttons.items():
            btn.configure(variant="tab_selected" if tid == curr else "tab_unselected")

    # --- ABA 1: CONFERÊNCIA ---
    def _build_conferencia(self):
        self.tab_frame.columnconfigure(0, weight=1)
        self.tab_frame.rowconfigure(0, weight=1)

        cols = [
            {"id": "Sku", "title": "SKU", "width": 100, "anchor": "w"},
            {"id": "Descricao", "title": "Descrição", "width": 350, "anchor": "w"},
            {"id": "progresso_txt", "title": "Progresso", "width": 120, "anchor": "center"},
            {"id": "Status", "title": "Status", "width": 140, "anchor": "center"},
            {"id": "Conferente", "title": "Conferente", "width": 150, "anchor": "w"},
        ]

        def _fetch_conf(page, page_size, filters):
            itens = recebimento_repo.list_itens_por_pr(self.pr_code)
            processed = []
            for it in itens:
                row = dict(it)

                qtd = float(it.get("Qtd", 0))
                coletado = float(it.get("QtdColetada", 0))
                row["progresso_txt"] = f"{coletado:g} / {qtd:g}"
                row["Conferente"] = it.get("ConferenteUltimo") or "-"

                st = str(it.get("Status", "")).lower()
                if "conferido" in st:
                    row["_text_color"] = Colors.SUCCESS
                elif "divergência" in st or "bloqueado" in st:
                    row["_text_color"] = "#DC2626"

                processed.append(row)

            return len(processed), processed

        tbl = StandardTable(self.tab_frame, columns=cols, fetch_fn=_fetch_conf, page_size=12)
        tbl.grid(row=0, column=0, sticky="nsew")

    def _build_acoes(self):
        # Limpa o frame da aba
        for widget in self.tab_frame.winfo_children():
            widget.destroy()

        # Coleta Dados (A função _calcular_dashboard agora garante o retorno das mensagens corretas)
        dados_dash = self._calcular_dashboard()

        veredito_nivel = dados_dash["veredito_nivel"]
        veredito_titulo = dados_dash["veredito_titulo"]
        veredito_msg = dados_dash["veredito_msg"]

        # --- SCROLLBAR SETUP ---
        scroll_container = tk.Frame(self.tab_frame, bg=Colors.BG_APP)
        scroll_container.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, bg=Colors.BG_APP, highlightthickness=0)

        style_sb = ttk.Style()
        style_sb.configure("Minimal.Vertical.TScrollbar", background="#E5E7EB", troughcolor=Colors.BG_APP,
                           borderwidth=0, arrowsize=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview,
                                  style="Minimal.Vertical.TScrollbar")

        main_frm = tk.Frame(canvas, bg=Colors.BG_APP)
        canvas_window = canvas.create_window((0, 0), window=main_frm, anchor="nw")

        def _configure_inner_frame(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            req_height = main_frm.winfo_reqheight()
            visible_height = canvas.winfo_height()
            if req_height > visible_height:
                scrollbar.pack(side="right", fill="y")
            else:
                scrollbar.pack_forget()

        def _configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
            _configure_inner_frame(None)

        main_frm.bind("<Configure>", _configure_inner_frame)
        canvas.bind("<Configure>", _configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)

        # ==============================================================================
        # 1. TOPO: VEREDITO (Esq) + EDIÇÃO (Dir)
        # ==============================================================================
        top_split_frame = tk.Frame(main_frm, bg=Colors.BG_APP)
        top_split_frame.pack(fill="x", padx=20, pady=(20, 15))

        top_split_frame.columnconfigure(0, weight=6)
        top_split_frame.columnconfigure(1, weight=4)
        top_split_frame.rowconfigure(0, weight=1)

        # --- COLUNA ESQUERDA: BANNER DE VEREDITO ---
        cores_banner = {
            "success": {"bg": "#10B981", "fg": "#FFFFFF", "icon": "check_green", "icon_color": None, "size": 16},
            "warning": {"bg": Colors.WARNING, "fg": "#374151", "icon": "alert", "icon_color": "#000000",
                        "size": 24},
            "critical": {"bg": Colors.DANGER, "fg": "#FFFFFF", "icon": "caution", "icon_color": "#FFFFFF",
                         "size": 24},
            "info": {"bg": "#3B82F6", "fg": "#FFFFFF", "icon": "eye", "icon_color": "#FFFFFF", "size": 24}
        }

        if veredito_titulo == "ATENÇÃO NECESSÁRIA":
            cores_banner["warning"]["icon"] = "alert_yellow"
            cores_banner["warning"]["icon_color"] = None

        style = cores_banner.get(veredito_nivel, cores_banner["info"])

        banner = RoundedCard(top_split_frame, radius=10, bg=style["bg"])
        banner.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        def _force_banner_height(event):
            banner._on_configure(event)
            pl, pt, pr, pb = banner._padding
            h_inner = max(1, event.height - (pt + pb))
            banner.itemconfigure(banner._win, height=h_inner)

        banner.bind("<Configure>", _force_banner_height)

        content_banner = tk.Frame(banner.content, bg=style["bg"], pady=15, padx=15)
        content_banner.pack(fill="both", expand=True)

        center_box = tk.Frame(content_banner, bg=style["bg"])
        center_box.pack(expand=True, anchor="center")

        title_row = tk.Frame(center_box, bg=style["bg"])
        title_row.pack(anchor="center", pady=(0, 6))

        try:
            icon_img = load_icon(style["icon"], style.get("size", 24), color=style.get("icon_color"))
            tk.Label(title_row, image=icon_img, bg=style["bg"]).pack(side="left", padx=(0, 8))
            title_row.icon_img = icon_img
        except:
            pass

        tk.Label(title_row, text=veredito_titulo.upper(), font=("Segoe UI", 12, "bold"),
                 fg=style["fg"], bg=style["bg"]).pack(side="left")

        tk.Label(center_box, text=veredito_msg, font=("Segoe UI", 10),
                 fg=style["fg"], bg=style["bg"], wraplength=400, justify="center").pack(anchor="center")

        # --- COLUNA DIREITA: EDIÇÃO OC / DESTINO ---
        edit_frame = RoundedCard(top_split_frame, radius=10, bg=Colors.BG_CARD)
        edit_frame.grid(row=0, column=1, sticky="nsew")

        frm_edit_content = tk.Frame(edit_frame.content, bg=Colors.BG_CARD, padx=10, pady=10)
        frm_edit_content.pack(fill="both", expand=True)

        tk.Label(frm_edit_content, text="DADOS PRINCIPAIS", font=("Segoe UI", 8, "bold"),
                 fg=Colors.TEXT_HINT, bg=Colors.BG_CARD).pack(anchor="w", pady=(0, 8))

        # CAMPO OC
        row_oc = tk.Frame(frm_edit_content, bg=Colors.BG_CARD)
        row_oc.pack(fill="x", pady=(0, 8))
        tk.Label(row_oc, text="OC:", font=("Segoe UI", 9), bg=Colors.BG_CARD, width=8, anchor="w").pack(side="left")
        self.entry_oc = TextField(row_oc, width=15)
        self.entry_oc.insert(0, self.header_data.get("Oc", ""))
        self.entry_oc.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_oc.configure(state="disabled")
        btn_edit_oc = PillButton(row_oc, text="", icon=load_icon("edit", 16), width=32, height=32,
                                 bg=Colors.BG_CARD, variant="outline")
        btn_edit_oc.pack(side="right")

        def _unlock_oc():
            current = str(self.entry_oc._entry["state"])
            if current == 'disabled':
                self.entry_oc.configure(state="normal")
                self.entry_oc.focus_set()
                btn_edit_oc.configure(bg="#EFF6FF")
            else:
                self.entry_oc.configure(state="disabled")
                btn_edit_oc.configure(bg=Colors.BG_CARD)

        btn_edit_oc.configure(command=_unlock_oc)

        # CAMPO DESTINO
        row_dest = tk.Frame(frm_edit_content, bg=Colors.BG_CARD)
        row_dest.pack(fill="x")
        tk.Label(row_dest, text="Destino:", font=("Segoe UI", 9), bg=Colors.BG_CARD, width=8, anchor="w").pack(
            side="left")
        lista_locais = [r["Nome"] for r in locations_repo.get_all() if r.get("Ativo", True)]
        if not lista_locais: lista_locais = ["Geral"]
        dest_atual = "Geral"
        itens_pr = recebimento_repo.list_itens_por_pr(self.pr_code)
        if itens_pr and itens_pr[0].get('Destino'):
            dest_atual = itens_pr[0].get('Destino')
        self.cmb_dest = PillCombobox(row_dest, values=lista_locais, width=15)
        self.cmb_dest.set(dest_atual)
        self.cmb_dest.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.cmb_dest.configure(state="disabled")
        btn_edit_dest = PillButton(row_dest, text="", icon=load_icon("edit", 16), width=32, height=32,
                                   bg=Colors.BG_CARD, variant="outline")
        btn_edit_dest.pack(side="right")

        def _unlock_dest():
            current_state = str(self.cmb_dest._entry["state"])
            if current_state == 'disabled':
                self.cmb_dest.configure(state="normal")
                btn_edit_dest.configure(bg="#EFF6FF")
            else:
                self.cmb_dest.configure(state="disabled")
                btn_edit_dest.configure(bg=Colors.BG_CARD)

        btn_edit_dest.configure(command=_unlock_dest)

        tk.Label(frm_edit_content, text="Aplica a todos os itens deste PR", font=("Segoe UI", 8),
                 fg=Colors.TEXT_HINT, bg=Colors.BG_CARD).pack(anchor="w", padx=(58, 0), pady=(2, 0))

        def _acao_aplicar_dados():
            nova_oc = self.entry_oc.get().strip()
            novo_dest = self.cmb_dest.get()
            recebimento_repo.update_pr_dados(self.pr_code, nova_oc=nova_oc, novo_destino=novo_dest,
                                             aplicar_a_todos=True)
            self.entry_oc.configure(state="disabled")
            self.cmb_dest.configure(state="disabled")
            btn_edit_oc.configure(bg=Colors.BG_CARD)
            btn_edit_dest.configure(bg=Colors.BG_CARD)
            self.header_data["Oc"] = nova_oc
            self._build_acoes()
            self.alert("Sucesso", "Dados atualizados com sucesso!", type="info")

        btn_container = tk.Frame(frm_edit_content, bg=Colors.BG_CARD)
        btn_container.pack(side="bottom", fill="x", pady=(8, 0))
        PillButton(btn_container, text="Aplicar", variant="success", command=_acao_aplicar_dados).pack(side="right")

        # ==============================================================================
        # 2. CARDS DE INSIGHTS (Meio)
        # ==============================================================================
        cards_container = tk.Frame(main_frm, bg=Colors.BG_APP)
        cards_container.pack(fill="both", expand=True, padx=20)

        cards_container.columnconfigure(0, weight=1)
        cards_container.columnconfigure(1, weight=1)
        cards_container.columnconfigure(2, weight=1)

        def _build_card_content(parent, titulo, icon_name, items_list, icon_color_header="#6B7280"):
            hdr = tk.Frame(parent, bg=Colors.BG_CARD)
            hdr.pack(fill="x", pady=(0, 10))

            try:
                tint_color = icon_color_header
                if icon_name in ["alert_red", "alert_yellow", "quality", "fisico"]:
                    tint_color = None

                ic = load_icon(icon_name, 16, color=tint_color)
                tk.Label(hdr, image=ic, bg=Colors.BG_CARD).pack(side="left", padx=(0, 8))
                hdr.ic = ic
            except:
                pass

            tk.Label(hdr, text=titulo, font=("Segoe UI", 10, "bold"),
                     fg="#000000", bg=Colors.BG_CARD).pack(side="left")

            for item in items_list:
                row = tk.Frame(parent, bg=Colors.BG_CARD)
                row.pack(fill="x", pady=1)

                cor_bullet = item.get("color", Colors.TEXT_MAIN)
                txt = item.get("text", "")

                tk.Label(row, text="•", font=("Arial", 12), fg=cor_bullet, bg=Colors.BG_CARD).pack(side="left",
                                                                                                   padx=(0, 6),
                                                                                                   anchor="n")
                tk.Label(row, text=txt, font=("Segoe UI", 9), fg="#374151", bg=Colors.BG_CARD, wraplength=200,
                         justify="left").pack(side="left", anchor="n")

        # Card 1: FÍSICO
        c1 = RoundedCard(cards_container, radius=10)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        _build_card_content(c1.content, "FÍSICO", "fisico", dados_dash["fisico_items"],
                            icon_color_header=Colors.DANGER)

        # Card 2: QUALIDADE
        c2 = RoundedCard(cards_container, radius=10)
        c2.grid(row=0, column=1, sticky="nsew", padx=5)
        _build_card_content(c2.content, "QUALIDADE", "quality", dados_dash["qualidade_items"],
                            icon_color_header=Colors.WARNING)

        # Card 3: FINANCEIRO
        c3 = RoundedCard(cards_container, radius=10)
        c3.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        _build_card_content(c3.content, "FINANCEIRO", "cifrao", dados_dash["financeiro_items"],
                            icon_color_header="#10B981")

        # ==============================================================================
        # 4. RODAPÉ DE AÇÃO
        # ==============================================================================
        footer = tk.Frame(self.tab_frame, bg=Colors.BG_APP)
        footer.pack(side="bottom", fill="x", padx=20, pady=20)

        status_pr = self.header_data.get("Status")
        conferente_atual = self.header_data.get("Conferente")

        tem_conferente = bool(conferente_atual and str(conferente_atual).strip())

        status_ativos_ou_iniciais = [
            StatusPR.EM_CONFERENCIA,
            StatusPR.AGUARDANDO_CONF,
            StatusPR.AGUARDANDO_LIBERACAO
        ]

        status_finalizados = [
            StatusPR.CONCLUIDO,
            StatusPR.CANCELADO,
            StatusPR.ESTORNADO
        ]

        pode_concluir = (
                tem_conferente and
                status_pr not in status_ativos_ou_iniciais and
                status_pr not in status_finalizados
        )

        wf = RecebimentoWorkflow(self.header_data)
        contexto_wf = wf.get_contexto_ui()
        pode_liberar = 'liberar_conferencia' in contexto_wf['acoes_workflow']

        if pode_concluir:
            lbl_btn = "Concluir"

            if veredito_nivel == "success":
                var_btn = "success"
                icon_btn = "check_green"
            else:
                var_btn = "warning"
                icon_btn = "alert_yellow"

            # ==============================================================================
            # MENU INTELIGENTE (RESPONSIVO)
            # ==============================================================================
            opcoes_aceite = []

            # 1. Analisa os itens para descobrir o contexto exato
            itens_pr = recebimento_repo.list_itens_por_pr(self.pr_code)

            tem_falta = False
            tem_avaria = False

            for i in itens_pr:
                # Checa Falta de Quantidade
                q_nota = float(i.get('Qtd', 0))
                q_real = float(i.get('QtdColetada', 0))
                if q_real < q_nota:
                    tem_falta = True

                # Checa Avaria/Qualidade
                dados_q = i.get('dados_qualidade', {})
                if isinstance(dados_q, str):
                    import json
                    try:
                        dados_q = json.loads(dados_q)
                    except:
                        dados_q = {}

                if (dados_q.get('material_integro') == 'Não' or
                        dados_q.get('embalagem_integra') == 'Não' or
                        dados_q.get('vencido', False)):
                    tem_avaria = True

            # 2. Constrói as opções baseadas no contexto
            if tem_falta:
                opcoes_aceite.append(("Recusa Parcial (Faltas)", self._acao_aceitar_parcial))

            if tem_avaria:
                opcoes_aceite.append(("Recusar Avariados", self._acao_recusar_avariados))

            # A Recusa Total atua como 'Abortar' e sempre fica disponível
            opcoes_aceite.append(("Recusa Total", self._acao_cancelar_pr))
            # ==============================================================================

            cmd_principal = lambda: self._acao_conclusao_forcada("Concluir")

            self.btn_action = SplitButton(
                footer,
                text=lbl_btn,
                variant=var_btn,
                icon=load_icon(icon_btn, 16),
                command=cmd_principal,
                options=opcoes_aceite
            )
            self.btn_action.pack(side="right", padx=(10, 0))

        # --- BOTÃO LIBERAR CONFERÊNCIA ---
        elif pode_liberar:
            PillButton(footer, text="Liberar Conferência", variant="primary", icon=load_icon("check_blue", 16),
                       height=34,
                       command=self._acao_liberar_conferencia).pack(side="right", padx=(10, 0))

        # --- LÓGICA DOS BOTÕES DE RETORNO/ESTORNO ---

        if status_pr == StatusPR.EM_CONFERENCIA:
            # Conferência Ativa -> Permite Cancelar (Estornar)
            PillButton(footer, text="Estornar Conferência", variant="outline", icon=load_icon("cancel", 16),
                       height=34,
                       command=self._acao_estornar_conferencia).pack(side="right", padx=(10, 0))

        elif dados_dash["pode_recontar"]:
            PillButton(footer, text="Reconferência", variant="outline", icon=load_icon("refresh", 16), height=34,
                       command=self._acao_estornar_conferencia).pack(side="right", padx=(10, 0))

        elif status_pr == StatusPR.AGUARDANDO_CONF:
            PillButton(footer, text="Desfazer Liberação", variant="outline", icon=load_icon("cancel", 16),
                       height=34,
                       command=self._acao_desfazer_liberacao).pack(side="right", padx=(10, 0))

        # --- LABEL DE STATUS FINAL ---
        if status_pr == StatusPR.CONCLUIDO:
            tk.Label(footer, text="Recebimento Concluído", font=("Segoe UI", 10, "bold"),
                     fg=Colors.SUCCESS, bg=Colors.BG_APP).pack(side="right")
        elif status_pr == "Cancelado":
            tk.Label(footer, text="Recebimento Cancelado", font=("Segoe UI", 10, "bold"),
                     fg=Colors.DANGER, bg=Colors.BG_APP).pack(side="right")

    def _calcular_dashboard(self):
        from datetime import datetime

        # 1. Busca dados brutos
        itens = recebimento_repo.list_itens_por_pr(self.pr_code)
        if not itens: return {}

        # Determina Status e Contexto
        status_pr = self.header_data.get("Status")
        cnpj_fornecedor = self.header_data.get("Cnpj") or ""

        # --- LÓGICA DE DETECÇÃO DE ESTADO ---
        conferente = self.header_data.get("Conferente")
        tem_conferente = (conferente is not None and conferente != "")
        tem_coleta = any(float(i.get('QtdColetada', 0)) > 0 for i in itens)
        eh_status_final = (status_pr in [StatusPR.CONCLUIDO, StatusPR.CANCELADO])
        exibir_comparativo = (tem_conferente or tem_coleta or eh_status_final)

        # Verifica se TEM OC
        tem_oc = False
        if itens and itens[0].get('_oc_existe_erp'):
            tem_oc = True

        # Variáveis de UI
        fisico_ui = []
        qualidade_ui = []
        financeiro_ui = []

        # Cores
        COR_AMARELO = Colors.WARNING
        COR_VERMELHO = Colors.DANGER
        COR_CINZA = Colors.TEXT_HINT
        COR_PRETO = Colors.TEXT_MAIN
        COR_VERDE = Colors.SUCCESS

        # --- SEPARAÇÃO DE ITENS POR VÍNCULO ---
        itens_com_vinculo = []
        itens_sem_vinculo = []

        for item in itens:
            cod_orig = item.get('CodOrig')
            tem_vinculo_tabela = False

            if cod_orig and cnpj_fornecedor:
                sku_alias = recebimento_repo.vinculo_service.consultar_vinculo(cnpj_fornecedor, cod_orig)
                if sku_alias:
                    tem_vinculo_tabela = True

            if tem_vinculo_tabela:
                itens_com_vinculo.append(item)
            else:
                itens_sem_vinculo.append(item)

        qtd_total_itens = len(itens)
        is_single_item = (qtd_total_itens == 1)

        # Identifica itens de bonificação
        itens_bonificacao = [i for i in itens if i.get('EhBonificacao') or float(i.get('Preco', 0)) == 0]
        qtd_bonif = len(itens_bonificacao)

        # Itens normais (que deveriam ter custo)
        itens_normais = [i for i in itens if i not in itens_bonificacao]
        qtd_normais = len(itens_normais)

        def fmt_moeda(val):
            return f"R$ {float(val):.2f}"

        def get_dias_minimos(sku):
            if not sku: return 0
            prod = products_repo.get_by_sku(sku)
            if prod:
                val_prod = prod.get('ValidadeMinimaDias')
                if val_prod is not None: return int(val_prod)
                familia_nome = prod.get('Familia')
                if familia_nome:
                    for f in families_repo.get_all():
                        if f.get('Nome') == familia_nome:
                            val_fam = f.get('ValidadeMinimaDias')
                            if val_fam is not None: return int(val_fam)
                            break
            return int(getattr(global_policies, 'validade_minima_padrao', 0))

        # Helper para comparar preços e gerar linha colorida
        def _gerar_linha_preco(item, prefixo_sku=False):
            sku = item.get('Sku') or "?"
            p_nota = float(item.get('Preco', 0))
            dados_oc = item.get('_dados_oc', {})
            item_na_oc = sku in dados_oc
            TOLERANCIA_VALOR = float(getattr(global_policies, "tolerancia_valor_recebimento", 0))
            TOLERANCIA_TIPO = getattr(global_policies, "tolerancia_tipo_recebimento", "Valor")

            if not item_na_oc:
                txt = "Não há ordem de compra para validar preços"
                if prefixo_sku: txt = f"{sku}: {txt}"
                return {"text": txt, "color": COR_AMARELO}

            p_oc = float(dados_oc[sku].get('Preco', 0))
            diff = abs(p_nota - p_oc)

            if TOLERANCIA_TIPO == "Porcentagem":
                limite_tol = p_oc * (TOLERANCIA_VALOR / 100.0)
            else:
                limite_tol = TOLERANCIA_VALOR

            if diff <= 0.001:
                txt = f"Preço unitário: {fmt_moeda(p_nota)} (Igual à OC)"
                cor = COR_PRETO
            elif diff <= limite_tol:
                txt = f"Preço unitário: {fmt_moeda(p_nota)} (Nota) vs {fmt_moeda(p_oc)} (OC)"
                cor = COR_VERDE
            else:
                txt = f"Preço unitário: {fmt_moeda(p_nota)} (Nota) vs {fmt_moeda(p_oc)} (OC)"
                cor = COR_VERMELHO

            if prefixo_sku: txt = f"{sku}: {txt}"
            return {"text": txt, "color": cor}

        # ==============================================================================
        # LÓGICA 1: TEM OC
        # ==============================================================================
        if tem_oc:
            if not exibir_comparativo:
                # MODO PLANEJAMENTO (SEM OC)
                for item in itens_com_vinculo:
                    sku = item.get('Sku') or "SKU (Vinculado)"
                    unid = item.get('Und', 'UN')
                    q_nota = float(item.get('Qtd', 0))

                    dados_oc = item.get('_dados_oc', {})
                    item_na_oc = sku in dados_oc
                    eh_bonif = item.get('EhBonificacao') or float(item.get('Preco', 0)) == 0

                    if item_na_oc and not eh_bonif:
                        q_oc_total = float(dados_oc[sku].get('Qtd', 0))
                        q_oc_rec = float(dados_oc[sku].get('QtdRecebida', 0))
                        q_oc = max(0.0, q_oc_total - q_oc_rec)

                        if is_single_item:
                            txt = f"Esperado: {q_nota:g} {unid} (Nota) | {q_oc:g} {unid} (OC)"
                        else:
                            txt = f"{sku}: Esperado: {q_nota:g} {unid} (Nota) | {q_oc:g} {unid} (OC)"

                        fisico_ui.append({"text": txt, "color": COR_PRETO})

                if itens_sem_vinculo:
                    qtd = len(itens_sem_vinculo)
                    lbl = "item" if qtd == 1 else "itens"
                    fisico_ui.append({"text": f"Há {qtd} {lbl} aguardando vínculo", "color": COR_AMARELO})

                count_nao_comprados = 0
                count_bonificacao = 0

                for item in itens_com_vinculo:
                    sku = item.get('Sku')
                    dados_oc = item.get('_dados_oc', {})
                    item_na_oc = sku in dados_oc if sku else False
                    eh_bonif = item.get('EhBonificacao') or float(item.get('Preco', 0)) == 0

                    if eh_bonif:
                        count_bonificacao += 1
                    elif not item_na_oc:
                        count_nao_comprados += 1

                if count_nao_comprados > 0:
                    lbl = "item" if count_nao_comprados == 1 else "itens"
                    comprado = "comprado" if count_nao_comprados == 1 else "comprados"
                    fisico_ui.append(
                        {"text": f"Há {count_nao_comprados} {lbl} não {comprado} na nota", "color": COR_AMARELO})

                if count_bonificacao > 0:
                    lbl = "item" if count_bonificacao == 1 else "itens"
                    fisico_ui.append({"text": f"Há {count_bonificacao} {lbl} de bonificação", "color": COR_PRETO})

                qualidade_ui.append({"text": "Aguardando conferência...", "color": COR_CINZA})

                if itens_sem_vinculo:
                    qtd = len(itens_sem_vinculo)
                    lbl = "item" if qtd == 1 else "itens"
                    financeiro_ui.append(
                        {"text": f"Há {qtd} {lbl} sem vínculo (impossível validar preços)", "color": COR_AMARELO})

                # Validação de preço no Planejamento
                for item in itens_com_vinculo:
                    financeiro_ui.append(_gerar_linha_preco(item, prefixo_sku=not is_single_item))

            else:
                # MODO COMPARATIVO (COM OC)
                for item in itens:

                    sku = item.get('Sku') or "Sem SKU"

                    unid = item.get('Und', 'UN')

                    if not item.get('Sku'): continue

                    q_conf = float(item.get('QtdColetada', 0))

                    q_nota = float(item.get('Qtd', 0))

                    dados_oc = item.get('_dados_oc', {})
                    info_oc = dados_oc.get(sku)

                    # Calcula o Saldo Pendente
                    q_oc_total = float(info_oc['Qtd']) if info_oc else 0.0
                    q_oc_rec = float(info_oc.get('QtdRecebida', 0.0)) if info_oc else 0.0
                    q_oc = max(0.0, q_oc_total - q_oc_rec)

                    # Usa a Nota Fiscal como base de cor para saber se a conferência está pendente ou passando
                    diff = q_conf - q_nota

                    # Formatação unificada solicitada

                    if is_single_item:

                        txt = f"Conferência: {q_conf:g} {unid} | Nota: {q_nota:g} {unid} | OC: {q_oc:g} {unid}"

                    else:

                        txt = f"{sku}: Conferência: {q_conf:g} {unid} | Nota: {q_nota:g} {unid} | OC: {q_oc:g} {unid}"

                    # Atribuição de Cores baseada na diferença

                    if diff < -0.001:

                        fisico_ui.append({"text": txt, "color": COR_VERMELHO})

                    elif diff > 0.001:

                        fisico_ui.append({"text": txt, "color": COR_AMARELO})

                    else:

                        # Só fica verde se já tiver conferido tudo

                        if q_conf > 0 or eh_status_final:
                            fisico_ui.append({"text": txt, "color": COR_VERDE})

                hoje = datetime.now()
                for item in itens:
                    sku = item.get('Sku') or "Sem SKU"
                    desc_visual = item.get("DivergenciaVisual")
                    val_str = item.get('Val')
                    dados_qual = item.get('dados_qualidade', {}) or {}
                    dias_minimos_item = get_dias_minimos(item.get('Sku'))

                    status_item = item.get("Status")

                    if desc_visual and status_item == StatusPR.EM_ANALISE:
                        # [NOVA FORMATAÇÃO SOLICITADA]
                        if is_single_item:
                            txt = f"Obs. visual: {desc_visual}"
                        else:
                            txt = f"{sku} - Obs. visual: {desc_visual}"

                        fisico_ui.append({"text": txt, "color": COR_PRETO})

                    if val_str and len(val_str) == 10:
                        try:
                            dt_val = datetime.strptime(val_str, "%d/%m/%Y")
                            dias_venc = (dt_val - hoje).days
                            if dias_venc < 0:
                                txt = "O produto está vencido" if is_single_item else f"{sku}: produto vencido"
                                qualidade_ui.append({"text": txt, "color": COR_VERMELHO})
                            elif dias_minimos_item > 0 and dias_venc < dias_minimos_item:
                                txt = f"Produto vence em {dias_venc} dias, abaixo do mínimo aceitável ({dias_minimos_item} dias)"
                                if not is_single_item: txt = f"{sku}: {txt}"
                                qualidade_ui.append({"text": txt, "color": COR_AMARELO})
                        except:
                            pass

                    if dados_qual.get('material_integro') == 'Não':
                        txt = "produto avariado" if is_single_item else f"{sku}: produto avariado"
                        qualidade_ui.append({"text": txt, "color": COR_VERMELHO})
                    if dados_qual.get('embalagem_integra') == 'Não':
                        txt = "Embalagem danificada" if is_single_item else f"{sku}: embalagem danificada"
                        qualidade_ui.append({"text": txt, "color": COR_VERMELHO})
                    if dados_qual.get('certificado') == 'Não' or item.get('CertQual') == 'Não':
                        txt = "Sem certificado de qualidade" if is_single_item else f"{sku}: sem certificado de qualidade"
                        qualidade_ui.append({"text": txt, "color": COR_AMARELO})

                if itens_sem_vinculo:
                    qtd = len(itens_sem_vinculo)
                    lbl = "item" if qtd == 1 else "itens"
                    financeiro_ui.append(
                        {"text": f"Há {qtd} {lbl} sem vínculo (impossível validar preços)", "color": COR_AMARELO})

                # Validação de preço no Comparativo
                for item in itens_com_vinculo:
                    financeiro_ui.append(_gerar_linha_preco(item, prefixo_sku=not is_single_item))

        # ==============================================================================
        # LÓGICA 2: NÃO TEM OC
        # ==============================================================================
        else:
            # 1. Físico
            # Itens Normais
            if qtd_normais > 0:
                lbl = "item" if qtd_normais == 1 else "itens"
                comprado = "comprado" if qtd_normais == 1 else "comprados"
                fisico_ui.append({"text": f"Há {qtd_normais} {lbl} não {comprado}", "color": COR_AMARELO})

            # Itens de Bonificação
            if qtd_bonif > 0:
                lbl = "item" if qtd_bonif == 1 else "itens"
                fisico_ui.append({"text": f"Há {qtd_bonif} {lbl} de bonificação", "color": COR_PRETO})

            # Itens sem vínculo (aviso geral)
            if itens_sem_vinculo:
                qtd = len(itens_sem_vinculo)
                lbl = "item" if qtd == 1 else "itens"
                fisico_ui.append({"text": f"Há {qtd} {lbl} aguardando vínculo", "color": COR_AMARELO})

            # 2. Qualidade
            qualidade_ui.append({"text": "Aguardando decisão...", "color": COR_CINZA})

            # 3. Financeiro
            if qtd_normais > 0:
                financeiro_ui.append({"text": "Impossível validar preços (sem OC)", "color": COR_AMARELO})

            if qtd_bonif > 0:
                financeiro_ui.append({"text": "Bonificação identificada", "color": COR_VERDE})

        if not qualidade_ui:
            qualidade_ui.append({"text": "Nenhum problema de qualidade identificado", "color": COR_VERDE})

        # --- VEREDITO FINAL ---
        has_issue_fisico = any(x['color'] in [COR_VERMELHO, COR_AMARELO] for x in fisico_ui)
        has_issue_qual = any(x['color'] in [COR_VERMELHO, COR_AMARELO] for x in qualidade_ui)
        has_issue_fin = any(x['color'] in [COR_VERMELHO, COR_AMARELO] for x in financeiro_ui)

        # Identifica se a tolerância foi utilizada (Item Verde)
        usou_tolerancia = any(x['color'] == COR_VERDE for x in financeiro_ui)

        v_nivel = "success"
        v_titulo = "TUDO CERTO!"
        v_msg = "Valores conferem."

        if status_pr == StatusPR.CANCELADO:
            v_nivel = "critical"
            v_titulo = "RECEBIMENTO CANCELADO"
            v_msg = "Processo abortado."

        elif status_pr == StatusPR.CONCLUIDO:
            v_titulo = "RECEBIMENTO CONCLUÍDO"
            v_msg = "Conferência finalizada. As quantidades batem com a nota fiscal."

        elif has_issue_fisico or has_issue_qual or has_issue_fin:
            v_nivel = "warning"
            v_titulo = "ATENÇÃO NECESSÁRIA"

            problemas = []
            if has_issue_fisico: problemas.append("Físico")
            if has_issue_qual: problemas.append("Qualidade")
            if has_issue_fin: problemas.append("Financeiro")

            if len(problemas) > 1:
                ultimo = problemas.pop()
                texto_problemas = ", ".join(problemas) + " e " + ultimo
            else:
                texto_problemas = problemas[0] if problemas else "Geral"

            v_msg = f"Verifique as pendências em: {texto_problemas}."

        elif tem_coleta:
            # Se já houve contagem e não há divergências pendentes (has_issue é falso)
            v_titulo = "CONFERÊNCIA OK"
            v_msg = "As quantidades batem com a nota fiscal."

        elif usou_tolerancia:
            # Caso não tenha iniciado a conferência, mostra o aviso financeiro
            v_msg = "Preços dentro da tolerância."

        elif status_pr == StatusPR.EM_CONFERENCIA:
            v_nivel = "info"
            v_titulo = "EM ANDAMENTO"
            v_msg = "Conferência em progresso."

        historico = []
        if self.header_data.get("DataChegada"):
            historico.append({"hora": self.header_data["DataChegada"].split(" ")[-1], "desc": "Início"})

        pode_recontar = ((tem_coleta or status_pr == StatusPR.EM_CONFERENCIA) and status_pr not in [StatusPR.CONCLUIDO, StatusPR.CANCELADO])

        return {
            "veredito_nivel": v_nivel,
            "veredito_titulo": v_titulo,
            "veredito_msg": v_msg,
            "fisico_items": fisico_ui,
            "qualidade_items": qualidade_ui,
            "financeiro_items": financeiro_ui,
            "historico": historico,
            "pode_recontar": pode_recontar
        }

    def _acao_aceitar_parcial(self):
        # 1. Busca dados ATUALIZADOS para checar o cabeçalho
        header = recebimento_repo.get_by_pr(self.pr_code)
        data_fim = header.get("DataFim")

        # VALIDAÇÃO CRÍTICA: Só permite "Parcial" se a conferência tiver DataFim preenchida.
        conferencia_finalizada = (data_fim and str(data_fim).strip() != "-" and str(data_fim).strip() != "")

        itens = recebimento_repo.list_itens_por_pr(self.pr_code)

        # Identifica divergências (Pendentes) comparando Qtd Nota vs Qtd Coletada
        divergentes = []
        for i in itens:
            q_nota = float(i.get('Qtd', 0))
            q_real = float(i.get('QtdColetada', 0))
            if abs(q_nota - q_real) > 0.001:
                divergentes.append(i)

        msg = "O Aceite Parcial concluirá o recebimento validando apenas as quantidades contadas.\n" \
              "O saldo restante (não contado) será cancelado.\n"

        if not conferencia_finalizada:
            msg += "\n⚠️ AVISO: Conferência não finalizada."

        if divergentes:
            msg += f"\n\nItens com divergência de quantidade: {len(divergentes)}"

        if not self.ask_yes_no("Confirmar Aceite Parcial", msg):
            return

        # Executa a conclusão. O repo vai alterar o status para CONCLUIDO.
        # Assumimos que o backend processa o estoque com base na QtdColetada.
        sucesso, msg_retorno = recebimento_repo.executar_transicao(
            self.pr_code,
            "concluir_recebimento",
            "Fiscal",
            obs="Conclusão Parcial (Saldo validado, divergências canceladas)."
        )

        if sucesso:
            self.alert("Sucesso", "Recebimento Parcial Concluído!")
            if self.on_close_callback: self.on_close_callback()
            self.close()
        else:
            self.alert("Erro", msg_retorno)

    def _acao_recusar_avariados(self):
        # Similar ao parcial, mas com log específico de avaria
        header = recebimento_repo.get_by_pr(self.pr_code)
        data_fim = header.get("DataFim")
        conferencia_finalizada = (data_fim and str(data_fim).strip() != "-" and str(data_fim).strip() != "")

        msg = "Esta opção rejeitará o saldo pendente alegando AVARIA/QUALIDADE.\n"

        if not conferencia_finalizada:
            msg += "\n⚠️ AVISO: DataFim não preenchida. Verifique se a conferência terminou."

        if not self.ask_yes_no("Confirmar Recusa por Avaria", msg):
            return

        sucesso, msg_retorno = recebimento_repo.executar_transicao(
            self.pr_code,
            "concluir_recebimento",
            "Fiscal",
            obs="Conclusão Parcial (Itens recusados por AVARIA/QUALIDADE)."
        )

        if sucesso:
            self.alert("Sucesso", "Recebimento Concluído (Com recusa por avaria).")
            if self.on_close_callback: self.on_close_callback()
            self.close()
        else:
            self.alert("Erro", msg_retorno)

    def _acao_conclusao_forcada(self, label_acao):
        # Método para tratar o clique no botão "Concluir" ou "Aceitar Divergência"
        obs = ""
        if "Divergência" in label_acao:
            # Pede justificativa simples
            # (Aqui poderia abrir um modal, mas vamos usar um prompt simples ou assumir "Aceite Fiscal")
            if not self.ask_yes_no("Confirmar Aceite",
                                   "Existem divergências. Ao concluir, você aceita as quantidades contadas como oficiais.\n\nDeseja prosseguir?"):
                return
            obs = "Divergência aceita via Dashboard Fiscal."

        # Executa transição para concluído
        sucesso, msg = recebimento_repo.executar_transicao(self.pr_code, "concluir_recebimento", "Fiscal")

        if sucesso:
            if obs:
                recebimento_repo.update_pr_status(self.pr_code, StatusPR.CONCLUIDO, "Fiscal", obs=obs)

            self.alert("Sucesso", "Recebimento Concluído!")
            if self.on_close_callback: self.on_close_callback()
            self.close()
        else:
            self.alert("Erro", msg)

    # --- ABA 3: EDITAR ---
    def _build_editar(self):
        frm = tk.Frame(self.tab_frame, bg=Colors.BG_APP)
        frm.pack(fill="both", expand=True, padx=50)  # Margem centralizada

        tk.Label(frm, text="Dados do Recebimento", font=("Segoe UI", 12, "bold"), bg=Colors.BG_APP).pack(anchor="w",
                                                                                                         pady=(20, 10))

        ttk.Label(frm, text="Ordem de Compra (OC):", style="TLabel").pack(anchor="w")
        self.ent_oc = TextField(frm)
        self.ent_oc.insert(0, self.header_data.get("Oc", ""))
        self.ent_oc.pack(fill="x", pady=(0, 15))

        tk.Label(frm, text="Destino", font=("Segoe UI", 12, "bold"), bg=Colors.BG_APP).pack(anchor="w", pady=(20, 10))

        ttk.Label(frm, text="Aplicar Destino Padrão (Todos os Itens):", style="TLabel").pack(anchor="w")

        lista_locais = [r["Nome"] for r in locations_repo.get_all() if r.get("Ativo", True)]
        if not lista_locais: lista_locais = ["Sem locais cadastrados"]

        self.cmb_dest = PillCombobox(frm, values=lista_locais)
        self.cmb_dest.pack(fill="x", pady=(0, 5))

        local_padrao = locations_repo.get_padrao()
        if local_padrao and local_padrao in lista_locais:
            self.cmb_dest.set(local_padrao)

        ttk.Label(frm, text="Isso sobrescreverá o destino de todos os itens deste PR.", font=("Segoe UI", 8),
                  foreground="#6B7280").pack(anchor="w")

        btn_box = tk.Frame(frm, bg=Colors.BG_APP)
        btn_box.pack(fill="x", pady=30)

        PillButton(btn_box, text="Salvar", variant="success", command=self._acao_salvar_edicao).pack(
            side="right")

    # --- LÓGICA DAS AÇÕES ---

    def _acao_desfazer_liberacao(self):
        # A validação de progresso já pode ser feita pelo workflow (Guard),
        # mas manter aqui como feedback visual rápido é ok.

        if not self.ask_yes_no("Confirmar Retorno",
                               "Deseja cancelar a conferência?"):
            return

        sucesso, msg = recebimento_repo.executar_transicao(self.pr_code, "desfazer_liberacao")

        if sucesso:
            self.alert("Sucesso", msg)
            if self.on_close_callback: self.on_close_callback()
            self.header_data = recebimento_repo.get_by_pr(self.pr_code)
            if self.current_tab.get() == "acoes":
                self._build_acoes()
        else:
            self.alert("Erro", msg, type="warning")

    def _acao_estornar_conferencia(self):
        if not self.ask_yes_no("Reconferência",
                               "Isso apagará TODAS as contagens realizadas até agora para este recebimento.\n\nDeseja realmente continuar?"):
            return

        sucesso, msg = recebimento_repo.executar_transicao(
            self.pr_code,
            "estornar_conferencia",
            usuario="PainelFiscal",
            obs="Reset solicitado via Painel"
        )

        if sucesso:
            self.alert("Conferência Zerada", "Todos os itens foram resetados com sucesso")

            # Notifica a janela pai
            if self.on_close_callback: self.on_close_callback()

            # 1. Recarrega dados do cabeçalho (Status mudou de EM_CONFERENCIA -> AGUARDANDO_CONF)
            self.header_data = recebimento_repo.get_by_pr(self.pr_code)

            if self.current_tab.get() == "acoes":
                self._build_acoes()
            elif self.current_tab.get() == "conferencia":
                self._switch_tab("conferencia")
        else:
            self.alert("Erro ao Estornar", f"Não foi possível resetar a conferência.\nMotivo: {msg}")

    def _acao_cancelar_pr(self):
        try:
            lpns_ativos = [l for l in lpn_repo.get_all() if
                           l.get("PrRef") == self.pr_code and l.get("Status") != "Cancelado"]
        except:
            lpns_ativos = []

        msg_extra = f"\n\nATENÇÃO: {len(lpns_ativos)} Paletes serão estornados!" if lpns_ativos else ""

        if not self.ask_yes_no("Cancelar Recebimento", f"Deseja CANCELAR definitivamente o {self.pr_code}?{msg_extra}"):
            return

        sucesso, msg = recebimento_repo.executar_transicao(self.pr_code, "cancelar_recebimento")

        if sucesso:
            self.alert("Cancelado", msg)
            if self.on_close_callback: self.on_close_callback()
            self.close()
        else:
            self.alert("Erro", msg, type="warning")

    def _acao_liberar_conferencia(self):
        wf = RecebimentoWorkflow(self.header_data)
        contexto = wf.get_contexto_ui()
        msg_bloqueio = contexto.get("mensagem_bloqueio")

        def _executar():
            sucesso, msg = recebimento_repo.executar_transicao(self.pr_code, "liberar_conferencia")
            if sucesso:
                self.alert("Sucesso", f"O Recebimento foi liberado para conferência", type="info")

                # Atualiza dados locais e refresh da tela
                self.header_data = recebimento_repo.get_by_pr(self.pr_code)
                if self.on_close_callback: self.on_close_callback()
                self._build_acoes()
            else:
                self.alert("Ação Negada", msg, type="warning")

        if msg_bloqueio:
            self.ask_yes_no(
                "Confirmar Liberação com Pendência",
                f"O recebimento possui pendências.\nMotivo: {msg_bloqueio}\n\nDeseja forçar a liberação?",
                on_yes=_executar
            )
        else:
            _executar()

    def _acao_salvar_edicao(self):
        nova_oc = self.ent_oc.get().strip()
        novo_destino = self.cmb_dest.get().strip()

        aplicar_dest = False
        if novo_destino and novo_destino != "Sem locais cadastrados":
            aplicar_dest = True

        # CORREÇÃO: Captura o retorno (status, motivo)
        resultado = recebimento_repo.update_pr_dados(
            self.pr_code,
            nova_oc=nova_oc,
            novo_destino=novo_destino if aplicar_dest else None,
            aplicar_a_todos=aplicar_dest
        )

        # Se houve validação fiscal (retornou tupla), tratamos a mensagem
        if isinstance(resultado, tuple):
            novo_status, motivo = resultado

            if "Bloqueado" in novo_status or "Vinculação" in novo_status:
                self.alert("Atenção - Bloqueio Fiscal",
                           f"Os dados foram salvos, mas o recebimento foi bloqueado.\n\nStatus: {novo_status}\nMotivo: {motivo}",
                           type="warning")
            else:
                self.alert("Sucesso", f"Dados atualizados e validados!\nStatus: {novo_status}")
        else:
            self.alert("Salvo", "Dados atualizados com sucesso!")

        if self.on_close_callback: self.on_close_callback()


class RecebimentoPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(
            os.path.abspath(__file__))
        self.config_file = os.path.join(base_path, "dados", "config_xml_path.json")
        self.pasta_monitorada = self._carregar_config_pasta()

        # Configuração do Grid da Página
        self.columnconfigure(0, weight=1)
        # Removido o peso da linha 0 antiga (toolbar separada)
        self.rowconfigure(0, weight=11, uniform="tabelas")  # Tabela Top (agora inclui a toolbar)
        self.rowconfigure(1, weight=0)  # Separador
        self.rowconfigure(2, weight=13, uniform="tabelas")  # Tabela Bottom

        # --- TABELA SUPERIOR (PRs) ---
        cols_top = [
                       {"id": "PrCode", "title": "PR", "type": "text", "width": 50, "anchor": "center"},
                       {"id": "Nfe", "title": "NFe", "type": "text", "width": 80, "anchor": "center"},
                       {"id": "Oc", "title": "OC", "type": "text", "width": 80, "anchor": "center"},
                       {"id": "Fornecedor", "title": "Fornecedor", "type": "text", "width": 250, "anchor": "w"},
                       {"id": "Conferente", "title": "Conferente", "type": "text", "width": 160, "anchor": "w"},
                       {"id": "DataChegada", "title": "Início", "type": "text", "width": 110,
                        "anchor": "center"},
                       {"id": "DataFim", "title": "Conclusão", "type": "text", "width": 110, "anchor": "center"},
                       {"id": "Status", "title": "Status", "type": "text", "width": 60, "anchor": "center"},
                   ] + AuditManager.get_columns()

        filter_defs = [
            {"key": "PrCode", "label": "PR"},
            {"key": "Nfe", "label": "NFe"},
            {"key": "Oc", "label": "OC"},
            {"key": "DataChegada", "label": "Entrada Física (Contém)"},
            {"key": "Conferente", "label": "Conferente"},
            {"key": "Fornecedor", "label": "Fornecedor"},
            {"key": "sku_item", "label": "Contém SKU (nos itens)"},
            {"key": "Status", "label": "Status"},
        ]

        # Instancia a tabela primeiro (para termos acesso ao .left_actions e .right_actions)
        self.table_top = StandardTable(
            self,
            columns=cols_top,
            fetch_fn=self._fetch_top,
            page_size=10,
            filter_columns=filter_defs,
            autohide_pagination=False
        )
        # Grid na row=0 (antiga posição da toolbar + tabela)
        self.table_top.grid(row=0, column=0, sticky="nsew", pady=(5, 5))

        # --- BOTÕES (Injetados na Toolbar da StandardTable) ---

        # Área ESQUERDA (Ações Principais)
        container_left = self.table_top.left_actions

        self.btn_gerenciar = PillButton(container_left, text="Painel", variant="outline",
                                        icon=load_icon("panel", 16), command=self._abrir_painel_controle)
        self.btn_gerenciar.pack(side="left", padx=(0, 10))

        self.btn_vincular = PillButton(container_left, text="Vincular SKU", variant="outline",
                                       icon=load_icon("link", 16), command=self._abrir_modal_vinculo)
        self.btn_vincular.pack(side="left", padx=(0, 10))

        self.btn_destino = PillButton(container_left, text="Alt. Destino", variant="outline",
                                      icon=load_icon("edit", 16), command=self._alterar_destino_item)
        self.btn_destino.pack(side="left", padx=(0, 10))

        # Área DIREITA (Configurações / Extras)
        # Área DIREITA
        # Movemos a configuração para o menu "..." para economizar espaço
        self.table_top.add_overflow_menu_action("Configurar Pasta XML...", self._configurar_pasta)

        # Estado Inicial dos Botões
        for btn in [self.btn_gerenciar, self.btn_vincular]:
            btn.state(["disabled"])

        # --- SEPARADOR ---
        sep = ttk.Separator(self, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew", padx=16, pady=5)

        # --- TABELA INFERIOR (Itens) ---
        cols_bottom = [
                          {"id": "Sku", "title": "SKU", "type": "text", "width": 110, "anchor": "w"},
                          {"id": "Descricao", "title": "Descrição", "type": "text", "width": 440, "anchor": "w"},
                          {"id": "Qtd", "title": "Qtd", "type": "number", "width": 70, "anchor": "center"},
                          {"id": "Und", "title": "Und", "type": "text", "width": 50, "anchor": "center"},
                          {"id": "Lote", "title": "Lote", "type": "text", "width": 150, "anchor": "w"},
                          {"id": "Fab", "title": "Fab", "type": "text", "width": 90, "anchor": "center"},
                          {"id": "Val", "title": "Val", "type": "text", "width": 90, "anchor": "center"},
                          {"id": "Vencimento", "title": "Vencimento", "type": "text", "width": 100, "anchor": "center"},
                          {"id": "IntEmb", "title": "Int. Embalagem", "type": "text", "width": 115,
                           "anchor": "center"},
                          {"id": "IntMat", "title": "Int. Material", "type": "text", "width": 100, "anchor": "center"},
                          {"id": "Identificacao", "title": "Identificação", "type": "text", "width": 110,
                           "anchor": "center"},
                          {"id": "CertQual", "title": "Certif. Qualidade", "type": "text", "width": 120,
                           "anchor": "center"},
                          {"id": "Destino", "title": "Destino", "type": "text", "width": 120, "anchor": "center"},
                          {"id": "Status", "title": "Status", "type": "text", "width": 150, "anchor": "center"},
                      ] + AuditManager.get_columns()

        self.table_bottom = StandardTable(self, columns=cols_bottom, fetch_fn=self._fetch_bottom, page_size=12,
                                          autohide_pagination=False)
        self.table_bottom.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        self.table_bottom.bind("<<TableDoubleClick>>", lambda e: self._abrir_painel_controle())

        # Configurações específicas da tabela de baixo
        if hasattr(self.table_bottom, 'btn_refresh'):
            self.table_bottom.btn_refresh.grid_remove()

        self.table_bottom.btn_filters.grid_remove()
        self.table_bottom.btn_clear.grid_remove()

        self.table_top.bind("<<TableSelect>>", self._on_top_select)
        self.table_bottom.bind("<<TableSelect>>", self._on_bottom_select)
        self._edit_context = "top"

        if recebimento_repo.event_bus:
            recebimento_repo.event_bus.subscribe("pr_atualizado", self._on_pr_updated)
            recebimento_repo.event_bus.subscribe("recebimento_concluido", self._on_pr_updated)

    def _on_pr_updated(self, data):
        # 1. Guarda quem estava selecionado antes de recarregar (para comparação)
        sel_anterior = self.table_top.get_selected()

        # 2. Recarrega a tabela superior (Cabeçalhos)
        self.table_top.load_page(self.table_top.page)

        # 3. Se o PR atualizado for o mesmo que estava sendo visualizado, recarrega os itens
        if sel_anterior:
            # Limpa prefixos para garantir comparação (ex: "PR-2025" vira "2025")
            pr_sel = str(sel_anterior.get("pr")).replace("PR-", "")
            pr_evt = str(data.get("pr")).replace("PR-", "")

            if pr_sel == pr_evt:
                # Recarrega a tabela inferior (Itens)
                self.table_bottom.load_page(self.table_bottom.page)

    def _fetch_top(self, page: int, page_size: int, filters: list):
        # 1. Busca dados
        total_raw, rows_raw = recebimento_repo.list(1, 10000, [])

        for r in rows_raw:
            if "PrCode" in r and "Pr" not in r: r["Pr"] = r["PrCode"]

        filtered_rows = []
        pr_items_cache = {}

        # 2. Filtragem
        for r in rows_raw:
            match_all = True
            for f in filters:
                ftype = f.get("type")
                val = str(f.get("value", "")).lower().strip()
                if not val: continue

                if ftype == "quick":
                    in_header = (
                            val in str(r.get("Fornecedor", "")).lower() or
                            val in str(r.get("Nfe", "")).lower() or
                            val in str(r.get("Oc", "")).lower() or
                            val in str(r.get("PrCode", "")).lower() or
                            val in str(r.get("Conferente", "")).lower()
                    )
                    in_items = False
                    if not in_header:
                        pr_code = r.get("PrCode")
                        if pr_code not in pr_items_cache:
                            pr_items_cache[pr_code] = recebimento_repo.list_itens_por_pr(pr_code)
                        for item in pr_items_cache[pr_code]:
                            desc_item = str(item.get("Descricao"))
                            if (val in str(item.get("Sku", "")).lower() or
                                    val in desc_item.lower() or
                                    val in str(item.get("Lote", "")).lower()):
                                in_items = True
                                break

                    if not (in_header or in_items):
                        match_all = False
                        break
                elif ftype == "advanced":
                    key = f.get("key")
                    if key == "sku_item":
                        pr_code = r.get("PrCode")
                        if pr_code not in pr_items_cache:
                            pr_items_cache[pr_code] = recebimento_repo.list_itens_por_pr(pr_code)
                        found_sku = False
                        for item in pr_items_cache[pr_code]:
                            if val in str(item.get("Sku", "")).lower():
                                found_sku = True;
                                break
                        if not found_sku: match_all = False
                    else:
                        if val not in str(r.get(key, "")).lower(): match_all = False

            if not match_all: continue
            filtered_rows.append(r)

        # 3. Processamento
        total = len(filtered_rows)
        start = (page - 1) * page_size
        end = start + page_size
        rows_page = filtered_rows[start:end]

        processed = []
        for r in rows_page:
            row_view = dict(r)
            row_view.update(AuditManager.process_row(r))

            row_view["data_chegada"] = row_view.get("DataChegada")
            row_view["data_fim"] = row_view.get("DataFim")

            if str(row_view.get("PrCode", "")).startswith("PR-"): row_view["PrCode"] = row_view["PrCode"].replace("PR-", "")

            # Tratamento OC (Vazio vira hífen)
            oc_val = str(row_view.get("Oc") or "").strip()
            if not oc_val or oc_val.lower() == "none":
                row_view["Oc"] = "-"
            else:
                if oc_val.startswith("OC-"): oc_val = oc_val.replace("OC-", "")
                row_view["Oc"] = oc_val

            status_real = row_view.get("Status")

            # --- CORREÇÃO DE CHAVE: Busca 'obsfiscal' minúsculo ---
            motivo_fiscal = (row_view.get("ObsFiscal"))

            row_view["Status"] = RecebimentoWorkflow.get_status_label(status_real)

            # Pegamos a cor do workflow
            cor_status = RecebimentoWorkflow.get_status_color(status_real)

            # IMPORTANTE: Só definimos "_text_color" se houver uma cor específica.
            # Se for None, NÃO criamos a chave, permitindo que a tabela use o Cinza Padrão do tema.
            if cor_status:
                row_view["_text_color"] = cor_status

            # Usamos a variável local 'cor_status' para decidir sobre o tooltip
            if cor_status == "#D97706":  # Se for cor de atenção (Laranja)
                row_view["_tooltip"] = motivo_fiscal
            else:
                row_view["_tooltip"] = None

            processed.append(row_view)

        return total, processed

    def _fetch_bottom(self, page: int, page_size: int, filters: list):
        # 1. Pega a seleção da tabela de cima
        selected = self.table_top.get_selected()
        if not selected: return 0, []

        pr_visual = selected.get("PrCode")
        pr_real = f"PR-{pr_visual}" if not str(pr_visual).startswith("PR-") else pr_visual

        # 2. Busca os itens (JÁ COM STATUS E MOTIVOS CALCULADOS PELO REPO)
        itens_raw = recebimento_repo.list_itens_por_pr(pr_real)

        # 3. Filtro Local (Busca rápida na tabela de baixo)
        search_term = ""
        for f in filters:
            if f.get("type") == "quick":
                search_term = str(f.get("value", "")).lower().strip()
                break

        filtered_items = []
        if search_term:
            for item in itens_raw:
                desc_txt = str(item.get("Descricao") or "")
                if (search_term in str(item.get("Sku", "")).lower() or
                        search_term in desc_txt.lower() or
                        search_term in str(item.get("Lote", "")).lower()):
                    filtered_items.append(item)
        else:
            filtered_items = itens_raw

        # 4. Paginação
        total = len(filtered_items)
        start = (page - 1) * page_size
        end = start + page_size
        itens_page = filtered_items[start:end]

        processed = []

        for item in itens_page:
            row_view = dict(item)

            lotes = item.get("_LotesDetalhados")
            if lotes and isinstance(lotes, list) and len(lotes) > 0:
                row_view["Lote"] = ", ".join(str(l) for l in lotes)

            if str(row_view.get("PrCode", "")).startswith("PR-"):
                row_view["pr"] = row_view["PrCode"].replace("PR-", "")

            st_item = row_view.get("StatusCalculado") or row_view.get("Status")

            # Formata o status para exibir
            row_view["Status"] = RecebimentoWorkflow.get_status_label(st_item)

            cor_status = RecebimentoWorkflow.get_status_color(st_item)

            if cor_status:
                row_view["_text_color"] = cor_status

            # Tooltip baseado na variável local e chave TitleCase 'MotivoSistema'
            if cor_status == "#D97706":
                row_view["_tooltip"] = row_view.get("MotivoSistema")
            else:
                row_view["_tooltip"] = None

            processed.append(row_view)

        return total, processed

    def _carregar_config_pasta(self):
        # Define a raiz do projeto
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Aponta especificamente para a subpasta "Novos" dentro de "XMLs"
        caminho_xmls = os.path.join(base_path, "XMLs")

        # Garante que a pasta exista para evitar erros
        if not os.path.exists(caminho_xmls):
            try:
                os.makedirs(caminho_xmls)
            except:
                pass

        return caminho_xmls

    def _configurar_pasta(self):
        top = SaaSModal(self, title="Configuração de Integração", width=500, height=270)

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # --- APENAS XML (NFe) ---
        ttk.Label(frm, text="Pasta de Monitoramento XML (NFe):", style="TLabel", font=("Segoe UI", 9, "bold")).pack(
            anchor="w")
        txt_xml = TextField(frm, height=34)
        txt_xml.insert(0, self.pasta_monitorada or "")
        txt_xml.pack(fill="x", pady=(5, 0))

        lbl_info_xml = ttk.Label(frm, text="O sistema varre esta pasta em busca de Notas Fiscais.",
                                 font=("Segoe UI", 8), foreground="#6B7280")
        lbl_info_xml.pack(anchor="w", pady=(2, 0))

        def _sel_xml():
            d = filedialog.askdirectory(parent=top, title="Selecione a pasta de XMLs")
            if d:
                txt_xml.delete(0, "end")
                txt_xml.insert(0, d)

        PillButton(frm, text="Selecionar...", command=_sel_xml, variant="outline", height=28).pack(anchor="e",
                                                                                                   pady=(5, 20))

        def _salvar_configs():
            p_xml = txt_xml.get().strip()

            if p_xml:
                self.pasta_monitorada = p_xml
                recebimento_repo.salvar_config_pasta(p_xml)

            top.close()
            self.alert("Sucesso", "Configuração salva!", type="info")
            self._executar_verificacao()

        PillButton(frm, text="Salvar", variant="success", command=_salvar_configs).pack(side="bottom",
                                                                                                      anchor="e")

    def _executar_verificacao(self):
        if self.pasta_monitorada and os.path.exists(self.pasta_monitorada):
            houve_mudanca = recebimento_repo.processar_xmls_da_pasta(self.pasta_monitorada)
            if houve_mudanca:
                self.table_top.load_page(1)

    def on_show(self, **kwargs):
        self._check_folder_loop()
        recebimento_repo.verificar_viculos_automaticos()
        self.table_top.load_page(1)
        self.table_bottom.load_page(1)
        self._check_folder_loop()

    def on_hide(self):
        if hasattr(self, "_folder_job"):
            self.after_cancel(self._folder_job)

    def _check_folder_loop(self):
        self._executar_verificacao()
        self._folder_job = self.after(5000, self._check_folder_loop)

    def _on_top_select(self, event):
        self._edit_context = "top"

        self.table_bottom.load_page(1)

        sel = self.table_top.get_selected()

        if not sel:
            self.btn_gerenciar.state(["disabled"])
            self.btn_vincular.state(["disabled"])
            self.btn_destino.state(["disabled"])
            return

        pr_visual = sel.get("PrCode")
        full_pr = f"PR-{pr_visual}" if not str(pr_visual).startswith("PR-") else pr_visual

        pr_data = recebimento_repo.get_by_pr(full_pr)

        if not pr_data:
            return

        wf = RecebimentoWorkflow(pr_data)

        contexto = wf.get_contexto_ui()

        if contexto.get('pode_gerenciar_painel'):
            self.btn_gerenciar.state(["!disabled"])
        else:
            self.btn_gerenciar.state(["disabled"])

        self.btn_vincular.state(["disabled"])
        self.btn_destino.state(["disabled"])

        msg_bloqueio = contexto.get('mensagem_bloqueio')
        if msg_bloqueio:
            pass

    def _on_bottom_select(self, event):
        self._edit_context = "bottom"

        # 1. Verifica se tem item selecionado
        item_sel = self.table_bottom.get_selected()

        if not item_sel:
            # Se não tem item, botões de ITEM ficam desabilitados
            self.btn_vincular.state(["disabled"])
            self.btn_destino.state(["disabled"])

            # Reverte foco para o topo se houver seleção lá (UI UX)
            if self.table_top.get_selected():
                self._edit_context = "top"
            return

        # 2. Busca dados frescos do PR (Pai) para checar permissões
        # O item selecionado tem a chave 'pr' (ex: "1023"), mas precisamos do objeto PR completo
        pr_code_visual = item_sel.get("PrCode")
        full_pr = f"PR-{pr_code_visual}" if not str(pr_code_visual).startswith("PR-") else str(pr_code_visual)

        # Buscamos o cabeçalho no banco para garantir que o status está atualizado
        pr_data = recebimento_repo.get_by_pr(full_pr)

        if not pr_data:
            # Fallback de segurança se o PR não for encontrado
            self.btn_vincular.state(["disabled"])
            self.btn_destino.state(["disabled"])
            return

        # 3. Instancia o Cérebro (Workflow)
        wf = RecebimentoWorkflow(pr_data)

        # Pede as permissões (Capabilities)
        contexto = wf.get_contexto_ui()

        # 4. Aplica as regras nos botões

        # Regra: VINCULAR
        # Só habilita se o Workflow disser que 'pode_vincular' (ex: Status Bloqueado ou Aguardando Vínculo)
        if contexto['pode_vincular']:
            self.btn_vincular.state(["!disabled"])
        else:
            self.btn_vincular.state(["disabled"])

        # Regra: ALTERAR DESTINO
        # Só habilita se o Workflow disser que 'pode_editar_destino' (ex: Não está Concluído nem Cancelado)
        if contexto['pode_editar_destino']:
            self.btn_destino.state(["!disabled"])
        else:
            self.btn_destino.state(["disabled"])

        self.btn_gerenciar.state(["!disabled"])

    def _abrir_modal_vinculo(self):
        item_sel = self.table_bottom.get_selected()
        if not item_sel: return

        pr_code = item_sel.get("PrCode")
        full_pr = f"PR-{pr_code}" if not str(pr_code).startswith("PR-") else pr_code
        header = recebimento_repo.get_by_pr(full_pr)

        if not header: return

        cnpj = header.get("Cnpj") or ""
        fornecedor = header.get("Fornecedor") or ""

        cod_xml_real = item_sel.get("CodOrig") or ""

        desc_item = item_sel.get("Descricao")
        qtd_xml = float(item_sel.get("Qtd", 0))
        preco_xml = float(item_sel.get("Preco", 0))

        sugestao_sku = None
        motivo_sugestao = ""
        oc_encontrada = ""

        oc_numero_raw = header.get("Oc", "")
        if oc_numero_raw:
            num_oc = oc_numero_raw.split(",")[0].strip()
            dados_oc = oc_repo.get_oc(num_oc)
            if dados_oc and "itens" in dados_oc:
                itens_oc = dados_oc["itens"]
                oc_encontrada = num_oc
                candidatos_perfeitos = []
                candidatos_qtd = []
                TOLERANCIA = getattr(global_policies, "tolerancia_valor_recebimento", 0.00)

                for sku_oc, dados_item_oc in itens_oc.items():
                    qtd_oc = float(dados_item_oc.get("Qtd", 0))
                    preco_oc = float(dados_item_oc.get("Preco", 0))
                    match_qtd = (qtd_xml == qtd_oc)
                    match_preco = abs(preco_xml - preco_oc) <= TOLERANCIA

                    if match_qtd and match_preco:
                        candidatos_perfeitos.append(sku_oc)
                    if match_qtd:
                        candidatos_qtd.append(sku_oc)

                if len(candidatos_perfeitos) == 1:
                    sugestao_sku = candidatos_perfeitos[0]
                    motivo_sugestao = f"Sugestão: item da OC {num_oc} compatível (Qtd e Preço)."
                elif len(candidatos_perfeitos) > 1:
                    motivo_sugestao = "AMBIGUIDADE"
                    sugestao_sku = None
                elif len(itens_oc) == 1 and len(candidatos_qtd) == 1:
                    sugestao_sku = candidatos_qtd[0]
                    motivo_sugestao = f"Sugestão: item da OC com quantidade compatível."

        top = SaaSModal(self, title="Vincular Produto", width=500, height=500)
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Fornecedor:", style="TLabel").pack(anchor="w")
        txt_forn = TextField(frm, height=34)
        txt_forn.insert(0, f"{fornecedor} ({cnpj})")
        txt_forn._entry.config(state="disabled")
        txt_forn.pack(fill="x", pady=(0, 10))

        ttk.Label(frm, text=f"Produto na Nota (Qtd: {qtd_xml} | Unt: R$ {preco_xml:.2f}):", style="TLabel").pack(
            anchor="w")
        txt_orig = TextField(frm, height=34)
        display_orig = f"{cod_xml_real} - {desc_item}" if cod_xml_real else f"{desc_item}"
        txt_orig.insert(0, display_orig)
        txt_orig._entry.config(state="disabled")
        txt_orig.pack(fill="x", pady=(0, 15))

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=10)
        ttk.Label(frm, text="Equivale ao SKU Interno:", style="TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        all_skus = [f"{p['Sku']} - {p['Descricao']}" for p in products_repo.get_all()]
        cmb_sku = PillCombobox(frm, values=all_skus, placeholder="Busque o SKU...", height=34)
        cmb_sku.pack(fill="x", pady=(0, 5))

        if sugestao_sku:
            match_text = next((s for s in all_skus if s.startswith(f"{sugestao_sku} -")), None)
            if match_text:
                cmb_sku.set(match_text)
                lbl_sug = tk.Label(frm, text=f" {motivo_sugestao}", image=load_icon("check", 16, Colors.SUCCESS), compound="left",
                                   fg=Colors.SUCCESS, bg=Colors.BG_APP, font=("Segoe UI", 9, "italic"), wraplength=440,
                                   justify="left")
                lbl_sug.pack(anchor="w", pady=(0, 10))
            else:
                msg_alerta = (
                    f" Encontramos o SKU '{sugestao_sku}' na OC {oc_encontrada}, mas ele não está cadastrado.")
                lbl_sug = tk.Label(frm, text=msg_alerta, image=load_icon("alert", 16), compound="left",
                                   fg="#D97706", bg=Colors.BG_APP, font=("Segoe UI", 9), justify="left", wraplength=440)
                lbl_sug.pack(anchor="w", pady=(0, 10))
        elif motivo_sugestao == "AMBIGUIDADE":
            msg_amb = f" Atenção: Múltiplos itens na OC com mesma Qtd/Preço. Verifique a descrição."
            lbl_sug = tk.Label(frm, text=msg_amb, image=load_icon("alert", 16), compound="left",
                               fg="#D97706", bg=Colors.BG_APP, font=("Segoe UI", 9), justify="left", wraplength=440)
            lbl_sug.pack(anchor="w", pady=(0, 10))
        else:
            tk.Label(frm, text="", bg=Colors.BG_APP).pack(pady=(0, 10))

        def _confirmar_vinculo():
            val = cmb_sku.get()
            if not val:
                top.alert("Atenção", "Selecione o SKU interno para vincular.")
                return

            parts = val.split(" - ", 1)
            sku_interno = parts[0].strip()
            sucesso, msg_servico = recebimento_repo.vinculo_service.vincular(
                item_sel['Id'],
                sku_interno,
                usuario="Admin"
            )

            if sucesso:
                header_atual = recebimento_repo.get_by_pr(full_pr)
                novo_status = header_atual.get('Status')
                msg_motivo = header_atual.get('ObsFiscal') or ""

                self.table_top.load_page(self.table_top.page)
                self.table_bottom.load_page(self.table_bottom.page)

                tipo_msg = "warning" if "Bloqueado" in novo_status or "Vinculação" in novo_status else "info"

                top.alert("Processado",
                          f"Vínculo salvo com sucesso!\n\nStatus atual do pedido: {novo_status}\n({msg_motivo})",
                          type=tipo_msg)
                top.close()
            else:
                top.alert("Erro", f"Falha ao vincular: {msg_servico}")

        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(fill="x", pady=10)
        PillButton(btn_box, text="Salvar", variant="success", command=_confirmar_vinculo).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _alterar_destino_item(self):
        item_sel = self.table_bottom.get_selected()
        if not item_sel: return

        # Cria o modal
        top = SaaSModal(self, title="Alterar Destino do Item", width=400, height=280)

        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # Info do Item
        txt_prod = f"{item_sel.get('Sku')} - {item_sel.get('Descricao')}"
        tk.Label(frm, text=txt_prod, font=("Segoe UI", 9, "bold"), bg=Colors.BG_APP, wraplength=350).pack(anchor="w",
                                                                                                          pady=(0, 15))

        # Campo de Seleção
        ttk.Label(frm, text="Novo Local de Destino:", style="TLabel").pack(anchor="w")

        # Carrega locais ativos
        locais = [l['Nome'] for l in locations_repo.get_all() if l.get('Ativo')]
        if not locais: locais = ["Geral"]

        cmb_locais = PillCombobox(frm, values=locais)
        cmb_locais.pack(fill="x", pady=(5, 0))

        # Pré-seleciona o atual se existir
        atual = item_sel.get('Destino')
        if atual and atual in locais:
            cmb_locais.set(atual)
        elif locais:
            cmb_locais.set(locais[0])

        def _salvar():
            novo = cmb_locais.get()
            if not novo:
                top.alert("Atenção", "Selecione um local.")
                return

            try:
                # Chama o método que criamos no Passo 1
                recebimento_repo.update_item_destino(item_sel['Id'], novo)

                # Atualiza a tabela
                self.table_bottom.load_page(self.table_bottom.page)
                top.close()
                
                self.alert("Sucesso", "Destino atualizado!", type="info")
            except Exception as e:
                top.alert("Erro", str(e))

        # Botões
        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(side="bottom", fill="x")

        PillButton(btn_box, text="Salvar", variant="success", command=_salvar).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=top.close).pack(side="right", padx=10)

    def _abrir_painel_controle(self):
        sel = self.table_top.get_selected()
        if not sel: return

        pr_visual = sel.get("PrCode")
        full_pr = f"PR-{pr_visual}" if not str(pr_visual).startswith("PR-") else pr_visual

        # Função de Callback para quando o modal fechar ou salvar
        def _ao_atualizar():
            self.table_top.load_page(self.table_top.page)
            self.table_bottom.load_page(self.table_bottom.page)

        RecebimentoControlPanel(self, full_pr, on_close_callback=_ao_atualizar)

    def _abrir_modal_analise_item(self, item_sel):
        # 1. Pega o TEXTO direto do item (Sem JSON)
        desc_visual = item_sel.get("DivergenciaVisual")
        status_item = item_sel.get("Status")

        if not desc_visual:
            self.alert("Aviso", "Não há pendências visuais para este item.")
            return

        # 2. Verifica se está pendente olhando o STATUS DO ITEM
        if status_item != StatusPR.EM_ANALISE:
            self.alert("Aviso", f"O item não está em análise (Status: {status_item}).")
            return

        top = SaaSModal(self, title="Análise de Produto", width=500, height=300)
        frm = ttk.Frame(top.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="O conferente reportou a seguinte situação:",
                 bg=Colors.BG_APP, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

        info_box = tk.Frame(frm, bg="#F3F4F6", bd=1, relief="solid", padx=10, pady=10)
        info_box.pack(fill="x", pady=10)

        # Mostra SKU e Descrição visual pura
        tk.Label(info_box, text=f"Item: {item_sel.get('Sku')}", font=("Segoe UI", 10, "bold"), bg="#F3F4F6").pack(
            anchor="w")

        tk.Label(info_box, text=f"Descrição Visual: {desc_visual}", bg="#F3F4F6", fg="#374151", wraplength=440,
                 justify="left").pack(
            anchor="w", pady=(5, 0))

        def _acao(tipo):
            sucesso, msg = recebimento_repo.resolver_divergencia_fiscal(
                item_sel['PrCode'], item_sel['Id'], tipo, "Fiscal"
            )
            top.close()
            # Refresh nas tabelas
            self.table_top.load_page(self.table_top.page)
            self.table_bottom.load_page(self.table_bottom.page)
            self.alert("Resultado", msg, type="info")

        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(fill="x", pady=20)

        PillButton(btn_box, text="Rejeitar", variant="outline", command=lambda: _acao("rejeitar")).pack(side="left")
        PillButton(btn_box, text="Validar", variant="success", command=lambda: _acao("validar")).pack(side="right")