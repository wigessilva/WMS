import tkinter as tk
from tkinter import ttk

from database.repositories import (
    addresses_repo, printers_repo,
    products_repo, units_repo, lpn_repo, printer_config, areas_repo
)
from ui.components import (
    Page, PillButton, StandardTable, SaaSModal,
    TextField, PillCombobox, BlueCheckButton, ToggleSwitch,
    BlueRadioButton, ScrollableFrame, ToolTip
)
from utils.constants import Colors
from utils.helpers import Utils, load_icon, AuditManager
from utils.printing import imprimir_etiqueta_endereco


class AddressDialog(SaaSModal):
    def __init__(self, parent, mode, data=None, on_done=None):
        title = "Novo Endereço" if mode == "add" else "Editar Endereço"
        super().__init__(parent, title, width=850, height=560)
        self.parent_ref = parent
        self.on_done = on_done
        self.mode = mode
        self.data = data or {}

        # Padding do container principal
        frm = ttk.Frame(self.content, style="Main.TFrame", padding=15)
        frm.pack(fill="both", expand=True)

        # ======================================================
        # LINHA 1: STATUS (Topo Direito)
        # ======================================================
        f_top_row = tk.Frame(frm, bg=Colors.BG_APP)
        f_top_row.pack(fill="x", pady=(0, 5))

        f_status_container = tk.Frame(f_top_row, bg=Colors.BG_APP)
        f_status_container.pack(side="right")

        self.var_ativo = tk.BooleanVar(value=True)
        ToggleSwitch(f_status_container, variable=self.var_ativo, on_color=Colors.SUCCESS,
                     bg=Colors.BG_APP).pack(side="left")
        self.lbl_st_text = tk.Label(f_status_container, text="Ativo", font=("Segoe UI", 9, "bold"),
                                    bg=Colors.BG_APP, fg=Colors.SUCCESS)
        self.lbl_st_text.pack(side="left", padx=(8, 0))

        def _update_st_label(*args):
            if self.var_ativo.get():
                self.lbl_st_text.config(text="Ativo", fg=Colors.SUCCESS)
            else:
                self.lbl_st_text.config(text="Inativo", fg=Colors.TEXT_HINT)

        self.var_ativo.trace_add("write", _update_st_label)

        # ======================================================
        # LINHA 2: ESTRUTURA E FINALIDADE
        # ======================================================
        f_config_row = tk.Frame(frm, bg=Colors.BG_APP)
        f_config_row.pack(fill="x", pady=(0, 10))
        f_config_row.columnconfigure(0, weight=1)
        f_config_row.columnconfigure(1, weight=1)

        # --- Coluna Esquerda: Estrutura ---
        f_left = tk.Frame(f_config_row, bg=Colors.BG_APP)
        f_left.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(f_left, text="Estrutura Física:", style="TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.cmb_tipo = PillCombobox(f_left, values=["Porta-Palete", "Estante", "Gaiola"], height=32)
        self.cmb_tipo.pack(fill="x", pady=(2, 0))
        self.cmb_tipo.set("Porta-Palete")

        # --- Coluna Direita: Finalidade ---
        f_right = tk.Frame(f_config_row, bg=Colors.BG_APP)
        f_right.grid(row=0, column=1, sticky="ew")

        ttk.Label(f_right, text="Finalidade:", style="TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.cmb_uso = PillCombobox(f_right, values=["Pulmão", "Picking", "Quarentena"], height=32)
        self.cmb_uso.pack(fill="x", pady=(2, 0))
        self.cmb_uso.set("Pulmão")

        self.cmb_tipo._entry.bind("<<ComboboxSelected>>", self._rebuild_dynamic_ui)
        self.cmb_uso._entry.bind("<<ComboboxSelected>>", self._toggle_picking_fields)

        # ======================================================
        # LINHA 3: CONFIGURAÇÃO DE PICKING (Condicional)
        # ======================================================
        self.fr_picking_cfg = tk.Frame(frm, bg=Colors.BG_APP)
        self.fr_picking_cfg.pack(fill="x", pady=(0, 5))

        self.fr_picking_cfg.columnconfigure(0, weight=2)  # SKU
        self.fr_picking_cfg.columnconfigure(1, weight=1)  # Cap
        self.fr_picking_cfg.columnconfigure(2, weight=1)  # Und

        # SKU
        f_p1 = tk.Frame(self.fr_picking_cfg, bg=Colors.BG_APP)
        f_p1.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(f_p1, text="Produto Vinculado:", style="TLabel").pack(anchor="w")

        lista_skus = [f"{p['Sku']} - {p['Descricao']}" for p in products_repo.get_all()]
        self.cmb_sku_fixo = PillCombobox(f_p1, values=lista_skus, placeholder="Opcional", height=32)
        self.cmb_sku_fixo.pack(fill="x")

        # Cap
        f_p2 = tk.Frame(self.fr_picking_cfg, bg=Colors.BG_APP)
        f_p2.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Label(f_p2, text="Cap. Máx:", style="TLabel").pack(anchor="w")
        self.ent_cap_pick = TextField(f_p2, placeholder="", height=32)
        self.ent_cap_pick.pack(fill="x")

        # Und
        f_p3 = tk.Frame(self.fr_picking_cfg, bg=Colors.BG_APP)
        f_p3.grid(row=0, column=2, sticky="ew")
        ttk.Label(f_p3, text="Und:", style="TLabel").pack(anchor="w")

        lista_unidades = [u["Sigla"] for u in units_repo.get_all()]
        self.cmb_und_pick = PillCombobox(f_p3, values=lista_unidades, placeholder="UN", height=32)
        self.cmb_und_pick.pack(fill="x")

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(5, 10))

        # ======================================================
        # LINHA 4: COORDENADAS (4 colunas) - ESTILO CARD (NOVO)
        # ======================================================

        # 1. Wrapper (Container Externo)
        f_coord_wrapper = tk.Frame(frm, bg=Colors.BG_APP)
        f_coord_wrapper.pack(fill="x", pady=(0, 5))

        # 2. Borda (Simulando LabelFrame com cor suave #E5E7EB)
        # pady=(10, 0) cria o espaço superior para o título flutuante
        f_coord_border = tk.Frame(f_coord_wrapper, bg=Colors.BG_APP, bd=0,
                                  highlightthickness=1, highlightbackground="#E5E7EB")
        f_coord_border.pack(fill="x", expand=True, pady=(10, 0))

        # 3. Título Flutuante (Overlay)
        lbl_gps = tk.Label(f_coord_wrapper, text=" Coordenadas", bg=Colors.BG_APP,
                           fg="#374151", font=("Segoe UI", 10, "bold"))
        lbl_gps.place(x=12, y=0)  # Posiciona em cima da borda

        # 4. Conteúdo Interno (Onde os campos vão ficar)
        f_coord = tk.Frame(f_coord_border, bg=Colors.BG_APP)
        f_coord.pack(fill="x", expand=True, padx=15, pady=20)  # Padding interno do card

        f_coord.columnconfigure(0, weight=1)
        f_coord.columnconfigure(1, weight=1)
        f_coord.columnconfigure(2, weight=1)
        f_coord.columnconfigure(3, weight=1)

        f_area = tk.Frame(f_coord, bg=Colors.BG_APP)
        f_area.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        tk.Label(f_area, text="Área:", bg=Colors.BG_APP, anchor="w", font=("Segoe UI", 9)).pack(fill="x")

        # Carrega áreas dinamicamente
        areas_disponiveis = [a['Nome'] for a in areas_repo.get_all() if a['Ativo']]
        self.ent_area = PillCombobox(f_area, values=areas_disponiveis, height=32)
        self.ent_area.pack(fill="x")

        self.ent_rua, _ = self._add_field_ref(f_coord, "Rua:", 0, 1)
        self.ent_pred, self.lbl_pred = self._add_field_ref(f_coord, "Prédio:", 0, 2)
        self.ent_niv, self.lbl_niv = self._add_field_ref(f_coord, "Nível:", 0, 3)

        # Posição / Grupo
        f_pos_container = tk.Frame(f_coord, bg=Colors.BG_APP)
        f_pos_container.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(8, 0))
        self.lbl_pos = tk.Label(f_pos_container, text="Posição:", bg=Colors.BG_APP, anchor="w",
                                font=("Segoe UI", 9, "bold"))
        self.lbl_pos.pack(fill="x")
        self.ent_pos = TextField(f_pos_container, placeholder="", height=34)
        self.ent_pos.pack(fill="x")

        # ======================================================
        # LINHA 5: DETALHES TÉCNICOS (Dinâmico)
        # ======================================================
        self.f_extra = tk.Frame(frm, bg=Colors.BG_APP)
        self.f_extra.pack(fill="x", pady=(5, 5))

        self.dyn_frame = tk.Frame(self.f_extra, bg=Colors.BG_APP)
        self.dyn_frame.pack(fill="x")
        self.ent_comp = None
        self.ent_peso = None

        # ======================================================
        # RODAPÉ
        # ======================================================
        tk.Frame(frm, bg=Colors.BG_APP).pack(fill="both", expand=True)

        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x", pady=(10, 0))

        PillButton(box, text="Salvar", variant="success", command=self._save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

        if mode == "add":
            PillButton(box, text="Gerar em Lote", variant="outline", icon=load_icon("batchgen", 16),
                       command=self._open_batch).pack(side="left")

        # ======================================================
        # CARREGAMENTO (Edit)
        # ======================================================
        if mode == "edit":
            tipo_salvo = self.data.get("Tipo", "Porta-Palete")
            if tipo_salvo in ["Padrao", "Raia"]: tipo_salvo = "Porta-Palete"
            if tipo_salvo in ["Tinta", "Picking"]: tipo_salvo = "Estante"
            self.cmb_tipo.set(tipo_salvo)

            self.cmb_uso.set(self.data.get("Uso", "Pulmão"))

            # CORRIGIDO: skufixo (sem underline)
            sku_salvo = self.data.get("SkuFixo", "")
            if sku_salvo:
                match_text = next((s for s in lista_skus if s.startswith(f"{sku_salvo} -")), sku_salvo)
                self.cmb_sku_fixo.set(match_text)

            if self.data.get("CapacidadePicking"):
                self.ent_cap_pick.insert(0, str(self.data.get("CapacidadePicking")))

            if self.data.get("UnidadePicking"):
                self.cmb_und_pick.set(self.data.get("UnidadePicking"))

            self.ent_area.insert(0, self.data.get("Area", ""))
            self.ent_rua.insert(0, str(self.data.get("Rua", 0)))
            self.ent_pred.insert(0, str(self.data.get("Predio", 0)))
            self.ent_niv.insert(0, str(self.data.get("Nivel", 0)))

            self.ent_pos.insert(0, self.data.get("GrupoBloqueio", ""))

            self.var_ativo.set(self.data.get("Ativo", True))
            _update_st_label()

        self._rebuild_dynamic_ui()
        self._toggle_picking_fields()

        if mode == "edit":
            if self.ent_comp:
                self.ent_comp.insert(0, str(self.data.get("ComprimentoUtil", 0)))
            if self.ent_peso:
                # CORRIGIDO: cargamaxkg
                self.ent_peso.insert(0, str(self.data.get("CargaMaxKg", 0)))

    # Métodos Auxiliares
    def _add_field_ref(self, parent, label_text, r, c):
        f = tk.Frame(parent, bg=Colors.BG_APP)
        f.grid(row=r, column=c, sticky="ew", padx=5, pady=2)
        lbl = tk.Label(f, text=label_text, bg=Colors.BG_APP, anchor="w", font=("Segoe UI", 9))
        lbl.pack(fill="x")
        e = TextField(f, placeholder="", height=32)
        e.pack(fill="x")
        return e, lbl

    def _add_field(self, parent, label, r, c):
        f = tk.Frame(parent, bg=Colors.BG_APP)
        f.grid(row=r, column=c, sticky="ew", padx=5, pady=2)
        tk.Label(f, text=label, bg=Colors.BG_APP, anchor="w", font=("Segoe UI", 9)).pack(fill="x")
        e = TextField(f, placeholder="", height=32)
        e.pack(fill="x")
        return e

    def _toggle_picking_fields(self, *args):
        state = "normal" if self.cmb_uso.get() == "Picking" else "disabled"
        self.cmb_sku_fixo.configure(state=state)
        self.ent_cap_pick._entry.configure(state=state)
        self.cmb_und_pick.configure(state=state)
        if state == "disabled":
            self.cmb_sku_fixo.set("")
            self.ent_cap_pick.delete(0, "end")
            self.cmb_und_pick.set("")

    def _rebuild_dynamic_ui(self, *args):
        for w in self.dyn_frame.winfo_children(): w.destroy()
        self.ent_comp = None
        self.ent_peso = None

        t = self.cmb_tipo.get()

        self.ent_pred._entry.configure(state="normal")
        self.ent_niv._entry.configure(state="normal")
        self.ent_pos._entry.configure(state="normal")
        self.f_extra.pack_forget()

        def _add_dyn(lbl, r, c):
            return self._add_field(self.dyn_frame, lbl, r, c)

        if t == "Estante":
            self.lbl_niv.config(text="Altura (1=A...):")
            self.lbl_pos.config(text="Gaveta (Ex: 01):")
            if self.mode == "add" and not self.ent_pos.get(): self.ent_pos.insert(0, "01")
            self.f_extra.pack(fill="x", pady=(0, 5))
            self.dyn_frame.columnconfigure(0, weight=1)
            self.ent_peso = _add_dyn("Carga Máx (kg):", 0, 0)
            if self.mode == "add": self.ent_peso.insert(0, "200")

        elif t == "Gaiola":
            self.lbl_niv.config(text="Nível:")
            self.lbl_pos.config(text="Identificação:")
            self.ent_pred.delete(0, "end")
            self.ent_pred.insert(0, "0")
            self.ent_pred._entry.configure(state="disabled")
            self.ent_niv.delete(0, "end")
            self.ent_niv.insert(0, "0")
            self.ent_niv._entry.configure(state="disabled")
            self.f_extra.pack(fill="x", pady=(0, 5))
            self.dyn_frame.columnconfigure(0, weight=1)
            self.dyn_frame.columnconfigure(1, weight=1)
            self.ent_comp = _add_dyn("Comprimento (mm):", 0, 0)
            self.ent_peso = _add_dyn("Carga Máx (kg):", 0, 1)

        else:  # Porta-Palete
            self.lbl_niv.config(text="Nível:")
            self.lbl_pos.config(text="Posições:")
            if self.mode == "add" and not self.ent_pos.get(): self.ent_pos.insert(0, "01")
            self.f_extra.pack(fill="x", pady=(0, 5))
            self.dyn_frame.columnconfigure(0, weight=1)
            self.ent_peso = _add_dyn("Carga Máxima (kg):", 0, 0)
            if self.mode == "add": self.ent_peso.insert(0, "1200")

    def _open_batch(self):
        self.close()
        BatchAddressDialog(self.parent_ref, on_done=self.on_done)

    def _save(self):
        try:
            area = self.ent_area.get().strip()
            rua_txt = self.ent_rua.get().strip()
            pred_txt = self.ent_pred.get().strip()
            niv_txt = self.ent_niv.get().strip()

            if not area:
                self.alert("Atenção", "O campo 'Área' é obrigatório.", focus_widget=self.ent_area)
                return
            if not rua_txt.isdigit():
                self.alert("Atenção", "A Rua deve ser um número inteiro.", focus_widget=self.ent_rua)
                return
            if not pred_txt.isdigit():
                self.alert("Atenção", "O Prédio deve ser um número inteiro.", focus_widget=self.ent_pred)
                return
            if not niv_txt.isdigit():
                self.alert("Atenção", "O Nível deve ser um número inteiro.", focus_widget=self.ent_niv)
                return

            grp = self.ent_pos.get().strip() if self.ent_pos else ""
            c_comp = Utils.safe_float(self.ent_comp.get()) if self.ent_comp else 0.0
            c_peso = Utils.safe_float(self.ent_peso.get()) if self.ent_peso else 0.0

            uso_sel = self.cmb_uso.get()
            sku_fixo_val = ""
            cap_pick_val = 0
            und_pick_val = ""

            if uso_sel == "Picking":
                raw_sku = self.cmb_sku_fixo.get()
                sku_fixo_val = raw_sku.split(" - ")[0].strip() if raw_sku else ""
                raw_cap = self.ent_cap_pick.get()
                if raw_cap: cap_pick_val = Utils.safe_float(raw_cap)
                und_pick_val = self.cmb_und_pick.get()
                if cap_pick_val > 0 and not und_pick_val:
                    self.alert("Atenção", "Informe a unidade.", focus_widget=self.cmb_und_pick)
                    return

            kwargs = {
                "Area": area, "Rua": int(rua_txt), "Predio": int(pred_txt), "Nivel": int(niv_txt),
                "Tipo": self.cmb_tipo.get(),
                "CapacidadeTipo": "Qtd", "CapacidadeVal": 1.0,
                "GrupoBloqueio": grp, "ComprimentoUtil": c_comp,
                "Uso": uso_sel, "SkuFixo": sku_fixo_val,
                "CapacidadePicking": cap_pick_val, "UnidadePicking": und_pick_val,
                "CargaMaxKg": c_peso
            }

            if self.mode == "add":
                addresses_repo.add(**kwargs)
            else:
                kwargs["Ativo"] = self.var_ativo.get()
                addresses_repo.update(uid=self.data["Id"], **kwargs)

            if self.on_done: self.on_done()
            self.close()
        except ValueError as e:
            self.alert("Atenção", str(e), type="error")
        except Exception as e:
            self.alert("Erro Crítico", str(e), type="error")


class PrintAddressesDialog(SaaSModal):
    def __init__(self, parent, addresses):
        super().__init__(parent, title=f"Imprimir {len(addresses)} Endereços", width=400, height=300)
        self.addresses = addresses

        frm = ttk.Frame(self.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Selecione a Impressora:", style="TLabel").pack(anchor="w", pady=(0, 6))

        # Carrega impressoras
        all_printers = printers_repo.get_all()
        self.printer_map = {f"{p['Nome']} ({p['Caminho']})": p for p in all_printers}
        printer_labels = list(self.printer_map.keys())

        self.cmb_printer = PillCombobox(frm, values=printer_labels, placeholder="Selecione...", height=34)
        self.cmb_printer.pack(fill="x", pady=(0, 20))

        # Preferência salva
        saved_default = printer_config.get_default("Endereco")

        self.var_save = tk.BooleanVar(value=False)
        chk = BlueCheckButton(frm, text="Salvar como padrão para Endereços", variable=self.var_save, bg=Colors.BG_APP)
        chk.pack(anchor="w", pady=(0, 20))

        if saved_default:
            match = next((l for l, p in self.printer_map.items() if p["Nome"] == saved_default), None)
            if match:
                self.cmb_printer.set(match)
                self.var_save.set(True)
        elif printer_labels:
            self.cmb_printer.set(printer_labels[0])

        ttk.Label(frm, text="Formato recomendado: 80mm x 50mm", font=("Segoe UI", 9), foreground="#6B7280").pack(
            anchor="w")

        btn_box = ttk.Frame(frm, style="Main.TFrame")
        btn_box.pack(side="bottom", fill="x")

        PillButton(btn_box, text="Imprimir", variant="primary", command=self._print).pack(side="right")
        PillButton(btn_box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

    def _print(self):
        label_sel = self.cmb_printer.get()
        if not label_sel or label_sel not in self.printer_map:
            self.alert("Atenção", "Selecione uma impressora válida.")
            return

        p_data = self.printer_map[label_sel]

        if self.var_save.get():
            printer_config.set_default("Endereco", p_data["Nome"])

        sucesso = 0
        erros = 0

        try:
            for addr in self.addresses:
                try:
                    imprimir_etiqueta_endereco(p_data, addr)
                    sucesso += 1
                except:
                    erros += 1

            # CORREÇÃO: Usar self.alert em vez de messagebox
            msg = f"{sucesso} etiquetas enviadas para {p_data['Nome']}."
            if erros > 0:
                msg += f"\n{erros} falharam."
                self.alert("Relatório", msg, type="warning")
            else:
                self.alert("Sucesso", msg, type="success")

            # Fecha após o usuário dar OK no alert
            self.close()

        except Exception as e:
            self.alert("Erro", str(e), type="error")


class BatchAddressDialog(SaaSModal):
    def __init__(self, parent, on_done=None):
        super().__init__(parent, "Gerador de Endereços em Lote", width=720, height=620)
        self.on_done = on_done

        # 1. BOTÕES (Rodapé)
        box_btns = ttk.Frame(self.content, style="Main.TFrame")
        box_btns.pack(side="bottom", fill="x", pady=15, padx=20)

        PillButton(box_btns, text="Gerar", variant="primary", command=self._run).pack(side="right")
        PillButton(box_btns, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

        # 2. CONTEÚDO (Scroll)
        scroll_container = ScrollableFrame(self.content, padding=(20, 20, 0, 0))
        scroll_container.pack(side="top", fill="both", expand=True)

        frm = scroll_container.content

        # --- SEÇÃO 1: CONFIGURAÇÃO BASE ---
        ttk.Label(frm, text="Configuração Base", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))

        box_base = tk.Frame(frm, bg=Colors.BG_APP)
        box_base.pack(fill="x")
        box_base.columnconfigure(0, weight=1)
        box_base.columnconfigure(1, weight=1)

        # Linha 0
        f_area = tk.Frame(box_base, bg=Colors.BG_APP)  # <--- Mudei de f_coord para box_base
        f_area.grid(row=0, column=0, sticky="ew", padx=8, pady=4)

        tk.Label(f_area, text="Área:", bg=Colors.BG_APP, anchor="w", font=("Segoe UI", 9)).pack(fill="x")

        # Carrega áreas do banco
        areas_disponiveis = [a['Nome'] for a in areas_repo.get_all() if a['Ativo']]
        self.ent_area = PillCombobox(f_area, values=areas_disponiveis, height=34)
        self.ent_area.pack(fill="x")

        # Coluna 1: Tipo (Já existia, mas mantenha alinhado)
        f_tipo = tk.Frame(box_base, bg=Colors.BG_APP)
        f_tipo.grid(row=0, column=1, sticky="ew", padx=8, pady=4)

        tk.Label(f_tipo, text="Perfil de Estrutura:", bg=Colors.BG_APP, font=("Segoe UI", 9)).pack(anchor="w")
        self.cmb_tipo = PillCombobox(f_tipo, values=["Porta-Palete", "Estante", "Gaiola"], height=34)
        self.cmb_tipo.set("Porta-Palete")
        self.cmb_tipo.pack(fill="x")

        # Linha 1
        self.ent_cap = self._add_field(box_base, "Nº de Posições (por nível):", 1, 0)
        self.ent_cap.insert(0, "1")

        self.ent_peso_lote = self._add_field(box_base, "Carga Máxima (kg):", 1, 1)

        # Linha 2
        f_uso = tk.Frame(box_base, bg=Colors.BG_APP)
        f_uso.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=10)

        tk.Label(f_uso, text="Finalidade do Endereço:", bg=Colors.BG_APP, font=("Segoe UI", 9)).pack(anchor="w",
                                                                                                     pady=(0, 4))
        self.var_uso_lote = tk.StringVar(value="Pulmão")

        f_radios = tk.Frame(f_uso, bg=Colors.BG_APP)
        f_radios.pack(anchor="w")
        BlueRadioButton(f_radios, "Pulmão", self.var_uso_lote, "Pulmão", bg=Colors.BG_APP).pack(side="left",
                                                                                                padx=(0, 20))
        BlueRadioButton(f_radios, "Picking", self.var_uso_lote, "Picking", bg=Colors.BG_APP).pack(side="left",
                                                                                                  padx=(0, 20))
        BlueRadioButton(f_radios, "Quarentena", self.var_uso_lote, "Quarentena", bg=Colors.BG_APP).pack(side="left")

        # Feedback visual
        self.lbl_feedback = tk.Label(self.ent_cap.master, text="", font=("Segoe UI", 9, "italic"),
                                     fg=Colors.PRIMARY, bg=Colors.BG_APP)

        self.lbl_feedback.pack(anchor="w", padx=0, pady=(2, 0))

        # Binds
        self.ent_cap._entry.bind("<KeyRelease>", self._update_feedback)
        self.cmb_tipo._entry.bind("<<ComboboxSelected>>",
                                  lambda e: (self._update_feedback(), self._rebuild_dynamic_ui()))

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=20)

        # --- SEÇÃO 2: INTERVALOS DE GERAÇÃO ---
        ttk.Label(frm, text="Intervalos de Geração", font=("Segoe UI", 10, "bold")).pack(anchor="w",
                                                                                                     pady=(0, 10))

        box_range = tk.Frame(frm, bg=Colors.BG_APP)
        box_range.pack(fill="x")
        box_range.columnconfigure(0, weight=1)
        box_range.columnconfigure(1, weight=1)

        self.r_ini = self._add_field(box_range, "Rua Início:", 0, 0)
        self.r_fim = self._add_field(box_range, "Rua Fim:", 0, 1)

        self.p_ini = self._add_field(box_range, "Prédio Início:", 1, 0)
        self.p_fim = self._add_field(box_range, "Prédio Fim:", 1, 1)

        self.n_ini = self._add_field(box_range, "Nível Início:", 2, 0)
        self.n_fim = self._add_field(box_range, "Nível Fim:", 2, 1)

        lbl_info = tk.Label(frm,
                            text="Dica: Para configurar o Nível 1 como Picking e os aéreos como Pulmão, execute este gerador duas vezes.",
                            fg=Colors.TEXT_HINT, bg=Colors.BG_APP, wraplength=600, justify="left")
        lbl_info.pack(pady=20, anchor="w", padx=5)

        # Inicializa estado dos campos
        self._update_feedback()
        self._rebuild_dynamic_ui()

    def _add_field(self, parent, label, r, c):
        f = tk.Frame(parent, bg=Colors.BG_APP)
        f.grid(row=r, column=c, sticky="new", padx=8, pady=4)
        tk.Label(f, text=label, bg=Colors.BG_APP, anchor="w", font=("Segoe UI", 9)).pack(fill="x")
        e = TextField(f, placeholder="", height=34)
        e.pack(fill="x")
        return e

    def _rebuild_dynamic_ui(self, *args):
        # Verifica se é Gaiola para travar Prédio e Nível
        t = self.cmb_tipo.get()

        if t == "Gaiola":
            self.p_ini.delete(0, "end")
            self.p_ini.insert(0, "0")
            self.p_ini._entry.configure(state="disabled")

            self.p_fim.delete(0, "end")
            self.p_fim.insert(0, "0")
            self.p_fim._entry.configure(state="disabled")

            self.n_ini.delete(0, "end")
            self.n_ini.insert(0, "0")
            self.n_ini._entry.configure(state="disabled")

            self.n_fim.delete(0, "end")
            self.n_fim.insert(0, "0")
            self.n_fim._entry.configure(state="disabled")
        else:
            self.p_ini._entry.configure(state="normal")
            self.p_fim._entry.configure(state="normal")
            self.n_ini._entry.configure(state="normal")
            self.n_fim._entry.configure(state="normal")

    def _update_feedback(self, event=None):
        val = self.ent_cap.get().strip()
        tipo = self.cmb_tipo.get()
        if not val.isdigit() or int(val) < 1:
            self.lbl_feedback.config(text="Digite um número válido.", fg="#DC2626")
            return
        qtd = int(val)
        exemplo = "Ex: ...-01, -02..." if tipo == "Porta-Palete" else "Ex: ...A-01, ...A-02..."
        self.lbl_feedback.config(text=f"Serão geradas {qtd} posições para cada nível ({exemplo}).", fg=Colors.PRIMARY)

    def _run(self):
        try:
            area = self.ent_area.get().strip()
            if not area:
                self.alert("Atenção", "Informe a Área.", focus_widget=self.ent_area)
                return

            for v, w, nome in [
                (self.r_ini.get(), self.r_ini, "Rua Início"), (self.r_fim.get(), self.r_fim, "Rua Fim"),
                (self.p_ini.get(), self.p_ini, "Prédio Início"), (self.p_fim.get(), self.p_fim, "Prédio Fim"),
                (self.n_ini.get(), self.n_ini, "Nível Início"), (self.n_fim.get(), self.n_fim, "Nível Fim")
            ]:
                if not v.strip() or not v.strip().isdigit():
                    self.alert("Atenção", f"{nome} inválido.", focus_widget=w)
                    return

            cap_val_str = self.ent_cap.get().strip()
            if not cap_val_str.isdigit() or int(cap_val_str) < 1:
                self.alert("Atenção", "Posições inválidas.", focus_widget=self.ent_cap)
                return

            peso_lote = Utils.safe_float(self.ent_peso_lote.get())
            qtd_posicoes = int(cap_val_str)
            uso_escolhido = self.var_uso_lote.get()

            cfg = {
                "area": area, "tipo": self.cmb_tipo.get(), "cap_tipo": "Qtd", "cap_val": 1.0,
                "rua_ini": int(self.r_ini.get()), "rua_fim": int(self.r_fim.get()),
                "pred_ini": int(self.p_ini.get()), "pred_fim": int(self.p_fim.get()),
                "niv_ini": int(self.n_ini.get()), "niv_fim": int(self.n_fim.get()),
                "comp_util": 0
            }

            count = 0
            erros = 0
            for r in range(cfg['rua_ini'], cfg['rua_fim'] + 1):
                for p in range(cfg['pred_ini'], cfg['pred_fim'] + 1):
                    for n in range(cfg['niv_ini'], cfg['niv_fim'] + 1):
                        for i in range(1, qtd_posicoes + 1):
                            suffix = f"{i:02d}"
                            try:
                                addresses_repo.add(
                                    Area=cfg['area'], Rua=r, Predio=p, Nivel=n,
                                    Tipo=cfg['tipo'], CapacidadeTipo="Qtd", CapacidadeVal=1.0,
                                    GrupoBloqueio=suffix, ComprimentoUtil=0,
                                    CargaMaxKg=peso_lote,
                                    Uso=uso_escolhido
                                )
                                count += 1
                            except ValueError:
                                erros += 1

            msg = f"{count} endereços de {uso_escolhido} criados!"
            if erros > 0: msg += f"\n({erros} ignorados pois já existiam)."

            # CORREÇÃO: Removido messagebox e usado self.alert
            self.alert("Concluído", msg, type="success")

            if self.on_done: self.on_done()
            self.close()

        except Exception as e:
            self.alert("Erro", str(e), type="error")


class BatchEditAddressDialog(SaaSModal):
    def __init__(self, parent, targets, on_done=None):
        # Aumentei a altura para caber o novo campo
        super().__init__(parent, title=f"Editar {len(targets)} Endereços", width=420, height=580)
        self.targets = targets
        self.on_done = on_done

        # Container Principal
        frm = ttk.Frame(self.content, style="Main.TFrame", padding=25)
        frm.pack(fill="both", expand=True)

        # Texto de ajuda
        tk.Label(frm, text="Defina apenas os campos que deseja alterar.\nOs demais manterão seus valores atuais.",
                 font=("Segoe UI", 9), bg=Colors.BG_APP, fg="#6B7280", justify="left").pack(anchor="w", pady=(0, 15))

        # --- CAMPOS (Label em cima, Input embaixo) ---

        # 1. Finalidade (Uso)
        tk.Label(frm, text="Finalidade", font=("Segoe UI", 9, "bold"), bg=Colors.BG_APP).pack(anchor="w", pady=(0, 2))
        self.cb_uso = PillCombobox(frm, values=["Selecione", "Pulmão", "Picking", "Quarentena"], height=34)
        self.cb_uso.set("Selecione")
        self.cb_uso.pack(fill="x", pady=(0, 10))

        # 2. Status
        tk.Label(frm, text="Status", font=("Segoe UI", 9, "bold"), bg=Colors.BG_APP).pack(anchor="w", pady=(0, 2))
        self.cb_status = PillCombobox(frm, values=["Selecione", "Ativo", "Inativo"], height=34)
        self.cb_status.set("Selecione")
        self.cb_status.pack(fill="x", pady=(0, 10))

        # 3. Capacidade de Carga (Peso)
        tk.Label(frm, text="Carga Máxima (kg) - Estrutura", font=("Segoe UI", 9, "bold"), bg=Colors.BG_APP).pack(
            anchor="w", pady=(0, 2))
        self.ent_carga = TextField(frm, height=34, placeholder="Opcional")
        self.ent_carga.pack(fill="x", pady=(0, 10))

        # 4. Produto Fixo (SKU)
        tk.Label(frm, text="Produto Fixo (Picking)", font=("Segoe UI", 9, "bold"), bg=Colors.BG_APP).pack(anchor="w",
                                                                                                          pady=(0, 2))

        lista_skus = []
        try:
            raw_prods = products_repo.get_all()
            lista_skus = [f"{p['Sku']} - {p['Descricao']}" for p in raw_prods]
        except Exception:
            lista_skus = []

        self.cb_sku = PillCombobox(frm, values=lista_skus, placeholder="Selecione ou Digite", height=34)
        self.cb_sku.set("")
        self.cb_sku.pack(fill="x", pady=(0, 10))
        self.cb_sku._entry.bind("<KeyRelease>", self._auto_open_sku, add="+")

        # 5. NOVO: Capacidade Picking (Quantidade)
        tk.Label(frm, text="Capacidade Máxima (Qtd. Caixas/Unidades)", font=("Segoe UI", 9, "bold"),
                 bg=Colors.BG_APP).pack(anchor="w", pady=(0, 2))
        self.ent_cap_pick = TextField(frm, height=34, placeholder="Ex: 50")
        self.ent_cap_pick.pack(fill="x", pady=(0, 20))

        # Botões
        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x")
        PillButton(box, text="Salvar Alterações", variant="success", command=self._save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

    def _auto_open_sku(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"): return
        texto = self.cb_sku._var.get()
        if texto and not self.cb_sku._is_open:
            self.cb_sku._open_dropdown()

    def _save(self):
        updates = {}

        # 1. Finalidade
        val_uso = self.cb_uso.get()
        if val_uso and val_uso != "Selecione":
            updates["Uso"] = val_uso

        # 2. Status
        val_status = self.cb_status.get()
        if val_status and val_status != "Selecione":
            updates["Ativo"] = (val_status == "Ativo")
            if updates["Ativo"] is False:
                if not self.ask_yes_no("Atenção", "Inativar endereços com saldo pode bloquear o estoque.\nContinuar?"):
                    return

        # 3. Carga (Peso)
        val_carga = self.ent_carga.get().strip()
        if val_carga:
            try:
                updates["CargaMaxKg"] = float(val_carga.replace(",", "."))
            except:
                self.alert("Erro", "Valor de Carga inválido.")
                return

        # 4. SKU Fixo
        val_sku_raw = self.cb_sku.get().strip()
        if not val_sku_raw: val_sku_raw = self.cb_sku._var.get().strip()

        if val_sku_raw:
            final_sku = val_sku_raw.split(" - ")[0].strip().upper()
            if final_sku != "SELECIONE OU DIGITE":
                updates["SkuFixo"] = final_sku

        # 5. Capacidade Picking (Quantidade) - NOVO
        val_cap_pick = self.ent_cap_pick.get().strip()
        if val_cap_pick:
            try:
                updates["CapacidadePicking"] = float(val_cap_pick.replace(",", "."))
            except:
                self.alert("Erro", "Quantidade de Picking inválida.")
                return

        if not updates:
            self.alert("Sem alterações", "Nenhum campo foi modificado.")
            return

        count, erros = 0, 0
        for row in self.targets:
            try:
                # 1. Cria kwargs baseados na linha atual (que já vem do banco em TitleCase!)
                #    Como padronizamos tudo, podemos usar os dados da linha quase direto.
                kwargs = {
                    "Area": row.get("Area"), "Rua": row.get("Rua"),
                    "Predio": row.get("Predio"), "Nivel": row.get("Nivel"),
                    "Tipo": row.get("Tipo"), "GrupoBloqueio": row.get("GrupoBloqueio", ""),
                    "CapacidadeTipo": row.get("CapacidadeTipo", "Qtd"),
                    "CapacidadeVal": row.get("CapacidadeVal", 1.0),
                    "ComprimentoUtil": row.get("ComprimentoUtil", 0),
                    "Ativo": row.get("Ativo"),
                    "Uso": row.get("Uso"),
                    "SkuFixo": row.get("SkuFixo", ""),
                    "CapacidadePicking": row.get("CapacidadePicking", 0),
                    "UnidadePicking": row.get("UnidadePicking", ""),
                    "CargaMaxKg": row.get("CargaMaxKg", 0)
                }

                # 2. Sobrescreve com as atualizações (que também estão em TitleCase)
                kwargs.update(updates)

                # 3. Chama update
                addresses_repo.update(uid=row["Id"], **kwargs)
                count += 1
            except Exception:
                erros += 1

        self.alert("Sucesso", f"{count} endereços atualizados!\n({erros} erros)", type="success")
        if self.on_done: self.on_done()
        self.close()


class AreaFormDialog(SaaSModal):
    def __init__(self, parent, mode, data=None, on_done=None):
        title = "Nova Área" if mode == "add" else "Editar Área"
        super().__init__(parent, title, width=450, height=320)
        self.mode = mode
        self.data = data or {}
        self.on_done = on_done

        frm = ttk.Frame(self.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # Nome
        tk.Label(frm, text="Nome da Área:", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.ent_nome = TextField(frm, placeholder="Ex: RECEBIMENTO", height=34)
        self.ent_nome.pack(fill="x", pady=(0, 15))

        # Descrição
        tk.Label(frm, text="Descrição:", bg=Colors.BG_APP, font=("Segoe UI", 9)).pack(anchor="w")
        self.ent_desc = TextField(frm, placeholder="Opcional", height=34)
        self.ent_desc.pack(fill="x", pady=(0, 15))

        # Ativo (Apenas na edição ou se quiser permitir criar inativo)
        self.var_ativo = tk.BooleanVar(value=True)
        if mode == "edit":
            chk = BlueCheckButton(frm, text="Ativo", variable=self.var_ativo, bg=Colors.BG_APP)
            chk.pack(anchor="w", pady=(0, 15))

        # Botões
        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x")

        PillButton(box, text="Salvar", variant="success", command=self._save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

        # Load Data
        if mode == "edit":
            self.ent_nome.insert(0, self.data.get("Nome", ""))
            self.ent_desc.insert(0, self.data.get("Descricao", ""))
            self.var_ativo.set(self.data.get("Ativo", True))

    def _save(self):
        nome = self.ent_nome.get().strip()
        desc = self.ent_desc.get().strip()

        if not nome:
            self.alert("Atenção", "Nome é obrigatório.")
            return

        try:
            if self.mode == "add":
                areas_repo.add(Nome=nome, Descricao=desc)
            else:
                areas_repo.update(self.data["Id"], Nome=nome, Descricao=desc, Ativo=self.var_ativo.get())

            if self.on_done: self.on_done()
            self.close()
        except Exception as e:
            self.alert("Erro", str(e))


class AreasManagerDialog(SaaSModal):
    def __init__(self, parent):
        super().__init__(parent, "Gerenciar Áreas", width=900, height=600)

        # --- 1. BARRA DE FERRAMENTAS (Topo) ---
        tb = tk.Frame(self.content, bg=Colors.BG_APP)

        # AJUSTE DE ALINHAMENTO:
        # A StandardTable tem um padding interno padrão de 16px + 15px de margem externa = 31px.
        # Definimos padx=(31, 15) aqui para que o primeiro botão comece exatamente na mesma linha visual.
        tb.pack(fill="x", padx=(31, 15), pady=(15, 5))

        # Botões (Quadradinhos)
        PillButton(tb, text="", variant="primary", icon=load_icon("add", 16), padx=9,
                   command=self._open_add).pack(side="left", padx=(0, 10))

        self.btn_edit = PillButton(tb, text="", variant="outline", icon=load_icon("edit", 16), padx=9,
                                   command=self._open_edit)
        self.btn_edit.pack(side="left", padx=(0, 10))
        self.btn_edit.state(["disabled"])

        self.btn_del = PillButton(tb, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._del_sel)
        self.btn_del.pack(side="left")
        self.btn_del.state(["disabled"])

        # Tooltips
        ToolTip(self.btn_edit, "Editar Área")
        ToolTip(self.btn_del, "Excluir Selecionadas")

        # --- 2. TABELA ---
        cols = [
                   {"id": "Nome", "title": "Nome", "width": 200, "anchor": "w"},
                   {"id": "Descricao", "title": "Descrição", "width": 250, "anchor": "w"},
                   {"id": "status_desc", "title": "Status", "width": 100, "anchor": "center"},
               ] + AuditManager.get_columns()

        self.table = StandardTable(self.content, columns=cols, fetch_fn=self._fetch, page_size=15, checkboxes=True)
        # Mantém padx=15 na tabela (externo), somado ao interno dela, alinhará com o padx=31 da barra acima
        self.table.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.table.bind("<<TableSelect>>", self._on_sel)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._open_edit())

        self.table.load_page(1)

    def _fetch(self, page, size, filters):
        total, rows = areas_repo.list(page, size, filters)
        processed = []
        for r in rows:
            cp = dict(r)
            cp.update(AuditManager.process_row(r))

            ativo = r.get("Ativo", True)
            cp["status_desc"] = "Ativo" if ativo else "Inativo"
            if not ativo:
                cp["_text_color"] = Colors.TEXT_HINT

            processed.append(cp)
        return total, processed

    def _on_sel(self, event):
        has = bool(self.table.get_selected())
        self.btn_edit.state(["!disabled"] if has else ["disabled"])
        self.btn_del.state(["!disabled"] if has else ["disabled"])

    def _open_add(self):
        AreaFormDialog(self, "add", on_done=lambda: self.table.refresh())

    def _open_edit(self):
        sel = self.table.get_selected()
        if not sel: return
        AreaFormDialog(self, "edit", data=sel, on_done=lambda: self.table.refresh())

    def _del_sel(self):
        sels = self.table.get_all_selected()
        if not sels: return
        if not self.ask_yes_no("Confirmar", f"Deseja excluir as {len(sels)} áreas selecionadas?"): return

        try:
            for s in sels:
                areas_repo.delete(s["Id"])
            self.table.refresh()
            self.alert("Sucesso", "Áreas excluídas.")
        except Exception as e:
            self.alert("Erro", str(e))


class EnderecosPage(Page):
    destroy_on_hide = False

    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        # Linha 0: Tabela (peso 0 para não esticar verticalmente além do necessário)
        self.rowconfigure(0, weight=0)
        # Linha 1: Espaçador (peso 1 para empurrar conteúdo para cima)
        self.rowconfigure(1, weight=1)

        cols = [
                   {"id": "visual", "title": "Endereço", "width": 160, "anchor": "w"},
                   {"id": "Tipo", "title": "Perfil", "width": 120, "anchor": "center"},
                   {"id": "uso_desc", "title": "Finalidade", "width": 180, "anchor": "w"},
                   {"id": "SkuFixo", "title": "SKU Fixo", "width": 120, "anchor": "center"},
                   {"id": "Area", "title": "Área", "width": 80, "anchor": "center"},
                   {"id": "status_uso", "title": "Status", "width": 120, "anchor": "center"},
               ] + AuditManager.get_columns()

        def _fetch(page, size, filters):
            total, rows = addresses_repo.list(1, 1000000, filters)

            processed = []
            import string
            letras = string.ascii_uppercase

            # Cache de ocupação
            ends_ocupados = {l["Endereco"] for l in lpn_repo.get_all() if l.get("QtdAtual", 0) > 0}

            for r in rows:
                cp = dict(r)
                cp.update(AuditManager.process_row(r))
                tipo_raw = r.get("Tipo", "Porta-Palete")
                if tipo_raw == "Picking": tipo_raw = "Estante"
                if tipo_raw == "Raia": tipo_raw = "Porta-Palete"

                cp["Tipo"] = tipo_raw

                rua = r.get("Rua", 0)
                pred = r.get("Predio", 0)
                niv = r.get("Nivel", 0)
                sub = r.get("GrupoBloqueio", "")

                # --- 1. VISUAL (GPS) ---
                visual_addr = ""
                if tipo_raw == "Estante":
                    idx = max(0, niv - 1) % 26
                    visual_addr = f"{rua:02d}-{pred:02d}-{letras[idx]}{sub}"
                elif tipo_raw == "Gaiola":
                    visual_addr = f"GAIOLA-{rua:02d}"
                else:  # Porta-Palete
                    base = f"{rua:02d}-{pred:02d}-{niv:02d}"
                    visual_addr = f"{base}-{sub}" if sub else base

                cp["visual"] = visual_addr

                # --- 2. FINALIDADE (PICKING/PULMÃO) ---
                uso = r.get("Uso", "Pulmão")
                sku_f = r.get("SkuFixo", "")

                if uso == "Picking":
                    if sku_f:
                        cp["uso_desc"] = f"Picking Fixo"
                        if r.get("Ativo", True):
                            cp["_text_color"] = Colors.PRIMARY
                    else:
                        cp["uso_desc"] = "Picking"
                        if r.get("Ativo", True):
                            cp["_text_color"] = "#0891b2"
                else:
                    cp["uso_desc"] = uso

                    if uso == "Quarentena":
                        cp["_text_color"] = "#Eab308"

                # --- 3. STATUS INTELIGENTE ---
                is_active = r.get("Ativo", True)
                is_occupied = (visual_addr in ends_ocupados)

                if not is_active:
                    cp["status_uso"] = "Bloqueado"
                    cp["_text_color"] = Colors.TEXT_HINT
                elif is_occupied:
                    cp["status_uso"] = "Ocupado"
                    cp["_text_color"] = "#D97706"
                else:
                    cp["status_uso"] = "Livre"
                    if "_text_color" not in cp:
                        cp["_text_color"] = Colors.SUCCESS

                for k, v in cp.items():
                    if v is None:
                        cp[k] = "-"

                if not cp.get("SkuFixo"):
                    cp["SkuFixo"] = "-"

                processed.append(cp)

            # --- ORDENAÇÃO ---
            processed.sort(key=lambda x: x["visual"])

            # --- PAGINAÇÃO MANUAL ---
            start = (page - 1) * size
            end = start + size
            paginated_rows = processed[start:end]

            return total, paginated_rows

        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch, page_size=27, checkboxes=True)
        self.table.grid(row=0, column=0, sticky="new")

        # --- BOTÕES NA BARRA DA TABELA ---

        # 1. ESQUERDA: Operações Principais
        left_box = self.table.left_actions

        # Adicionar (Quadradinho)
        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16), padx=9,
                                  command=self._open_add)
        self.btn_add.pack(side="left", padx=(0, 10))

        # Editar (Quadradinho)
        self.btn_edit = PillButton(left_box, text="", variant="outline", icon=load_icon("edit", 16), padx=9,
                                   command=self._handle_smart_edit)
        self.btn_edit.pack(side="left", padx=(0, 10))
        self.btn_edit.state(["disabled"])

        # Excluir (Quadradinho)
        self.btn_del = PillButton(left_box, text="", variant="outline", icon=load_icon("delete", 16), padx=9,
                                  command=self._del_sel)
        self.btn_del.pack(side="left", padx=(0, 10))
        self.btn_del.state(["disabled"])

        # Ferramentas de Endereçamento (Mantêm texto pois são ações específicas)
        self.btn_areas = PillButton(left_box, text="Áreas", variant="outline", icon=load_icon("conf", 16),
                                    command=self._open_areas_manager)
        self.btn_areas.pack(side="left", padx=(0, 10))

        # 2. DIREITA: Impressão
        right_box = self.table.right_actions

        self.btn_print = PillButton(right_box, text="", padx=9, variant="outline", icon=load_icon("print", 16),
                                    command=self._open_print_dialog)
        self.btn_print.pack(side="right", padx=(10, 0))
        self.btn_print.state(["disabled"])

        self._tt_print = ToolTip(self.btn_print)
        self.btn_print.bind("<Enter>", lambda e: self._tt_print.show("Imprimir", e.x_root, e.y_root + 25), add="+")
        self.btn_print.bind("<Leave>", lambda e: self._tt_print.hide(), add="+")

        # Binds da Tabela
        self.table.bind("<<TableSelect>>", self._on_sel)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._handle_smart_edit())

    def _on_sel(self, e):
        has = (self.table.get_selected() is not None)
        self.btn_edit.state(["!disabled"] if has else ["disabled"])
        self.btn_del.state(["!disabled"] if has else ["disabled"])
        self.btn_print.state(["!disabled"] if has else ["disabled"])

    def on_show(self, **kwargs):
        self.table.load_page(1)
        self.table.body_canvas.focus_set()

    def _open_add(self):
        self._modal_single("add")

    def _handle_smart_edit(self):
        # Pega todos os itens selecionados (seja 1 ou 50)
        selecionados = self.table.get_all_selected()

        if not selecionados:
            return

        if len(selecionados) == 1:
            # Se for apenas 1, abre o modal de edição normal (com todos os campos)
            self._modal_single("edit", selecionados[0])
        else:
            # Se forem vários, abre o modal de edição em lote
            BatchEditAddressDialog(self, targets=selecionados, on_done=lambda: self.table.load_page(1))

    # O método _open_edit antigo pode ser removido ou mantido se for usado internamente
    def _open_edit(self):
        # Mantido apenas por compatibilidade, mas redireciona para o smart
        self._handle_smart_edit()

    def _del_sel(self):
        selecionados = self.table.get_all_selected()
        if not selecionados: return

        qtd_sel = len(selecionados)
        total_repo, _ = addresses_repo.list(1, 1, self.table.filters)
        pode_excluir_tudo = (total_repo > qtd_sel)

        top_scope = SaaSModal(self, title="Opções de Exclusão", width=450, height=320)
        frm = ttk.Frame(top_scope.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Defina o alcance desta ação:", font=("Segoe UI", 10, "bold"),
                 bg=Colors.BG_APP, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))
        tk.Label(frm, text=f"Você selecionou {qtd_sel} item(ns).", bg=Colors.BG_APP, fg="#6B7280").pack(anchor="w")

        var_delete_all = tk.BooleanVar(value=False)
        if pode_excluir_tudo:
            box = tk.Frame(frm, bg="#EFF6FF", bd=1, relief="solid")
            box.pack(fill="x", pady=15, ipady=5)
            BlueCheckButton(box, text=f"Excluir TODOS os {total_repo} endereços",
                            variable=var_delete_all, bg="#EFF6FF").pack(anchor="w", padx=10, pady=5)
        else:
            tk.Label(frm, text="(Apenas os itens selecionados serão excluídos)",
                     bg=Colors.BG_APP, fg=Colors.SUCCESS).pack(pady=10)

        def _processar():
            usar_global = var_delete_all.get()
            top_scope.close()
            self.after(50, lambda: self._step_2_analise(selecionados, usar_global))

        btn = ttk.Frame(frm, style="Main.TFrame")
        btn.pack(side="bottom", fill="x")
        PillButton(btn, text="Continuar", variant="primary", command=_processar).pack(side="right")
        PillButton(btn, text="Cancelar", variant="outline", command=top_scope.close).pack(side="right", padx=10)

    def _step_2_analise(self, selecionados_tela, usar_global):
        lista_processar = []
        if usar_global:
            _, lista_processar = addresses_repo.list(1, 1000000, self.table.filters)
        else:
            lista_processar = selecionados_tela

        candidatos = []
        import string
        letras = string.ascii_uppercase

        for r in lista_processar:
            if "visual" in r:
                vis = r["visual"]
            else:
                t, ru, p, n = r.get("Tipo"), r.get("Rua", 0), r.get("Predio", 0), r.get("Nivel", 0)
                sub = r.get("GrupoBloqueio", "")
                if t in ["Estante", "Picking"]:
                    idx = max(0, n - 1) % 26
                    vis = f"{ru:02d}-{p:02d}-{letras[idx]}{sub}"
                elif t == "Gaiola":
                    vis = f"GAIOLA-{ru:02d}"
                else:
                    base = f"{ru:02d}-{p:02d}-{n:02d}"
                    vis = f"{base}-{sub}" if sub else base

            candidatos.append({"Id": r["Id"], "visual": vis})

        ends_ocupados = {l["Endereco"] for l in lpn_repo.get_all() if l.get("QtdAtual", 0) > 0}

        ids_deletar = []
        count_bloqueados = 0

        for c in candidatos:
            if c["visual"] in ends_ocupados:
                count_bloqueados += 1
            else:
                ids_deletar.append(c["Id"])

        self._show_final_report(len(ids_deletar), count_bloqueados, ids_deletar)

    def _show_final_report(self, qtd_ok, qtd_block, ids_deletar):
        if qtd_ok == 0 and qtd_block == 0: return

        if qtd_ok == 0:
            top_err = SaaSModal(self, title="Ação Bloqueada", width=400, height=250)
            frm = ttk.Frame(top_err.content, style="Main.TFrame", padding=20)
            frm.pack(fill="both", expand=True)
            tk.Label(frm, text=f"Todos os {qtd_block} endereços selecionados possuem saldo.",
                     fg="#DC2626", bg=Colors.BG_APP, font=("Segoe UI", 10, "bold"), wraplength=350).pack(pady=20)
            tk.Label(frm, text="Esvazie os endereços antes de excluir.", bg=Colors.BG_APP).pack()
            PillButton(frm, text="Entendi", variant="outline", command=top_err.close).pack(side="bottom", anchor="e")
            return

        top_confirm = SaaSModal(self, title="Confirmar Exclusão", width=450, height=350)
        frm = ttk.Frame(top_confirm.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Resumo da Operação:", font=("Segoe UI", 11, "bold"),
                 bg=Colors.BG_APP, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 15))

        f_ok = tk.Frame(frm, bg=Colors.BG_APP)
        f_ok.pack(fill="x", pady=2)
        tk.Label(f_ok, text="✔", fg=Colors.SUCCESS, bg=Colors.BG_APP, font=("Segoe UI", 12)).pack(side="left")
        tk.Label(f_ok, text=f"{qtd_ok} endereços vazios serão excluídos.", fg=Colors.TEXT_MAIN, bg=Colors.BG_APP).pack(
            side="left", padx=10)

        if qtd_block > 0:
            f_bad = tk.Frame(frm, bg=Colors.BG_APP)
            f_bad.pack(fill="x", pady=8)
            tk.Label(f_bad, text="⚠", fg="#D97706", bg=Colors.BG_APP, font=("Segoe UI", 12)).pack(side="left")
            tk.Label(f_bad, text=f"{qtd_block} endereços serão MANTIDOS (possuem saldo).", fg="#D97706",
                     bg=Colors.BG_APP).pack(side="left", padx=10)

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=20)
        tk.Label(frm, text="Tem certeza que deseja continuar?", bg=Colors.BG_APP).pack(anchor="w")

        def _execute():
            try:
                for uid in ids_deletar: addresses_repo.delete(uid)
                # CORREÇÃO: Usando alert interno do modal top_confirm
                top_confirm.alert("Sucesso", f"{qtd_ok} endereços excluídos.", type="success")
                top_confirm.close()
                self.table.load_page(1)
            except Exception as e:
                top_confirm.alert("Erro", str(e), type="error")

        btn = ttk.Frame(frm, style="Main.TFrame")
        btn.pack(side="bottom", fill="x")
        PillButton(btn, text="Confirmar", variant="primary", command=_execute).pack(side="right")
        PillButton(btn, text="Cancelar", variant="outline", command=top_confirm.close).pack(side="right", padx=10)

    def _modal_single(self, mode, data=None):
        AddressDialog(self, mode, data, on_done=lambda: self.table.load_page(1))

    def _open_batch(self):
        BatchAddressDialog(self, on_done=lambda: self.table.load_page(1))

    def _open_print_dialog(self):
        sel_rows = self.table.get_all_selected()
        if not sel_rows: return
        PrintAddressesDialog(self, addresses=sel_rows)

    def _open_areas_manager(self):
        AreasManagerDialog(self)