import tkinter as tk
from tkinter import ttk
from ui.components import Page, PillButton, ScrollableFrame, ConferenciaModal, SupervisorAuthDialog
from database.repositories import recebimento_repo
from utils.constants import Colors


class AtividadesPage(Page):
    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Cabeçalho ---
        header = ttk.Frame(self, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        lbl_title = tk.Label(header, text="Minhas Atividades", font=("Segoe UI", 18, "bold"),
                             bg=Colors.BG_APP, fg=Colors.TEXT_MAIN)
        lbl_title.pack(side="left")

        # Filtros
        filtros_frame = tk.Frame(header, bg=Colors.BG_APP)
        filtros_frame.pack(side="right", padx=(0, 11))

        PillButton(filtros_frame, text="Tudo", variant="primary", height=28).pack(side="left", padx=4)
        PillButton(filtros_frame, text="Recebimento", variant="outline", height=28).pack(side="left", padx=4)

        # --- Área de Rolagem ---
        self.scroll = ScrollableFrame(self, padding=(20, 0, 35, 20), bg=Colors.BG_APP)
        self.scroll.grid(row=1, column=0, sticky="nsew")

        self.card_container = self.scroll.content
        self.card_container.columnconfigure(0, weight=1)

    def on_show(self, **kwargs):
        self.refresh_cards()

    def refresh_cards(self):
        for widget in self.card_container.winfo_children():
            widget.destroy()

        atividades = recebimento_repo.get_atividades_pendentes()

        if not atividades:
            lbl = tk.Label(self.card_container, text="Nenhuma atividade pendente. Bom trabalho! 🎉",
                           font=("Segoe UI", 14), fg="#9CA3AF", bg=Colors.BG_APP)
            lbl.pack(pady=50)
            return

        # Nota: ActivityCard precisa estar disponível. Se estava no main, mova para components.py
        from ui.components import ActivityCard

        for i, data in enumerate(atividades):
            card = ActivityCard(self.card_container, data, on_action=self.handle_card_action)
            card.pack(fill="x", pady=(0, 10))

    def handle_card_action(self, dados_atividade, action_type="main"):
        pr = dados_atividade['PrCode']

        if action_type == "main":
            def _ao_fechar_modal(precisa_atualizar):
                # Ignora a flag precisa_atualizar. Ao abrir e fechar a conferencia,
                # o status da sessão muda para "Iniciando...", exigindo refresh obrigatorio.
                self.refresh_cards()

            ConferenciaModal(self, pr_code=pr, on_close=_ao_fechar_modal)

        elif action_type == "cancel":
            tem_progresso = recebimento_repo.verificar_progresso(pr)

            if not tem_progresso:
                self.ask_yes_no(
                    "Desfazer Início",
                    "Nenhum item foi conferido ainda.\nDeseja desfazer o início e voltar para a fila?",
                    on_yes=lambda: self._executar_estorno(pr)
                )
            else:
                def _autorizado():
                    self._executar_estorno(pr, supervisor="Admin")

                SupervisorAuthDialog(self, on_success=_autorizado)

    def _executar_estorno(self, pr, supervisor=None):
        # Define quem está fazendo a ação para logar no histórico da FSM
        usuario_acao = f"Supervisor ({supervisor})" if supervisor else "Usuario Atual"

        # Chama a FSM em vez do método antigo
        sucesso, msg = recebimento_repo.executar_transicao(pr, "estornar_conferencia", usuario=usuario_acao)

        if sucesso:
            self.refresh_cards()
            self.alert("Estornado", "A conferência foi cancelada e voltou para a fila.", type="info")
        else:
            self.alert("Erro", f"Não foi possível estornar:\n{msg}", type="warning")