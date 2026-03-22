import tkinter as tk
from tkinter import ttk

from ui.components import Page, PillButton, StandardTable, SaaSModal, TextField, PillCombobox, ToggleSwitch
from database.repositories import usuarios_repo
from utils.constants import PAGE_SIZE_DEFAULT, Colors
from utils.helpers import load_icon


class UsuarioDialog(SaaSModal):
    def __init__(self, parent, mode, data=None, on_done=None):
        title = "Novo Usuário" if mode == "add" else "Editar Usuário"

        # Aumentamos um pouco a altura se for "add" para caber o campo de senha
        height = 480 if mode == "add" else 400
        super().__init__(parent, title, width=450, height=height)

        self.mode = mode
        self.data = data or {}
        self.on_done = on_done

        # Busca os perfis ativos direto do banco para popular a Combobox
        # Criamos um mapa { "Nome do Perfil": Id } para facilitar na hora de salvar
        res_perfis = usuarios_repo.execute_query("SELECT Id, Nome FROM Perfis ORDER BY Nome")

        self.perfis_map = {p["Nome"]: p["Id"] for p in res_perfis} if res_perfis else {}
        lista_perfis = list(self.perfis_map.keys())

        # Container Principal
        frm = ttk.Frame(self.content, style="Main.TFrame", padding=20)
        frm.pack(fill="both", expand=True)

        # ======================================================
        # TOPO DIREITO: STATUS (Toggle Switch)
        # ======================================================
        f_top = tk.Frame(frm, bg=Colors.BG_APP)
        f_top.pack(fill="x", pady=(0, 15))

        f_status = tk.Frame(f_top, bg=Colors.BG_APP)
        f_status.pack(side="right")

        self.var_ativo = tk.BooleanVar(value=True)
        ToggleSwitch(f_status, variable=self.var_ativo, on_color=Colors.SUCCESS, bg=Colors.BG_APP).pack(side="left")

        self.lbl_st = tk.Label(f_status, text="Ativo", font=("Segoe UI", 9, "bold"), fg=Colors.SUCCESS,
                               bg=Colors.BG_APP)
        self.lbl_st.pack(side="left", padx=(8, 0))

        def _update_st_label(*args):
            if self.var_ativo.get():
                self.lbl_st.config(text="Ativo", fg=Colors.SUCCESS)
            else:
                self.lbl_st.config(text="Inativo", fg=Colors.TEXT_HINT)

        self.var_ativo.trace_add("write", _update_st_label)

        # ======================================================
        # CAMPOS DO FORMULÁRIO
        # ======================================================

        # Nome Completo
        tk.Label(frm, text="Nome", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w",
                                                                                                 pady=(0, 2))
        self.ent_nome = TextField(frm, placeholder="Nome", height=34)
        self.ent_nome.pack(fill="x", pady=(0, 15))

        # Login
        tk.Label(frm, text="Login", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w",
                                                                                                    pady=(0, 2))
        self.ent_login = TextField(frm, placeholder="Login", height=34)
        self.ent_login.pack(fill="x", pady=(0, 15))

        # Perfil (Combobox)
        tk.Label(frm, text="Perfil de Acesso", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w",
                                                                                                    pady=(0, 2))
        self.cb_perfil = PillCombobox(frm, values=lista_perfis, placeholder="Selecione o perfil...", height=34)
        self.cb_perfil.pack(fill="x", pady=(0, 15))

        # Senha (Exibida apenas na criação)
        if self.mode == "add":
            tk.Label(frm, text="Senha", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(
                anchor="w", pady=(0, 2))

            # Placeholder com 6 pontinhos conforme solicitado
            self.ent_senha = TextField(frm, placeholder="●●●●●●", height=34)
            self.ent_senha._entry.config(show="●")
            self.ent_senha.pack(fill="x", pady=(0, 15))

        # ======================================================
        # RODAPÉ (Botões)
        # ======================================================
        box = ttk.Frame(frm, style="Main.TFrame")
        box.pack(side="bottom", fill="x", pady=(10, 0))

        PillButton(box, text="Salvar", variant="success", command=self._save).pack(side="right")
        PillButton(box, text="Cancelar", variant="outline", command=self.close).pack(side="right", padx=10)

        # ======================================================
        # CARREGAMENTO DOS DADOS (Modo Edição)
        # ======================================================
        if self.mode == "edit":
            self.ent_nome.insert(0, self.data.get("Nome", ""))
            self.ent_login.insert(0, self.data.get("Login", ""))

            perfil_salvo = self.data.get("Perfil", "")
            if perfil_salvo in lista_perfis:
                self.cb_perfil.set(perfil_salvo)

            self.var_ativo.set(self.data.get("Ativo", True))
            _update_st_label()

    def _save(self):
        nome = self.ent_nome.get().strip()
        login = self.ent_login.get().strip()
        perfil_nome = self.cb_perfil.get().strip()
        ativo = self.var_ativo.get()

        # Validações básicas
        if not nome or not login or not perfil_nome:
            self.alert("Atenção", "Preencha o Nome, Login e selecione um Perfil.")
            return

        perfil_id = self.perfis_map.get(perfil_nome)
        if not perfil_id:
            self.alert("Atenção", "O Perfil selecionado é inválido.")
            return

        try:
            if self.mode == "add":
                senha = self.ent_senha.get()

                # Validação estrita: exatamente 6 dígitos numéricos
                if not senha or not senha.isdigit() or len(senha) != 6:
                    self.alert("Atenção", "A senha deve conter 6 números.",
                               focus_widget=self.ent_senha)
                    return

                # A função criar_usuario no repositorio já faz o bcrypt interno
                # 1 é o ID genérico de sistema/admin provisório
                usuarios_repo.criar_usuario(perfil_id=perfil_id, nome=nome, login=login, senha_plana=senha,
                                            usuario_logado_id=1)
                self.alert("Sucesso", "Usuário criado com sucesso!", type="success")
            else:
                # Atualização via método genérico da BaseRepo
                usuarios_repo.update(uid=self.data["Id"], Nome=nome, Login=login, PerfilId=perfil_id, Ativo=ativo)
                self.alert("Sucesso", "Usuário atualizado com sucesso!", type="success")

            if self.on_done:
                self.on_done()
            self.close()

        except Exception as e:
            # Caso o login já exista, o banco vai disparar um erro de Unique Constraint
            if "UNIQUE" in str(e).upper() or "DUPLICATE" in str(e).upper():
                self.alert("Erro", "Já existe um usuário com este Login.", type="error")
            else:
                self.alert("Erro de Sistema", f"Falha ao salvar o usuário:\n{str(e)}", type="error")


class UsuariosPage(Page):
    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        # Definição das colunas da tabela
        cols = [
            {"id": "Nome", "title": "Nome", "width": 200, "anchor": "w"},
            {"id": "Login", "title": "Login", "width": 120, "anchor": "center"},
            {"id": "Perfil", "title": "Perfil", "width": 120, "anchor": "center"},
            {"id": "ultimo_login_show", "title": "Último Login", "width": 150, "anchor": "center"},
            {"id": "ativo_show", "title": "Status", "width": 100, "anchor": "center"},
        ]

        def _fetch_data(page, size, filters):
            total, rows = usuarios_repo.list(page, size, filters)

            # Formatação visual dos dados para a tabela
            for r in rows:
                is_ativo = r.get("Ativo", True)
                r["ativo_show"] = "Ativo" if is_ativo else "Inativo"

                # Muda a cor do texto se estiver inativo
                if not is_ativo:
                    r["_text_color"] = Colors.TEXT_HINT

                dt = r.get("UltimoLogin")
                r["ultimo_login_show"] = dt.strftime("%d/%m/%Y %H:%M") if dt else "-"

            return total, rows

        # Criação da tabela padrão do sistema
        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch_data, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="new")

        # Barra de ferramentas (Botões de ação)
        left_box = self.table.left_actions

        # Botão Adicionar
        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16),
                                  padx=9, command=self._on_add)
        self.btn_add.pack(side="left", padx=(0, 10))

        # Botão Editar
        self.btn_edit = PillButton(left_box, text="", variant="outline", icon=load_icon("edit", 16),
                                   padx=9, command=self._on_edit)
        self.btn_edit.pack(side="left", padx=(0, 10))
        self.btn_edit.state(["disabled"])  # Começa desabilitado

        # Registro de eventos da tabela
        self.table.bind("<<TableSelect>>", self._on_selection_change)
        self.table.bind("<<TableDoubleClick>>", lambda e: self._on_edit())

    def _on_selection_change(self, _e=None):
        # Habilita o botão de edição apenas se houver uma linha selecionada
        has_selection = (self.table.get_selected() is not None)
        self.btn_edit.state(["!disabled"] if has_selection else ["disabled"])

    def _on_add(self):
        # Abre o modal no modo de criação e recarrega a tabela ao salvar
        UsuarioDialog(self, mode="add", on_done=lambda: self.table.load_page(1))

    def _on_edit(self):
        selecionado = self.table.get_selected()
        if not selecionado:
            return
        # Abre o modal passando os dados da linha selecionada
        UsuarioDialog(self, mode="edit", data=selecionado, on_done=lambda: self.table.load_page(self.table.page))

    def on_show(self, **kwargs):
        self.table.load_page(1)