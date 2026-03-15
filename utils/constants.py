PAGE_SIZE_DEFAULT = 18
FONT_BTN = ("Segoe UI", 10, "bold")
ARROW_FONT = ("Segoe UI", 10)
SUB_FONT = ("Segoe UI", 10)
GAP_Y = 6
TOP_PAD = 6
MARKER_W = 12


class Colors:
    # Fundos
    BG_APP = "#F8F9FB"
    BG_SIDEBAR = "#004477"
    BG_CARD = "#FFFFFF"

    # Cores de Input
    BG_INPUT = "#FFFFFF"  # Branco puro quando habilitado
    BG_DISABLED = "#F0F2F5"  # Cinza suave quando desabilitado

    # Tabelas e Seleção
    ROW_HOVER_SB = "#1D6197"
    ROW_SELECTED = "#DBEAFE"
    HEADER_TABLE = "#E8EEF6"

    # Ações e Status
    PRIMARY = "#1A63B6"
    PRIMARY_HOVER = "#3173BD"
    SUCCESS = "#09A7A5"
    SUCCESS_HOVER = "#0BB5B3"

    DANGER = "#CF3F3E"
    DANGER_HOVER = "#D95251"

    WARNING = "#FAC82B"
    WARNING_HOVER = "#FBD265"

    # Texto e Bordas
    TEXT_MAIN = "#111827"
    TEXT_SIDEBAR = "#ffffff"
    TEXT_HINT = "#9CA3AF"

    BORDER = "#C6CDDD"
    BORDER_FOCUS = "#93C5FD"
    BORDER_LIGHT = "#E5E7EB"


