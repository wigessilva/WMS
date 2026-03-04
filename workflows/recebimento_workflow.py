from datetime import datetime
from transitions import Machine
from utils.constants import StatusPR, Colors


class RecebimentoWorkflow:

    states = [
        StatusPR.AGUARDANDO_VINCULO,
        StatusPR.AGUARDANDO_LIBERACAO,
        StatusPR.BLOQUEADO_FISCAL,
        StatusPR.AGUARDANDO_CONF,
        StatusPR.EM_CONFERENCIA,
        StatusPR.EM_ANALISE,
        StatusPR.AGUARDANDO_DECISAO,
        StatusPR.DIVERGENCIA,
        StatusPR.AGUARDANDO_CONCLUSAO,
        StatusPR.CONCLUIDO,
        StatusPR.CANCELADO,
        StatusPR.RECUSADO
    ]

    def __init__(self, pr_data, repo_instance=None):
        self.pr_data = pr_data
        self.repo = repo_instance

        # Garante que temos um status válido
        initial_state = pr_data.get('Status') or StatusPR.AGUARDANDO_VINCULO

        # Se o status do banco não estiver na lista (ex: status antigo), fallback seguro
        if initial_state not in self.states:
            initial_state = StatusPR.AGUARDANDO_VINCULO

        self.state = initial_state
        self.machine = Machine(model=self, states=self.states, initial=initial_state)

        # --- DEFINIÇÃO DAS TRANSIÇÕES ---

        # 1. Liberação
        self.machine.add_transition(
            trigger='liberar_conferencia',
            source=[StatusPR.AGUARDANDO_LIBERACAO, StatusPR.BLOQUEADO_FISCAL, StatusPR.DIVERGENCIA,
                    StatusPR.EM_ANALISE],
            dest=StatusPR.AGUARDANDO_CONF,
            conditions=['_check_pode_liberar']
        )

        # 2. Início do Trabalho
        self.machine.add_transition(
            trigger='iniciar_conferencia',
            source=StatusPR.AGUARDANDO_CONF,
            dest=StatusPR.EM_CONFERENCIA
        )

        # 3. Bloqueios
        self.machine.add_transition(
            trigger='bloquear_fiscal',
            source=[StatusPR.AGUARDANDO_LIBERACAO, StatusPR.AGUARDANDO_CONF, StatusPR.EM_CONFERENCIA,
                    StatusPR.EM_ANALISE, StatusPR.AGUARDANDO_DECISAO, StatusPR.DIVERGENCIA],
            dest=StatusPR.BLOQUEADO_FISCAL
        )

        self.machine.add_transition(
            trigger='registrar_divergencia_visual',
            source=[StatusPR.EM_CONFERENCIA, StatusPR.AGUARDANDO_CONF],
            dest=StatusPR.EM_ANALISE
        )

        self.machine.add_transition(
            trigger='registrar_divergencia_qtd',
            source=[StatusPR.EM_CONFERENCIA],
            dest=StatusPR.AGUARDANDO_DECISAO
        )

        # 4. Resolução
        self.machine.add_transition(
            trigger='resolver_divergencia',
            source=[StatusPR.EM_ANALISE, StatusPR.AGUARDANDO_DECISAO, StatusPR.BLOQUEADO_FISCAL],
            dest=StatusPR.EM_CONFERENCIA
        )

        # 5. Finalização
        self.machine.add_transition(
            trigger='concluir_recebimento',
            # Adicionado AGUARDANDO_CONCLUSAO na lista de origem
            source=[StatusPR.EM_CONFERENCIA, StatusPR.AGUARDANDO_DECISAO, StatusPR.EM_ANALISE,
                    StatusPR.AGUARDANDO_CONCLUSAO],
            dest=StatusPR.CONCLUIDO,
            conditions=['_check_tudo_conferido']
        )

        # Transição para Recusa Total
        self.machine.add_transition(
            trigger='rejeitar_recebimento',
            source='*',
            dest=StatusPR.RECUSADO
        )

        # 6. Cancelamento
        estados_cancelaveis = [s for s in self.states if s not in [StatusPR.CONCLUIDO, StatusPR.CANCELADO]]
        self.machine.add_transition(
            trigger='cancelar_recebimento',
            source=estados_cancelaveis,
            dest=StatusPR.CANCELADO
        )

        # 7. Gestão de Fluxo
        self.machine.add_transition(
            trigger='desfazer_liberacao',
            source=[StatusPR.AGUARDANDO_CONF,
                    StatusPR.EM_CONFERENCIA,],
            dest=StatusPR.AGUARDANDO_LIBERACAO,
            after='_callback_limpeza_dados'
        )

        # 8. Estorno
        self.machine.add_transition(
            trigger='estornar_conferencia',
            source=[StatusPR.EM_CONFERENCIA, StatusPR.EM_ANALISE, StatusPR.AGUARDANDO_DECISAO, StatusPR.DIVERGENCIA],
            dest=StatusPR.AGUARDANDO_CONF,
            after='_callback_limpeza_dados'
        )

    # --- GUARDS ---

    def _check_pode_liberar(self):
        if self.pr_data.get('Status') == StatusPR.AGUARDANDO_VINCULO:
            return False
        return True

    def _check_tudo_conferido(self):
        return True

    # --- CALLBACKS ---

    def _callback_limpeza_dados(self):
        if self.repo and hasattr(self.repo, '_limpar_dados_conferencia_interno'):
            self.repo._limpar_dados_conferencia_interno(self.pr_data.get('pr'))

    # --- HELPER UI ---

    def get_acoes_disponiveis(self):
        acoes = []
        for trigger in self.machine.get_triggers(self.state):
            if not trigger.startswith('to_'):
                acoes.append(trigger)
        return acoes

    @classmethod
    def get_status_label(cls, status_raw):
        # Traduz o status técnico para texto amigável na grid
        mapa = {
            StatusPR.AGUARDANDO_VINCULO: "Aguard. Vinc.",
            StatusPR.AGUARD_VINC_UNID: "Aguard. Unidade",
            StatusPR.AGUARDANDO_LIBERACAO: "Aguard. Lib.",
            StatusPR.BLOQUEADO_FISCAL: "Bloqueado",
            StatusPR.AGUARDANDO_CONF: "Aguard. Conf.",
            StatusPR.EM_CONFERENCIA: "Em Conf.",
            StatusPR.AGUARDANDO_DECISAO: "Aguard. Decisão",
            StatusPR.AGUARDANDO_CONCLUSAO: "Aguard. Fiscal",
            StatusPR.RECUSADO: "Recusado Total",
            StatusPR.DIVERGENCIA: "Divergência",
            StatusPR.EM_ANALISE: "Em Análise",
            StatusPR.CONCLUIDO: "Concluído",
            StatusPR.CANCELADO: "Cancelado"
        }
        return mapa.get(status_raw, status_raw)

    @classmethod
    def get_status_color(cls, status_raw):
        if status_raw in [StatusPR.BLOQUEADO_FISCAL, StatusPR.AGUARDANDO_VINCULO,
                          StatusPR.EM_ANALISE, StatusPR.AGUARDANDO_DECISAO, StatusPR.DIVERGENCIA, StatusPR.AGUARD_VINC_UNID]:
            return "#D97706"

        if status_raw == StatusPR.CONCLUIDO:
            return "#09A7A5"

        if status_raw == StatusPR.CANCELADO:
            return "#9CA3AF"

        if status_raw == StatusPR.AGUARDANDO_CONCLUSAO:
            return "#8B5CF6"

        if status_raw == StatusPR.RECUSADO:
            return "#EF4444"

        return None

    # =========================================================================
    # Contexto de UI (Capabilities)
    # =========================================================================

    def get_contexto_ui(self):
        # Retorna um objeto rico com tudo que a UI precisa saber sobre o estado atual.

        # 1. Detecta quais transições (botões de ação) são possíveis agora
        triggers = self.machine.get_triggers(self.state)
        # Filtra transições internas (que começam com 'to_' ou '_')
        acoes_disponiveis = [t for t in triggers if not t.startswith('to_') and not t.startswith('_')]

        return {
            "estado_atual": self.state,
            "cor_estado": self._get_cor_visual(),
            "rotulo_estado": self.state,  # Pode usar um map para nomes amigáveis se quiser
            "acoes_workflow": acoes_disponiveis,

            # Capacidades Específicas (Capabilities)
            "pode_vincular": self._capability_vincular(),
            "pode_editar_destino": self._capability_editar_destino(),
            "pode_gerenciar_painel": True,  # Painel sempre disponível para leitura

            # Dicas de UI
            "mensagem_bloqueio": self.pr_data.get("ObsFiscal") if "Bloqueado" in self.state else None
        }

    def _get_cor_visual(self):
        # Centraliza a lógica de cores baseada no estado"""
        if self.state in [StatusPR.BLOQUEADO_FISCAL, StatusPR.DIVERGENCIA, StatusPR.AGUARDANDO_DECISAO]:
            return "#D97706"  # Warning/Laranja (ou Colors.WARNING se importar)
        if self.state in [StatusPR.CANCELADO, StatusPR.AGUARDANDO_VINCULO]:
            return Colors.TEXT_HINT  # Cinza
        if self.state == StatusPR.CONCLUIDO:
            return Colors.SUCCESS  # Verde

        # Padrão
        return Colors.PRIMARY

    # --- Regras de Negócio (Capabilities) ---

    def _capability_vincular(self):

        # Define quando o botão 'Vincular SKU' deve estar habilitado.
        # Regra: Pode vincular se estiver esperando vínculo, bloqueado ou aguardando liberação.
        # Não pode se já estiver em conferência ou concluído.

        estados_permitidos = [
            StatusPR.AGUARDANDO_VINCULO,
            StatusPR.BLOQUEADO_FISCAL,
            StatusPR.AGUARDANDO_LIBERACAO
        ]
        return self.state in estados_permitidos

    def _capability_editar_destino(self):

        # Define quando podemos alterar o destino dos itens.
        # Regra: Pode alterar enquanto não estiver Concluído ou Cancelado.

        bloqueados = [StatusPR.CONCLUIDO, StatusPR.CANCELADO]
        return self.state not in bloqueados