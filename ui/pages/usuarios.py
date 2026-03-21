import tkinter as tk
from ui.components import Page, PillButton, StandardTable
from database.repositories import usuarios_repo
from utils.constants import PAGE_SIZE_DEFAULT
from utils.helpers import load_icon


class UsuariosPage(Page):
    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Definição das colunas solicitadas
        cols = [
            {"id": "Nome", "title": "Nome", "width": 200, "anchor": "w"},
            {"id": "Login", "title": "Login", "width": 120, "anchor": "center"},
            {"id": "Perfil", "title": "Perfil", "width": 120, "anchor": "center"},
            {"id": "ultimo_login_show", "title": "Último Login", "width": 150, "anchor": "center"},
            {"id": "ativo_show", "title": "Ativo", "width": 80, "anchor": "center"},
        ]

        # Função que conecta a tabela ao banco de dados
        def _fetch_data(page, size, filters):
            total, rows = usuarios_repo.list(page, size, filters)

            # Formatação visual dos dados para a tabela
            for r in rows:
                r["ativo_show"] = "Sim" if r["Ativo"] else "Não"
                dt = r["UltimoLogin"]
                r["ultimo_login_show"] = dt.strftime("%d/%m/%Y %H:%M") if dt else "-"

            return total, rows

        # Criação da tabela padrão do sistema
        self.table = StandardTable(self, columns=cols, fetch_fn=_fetch_data, page_size=PAGE_SIZE_DEFAULT)
        self.table.grid(row=0, column=0, sticky="nsew")

        # Barra de ferramentas (Botões de ação)
        left_box = self.table.left_actions
        self.btn_add = PillButton(left_box, text="", variant="primary", icon=load_icon("add", 16),
                                  padx=9, command=self._on_add)
        self.btn_add.pack(side="left", padx=(0, 10))

        # Registro de eventos da tabela
        self.table.bind("<<TableSelect>>", self._on_selection_change)

    def _on_selection_change(self, _e=None):
        # Lógica para habilitar/desabilitar botões de edição quando houver seleção
        pass

    def _on_add(self):
        # Lógica para abrir modal de cadastro
        pass

    def on_show(self, **kwargs):
        self.table.load_page(1)