class StatusPR:
    # --- Configurações / Regras ---
    LIMITE_TENTATIVAS = 3

    # --- Constantes (Fonte da Verdade) ---
    PROCESSANDO = "Processando..."
    AGUARDANDO_VINCULO = "Aguardando Vinculação"
    AGUARD_VINC_UNID = "Aguard. Vinc."
    AGUARDANDO_LIBERACAO = "Aguardando Liberação"
    BLOQUEADO_FISCAL = "Bloqueado Fiscal"
    AGUARDANDO_CONF = "Aguardando Conf."
    EM_CONFERENCIA = "Em Conferência"
    EM_ANALISE = "Em Análise"  # Divergência Visual/Qualidade
    AGUARDANDO_DECISAO = "Aguardando Decisão"  # Divergência de Quantidade
    AGUARDANDO_CONCLUSAO = "Aguardando Conclusão"  # Conferência OK, esperando Fiscal

    # ESTADOS TERMINAIS (Definidos por evento, não por cálculo)
    RECUSADO = "Recusado"
    CONCLUIDO = "Concluído"
    CANCELADO = "Cancelado"
    ESTORNADO = "Estornado"

    DIVERGENCIA = "Divergência"
    # --- 1. Motor de Pesos (Hierarquia) ---
    @classmethod
    def get_peso(cls, status):
        # Define a gravidade absoluta. O maior número prevalece.

        pesos = {
            cls.BLOQUEADO_FISCAL: 100,
            cls.PROCESSANDO: 99,
            cls.AGUARDANDO_VINCULO: 98,
            cls.AGUARD_VINC_UNID: 97,
            cls.DIVERGENCIA: 95,
            cls.EM_ANALISE: 90,
            cls.AGUARDANDO_DECISAO: 85,
            cls.AGUARDANDO_LIBERACAO: 70,
            cls.EM_CONFERENCIA: 60,
            cls.AGUARDANDO_CONF: 50,
            cls.AGUARDANDO_CONCLUSAO: 25,
            cls.CONCLUIDO: 0,
            cls.RECUSADO: 0,
            cls.CANCELADO: 0
        }
        return pesos.get(status, 0)

    # --- 2. O Diagnóstico Inteligente ---
    @classmethod
    def diagnosticar(cls, tem_sku, unidade_valida, oc_existe, eh_bonificacao,
                     item_fora_da_oc, eh_parcial, div_excedente,
                     div_preco_maior, div_preco_menor,
                     div_qualidade, liberado, iniciado, finalizado,
                     excedeu_tentativas):

        candidatos = []

        # --- 1. BLOQUEIOS ESTRUTURAIS (Peso 100) ---

        if not eh_bonificacao:
            # Sem OC no sistema -> Bloqueia Fiscal
            if not oc_existe:
                candidatos.append(cls.BLOQUEADO_FISCAL)

            # Item não pedido -> Gera divergência
            elif item_fora_da_oc:
                candidatos.append(cls.DIVERGENCIA)

        # --- 2. DIVERGÊNCIAS (Peso 90-96) ---

        if not eh_bonificacao:
            # Preço Maior -> Divergência (Grave)
            if div_preco_maior:
                candidatos.append(cls.DIVERGENCIA)

                # Preço Menor -> Divergência (Pode ser alerta, mas marcamos divergência para análise)
            if div_preco_menor:
                candidatos.append(cls.DIVERGENCIA)

            # Divergência de regra:
            if excedeu_tentativas:
                candidatos.append(cls.AGUARDANDO_DECISAO)

            # Excedente -> Divergência de Quantidade (Agora tem nome específico)
            if div_excedente:
                candidatos.append(cls.AGUARDANDO_DECISAO)

                # Qualidade (Avaria)
        if div_qualidade:
            candidatos.append(cls.EM_ANALISE)

        # --- 3. TRAVAS OPERACIONAIS (Peso 80) ---
        if not tem_sku:
            candidatos.append(cls.AGUARDANDO_VINCULO)
        elif not unidade_valida:  # Nova Trava
            candidatos.append(cls.AGUARD_VINC_UNID)

        # --- 4. STATUS OPERACIONAL ---
        # (Só chegamos aqui se não houver bloqueios graves acima)

        if finalizado:
            candidatos.append(cls.AGUARDANDO_CONCLUSAO)
        elif iniciado:
            candidatos.append(cls.EM_CONFERENCIA)
        elif liberado:
            candidatos.append(cls.AGUARDANDO_CONF)
        else:
            candidatos.append(cls.AGUARDANDO_LIBERACAO)

        # Nota sobre eh_parcial:
        # Entrega parcial não bloqueia o recebimento,
        # então ela não adiciona status de erro na lista, permitindo seguir para 'Aguardando Conf'.

        return cls.calcular_status_predominante(candidatos)

    # --- 3. O Juiz (Cálculo) ---
    @classmethod
    def calcular_status_predominante(cls, lista_status):
        if not lista_status: return cls.AGUARDANDO_CONF

        validos = [s for s in lista_status if s]
        if not validos: return cls.AGUARDANDO_CONF

        # Ordena pelo peso (maior primeiro) e pega o topo
        validos.sort(key=lambda s: cls.get_peso(s), reverse=True)
        return validos[0]

    # --- 4. O Escrivão ---
    @classmethod
    def motivo_status_pr(cls, status,
                         oc_existe=True, item_fora_da_oc=False,
                         div_excedente=False, div_preco_maior=False, div_preco_menor=False,
                         tem_sku=True, unidade_valida=True, sku_oc=None, preco_nf=0, preco_oc=0,
                         excedeu_tentativas=False,
                         itens_header=None):

        # --- MODO CABEÇALHO (Resumo) ---
        if itens_header is not None:
            qtd_afetada = sum(
                1 for i in itens_header if i.get('Status') == status or i.get('StatusCalculado') == status)
            termo = "item" if qtd_afetada == 1 else "itens"

            if status == cls.BLOQUEADO_FISCAL:
                return f"• Há {qtd_afetada} {termo} inválido ou OC desconhecida"
            elif status == cls.AGUARDANDO_VINCULO:
                return f"• Há {qtd_afetada} {termo} aguardando vínculo"
            elif status == cls.AGUARD_VINC_UNID:
                return f"• Há {qtd_afetada} {termo} com unidade desconhecida"
            elif status == cls.AGUARDANDO_DECISAO:
                return f"• Há {qtd_afetada} {termo} aguardando decisão"
            elif status == cls.DIVERGENCIA:
                return f"• Há {qtd_afetada} {termo} com divergência de preço"
            elif status == cls.EM_ANALISE:
                return f"• Há {qtd_afetada} {termo} em análise de qualidade"

            return None

        # --- MODO ITEM (Detalhe) ---
        motivos = []

        # 1. BLOQUEADO FISCAL
        if status == cls.BLOQUEADO_FISCAL:
            if not oc_existe:
                motivos.append("OC não encontrada ou inválida")
            if item_fora_da_oc:
                motivos.append("Item não consta na OC")

        # 2. DIVERGÊNCIA (Preço)
        elif status == cls.DIVERGENCIA:
            diff = preco_nf - preco_oc
            if div_preco_maior:
                motivos.append(f"Preço Unitário MAIOR que na OC (+R$ {diff:.2f})")
            if div_preco_menor:
                motivos.append(f"Preço Unitário MENOR que na OC (R$ {diff:.2f})")

        # 3. AGUARDANDO DECISÃO (Quantidade)
        elif status == cls.AGUARDANDO_DECISAO:
            if excedeu_tentativas:
                motivos.append("Excesso de tentativas incorretas")
            if div_excedente:
                motivos.append("Quantidade excede o saldo da OC")

        # 4. AGUARDANDO VINCULAÇÃO
        elif status == cls.AGUARDANDO_VINCULO:
            if not tem_sku:
                motivos.append("Produto novo ou sem vínculo")

        elif status == cls.AGUARD_VINC_UNID:
            if not unidade_valida:
                motivos.append("Unidade não cadastrada nas embalagens do produto")

        if not motivos:
            return None

        return "\n".join([f"• {m}" for m in motivos])

    # --- Métodos Auxiliares ---
    @classmethod
    def permite_liberacao_doca(cls, status):
        # Só permite liberar se estiver parado na etapa de liberação ou com travas fiscais/qualidade
        return status in [cls.AGUARDANDO_LIBERACAO, cls.BLOQUEADO_FISCAL, cls.DIVERGENCIA, cls.EM_ANALISE]

    @classmethod
    def exige_analise_fiscal(cls, status):
        return status in [cls.AGUARDANDO_DECISAO, cls.BLOQUEADO_FISCAL, cls.DIVERGENCIA]

    @classmethod
    def exige_analise_visual(cls, status):
        return status == cls.EM_ANALISE

    @classmethod
    def pode_receber_vinculo(cls, status):
        # Permitimos vincular mesmo se estiver Aguardando Liberação para adiantar
        return status in [cls.AGUARDANDO_VINCULO, cls.BLOQUEADO_FISCAL, cls.AGUARDANDO_LIBERACAO]