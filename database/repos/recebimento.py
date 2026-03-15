import glob
import json
import os
import shutil
import sys
import defusedxml.ElementTree as ET
import re
from datetime import datetime

from utils.constants import StatusPR
from utils.helpers import Utils
from ..base import BaseRepo
from .movimentacao import MovementsRepo
from workflows.recebimento_workflow import RecebimentoWorkflow

# Cálculo de ROOT para buscar arquivos
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class OcRepo(BaseRepo):
    def __init__(self):
        # Conecta no ERP_DB
        super().__init__(database="ERP_DB")

    def get_oc(self, numero_oc):
        if not numero_oc: return None

        chave = str(numero_oc).strip().lstrip("0")

        # 1. Busca Cabeçalho (Usamos AS para garantir o nome da chave)
        query_header = """
            SELECT 
                NumeroOC AS NumeroOC, 
                Fornecedor AS Fornecedor 
            FROM PedidosCompra 
            WHERE NumeroOC LIKE ?
        """
        header_res = self.execute_query(query_header, (f"%{chave}",))

        if not header_res:
            return None

        header = header_res[0]
        full_oc_num = header['NumeroOC']
        fornecedor = header['Fornecedor']

        # 2. Busca Itens
        query_itens = """
                    SELECT 
                        Sku AS Sku, 
                        Descricao AS Descricao, 
                        Qtd AS Qtd, 
                        ISNULL(QtdRecebida, 0) AS QtdRecebida,
                        PrecoUnitario AS PrecoUnitario,
                        Und AS Und
                    FROM PedidosCompraItens 
                    WHERE NumeroOC = ?
                """
        itens_res = self.execute_query(query_itens, (full_oc_num,))

        itens_dict = {}
        for row in itens_res:
            r_sku = row['Sku']
            r_desc = row['Descricao']
            r_qtd = row['Qtd']
            r_qtd_rec = row['QtdRecebida']
            r_preco = row['PrecoUnitario']
            r_und = row.get('Und', 'UN')

            if r_sku not in itens_dict:
                itens_dict[r_sku] = {
                    "Sku": r_sku,
                    "Descricao": r_desc,
                    "Qtd": 0.0,
                    "QtdRecebida": 0.0,
                    "Preco": 0.0,
                    "Und": r_und
                }

            itens_dict[r_sku]["Qtd"] += float(r_qtd)
            itens_dict[r_sku]["QtdRecebida"] += float(r_qtd_rec)
            itens_dict[r_sku]["Preco"] = float(r_preco)

        return {
            "Oc": full_oc_num,
            "Fornecedor": fornecedor,
            "itens": itens_dict
        }


class RecebimentoRepo(BaseRepo):
    def __init__(self, oc_repo, products_repo, lpn_repo, locations_repo, addresses_repo, product_alias_repo, units_repo,
                 unit_alias_repo, global_policies, event_bus=None):
        super().__init__("Recebimento")

        self.oc_repo = oc_repo
        self.products_repo = products_repo
        self.lpn_repo = lpn_repo
        self.locations_repo = locations_repo
        self.addresses_repo = addresses_repo
        self.product_alias_repo = product_alias_repo
        self.units_repo = units_repo
        self.unit_alias_repo = unit_alias_repo
        self.global_policies = global_policies
        self.event_bus = event_bus
        self.vinculo_service = VinculoService(self)
        self.processed_keys = self._load_history_sql()

        if self.event_bus:
            # 1. Listener de Configurações
            self.event_bus.subscribe("policy_changed", lambda data: self.recalcular_todos_prs_abertos())

            # 2. Listener de Conclusão (O próprio Recebimento reage para gravar histórico)
            self.event_bus.subscribe("recebimento_concluido", lambda data: self._ao_concluir_recebimento(data))

            self.event_bus.subscribe("produto_alterado", lambda data: self.recalcular_prs_por_sku(data.get("sku")))

            self.event_bus.subscribe("familia_alterada", lambda data: self.recalcular_todos_prs_abertos())

            self.event_bus.subscribe("alias_unidade_alterado", lambda data: self.recalcular_todos_prs_abertos())

            self.event_bus.subscribe("alias_produto_criado", lambda data: self.verificar_viculos_automaticos())

    def _load_history_sql(self):
        try:
            res = self.execute_query("SELECT ChaveNfe FROM HistoricoXml")
            return {r['ChaveNfe'] for r in res}
        except:
            return set()

    def recalcular_prs_por_sku(self, sku):
        if not sku: return
        # Busca apenas recebimentos ABERTOS que contenham este SKU
        query = f"""
            SELECT DISTINCT r.PrCode 
            FROM Recebimento r
            JOIN RecebimentoItens i ON r.PrCode = i.PrCode
            WHERE i.Sku = ? AND r.Status NOT IN ('{StatusPR.CONCLUIDO}', '{StatusPR.CANCELADO}')
        """
        try:
            res = self.execute_query(query, (str(sku).strip(),))
            for row in res:
                self.recalcular_status_geral(row['PrCode'], "Sistema (Trigger Produto)")
                print(f"Recalculado PR {row['PrCode']} devido alteração no SKU {sku}")
        except Exception as e:
            print(f"Erro ao recalcular PRs por SKU: {e}")

    def _save_history_key(self, chave_nfe):
        try:
            self.execute_non_query("INSERT INTO HistoricoXml (ChaveNfe, DataProcessamento) VALUES (?, ?)",
                                   (chave_nfe, datetime.now()))
            self.processed_keys.add(chave_nfe)
        except:
            pass

    def add_recebimento(self, **kwargs):
        agora_dt = datetime.now()
        ano = agora_dt.year

        # Gera PrCode
        res = self.execute_query("SELECT COUNT(*) as Qtd FROM Recebimento WHERE PrCode LIKE ?", (f"PR-{ano}-%",))
        seq = res[0]['Qtd'] + 1
        pr_code = f"PR-{ano}-{seq:04d}"

        # Extração Padronizada (TitleCase)
        nfe = kwargs.get("Nfe")
        fornecedor = kwargs.get("Fornecedor")
        cnpj = kwargs.get("Cnpj")
        oc = kwargs.get("Oc")
        data_chegada = kwargs.get("DataChegada", "-")
        status = kwargs.get("Status", StatusPR.PROCESSANDO)
        conferente = kwargs.get("Conferente", "")
        obs = kwargs.get("ObsFiscal", "")

        data_str = agora_dt.strftime("%d/%m/%Y %H:%M")

        query = """
                    INSERT INTO Recebimento (PrCode, Nfe, Fornecedor, Cnpj, Oc, DataChegada, Status, Conferente, 
                                             ObsFiscal, Cadastro, Alteracao, RowVersion, HistoricoTentativas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '[]')
                """
        self.execute_non_query(query, (pr_code, nfe, fornecedor, cnpj, oc, data_chegada, status, conferente,
                                       obs, agora_dt, data_str))
        return pr_code

    def add_item(self, **kwargs):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Extração Padronizada (TitleCase)
        pr = kwargs.get("PrCode")
        sku = kwargs.get("Sku")
        desc = kwargs.get("Descricao")
        qtd = float(kwargs.get("Qtd", 0))
        und = kwargs.get("Und")

        lote = kwargs.get("Lote", "")
        fab = kwargs.get("Fab", "")
        val = kwargs.get("Val", "")
        venc = kwargs.get("Vencimento", "")

        int_emb = kwargs.get("IntEmb", "")
        int_mat = kwargs.get("IntMat", "")
        ident = kwargs.get("Identificacao", "")
        cert_qual = kwargs.get("CertQual", "")

        try:
            larg = float(kwargs.get("Larg", 0))
        except:
            larg = 0.0

        try:
            comp = float(kwargs.get("Comp", 0))
        except:
            comp = 0.0

        status = kwargs.get("Status", StatusPR.PROCESSANDO)
        destino = kwargs.get("Destino", "")
        ean_nota = kwargs.get("EanNota", "")
        preco = float(kwargs.get("Preco", 0.0))

        cod_orig = kwargs.get("CodOrig", "")
        eh_bonificacao = 1 if kwargs.get("EhBonificacao") else 0
        desc_xml = kwargs.get("DescricaoXml", "")

        query = """
            INSERT INTO RecebimentoItens (PrCode, Sku, Descricao, Qtd, Und, Lote, Fab, Val, Vencimento, 
                                          IntEmb, IntMat, Identificacao, CertQual, Larg, Comp, Status, 
                                          Destino, EanNota, Preco, Cadastro, Alteracao, RowVersion, 
                                          QtdColetada, DadosQualidade, CodOrig, EhBonificacao, DescricaoXml)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, '{}', ?, ?, ?)
        """
        self.execute_non_query(query, (pr, sku, desc, qtd, und, lote, fab, val, venc, int_emb, int_mat,
                                       ident, cert_qual, larg, comp, status, destino, ean_nota, preco,
                                       agora, agora, cod_orig, eh_bonificacao, desc_xml))

    def _calcular_status_real_item(self, item, header_status, unidade_valida=True):

        # ==============================================================================
        # TRAVA DE STATUS FINAL E BLOQUEIOS
        # Se o item já está finalizado ou bloqueado (ex: excesso de tentativas),
        # pula o recálculo de divergências e preserva a decisão do sistema.
        # ==============================================================================
        status_banco = item.get('Status')
        status_finais = [
            StatusPR.CONCLUIDO,
            StatusPR.CANCELADO,
            StatusPR.RECUSADO,
            StatusPR.BLOQUEADO_FISCAL,
            StatusPR.AGUARDANDO_DECISAO
        ]

        if status_banco in status_finais:
            return status_banco, item.get('ObsFiscal') or ""

        if header_status in status_finais:
            return header_status, ""

        # ==============================================================================
        # [TRAVA 2 - TRAVA DE CONFERÊNCIA PARCIAL (LPN)
        # ==============================================================================
        dados_raw = item.get("dados_qualidade") or item.get("DadosQualidade") or "{}"
        if isinstance(dados_raw, str):
            import json
            try:
                dq = json.loads(dados_raw)
            except:
                dq = {}
        else:
            dq = dados_raw

        if dq.get("eh_parcial") is True:
            return StatusPR.EM_CONFERENCIA, ""

        sku_nota = str(item.get('Sku') or "").upper()
        qtd_nota = float(item.get('Qtd') or 0)
        preco_nota = float(item.get('Preco') or 0)
        dados_oc_global = item.get('_dados_oc', {})
        oc_existe_erp = item.get('_oc_existe_erp', False)

        dados_item_oc = dados_oc_global.get(sku_nota)

        # --- LÓGICA DE SALDO PENDENTE ---
        qtd_oc_total = float(dados_item_oc['Qtd']) if dados_item_oc else 0.0
        qtd_oc_recebida = float(dados_item_oc.get('QtdRecebida', 0.0)) if dados_item_oc else 0.0
        qtd_oc = max(0.0, qtd_oc_total - qtd_oc_recebida)

        preco_oc = float(dados_item_oc['Preco']) if dados_item_oc else 0.0
        und_oc = dados_item_oc.get('Und', 'UN') if dados_item_oc else 'UN'

        und_nota = str(item.get('Und') or 'UN').strip().upper()

        if dados_item_oc and und_oc != und_nota:
            res_conv = self.products_repo.converter_unidades(
                sku=sku_nota,
                qtd=qtd_oc,
                und_origem=und_oc,
                und_destino=und_nota
            )
            if res_conv['sucesso']:
                qtd_oc = res_conv['qtd_convertida']
                if res_conv['fator'] > 0:
                    preco_oc = preco_oc / res_conv['fator']

        tentativas = int(item.get('TentativasErro') or 0)
        excedeu_tentativas = (tentativas >= StatusPR.LIMITE_TENTATIVAS)

        tem_sku = (sku_nota is not None and sku_nota != "")
        item_fora_da_oc = False
        if oc_existe_erp and tem_sku:
            item_fora_da_oc = (dados_item_oc is None)

        qtd_coletada = float(item.get('QtdColetada') or 0)
        finalizado = (qtd_coletada >= (qtd_nota - 0.001))
        iniciado = (qtd_coletada > 0.001)

        div_excedente_fisico = (qtd_coletada > (qtd_nota + 0.001))
        div_excedente_fiscal = (qtd_nota > qtd_oc)
        eh_parcial_fiscal = (qtd_nota < qtd_oc)

        tol_val = getattr(self.global_policies, "tolerancia_valor_recebimento", 0.00)
        tol_tipo = getattr(self.global_policies, "tolerancia_tipo_recebimento", "Valor")

        if tol_tipo == "Porcentagem":
            delta_tol = preco_oc * (tol_val / 100.0)
        else:
            delta_tol = tol_val

        div_preco_maior = (preco_nota > (preco_oc + delta_tol)) and (dados_item_oc is not None)
        div_preco_menor = (preco_nota < (preco_oc - delta_tol)) and (dados_item_oc is not None)

        eh_bonificacao = item.get('EhBonificacao')
        dados_q = item.get('dados_qualidade') or item.get('DadosQualidade') or {}
        if isinstance(dados_q, str):
            import json
            try:
                dados_q = json.loads(dados_q)
            except:
                dados_q = {}

        div_qualidade = (
                dados_q.get('embalagem_integra') == 'Não' or
                dados_q.get('material_integro') == 'Não' or
                dados_q.get('vencido') is True or
                bool(item.get('DivergenciaVisual'))
        )

        liberado = header_status not in [
            StatusPR.AGUARDANDO_LIBERACAO,
            StatusPR.BLOQUEADO_FISCAL,
            StatusPR.DIVERGENCIA,
            StatusPR.AGUARDANDO_VINCULO,
            StatusPR.AGUARD_VINC_UNID
        ]

        status_final = StatusPR.diagnosticar(
            tem_sku=tem_sku,
            unidade_valida=unidade_valida,
            oc_existe=oc_existe_erp,
            eh_bonificacao=eh_bonificacao,
            item_fora_da_oc=item_fora_da_oc,
            eh_parcial=eh_parcial_fiscal,
            div_excedente=div_excedente_fiscal or div_excedente_fisico,
            div_preco_maior=div_preco_maior,
            div_preco_menor=div_preco_menor,
            div_qualidade=div_qualidade,
            liberado=liberado,
            iniciado=iniciado,
            finalizado=finalizado,
            excedeu_tentativas=excedeu_tentativas
        )

        motivo_texto = StatusPR.motivo_status_pr(
            status=status_final,
            oc_existe=oc_existe_erp,
            item_fora_da_oc=item_fora_da_oc,
            div_excedente=div_excedente_fiscal or div_excedente_fisico,
            div_preco_maior=div_preco_maior,
            div_preco_menor=div_preco_menor,
            tem_sku=tem_sku,
            unidade_valida=unidade_valida,
            preco_nf=preco_nota,
            preco_oc=preco_oc,
            excedeu_tentativas=excedeu_tentativas
        )

        if div_excedente_fisico and status_final == StatusPR.AGUARDANDO_DECISAO:
            motivo_texto = "Quantidade física excede a Nota Fiscal"

        return status_final, motivo_texto

    # --- MÉTODO FSM (MÁQUINA DE ESTADOS ENTERPRISE) ---
    def executar_transicao(self, pr_code, gatilho, usuario="Sistema", obs=None):
        # 1. Carrega dados frescos (incluindo RowVersion para trava otimista)
        pr_data = self.get_by_pr(pr_code)
        if not pr_data:
            return False, "Recebimento não encontrado."

        # Recupera a versão atual do registro (Safety Check)
        # Se o banco for legado e não tiver RowVersion preenchido, tratamos como 0 ou 1
        row_version = pr_data.get('RowVersion')
        if row_version is None: row_version = 1

        status_anterior = pr_data.get('Status')

        # 2. Instancia o Workflow e Simula
        wf = RecebimentoWorkflow(pr_data, repo_instance=self)

        if not hasattr(wf, gatilho):
            return False, f"Ação '{gatilho}' não permitida pelo sistema."

        try:
            # Simula a transição em memória. Se a regra de negócio proibir, vai estourar erro aqui.
            metodo_acao = getattr(wf, gatilho)
            metodo_acao()

            novo_status = wf.state
        except Exception as e:
            msg_erro = str(e)
            if "Can't trigger" in msg_erro: msg_erro = "Esta ação não é permitida no status atual."
            return False, f"Transição negada: {msg_erro}"

        # 3. Preparação da Transação Atômica (O 'Pulo do Gato')
        cmds = []
        agora = datetime.now()

        # A. Comando de Update com Trava Otimista
        # Se a ação for liberar a conferência, carimba a Data de Chegada oficial!
        if gatilho == "liberar_conferencia":
            sql_update = """
                    UPDATE Recebimento 
                    SET Status = ?, AtualizadoPor = ?, Alteracao = ?, ObsFiscal = ISNULL(?, ObsFiscal), 
                        DataChegada = ?, RowVersion = RowVersion + 1
                    WHERE PrCode = ? AND RowVersion = ?
                """
            agora_str = agora.strftime("%d/%m/%Y %H:%M")
            cmds.append((sql_update, (novo_status, usuario, agora, obs, agora_str, pr_code, row_version)))

        # Se a ação for desfazer a liberação, limpa a Data de Chegada
        elif gatilho == "desfazer_liberacao":
            sql_update = """
                    UPDATE Recebimento 
                    SET Status = ?, AtualizadoPor = ?, Alteracao = ?, ObsFiscal = ISNULL(?, ObsFiscal), 
                        DataChegada = '-', RowVersion = RowVersion + 1
                    WHERE PrCode = ? AND RowVersion = ?
                """
            cmds.append((sql_update, (novo_status, usuario, agora, obs, pr_code, row_version)))

        # Transição normal para outros status
        else:
            sql_update = """
                    UPDATE Recebimento 
                    SET Status = ?, AtualizadoPor = ?, Alteracao = ?, ObsFiscal = ISNULL(?, ObsFiscal), RowVersion = RowVersion + 1
                    WHERE PrCode = ? AND RowVersion = ?
                """
            cmds.append((sql_update, (novo_status, usuario, agora, obs, pr_code, row_version)))

        # B. Comando de Auditoria (Log Eterno)
        sql_log = """
            INSERT INTO LogTransicoes (Tabela, RegistroId, De, Para, Usuario, DataHora, Motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        motivo_log = f"Gatilho: {gatilho}"
        if obs: motivo_log += f" | Obs: {obs}"

        cmds.append((sql_log, ('Recebimento', pr_code, status_anterior, novo_status, usuario, agora, motivo_log)))

        # 4. Execução da Transação
        try:
            # Envia o pacote para o banco. Ou vai tudo, ou não vai nada.
            self.execute_transaction(cmds)

            # --- PÓS-COMMIT (Efeitos colaterais seguros) ---

            if novo_status == StatusPR.CONCLUIDO and self.event_bus:
                print(f"Evento: Publicando recebimento_concluido para PR {pr_code}")
                self.event_bus.publish("recebimento_concluido", {
                    "pr": pr_code,
                    "usuario": usuario,
                    "data_conclusao": agora
                })

                # [CORREÇÃO] Trata Cancelamento E Recusa (Rejeição)
            if novo_status in [StatusPR.CANCELADO, StatusPR.RECUSADO]:

                # 1. Limpeza de Estoque (Apenas para Cancelado)
                # Se for Recusado, talvez você queira manter o histórico, mas se quiser limpar também, mova para fora do if
                if novo_status == StatusPR.CANCELADO:
                    qtd_removida = self.lpn_repo.excluir_lpns_do_recebimento(pr_code)
                    print(f"Recebimento Cancelado: {qtd_removida} LPNs foram estornados automaticamente.")

                # 2. [NOVO] Força a atualização de TODOS os itens para o status final
                # Isso impede que eles fiquem travados como "Em Análise" ou "Divergência"
                self.execute_non_query(
                    f"UPDATE RecebimentoItens SET Status=? WHERE PrCode=?",
                    (novo_status, pr_code)
                )

            return True, f"Status atualizado: {status_anterior} -> {novo_status}"

        except Exception as e:
            # Se cair aqui, o Optimistic Lock pode ter ativado (Concorrência) ou erro de banco.
            return False, f"Erro ao salvar (Tente novamente): {str(e)}"

    def get_acoes_permitidas(self, pr_code):

        # Retorna lista de triggers (ex: ['liberar_conferencia', 'cancelar_recebimento'])
        # disponíveis para o estado atual do PR.

        pr_data = self.get_by_pr(pr_code)
        if not pr_data:
            return []

        # Instancia o Workflow apenas para consultar as permissões
        wf = RecebimentoWorkflow(pr_data, repo_instance=self)
        return wf.get_acoes_disponiveis()

    def update_pr_status(self, pr_code, novo_status, usuario="Sistema", obs=None):

        # Se veio uma observação (motivo), atualizamos ela também.
        # Caso contrário, atualizamos apenas o status.
        if obs is not None:
            query = """
                UPDATE Recebimento 
                SET Status = ?, ObsFiscal = ?, AtualizadoPor = ?, Alteracao = GETDATE() 
                WHERE PrCode = ?
            """
            self.execute_non_query(query, (novo_status, obs, usuario, pr_code))
        else:
            query = """
                UPDATE Recebimento 
                SET Status = ?, AtualizadoPor = ?, Alteracao = GETDATE() 
                WHERE PrCode = ?
            """
            self.execute_non_query(query, (novo_status, usuario, pr_code))

    def get_by_pr(self, pr):
        res = self.execute_query("SELECT * FROM Recebimento WHERE PrCode = ?", (pr,))
        if not res: return None
        r = res[0]

        r["divergencias_visuais"] = []

        try:
            r["historico_tentativas"] = json.loads(r.get("HistoricoTentativas") or "[]")
        except:
            r["historico_tentativas"] = []

        r["pr"] = r["PrCode"]
        return r

    def list_itens_por_pr(self, pr):
        # Adicionei r.Cnpj e r.Fornecedor no SELECT
        query = """
            SELECT i.*, r.Status as HeaderStatus, r.Oc, r.Cnpj, r.Fornecedor
            FROM RecebimentoItens i
            JOIN Recebimento r ON i.PrCode = r.PrCode
            WHERE i.PrCode = ?
        """
        itens = self.execute_query(query, (pr,))

        if not itens: return []

        # --- BULK LOAD: LOTES (Busca lotes detalhados na tabela de LPNs) ---
        lotes_por_sku = {}
        try:
            # Busca lotes distintos vinculados a este PR na tabela de LPNs ignorando os LPNs Cancelados
            query_lotes = "SELECT Sku, Lote FROM Lpns WHERE PrRef = ? AND Lote IS NOT NULL AND Lote != '' AND Status != 'Cancelado'"
            res_lotes = self.execute_query(query_lotes, (pr,))

            for row in res_lotes:
                s = str(row['Sku']).upper()
                l = str(row['Lote']).strip()
                if s not in lotes_por_sku: lotes_por_sku[s] = set()
                lotes_por_sku[s].add(l)
        except Exception as e:
            print(f"Erro ao carregar lotes detalhados: {e}")

        # 2. PRÉ-CARREGAMENTO: Busca dados detalhados da OC (Qtd e Preço)
        dados_erp_por_sku = {}
        oc_encontrada_erp = False

        oc_header = itens[0]['Oc']
        if oc_header:
            lista_ocs = [x.strip().lstrip("0") for x in oc_header.split(',') if x.strip()]
            for num_oc in lista_ocs:
                dados_oc = self.oc_repo.get_oc(num_oc)
                if dados_oc:
                    oc_encontrada_erp = True
                    if 'itens' in dados_oc:
                        for sku_oc, info in dados_oc['itens'].items():
                            dados_erp_por_sku[str(sku_oc).upper()] = {
                                'Qtd': float(info.get('Qtd', 0)),
                                'QtdRecebida': float(info.get('QtdRecebida', 0)),
                                'Preco': float(info.get('Preco', 0))
                            }

        # --- NOVA LÓGICA: BULK LOAD DE UNIDADES E ALIAS (Para Validação Visual) ---
        skus_presentes = list({str(i['Sku']) for i in itens if i.get('Sku')})
        valid_units_map = {}
        alias_map = {}

        if skus_presentes:
            # A. Embalagens
            placeholders = ','.join(['?'] * len(skus_presentes))
            query_emb = f"""
                        SELECT p.Sku, pe.Unidade 
                        FROM ProdutoEmbalagens pe
                        JOIN Produtos p ON pe.ProdutoId = p.Id
                        WHERE p.Sku IN ({placeholders})
                    """
            try:
                res_emb = self.execute_query(query_emb, tuple(skus_presentes))
                for row in res_emb:
                    s = str(row['Sku']).upper()
                    u = str(row['Unidade']).strip().upper()
                    if s not in valid_units_map: valid_units_map[s] = set()
                    valid_units_map[s].add(u)
            except Exception as e:
                print(f"Erro ao carregar embalagens na lista: {e}")

            # B. Alias
            try:
                res_alias = self.execute_query("SELECT UXml, UInterna FROM UnidadesAlias")
                for r in res_alias:
                    sigla_xml = str(r['UXml']).strip().upper()
                    sigla_sys = str(r['UInterna']).strip().upper()
                    alias_map[sigla_xml] = sigla_sys
            except Exception as e:
                print(f"Erro ao carregar alias na lista: {e}")
        # -----------------------------------------------------------------------

        # 3. Processamento Individual
        for i in itens:
            i["Pr"] = i["PrCode"]
            try:
                i["dados_qualidade"] = json.loads(i.get("DadosQualidade") or "{}")
            except:
                i["dados_qualidade"] = {}

            i['_oc_existe_erp'] = oc_encontrada_erp
            i['_dados_oc'] = dados_erp_por_sku

            # --- Validação de Unidade para Visualização ---
            sku_item = str(i.get('Sku') or "").upper()
            und_item = str(i.get('Und') or "").strip().upper()
            unidade_valida = True

            sku_key = str(i.get('Sku') or "").upper()
            lista_lotes = []

            # 1. Tenta pegar dos LPNs (Fonte mais precisa)
            if sku_key in lotes_por_sku:
                lista_lotes = sorted(list(lotes_por_sku[sku_key]))

            # 2. Se não achou em LPNs, usa o próprio Lote do item (se não for "Vários")
            if not lista_lotes:
                lote_atual = str(i.get("Lote") or "").strip()
                if lote_atual and lote_atual.lower() != "vários":
                    lista_lotes.append(lote_atual)

            i['_LotesDetalhados'] = lista_lotes

            if sku_item:
                unidades_deste_sku = valid_units_map.get(sku_item, set())
                match_direto = und_item in unidades_deste_sku

                match_via_alias = False
                if not match_direto:
                    traducao = alias_map.get(und_item)
                    if traducao and traducao in unidades_deste_sku:
                        match_via_alias = True

                if not match_direto and not match_via_alias:
                    unidade_valida = False
            # ----------------------------------------------

            status, motivo = self._calcular_status_real_item(i, i.get('HeaderStatus'), unidade_valida=unidade_valida)

            i['StatusCalculado'] = status
            i['MotivoSistema'] = motivo

        return itens

    def verificar_viculos_automaticos(self, pr_code=None):
        # Tenta resolver itens sem SKU.
        # ORDEM:
        # 1. Alias (O que o sistema já aprendeu).
        # 2. EAN (O que o sistema pode descobrir e aprender agora).

        filtro = "WHERE Sku IS NULL"
        params = []

        if pr_code:
            filtro += " AND PrCode = ?"
            params.append(pr_code)

        # Busca itens pendentes
        itens_pendentes = self.execute_query(f"SELECT Id, EanNota FROM RecebimentoItens {filtro}", tuple(params))

        for item in itens_pendentes:
            item_id = item['Id']
            ean = item.get('EanNota')

            # 1. TENTA ALIAS (Memória)
            # Se encontrar, ele atualiza o SKU e retorna True.
            ja_vinculou = self.vinculo_service.vinculo_automatico_alias(item_id)

            # 2. TENTA EAN
            if not ja_vinculou and ean:
                self.vinculo_service.vinculo_automatico(item_id, ean)

    def get_qtd_recebida_por_oc(self, numero_oc, sku, ignorar_pr=None):
        total = 0.0
        oc_target = str(numero_oc).strip().lstrip("0")
        query = f"SELECT PrCode, Oc FROM Recebimento WHERE Status != '{StatusPR.CANCELADO}' AND Oc LIKE ?"
        prs_candidatos = self.execute_query(query, (f"%{oc_target}%",))

        for r in prs_candidatos:
            if ignorar_pr and r["PrCode"] == ignorar_pr: continue
            r_oc = str(r.get("Oc", "")).strip().lstrip("0")
            if oc_target in [x.strip() for x in r_oc.split(",")]:
                itens = self.execute_query("SELECT Qtd FROM RecebimentoItens WHERE PrCode=? AND Sku=?",
                                           (r["PrCode"], sku))
                for i in itens: total += float(i["Qtd"])
        return total

    def processar_xmls_da_pasta(self, pasta_origem):
        if not os.path.exists(pasta_origem): return False
        pasta_destino = os.path.join(pasta_origem, "Processados")
        if not os.path.exists(pasta_destino): os.makedirs(pasta_destino)

        arquivos = glob.glob(os.path.join(pasta_origem, "*.xml"))
        novos_prs = []

        # Carrega padrão de destino uma vez só
        local_destino_padrao = self.locations_repo.get_padrao()

        for arquivo in arquivos:
            try:
                with open(arquivo, 'r', encoding='utf-8') as f_read:
                    xml_content = f_read.read()

                xml_content = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
                xml_content = re.sub(r'\sxmlns:xsi="[^"]+"', '', xml_content, count=1)
                xml_content = re.sub(r'nfe:', '', xml_content)

                root = ET.fromstring(xml_content)
                inf_nfe = root.find('.//infNFe')
                if inf_nfe is None: continue

                chave_nfe = inf_nfe.get('Id', '').replace('NFe', '')
                if chave_nfe in self.processed_keys:
                    self._mover_arquivo(arquivo, pasta_destino)
                    continue

                ide = inf_nfe.find('ide')
                emit = inf_nfe.find('emit')

                num_nfe = ide.find('nNF').text
                fornecedor = emit.find('xNome').text
                cnpj_fornec = emit.find('CNPJ').text

                pedidos_encontrados = set()
                itens_para_adicionar = []

                dets = inf_nfe.findall('det')
                for det in dets:
                    prod = det.find('prod')
                    cfop_tag = prod.find('CFOP')
                    cfop = cfop_tag.text if cfop_tag is not None else ""
                    eh_bonificacao = cfop in ["1910", "2910", "5910", "6910", "1911", "2911", "5911", "6911"]

                    cod_fornec = prod.find('cProd').text
                    desc_fornec = prod.find('xProd').text

                    tag_ean = prod.find('cEAN')
                    ean_xml = tag_ean.text if tag_ean is not None else ""
                    if not ean_xml or ean_xml.upper() == "SEM GTIN":
                        tag_ean_trib = prod.find('cEANTrib')
                        if tag_ean_trib is not None and tag_ean_trib.text: ean_xml = tag_ean_trib.text

                    sku_final, desc_final = cod_fornec, desc_fornec
                    sku_vinculado = self.vinculo_service.consultar_vinculo(cnpj_fornec, cod_fornec)

                    if sku_vinculado:
                        sku_final = sku_vinculado
                        prod_interno = self.products_repo.get_by_sku(sku_final)
                        if prod_interno:
                            desc_final = prod_interno.get("Descricao", desc_fornec)
                    else:
                        sku_final = None

                    u_xml_raw = prod.find('uCom').text
                    und_final = self.unit_alias_repo.get_internal(u_xml_raw)

                    tag_xped = prod.find('xPed')
                    if tag_xped is not None and tag_xped.text: pedidos_encontrados.add(tag_xped.text)

                    preco_xml = 0.0
                    tag_vun = prod.find('vUnCom')
                    if tag_vun is not None: preco_xml = float(tag_vun.text)

                    # Monta Dicionário do Item em TitleCase
                    itens_para_adicionar.append({
                        "Sku": sku_final,
                        "Descricao": desc_final,
                        "Qtd": float(prod.find('qCom').text),
                        "Und": und_final,
                        "CodOrig": cod_fornec,
                        "EanNota": ean_xml,
                        "Preco": preco_xml,
                        "EhBonificacao": eh_bonificacao,
                        "DescricaoXml": desc_fornec,
                        "Destino": local_destino_padrao,
                        "Status": StatusPR.PROCESSANDO
                    })

                oc_valor = ",".join(pedidos_encontrados) if pedidos_encontrados else ""

                # Chama add_recebimento com Kwargs (TitleCase)
                pr_code = self.add_recebimento(
                    Nfe=num_nfe,
                    Fornecedor=fornecedor,
                    Cnpj=cnpj_fornec,
                    Oc=oc_valor,
                    DataChegada="-",
                    Status=StatusPR.PROCESSANDO,
                    ObsFiscal="Processando importação..."
                )

                # Insere os itens usando Kwargs
                for item_dict in itens_para_adicionar:
                    item_dict["PrCode"] = pr_code  # Adiciona o PR gerado ao dicionário
                    self.add_item(**item_dict)  # Passa tudo como kwargs

                self._save_history_key(chave_nfe)
                novos_prs.append(pr_code)
                self._mover_arquivo(arquivo, pasta_destino)

            except Exception as e:
                print(f"Erro XML {arquivo}: {e}")

        for pr_novo in novos_prs:
            self.verificar_viculos_automaticos(pr_novo)
            self.recalcular_status_geral(pr_novo)

        return len(novos_prs) > 0

    def _mover_arquivo(self, arquivo, pasta_destino):
        subpasta_mes = datetime.now().strftime("%Y-%m")
        pasta_final = os.path.join(pasta_destino, subpasta_mes)
        if not os.path.exists(pasta_final): os.makedirs(pasta_final)
        try:
            shutil.move(arquivo, os.path.join(pasta_final, os.path.basename(arquivo)))
        except:
            pass

    # --- LÓGICA DE NEGÓCIO (ADAPTADA PARA SQL) ---

    def salvar_config_pasta(self, nova_pasta):
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_file = os.path.join(base_path, "dados", "config_xml_path.json")
        try:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump({"pasta_xml": nova_pasta}, f)
        except Exception as e:
            print(f"Erro config XML: {e}")

    def get_atividades_pendentes(self):
        query = f"SELECT r.PrCode, r.Nfe, r.Oc, r.Fornecedor, CASE WHEN r.Status = '{StatusPR.EM_CONFERENCIA}' THEN ISNULL( (SELECT TOP 1 FORMAT(s.DataInicio, 'dd/MM/yyyy HH:mm') FROM RecebimentoSessoes s WHERE s.PrCode = r.PrCode AND s.Status = 'Em Andamento' ORDER BY s.Id DESC), 'Iniciando...' ) ELSE 'Aguardando Início' END as DataChegada, r.Status, r.Id, COUNT(i.Id) as QtdSkus, SUM(i.Qtd) as QtdTotal FROM Recebimento r JOIN RecebimentoItens i ON r.PrCode = i.PrCode WHERE r.Status IN ('{StatusPR.AGUARDANDO_CONF}', '{StatusPR.EM_CONFERENCIA}') GROUP BY r.PrCode, r.Nfe, r.Oc, r.Fornecedor, r.DataChegada, r.Status, r.Id"
        # Substituindo por uma formatacao mais legivel com f-string limpa
        query = f"""
            SELECT r.PrCode, r.Nfe, r.Oc, r.Fornecedor, 
                   CASE 
                       WHEN r.Status = '{StatusPR.EM_CONFERENCIA}' THEN
                           ISNULL(
                               (SELECT TOP 1 FORMAT(s.DataInicio, 'dd/MM/yyyy HH:mm') 
                                FROM RecebimentoSessoes s 
                                WHERE s.PrCode = r.PrCode AND s.Status = 'Em Andamento'
                                ORDER BY s.Id DESC),
                               'Iniciando...'
                           )
                       ELSE 'Aguardando Início'
                   END as DataChegada,
                   r.Status, r.Id,
                   COUNT(i.Id) as QtdSkus, SUM(i.Qtd) as QtdTotal
            FROM Recebimento r
            JOIN RecebimentoItens i ON r.PrCode = i.PrCode
            WHERE r.Status IN ('{StatusPR.AGUARDANDO_CONF}', '{StatusPR.EM_CONFERENCIA}')
            GROUP BY r.PrCode, r.Nfe, r.Oc, r.Fornecedor, r.DataChegada, r.Status, r.Id
        """
        return self.execute_query(query)

    def iniciar_conferencia(self, pr_code, usuario):
        header = self.get_by_pr(pr_code)
        if not header: return False, "PR não encontrado."

        status_atual = header.get('Status')
        conferente_atual = header.get('Conferente')

        # Regra de status
        if status_atual not in [StatusPR.AGUARDANDO_CONF, StatusPR.EM_CONFERENCIA]:
            return False, f"Não é possível iniciar conferência no status: {status_atual}"

        # Bloqueio de concorrência: Impede que 2 pessoas operem a mesma nota ao mesmo tempo
        if conferente_atual and conferente_atual != usuario and status_atual == StatusPR.EM_CONFERENCIA:
            return False, f"O usuário {conferente_atual} já está conferindo este PR."

        # ======== LÓGICA DE CONTINUIDADE ========
        # Verifica se JÁ EXISTE uma sessão aberta (DataFim IS NULL) para este PR.
        # Não importa quem é o operador ou quantos LPNs foram abertos.
        sessao_aberta = self.execute_query(
            "SELECT COUNT(*) as Qtd FROM RecebimentoSessoes WHERE PrCode = ? AND DataFim IS NULL",
            (pr_code,)
        )

        if sessao_aberta and sessao_aberta[0]['Qtd'] > 0:
            # Pega o número da contagem atual só para exibir a mensagem corretamente
            res_sessao_atual = self.execute_query("SELECT COUNT(*) as Qtd FROM RecebimentoSessoes WHERE PrCode = ?", (pr_code,))
            num_sessao_atual = res_sessao_atual[0]['Qtd']
            msg = f"Continuando {num_sessao_atual}ª Contagem."
        else:
            # Se não tem sessão aberta (é o 1º acesso, ou o fiscal pediu recontagem), cria uma nova
            num_sessao = self._criar_sessao(pr_code, usuario)
            msg = f"Iniciada {num_sessao}ª Contagem."
        # ===============================================

        query = """
                    UPDATE Recebimento 
                    SET Status=?, Conferente=?, AtualizadoPor=?, Alteracao=GETDATE()
                    WHERE PrCode=?
                """
        self.execute_non_query(query, (StatusPR.EM_CONFERENCIA, usuario, usuario, pr_code))

        return True, msg

    def _obter_numero_sessao(self, pr_code):
        res = self.execute_query("SELECT COUNT(*) as Qtd FROM RecebimentoSessoes WHERE PrCode = ?", (pr_code,))
        return res[0]['Qtd'] + 1

    def _criar_sessao(self, pr_code, usuario):
        # 1. Descobre se é a 1ª, 2ª, 3ª...
        num_sessao = self._obter_numero_sessao(pr_code)
        tipo = f"{num_sessao}ª Contagem"

        # 2. Fecha sessões anteriores "penduradas" (Safety Check)
        self._fechar_sessao_ativa(pr_code, status_fim="Interrompida", obs="Nova sessão iniciada forçadamente")

        # 3. Cria a nova usando o horário local da máquina (Python) em vez do servidor de banco de dados
        agora = datetime.now()
        query = """
            INSERT INTO RecebimentoSessoes (PrCode, Tipo, Usuario, DataInicio, Status)
            VALUES (?, ?, ?, ?, 'Em Andamento')
        """
        self.execute_non_query(query, (pr_code, tipo, usuario, agora))

        return num_sessao

    def _fechar_sessao_ativa(self, pr_code, status_fim="Concluída", obs=None):
        agora = datetime.now()
        query = """
            UPDATE RecebimentoSessoes 
            SET DataFim = ?, Status = ?, Observacao = ISNULL(?, Observacao)
            WHERE PrCode = ? AND DataFim IS NULL
        """
        self.execute_non_query(query, (agora, status_fim, obs, pr_code))

    def _obter_tipo_proxima_sessao(self, pr_code):
        # Conta quantas sessões já existiram para definir se é 1ª, 2ª, etc.
        res = self.execute_query("SELECT COUNT(*) as Qtd FROM RecebimentoSessoes WHERE PrCode = ?", (pr_code,))
        qtd = res[0]['Qtd']
        return "1ª Contagem" if qtd == 0 else f"{qtd + 1}ª Contagem"

    def _ao_concluir_recebimento(self, data):
        pr_code = data['pr']
        usuario = data.get('Usuario', 'Sistema')

        # 1. Executa a lógica antiga (Snapshot)
        self.gravar_chapa_quente(pr_code)

        # 2. Fecha a sessão ativa na tabela de tempos (RecebimentoSessoes)
        self._fechar_sessao_ativa(pr_code, status_fim="Concluída")

        # 3. CORREÇÃO: Verifica se o cabeçalho JÁ TEM data fim. Se não tiver (NULL ou vazio), atualiza.
        # Isso cobre tanto a 1ª contagem quanto recontagens onde a data foi limpa ou nunca gravada.
        header = self.get_by_pr(pr_code)
        data_fim_atual = header.get('DataFim')

        possui_data = data_fim_atual and str(data_fim_atual).strip() != '' and str(data_fim_atual).strip() != '-'

        if not possui_data:
            agora_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            self.execute_non_query("UPDATE Recebimento SET DataFim=? WHERE PrCode=?", (agora_str, pr_code))

        self.execute_non_query(
            f"UPDATE RecebimentoItens SET Status='{StatusPR.CONCLUIDO}' WHERE PrCode=?",
            (pr_code,)
        )

    def incrementar_erro_contagem(self, item_id, qtd_errada=None, usuario="Sistema", ean_lido=None, lpn=None):
        # 1. Incrementa contador
        self.execute_non_query(
            "UPDATE RecebimentoItens SET TentativasErro = ISNULL(TentativasErro, 0) + 1 WHERE Id = ?", (item_id,))

        # Descobre qual é a tentativa atual
        res = self.execute_query("SELECT TentativasErro FROM RecebimentoItens WHERE Id = ?", (item_id,))
        tentativas = int(res[0]['TentativasErro']) if res else 1

        # 2. Grava a tentativa falha na tabela de leituras com Estornado = 1
        # A trava 'tentativas < 3' impede a criação de linha duplicada, pois a 3ª
        # tentativa será gravada exclusivamente pela função registrar_erro_tentativa.
        if qtd_errada is not None and tentativas < 3:
            agora = datetime.now()
            ean_final = ean_lido if ean_lido and str(ean_lido).strip() != "" else None
            lpn_final = lpn if lpn and str(lpn).strip() != "" else None

            query_log = "INSERT INTO RecebimentoLeituras " \
                        "(RecebimentoItemId, Qtd, EanLido, Usuario, DataHora, Lpn, Estornado, DispositivoId) " \
                        "VALUES (?, ?, ?, ?, ?, ?, 1, NULL)"

            self.execute_non_query(query_log, (item_id, float(qtd_errada), ean_final, usuario, agora, lpn_final))

        # 3. Retorna o valor atualizado para a UI decidir
        return tentativas

    def registrar_erro_tentativa(self, pr_code, item_id, qtd_errada, usuario, obs_texto="", ean_lido=None, lpn=None):
        # 1. Prepara a data e a lista de comandos da transação atômica
        agora = datetime.now()
        cmds = []

        # Tratamento do EAN: Se for vazio (ex: botão Sem GTIN), garante que envia NULL para o banco
        ean_final = ean_lido if ean_lido and str(ean_lido).strip() != "" else None

        # Tratamento do LPN: Se for vazio, garante que envia NULL
        lpn_final = lpn if lpn and str(lpn).strip() != "" else None

        # 2. Inativa leituras temporárias para evitar duplicidade na soma do saldo
        # Se um LPN foi informado, inativamos as leituras daquele LPN. Senão, as soltas.
        if lpn_final:
            cmds.append((
                "UPDATE RecebimentoLeituras SET Estornado=1 WHERE RecebimentoItemId=? AND Lpn=?",
                (item_id, lpn_final)
            ))
        else:
            cmds.append((
                "UPDATE RecebimentoLeituras SET Estornado=1 WHERE RecebimentoItemId=? AND (Lpn IS NULL OR Lpn='')",
                (item_id,)
            ))

        # 3. Insere a leitura final que causou o bloqueio
        cmds.append((
            "INSERT INTO RecebimentoLeituras (RecebimentoItemId, Qtd, EanLido, Usuario, DataHora, DispositivoId, Lpn) VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (item_id, float(qtd_errada), ean_final, usuario, agora, lpn_final)
        ))

        # 4. Bloqueia o item para análise fiscal (Tentativa 3) e salva a quantidade
        query_item = "UPDATE RecebimentoItens SET Status=?, QtdColetada=?, AtualizadoPor=?, Alteracao=?, ObsFiscal=? WHERE Id=?"
        obs_final = f"Bloqueio por excesso de tentativas (3). Obs: {obs_texto}"

        cmds.append((
            query_item,
            (StatusPR.BLOQUEADO_FISCAL, float(qtd_errada), usuario, agora, obs_final, item_id)
        ))

        # 5. Executa tudo de uma vez atomicamente
        self.execute_transaction(cmds)

        # 6. Recalcula o status do PR
        self.recalcular_status_geral(pr_code, usuario)

    def verificar_progresso(self, pr):
        res = self.execute_query("SELECT COUNT(*) as Q FROM RecebimentoItens WHERE PrCode=? AND QtdColetada > 0", (pr,))
        return res[0]['Q'] > 0

    def _limpar_dados_conferencia_interno(self, pr):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        autor = "Sistema (Estorno)"

        # 1. Fecha a sessão atual como 'Estornada'
        self._fechar_sessao_ativa(pr, status_fim="Estornada", obs="Solicitado recontagem")

        # --- LIMPEZA DE LPNs (ARQUIVO MORTO) ---
        try:
            qtd_lpns = self.lpn_repo.excluir_lpns_do_recebimento(pr, motivo="Reconferência")
            print(f"Estorno PR {pr}: {qtd_lpns} LPNs foram enviados para o arquivo morto.")
        except Exception as e:
            print(f"Aviso: Erro ao limpar LPNs no estorno: {e}")

        # 3. Inativa Logs de Leitura (Auditoria preservada)
        self.execute_non_query(
            "UPDATE RecebimentoLeituras SET Estornado = 1 WHERE RecebimentoItemId IN (SELECT Id FROM RecebimentoItens WHERE PrCode = ?)",
            (pr,)
        )

        # 4. Reseta Cabeçalho (Agora APENAS limpa a ObsFiscal e o Status)
        sql_header = """
            UPDATE Recebimento SET 
                Status=?, Conferente='', AtualizadoPor=?, Alteracao=GETDATE(),
                DataFim=NULL, ObsFiscal=NULL
            WHERE PrCode=?
        """
        self.execute_non_query(sql_header, (StatusPR.AGUARDANDO_CONF, autor, pr))

        # 5. Reseta Itens (Aqui sim limpamos a DivergenciaVisual do item)
        self.execute_non_query(f"""
            UPDATE RecebimentoItens SET 
                Status='{StatusPR.AGUARDANDO_CONF}', 
                QtdColetada=0,
                DivergenciaVisual=NULL,
                Alteracao=GETDATE(),
                DadosQualidade='{{}}',
                TentativasErro=0,
                ObsFiscal=NULL,
                ConferenteUltimo=NULL,
                DataUltimaBipagem=NULL
            WHERE PrCode=?
        """, (pr,))

        return True

    def processar_bipagem(self, pr_code, codigo_lido, usuario="Conferente"):
        itens_pr = self.list_itens_por_pr(pr_code)
        item_alvo = None
        for item in itens_pr:
            ean_xml = str(item.get("EanNota", "")).strip()
            if ean_xml and ean_xml == codigo_lido: item_alvo = item; break

        if not item_alvo:
            for item in itens_pr:
                if str(item.get("Sku", "")).upper() == codigo_lido.upper(): item_alvo = item; break

        if not item_alvo: return False, "Produto não pertence a esta Nota."

        sku_item = item_alvo.get("Sku")
        produto_db = self.products_repo.get_by_sku(sku_item)
        if produto_db:
            ean_banco = str(produto_db.get("Ean", "")).strip()
            if ean_banco != codigo_lido:
                self.products_repo.atualizar_ean_auto(sku_item, codigo_lido, origem=f"{pr_code}", usuario=usuario)

        return True, item_alvo

    def _buscar_pr_irmao_pendente(self, cnpj, sku, pr_atual):
        # Verifica se existe outro PR do mesmo fornecedor e mesmo SKU
        # aguardando conferência.

        query = """
            SELECT TOP 1 r.PrCode
            FROM Recebimento r
            JOIN RecebimentoItens i ON r.PrCode = i.PrCode
            WHERE r.Cnpj = ?
              AND r.Status = ?
              AND r.PrCode != ?
              AND i.Sku = ?
              AND i.Qtd > i.QtdColetada 
        """
        res = self.execute_query(query, (cnpj, StatusPR.AGUARDANDO_CONF, pr_atual, sku))

        return res[0]['PrCode'] if res else None

    def tentar_contagem(self, pr_code, codigo_lido, qtd_informada, usuario, lpn_ref=None):
        # 1. Identificação Inteligente (Usa ProductsRepo)
        codigo_limpo = str(codigo_lido).strip().upper().lstrip("0")
        if not codigo_limpo: return False, "Código vazio.", None, "ERRO"

        # A: Busca Global (Produtos e Embalagens)
        prod_db, dados_emb = self.products_repo.identificar_por_codigo(codigo_limpo)

        itens_pr = self.list_itens_por_pr(pr_code)
        item_alvo = None

        # B: Match com o PR
        if prod_db:
            # Se achou o produto no banco, verifica se ele está na lista do PR
            sku_banco = prod_db['Sku']
            item_alvo = next((i for i in itens_pr if i['Sku'] == sku_banco), None)
        else:
            # Fallback: Se não achou no cadastro global, tenta EAN da Nota (Contexto PR)
            # Isso cobre o caso de produtos novos que ainda não foram cadastrados mas vieram no XML
            item_alvo = next(
                (i for i in itens_pr if str(i.get("EanNota", "")).strip().upper().lstrip("0") == codigo_limpo), None)

            if item_alvo:
                # Se achou pelo EAN da nota, carrega o produto para ter dados de conversão
                prod_db = self.products_repo.get_by_sku(item_alvo['Sku'])
                dados_emb = {"unidade": prod_db['Unidade'], "fator": 1.0}  # Assume base

        if not item_alvo:
            return False, "Produto não identificado neste recebimento.", None, "ERRO"

        if not prod_db:
            return False, "Produto vinculado ao item não existe no cadastro.", item_alvo, "ERRO"

        # 2. Conversão de Unidades (A Mágica Centralizada)
        und_lida = dados_emb['Unidade']  # Unidade do código de barras (ex: CX)
        und_nota = str(item_alvo.get("Und", "")).strip().upper()  # Unidade do XML (ex: UN)
        und_base = prod_db['Unidade']  # Unidade de Estoque (ex: UN)

        # Conversão A: Bip -> Nota (Para validar progresso e mostrar na tela)
        res_nota = self.products_repo.converter_unidades(
            sku=item_alvo['Sku'], qtd=qtd_informada, und_origem=und_lida, und_destino=und_nota
        )
        if not res_nota['sucesso']: return False, f"Erro Unidade: {res_nota['erro']}", item_alvo, "ERRO"
        qtd_bip_nota = res_nota['qtd_convertida']

        # Conversão B: Bip -> Base (Para gravar no Log/Estoque)
        res_base = self.products_repo.converter_unidades(
            sku=item_alvo['Sku'], qtd=qtd_informada, und_origem=und_lida, und_destino=und_base
        )
        qtd_bip_base = res_base['qtd_convertida']

        # 3. Lógica de Saldo e Tentativas
        # Recupera saldo atual (já convertido para Nota)
        item_id = item_alvo['Id']
        # Recupera saldo atual ignorando os estornados
        res_logs = self.execute_query(
            "SELECT ISNULL(SUM(Qtd), 0) as Qtd FROM RecebimentoLeituras WHERE RecebimentoItemId=? AND Estornado=0",
            (item_id,)
        )
        qtd_acumulada_base = float(res_logs[0]['Qtd'])

        # Converte o acumulado base -> nota
        res_conv_total = self.products_repo.converter_unidades(
            sku=item_alvo['Sku'], qtd=qtd_acumulada_base, und_origem=und_base, und_destino=und_nota
        )
        qtd_acumulada_nota = res_conv_total['qtd_convertida']

        nova_projecao_nota = qtd_acumulada_nota + qtd_bip_nota
        qtd_meta = float(item_alvo.get("Qtd", 0))

        # Checa excesso com tolerância
        if nova_projecao_nota > (qtd_meta + 0.001):
            # Verifica PR Irmão
            pr_irmao = self._buscar_pr_irmao_pendente(item_alvo.get("Cnpj"), item_alvo["Sku"], pr_code)
            if pr_irmao:
                return False, f"Limite atingido. Excedente vai para {pr_irmao}.", item_alvo, "ALERTA_IRMAO"

            # Incrementa erro
            tentativas = int(item_alvo.get("TentativasErro") or 0) + 1
            self.execute_non_query("UPDATE RecebimentoItens SET TentativasErro=?, ConferenteUltimo=? WHERE Id=?",
                                   (tentativas, usuario, item_id))

            # Grava a tentativa de excesso na tabela de leituras como estornada
            agora = datetime.now()
            query_excesso = "INSERT INTO RecebimentoLeituras " \
                            "(RecebimentoItemId, Qtd, EanLido, Usuario, DataHora, Lpn, Estornado, DispositivoId) " \
                            "VALUES (?, ?, ?, ?, ?, ?, 1, 'ERRO_EXCESSO')"

            self.execute_non_query(query_excesso, (item_id, qtd_bip_base, codigo_limpo, usuario, agora, lpn_ref))

            msg = f"Excesso! Leu {qtd_bip_nota} {und_nota}, faltava {qtd_meta - qtd_acumulada_nota}. (Tentativa {tentativas}/3)"
            if tentativas >= 3:
                self.recalcular_status_geral(pr_code, usuario)
                msg = "Bloqueado por excesso de tentativas."

            return False, msg, item_alvo, "ERRO"

        # 4. Gravação (Sucesso)
        agora = datetime.now()
        cmds = []

        # Insere LOG (Sempre em unidade Base)
        cmds.append((
                    "INSERT INTO RecebimentoLeituras (RecebimentoItemId, Qtd, EanLido, Usuario, DataHora, Lpn) VALUES (?, ?, ?, ?, ?, ?)",
                    (item_id, qtd_bip_base, codigo_limpo, usuario, agora, lpn_ref)))

        # Prepara dados para o helper de persistência
        dados_qual = json.loads(item_alvo.get('DadosQualidade') or '{}')
        dados_qual['UndConferencia'] = und_lida  # Guarda qual unidade foi usada no bip

        # Chama Helper para gerar Update do Item
        cmds, novo_status = self._persistir_dados_conferencia(
            item_alvo, nova_projecao_nota, dados_qual, lpn_ref, cmds, usuario, agora
        )

        # Update específico de LPN (Soma incremental - diferente do modal)
        # O Helper não tratou LPN porque aqui é UPDATE incremental e no modal é REPLACE
        if lpn_ref:
            # Atualiza Qtd do LPN somando o novo bip (Base)
            self.lpn_repo.somar_qtd_lpn(lpn_ref, qtd_bip_base, usuario)  # Supondo que exista ou add lógica update aqui

        try:
            self.execute_transaction(cmds)
            item_alvo["QtdColetada"] = nova_projecao_nota
            self.recalcular_status_geral(pr_code, usuario)
            return True, f"Leitura OK (+{qtd_bip_nota:g} {und_nota})", item_alvo, "OK"
        except Exception as e:
            return False, f"Erro BD: {str(e)}", None, "ERRO"

    def registrar_divergencia_visual(self, pr_code, sku_selecionado, ean_lido, descricao_visual, qtd, usuario):
        # 1. Encontra o item
        itens = self.list_itens_por_pr(pr_code)
        item_alvo = next((i for i in itens if i["Sku"] == sku_selecionado), None)

        if not item_alvo:
            return False, "Item não encontrado."

        # 2. Atualiza diretamente o ITEM com TEXTO PURO
        # O controle de que isso é uma pendência será o Status = EM_ANALISE
        query = """
            UPDATE RecebimentoItens 
            SET DivergenciaVisual = ?, Status = ?, QtdColetada = QtdColetada + ? 
            WHERE Id = ?
        """
        # Note: Passamos 'descricao_visual' direto, sem json.dumps
        self.execute_non_query(query, (descricao_visual, StatusPR.EM_ANALISE, float(qtd), item_alvo["Id"]))

        # 3. Atualiza o status do Pai (PR)
        self.recalcular_status_geral(pr_code, usuario)

        return True, "Enviado para análise fiscal."

    def resolver_divergencia_fiscal(self, pr_code, item_id, acao, usuario):
        item = self.execute_query("SELECT DivergenciaVisual FROM RecebimentoItens WHERE Id=?", (item_id,))[0]
        texto_atual = item.get("DivergenciaVisual", "")

        if acao == "validar":
            obs = f"Divergência Visual Aceita: {texto_atual} (por {usuario})"
            self.execute_non_query(
                f"UPDATE RecebimentoItens SET Status='{StatusPR.CONCLUIDO}', ObsFiscal=? WHERE Id=?",
                (obs, item_id)
            )

        elif acao == "rejeitar":
            self.execute_non_query(
                f"UPDATE RecebimentoItens SET Status='{StatusPR.EM_CONFERENCIA}', DivergenciaVisual=NULL WHERE Id=?",
                (item_id,)
            )
            # ======== GATILHO DA RECONTAGEM ========
            self._fechar_sessao_ativa(pr_code, status_fim="Recontagem Solicitada", obs=f"Fiscal {usuario} rejeitou divergência visual.")

        self.recalcular_status_geral(pr_code, usuario)
        return True, f"Divergência {acao}."

    def resolver_divergencia_item(self, item_id, decisao, usuario_fiscal):
        item = self.execute_query("SELECT * FROM RecebimentoItens WHERE Id=?", (item_id,))[0]
        pr_code = item['PrCode']

        if decisao == 'RECONTAR':
            cmds = []

            # 1. Descobre QUAIS LPNs foram gerados EXATAMENTE para este item específico
            # Isso evita depender de SKUs que podem estar vazios ou duplicados
            lpns_gerados = self.execute_query(
                "SELECT DISTINCT Lpn FROM RecebimentoLeituras WHERE RecebimentoItemId = ? AND Lpn IS NOT NULL AND Lpn != ''",
                (item_id,)
            )
            lista_lpns = [r['Lpn'] for r in lpns_gerados if r['Lpn']]

            # 2. INATIVA os logs de leitura do item
            cmds.append((
                "UPDATE RecebimentoLeituras SET Estornado = 1 WHERE RecebimentoItemId = ?",
                (item_id,)
            ))

            # 3. Invalida os LPNs exatos encontrados (Tira do Saldo Físico)
            for lpn_code in lista_lpns:
                cmds.append((
                    """
                    UPDATE Lpns 
                    SET QtdAtual = 0, 
                        Endereco = 'CANCELADOS',
                        Status = 'Cancelado',
                        Obs = 'Estornado via Reconferência',
                        Alteracao = GETDATE()
                    WHERE Lpn = ?
                    """,
                    (lpn_code,)
                ))

            # 4. Reseta TOTALMENTE o item no banco
            sql_item = f"""
                UPDATE RecebimentoItens 
                SET TentativasErro=0, 
                    QtdColetada=0, 
                    Status='{StatusPR.AGUARDANDO_CONF}', 
                    ConferenteUltimo=NULL,
                    DadosQualidade='{{}}', 
                    ObsFiscal=NULL, 
                    DivergenciaVisual=NULL,
                    DataUltimaBipagem=NULL,
                    Lote=NULL, 
                    Val=NULL, 
                    Fab=NULL, 
                    Vencimento=NULL,
                    IntEmb=NULL, 
                    IntMat=NULL, 
                    Identificacao=NULL, 
                    CertQual=NULL, 
                    UndConferencia=NULL,
                    RowVersion=ISNULL(RowVersion, 0) + 1
                WHERE Id=?
            """
            cmds.append((sql_item, (item_id,)))

            # Executa tudo em uma única transação atômica
            self.execute_transaction(cmds)

            msg = "Item zerado e liberado para recontagem."

            # Gatilho da recontagem para a tabela de sessões
            self._fechar_sessao_ativa(pr_code, status_fim="Recontagem Solicitada",
                                      obs=f"Fiscal {usuario_fiscal} pediu recontagem.")


        elif decisao == 'ACEITAR_CONTAGEM':

            sql = f"UPDATE RecebimentoItens SET Status='{StatusPR.CONCLUIDO}', ObsFiscal=?, AtualizadoPor=?, RowVersion=ISNULL(RowVersion, 0) + 1 WHERE Id=?"
            obs = f"Divergência aceita por {usuario_fiscal} em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            self.execute_non_query(sql, (obs, usuario_fiscal, item_id))
            msg = "Divergência aceita. Item concluído."

        # A máquina de estados só roda DEPOIS que temos 100% de certeza que o banco zerou
        self.recalcular_status_geral(pr_code, usuario_fiscal)

        return True, msg

    def salvar_item_conferencia(self, item_id, dados_conferencia):
        # 1. Carrega Contexto
        item_res = self.execute_query("SELECT * FROM RecebimentoItens WHERE Id=?", (item_id,))
        if not item_res: return False, "Item não encontrado"
        item = item_res[0]
        sku = item['Sku']
        if not sku: return False, "Item sem SKU."

        # 2. Conversão de Unidades (Via ProductsRepo)
        qtd_digitada = float(dados_conferencia.get("qtd", 0))
        und_selecionada = str(dados_conferencia.get("unidade", "")).strip().upper()
        und_nota = str(item.get("Und", "")).strip().upper()

        # Busca produto para saber unidade Base
        prod = self.products_repo.get_by_sku(sku)
        if not prod: return False, "Produto não cadastrado."
        und_base = prod['Unidade']

        # A: Modal -> Base (Para o LPN/Estoque)
        res_base = self.products_repo.converter_unidades(sku, qtd_digitada, und_selecionada, und_base)
        if not res_base['sucesso']: return False, res_base['erro']
        qtd_lpn_base = res_base['qtd_convertida']

        # 3. Calcula Total Acumulado (Para o Item/Nota)
        # Soma outros LPNs (já em base) + este novo LPN (em base)
        lpn_novo = dados_conferencia.get("lpn")

        # Soma outros LPNs ignorando os estornados
        sql_outros = "SELECT ISNULL(SUM(Qtd),0) as Q FROM RecebimentoLeituras WHERE RecebimentoItemId=? AND Estornado=0 AND (Lpn IS NULL OR Lpn != ?)"
        qtd_outros_base = float(self.execute_query(sql_outros, (item_id, lpn_novo or ''))[0]['Q'])

        qtd_total_base = qtd_outros_base + qtd_lpn_base

        # B: Base -> Nota (Para o Status/Progresso)
        res_nota = self.products_repo.converter_unidades(sku, qtd_total_base, und_base, und_nota)
        if not res_nota['sucesso']: return False, res_nota['erro']
        qtd_final_nota = res_nota['qtd_convertida']

        # 4. Gravação
        cmds = []
        agora = datetime.now()
        usuario = dados_conferencia.get("usuario", "Sistema")

        # Inativa logs anteriores deste LPN (Substituição Total) em vez de apagar
        if lpn_novo:
            cmds.append(
                ("UPDATE RecebimentoLeituras SET Estornado=1 WHERE RecebimentoItemId=? AND Lpn=?", (item_id, lpn_novo)))
        else:
            cmds.append(
                ("UPDATE RecebimentoLeituras SET Estornado=1 WHERE RecebimentoItemId=? AND (Lpn IS NULL OR Lpn='')",
                 (item_id,)))

        # Insere novo Log (Base)
        if qtd_lpn_base > 0:
            cmds.append((
                        "INSERT INTO RecebimentoLeituras (RecebimentoItemId, Qtd, EanLido, Usuario, DataHora, Lpn, DispositivoId) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (item_id, qtd_lpn_base, dados_conferencia.get("ean_lido", ""), usuario, agora, lpn_novo,
                         "MODAL")))

        # Prepara objeto de qualidade
        dados_qual = {
            "embalagem_integra": dados_conferencia.get("emb_integra"),
            "material_integro": dados_conferencia.get("mat_integro"),
            "identificacao_correta": dados_conferencia.get("ident_correta"),  # Novo
            "possui_certificado": dados_conferencia.get("tem_certificado"),  # Novo
            "vencido": dados_conferencia.get("vencido"),
            "und_conferencia": und_selecionada,
            "lpn_vinculado": lpn_novo,
            "lote": dados_conferencia.get("lote"),
            "validade": dados_conferencia.get("validade"),
            "fabricacao": dados_conferencia.get("fabricacao"),
            "eh_parcial": dados_conferencia.get("eh_parcial", False)
        }

        # Extrai a observação visual do dicionário
        obs_visual = dados_conferencia.get("obs_visual")

        # Chama Helper passando a observação visual
        cmds, novo_status = self._persistir_dados_conferencia(
            item, qtd_final_nota, dados_qual, lpn_novo, cmds, usuario, agora, obs_visual
        )

        # Atualiza LPN no Estoque (Replace/Insert)
        if lpn_novo:
            # Lógica de UPSERT no LPN (usando qtd_lpn_base)
            self.lpn_repo.atualizar_ou_criar_lpn_transacao(lpn_novo, item, qtd_lpn_base, dados_conferencia, cmds,
                                                           usuario, agora)

        try:
            self.execute_transaction(cmds)
            self.recalcular_status_geral(item['PrCode'], usuario)
            return True, f"Salvo! Total: {qtd_final_nota:g} {und_nota}"
        except Exception as e:
            return False, f"Erro ao salvar: {e}"

    def _persistir_dados_conferencia(self, item_alvo, qtd_final_nota, dados_qualidade,
                                     lpn_ref, cmds_leitura, usuario, agora, obs_visual=None):
        cmds = list(cmds_leitura)
        item_id = item_alvo['Id']

        # 1. Montamos um dicionário simulando como o item ficará após o update
        item_simulado = dict(item_alvo)
        item_simulado['QtdColetada'] = qtd_final_nota
        item_simulado['dados_qualidade'] = dados_qualidade
        item_simulado['MotivoSistema'] = ""

        # 2. Perguntamos ao cérebro o status real
        novo_status, _ = self._calcular_status_real_item(item_simulado, item_alvo.get('HeaderStatus'))

        # ==============================================================================
        # TRAVA DE QUALIDADE
        # Se o usuário relatou uma divergência visual, força obrigatoriamente para Análise
        # ==============================================================================
        if obs_visual and str(obs_visual).strip() != "":
            novo_status = StatusPR.EM_ANALISE

        # ==============================================================================
        # PREVENÇÃO DE ENCERRAMENTO PRECOCE
        # ==============================================================================
        eh_parcial = dados_qualidade.get("eh_parcial", False)

        if eh_parcial:
            novo_status = StatusPR.EM_CONFERENCIA
        else:
            if novo_status == StatusPR.CONCLUIDO:
                novo_status = StatusPR.AGUARDANDO_CONCLUSAO

        def _fmt_status(val):
            if val is None: return None
            s_val = str(val).strip().lower()
            if s_val in ["sim", "ok", "true", "1"]: return "OK"
            if s_val in ["não", "nao", "false", "0"]: return "Não Conforme"
            return str(val)

        int_emb = _fmt_status(dados_qualidade.get("embalagem_integra"))
        int_mat = _fmt_status(dados_qualidade.get("material_integro"))
        ident = _fmt_status(dados_qualidade.get("identificacao_correta"))

        cert_raw = dados_qualidade.get("possui_certificado")
        cert_qual = "Sim" if cert_raw in [True, "Sim", "OK"] else "Não"

        is_vencido = dados_qualidade.get("vencido")
        status_venc = "Vencido" if is_vencido else "No prazo"

        # ATUALIZAÇÃO: Coluna DivergenciaVisual adicionada na Query
        sql_item = """
            UPDATE RecebimentoItens 
            SET QtdColetada=?, UndConferencia=?, Status=?, DadosQualidade=?, 
                ConferenteUltimo=?, DataUltimaBipagem=?, TentativasErro=?, RowVersion=RowVersion+1,
                Lote=?, Val=?, Fab=?, Vencimento=?, IntEmb=?, IntMat=?, Identificacao=?, CertQual=?, DivergenciaVisual=?
            WHERE Id=?
        """

        cmds.append((sql_item, (
            qtd_final_nota,
            dados_qualidade.get("und_conferencia", ""),
            novo_status,
            json.dumps(dados_qualidade),
            usuario,
            agora,
            0 if novo_status == StatusPR.AGUARDANDO_CONCLUSAO else item_alvo.get("TentativasErro", 0),
            dados_qualidade.get("lote"),
            dados_qualidade.get("validade"),
            dados_qualidade.get("fabricacao"),
            status_venc,
            int_emb,
            int_mat,
            ident,
            cert_qual,
            obs_visual,
            item_id
        )))

        return cmds, novo_status

    def fechar_lpn_conferencia(self, pr_code, lpn, usuario):

        # Consolida as leituras temporárias de um LPN e grava na tabela oficial de Estoque (Lpns).

        # 1. Busca tudo que foi bipado para este LPN
        sql_sum = """
                    SELECT RecebimentoItemId, SUM(Qtd) as Total 
                    FROM RecebimentoLeituras 
                    WHERE Lpn = ? AND Estornado = 0
                    GROUP BY RecebimentoItemId
                """
        res = self.execute_query(sql_sum, (lpn,))

        if not res:
            return False, "Nenhuma leitura encontrada para este LPN."

        # Validação Mono-SKU: Se tiver mais de 1 item diferente no mesmo LPN, bloqueia
        # (A menos que você mude a tabela Lpns para suportar multi-sku, hoje ela só tem 1 coluna SKU)
        if len(res) > 1:
            return False, "Erro: LPN contém múltiplos produtos misturados. O sistema exige 1 SKU por LPN."

        item_id = res[0]['RecebimentoItemId']
        qtd_total = float(res[0]['Total'])

        # Busca dados do produto (Sku, Descricao, Lote, Validade)
        # Nota: Lote e Validade teriam que vir de algum lugar.
        # Num sistema maduro, o operador informa Lote/Validade NA ABERTURA do LPN ou no primeiro bipe.
        # Por simplificação, vamos pegar do cadastro do Item do Recebimento (cache).
        item_data = self.execute_query("SELECT Sku, Descricao, Lote, Val FROM RecebimentoItens WHERE Id=?", (item_id,))[
            0]

        cmds = []
        agora = datetime.now()

        # 2. Verifica se o LPN já existe na tabela Mestra
        lpn_existe = self.execute_query("SELECT COUNT(*) as Q FROM Lpns WHERE Lpn=?", (lpn,))
        existe = lpn_existe[0]['Q'] > 0

        if existe:
            # Atualiza
            sql_update = """
                UPDATE Lpns 
                SET Sku=?, Descricao=?, QtdAtual=?, QtdOriginal=?, Status='Aguardando Armazenamento',
                    Lote=?, Validade=?, PrRef=?, Origem=?, AtualizadoPor=?, Alteracao=?, RowVersion=RowVersion+1
                WHERE Lpn=?
            """
            cmds.append((sql_update, (
                item_data['Sku'], item_data['Descricao'], qtd_total, qtd_total,
                item_data['Lote'], item_data['Val'] or None,
                pr_code, pr_code, usuario, agora, lpn
            )))
        else:
            # Cria
            sql_insert = """
                INSERT INTO Lpns (Lpn, Sku, Descricao, QtdOriginal, QtdAtual, Status, 
                                  Lote, Validade, Endereco, PrRef, Origem, CriadoPor, Cadastro, RowVersion)
                VALUES (?, ?, ?, ?, ?, 'Aguardando Armazenamento', 
                        ?, ?, 'RECEBIMENTO', ?, ?, ?, ?, 1)
            """
            cmds.append((sql_insert, (
                lpn, item_data['Sku'], item_data['Descricao'], qtd_total, qtd_total,
                item_data['Lote'], item_data['Val'] or None,
                pr_code, pr_code, usuario, agora
            )))

        try:
            self.execute_transaction(cmds)
            return True, f"LPN {lpn} fechado com {qtd_total} un."
        except Exception as e:
            return False, f"Erro ao fechar LPN: {e}"

    def update_pr_dados(self, pr, nova_oc=None, novo_destino=None, aplicar_a_todos=False):
        # 1. Atualiza OC no Header
        if nova_oc is not None:
            self.execute_non_query("UPDATE Recebimento SET Oc=? WHERE PrCode=?", (nova_oc, pr))

        # 2. Atualiza Destino em massa (se solicitado)
        if novo_destino is not None and aplicar_a_todos:
            self.execute_non_query("UPDATE RecebimentoItens SET Destino=? WHERE PrCode=?", (novo_destino, pr))

        # 3. CORREÇÃO: Chama o recálculo para validar a nova OC e retorna o status
        if nova_oc is not None:
            return self.recalcular_status_geral(pr)

        return None

    def update_item_destino(self, item_id, novo_destino):
        query = "UPDATE RecebimentoItens SET Destino=?, AtualizadoPor='Admin', Alteracao=? WHERE Id=?"
        self.execute_non_query(query, (novo_destino, datetime.now(), item_id))
        return True

    def recalcular_status_geral(self, pr_code, usuario="Sistema", auto_reparar=False):
        header = self.get_by_pr(pr_code)
        if not header: return None, None

        status_atual_banco = header.get('Status')
        obs_atual_banco = header.get('ObsFiscal')

        itens = self.list_itens_por_pr(pr_code)
        if not itens: return "Erro", "PR sem itens"

        skus_presentes = list({str(i['Sku']) for i in itens if i.get('Sku')})
        valid_units_map = {}
        if skus_presentes:
            placeholders = ','.join(['?'] * len(skus_presentes))
            query_emb = f"""
                        SELECT p.Sku, pe.Unidade 
                        FROM ProdutoEmbalagens pe
                        JOIN Produtos p ON pe.ProdutoId = p.Id
                        WHERE p.Sku IN ({placeholders})
                    """
            try:
                res_emb = self.execute_query(query_emb, tuple(skus_presentes))
                for row in res_emb:
                    s = str(row['Sku']).upper()
                    u = str(row['Unidade']).strip().upper()
                    if s not in valid_units_map: valid_units_map[s] = set()
                    valid_units_map[s].add(u)
            except Exception as e:
                print(f"Erro ao carregar embalagens: {e}")

        alias_map = {}
        try:
            res_alias = self.execute_query("SELECT UXml, UInterna FROM UnidadesAlias")
            for r in res_alias:
                sigla_xml = str(r['UXml']).strip().upper()
                sigla_sys = str(r['UInterna']).strip().upper()
                alias_map[sigla_xml] = sigla_sys
        except Exception as e:
            print(f"Erro ao carregar alias: {e}")

        cmds_correcao_itens = []

        conferencia_iniciada = (status_atual_banco == StatusPR.EM_CONFERENCIA)
        tem_pendencia_vinculo = False
        tem_pendencia_unidade = False
        tem_problema_qualidade = False
        tem_divergencia_qtd = False
        tem_divergencia_financeira = False
        tem_bloqueio_fiscal = False

        todos_itens_conferidos = True

        for i in itens:
            sku_item = str(i.get('Sku') or "").upper()
            und_item = str(i.get('Und') or "").strip().upper()

            if not i.get('Sku'):
                tem_pendencia_vinculo = True

            if sku_item:
                unidades_deste_sku = valid_units_map.get(sku_item, set())
                match_direto = und_item in unidades_deste_sku
                match_via_alias = False
                if not match_direto:
                    traducao = alias_map.get(und_item)
                    if traducao and traducao in unidades_deste_sku:
                        match_via_alias = True
                if not match_direto and not match_via_alias:
                    tem_pendencia_unidade = True
                    i['StatusCalculado'] = StatusPR.AGUARD_VINC_UNID

            status_calculado = i.get('StatusCalculado')
            status_banco = i.get('Status')

            if status_calculado and status_banco != status_calculado:
                if status_banco not in [StatusPR.CONCLUIDO, StatusPR.CANCELADO]:
                    cmds_correcao_itens.append(
                        (f"UPDATE RecebimentoItens SET Status = ? WHERE Id = ?", (status_calculado, i['Id'])))
                    i['Status'] = status_calculado
                    status_banco = status_calculado

            qtd_nota = float(i.get('Qtd', 0))
            qtd_coletada = float(i.get('QtdColetada', 0))
            status_item = i.get('Status')

            if qtd_coletada > 0:
                conferencia_iniciada = True

            # LÓGICA DE PROGRESSO: Verifica se a quantidade bate com a nota
            if abs(qtd_nota - qtd_coletada) > 0.001:
                if status_item not in [StatusPR.AGUARDANDO_DECISAO, StatusPR.BLOQUEADO_FISCAL, StatusPR.EM_ANALISE,
                                       StatusPR.DIVERGENCIA]:
                    todos_itens_conferidos = False

            if status_item in [StatusPR.AGUARDANDO_CONF, StatusPR.EM_CONFERENCIA, StatusPR.AGUARDANDO_VINCULO,
                               StatusPR.AGUARD_VINC_UNID]:
                todos_itens_conferidos = False

            # DEFINIÇÃO DE FLAGS BASEADA ESTRITAMENTE NO STATUS DO ITEM
            if status_item == StatusPR.BLOQUEADO_FISCAL:
                tem_bloqueio_fiscal = True
            elif status_item == StatusPR.DIVERGENCIA:
                tem_divergencia_financeira = True
            elif status_item == StatusPR.EM_ANALISE:
                tem_problema_qualidade = True
            elif status_item == StatusPR.AGUARDANDO_DECISAO:
                tem_divergencia_qtd = True

        if cmds_correcao_itens:
            try:
                self.execute_transaction(cmds_correcao_itens)
            except Exception as e:
                print(f"Aviso: Erro ao sincronizar status dos itens: {e}")

        if status_atual_banco in [StatusPR.CANCELADO, StatusPR.RECUSADO]:
            return status_atual_banco, obs_atual_banco

        if status_atual_banco == StatusPR.CONCLUIDO and not auto_reparar:
            return StatusPR.CONCLUIDO, obs_atual_banco

        # FASE 1: PREPARAÇÃO
        if not conferencia_iniciada and status_atual_banco != StatusPR.AGUARDANDO_CONCLUSAO:
            if tem_bloqueio_fiscal:
                novo_status = StatusPR.BLOQUEADO_FISCAL
            elif tem_pendencia_vinculo:
                novo_status = StatusPR.AGUARDANDO_VINCULO
            elif tem_pendencia_unidade:
                novo_status = StatusPR.AGUARD_VINC_UNID
            elif tem_divergencia_financeira:
                novo_status = StatusPR.DIVERGENCIA
            else:
                if status_atual_banco in [StatusPR.PROCESSANDO, StatusPR.AGUARDANDO_LIBERACAO]:
                    novo_status = StatusPR.AGUARDANDO_LIBERACAO
                else:
                    novo_status = StatusPR.AGUARDANDO_CONF
        # FASE 2: EXECUÇÃO
        else:
            if not todos_itens_conferidos:
                novo_status = StatusPR.EM_CONFERENCIA
            elif tem_bloqueio_fiscal:
                novo_status = StatusPR.BLOQUEADO_FISCAL
            elif tem_divergencia_financeira:
                novo_status = StatusPR.DIVERGENCIA
            elif tem_problema_qualidade:
                novo_status = StatusPR.EM_ANALISE
            elif tem_divergencia_qtd:
                novo_status = StatusPR.AGUARDANDO_DECISAO
            else:
                novo_status = StatusPR.AGUARDANDO_CONCLUSAO

        for i in itens:
            if i.get('StatusCalculado'): i['Status'] = i['StatusCalculado']
        novo_motivo = StatusPR.motivo_status_pr(novo_status, itens_header=itens)

        mudou_status = (status_atual_banco != novo_status)

        if todos_itens_conferidos and conferencia_iniciada:
            self._fechar_sessao_ativa(pr_code, status_fim="Finalizado Físico")

        if mudou_status:
            query = """
                        UPDATE Recebimento 
                        SET Status = ?, ObsFiscal = ?, AtualizadoPor = ?, Alteracao = GETDATE(), RowVersion = RowVersion + 1 
                        WHERE PrCode = ?
                    """
            self.execute_non_query(query, (novo_status, novo_motivo, usuario, pr_code))

        elif (obs_atual_banco or "") != (novo_motivo or ""):
            query = "UPDATE Recebimento SET ObsFiscal = ?, RowVersion = RowVersion + 1 WHERE PrCode = ?"
            self.execute_non_query(query, (novo_motivo, pr_code))

        return novo_status, novo_motivo

    def recalcular_todos_prs_abertos(self):
        # Gatilho Ativo: Força a atualização de todos os recebimentos em aberto.
        # Deve ser chamado quando configurações globais (ex: tolerância) mudam.

        query = f"SELECT PrCode FROM Recebimento WHERE Status NOT IN ('{StatusPR.CONCLUIDO}', '{StatusPR.CANCELADO}')"
        res = self.execute_query(query)
        count = 0
        for r in res:
            self.recalcular_status_geral(r['PrCode'], "Sistema (Config Update)")
            count += 1

    def obter_sugestao_armazenagem(self, item_id):
        # Busca Status e TentativasErro
        res = self.execute_query("SELECT Sku, Status, TentativasErro FROM RecebimentoItens WHERE Id=?", (item_id,))
        if not res: return "N/D"
        item = res[0]

        status = item["Status"]
        tentativas = int(item.get("TentativasErro") or 0)

        # Regra Centralizada + Checagem de Fato (Tentativas)
        status_quarentena = [
            StatusPR.BLOQUEADO_FISCAL,
            StatusPR.DIVERGENCIA,
            StatusPR.EM_ANALISE,
            StatusPR.AGUARDANDO_DECISAO
        ]

        # Se o status diz que é problema OU se estourou as tentativas (mesmo que o status esteja desatualizado)
        if (status in status_quarentena) or (tentativas >= StatusPR.LIMITE_TENTATIVAS):
            return self.sugerir_endereco_quarentena()

        return "PADRAO-ARMAZENAGEM"

    def sugerir_endereco_quarentena(self):

        # Busca endereço físico de quarentena vazio.
        # (Este método substitui o _buscar_endereco_quarentena_livre)

        ENDERECO_CORINGA = "AREA_TRANSBORDO_QUA"

        try:
            # 1. Busca candidatos no banco (Endereços físicos de uso 'Quarentena')
            query_locais = """
                SELECT Id, Rua, Predio, Nivel, GrupoBloqueio, Visual 
                FROM Enderecos 
                WHERE (Uso = 'Quarentena' OR Nome LIKE 'QUA%') 
                  AND Ativo = 1
                ORDER BY Rua, Predio, Nivel
            """
            candidatos = self.execute_query(query_locais)

            if not candidatos:
                return ENDERECO_CORINGA

            # 2. Checa ocupação
            for cand in candidatos:
                # Se não tiver ninguém ocupando este endereço na tabela Estoque...
                query_ocup = "SELECT COUNT(*) as Qtd FROM Estoque WHERE EnderecoId = ?"
                check = self.execute_query(query_ocup, (cand['Id'],))

                if check and check[0]['Qtd'] == 0:
                    return self._formatar_endereco_visual(cand)

            # 3. Se tudo cheio, manda pro transbordo
            return ENDERECO_CORINGA

        except Exception as e:
            print(f"Erro ao sugerir quarentena: {e}")
            return ENDERECO_CORINGA

    def _formatar_endereco_visual(self, dados_addr):
        # Helper simples
        if dados_addr.get('Visual'): return dados_addr['Visual']

        r, p, n = dados_addr['Rua'], dados_addr['Predio'], dados_addr['Nivel']
        g = dados_addr.get('GrupoBloqueio', '')
        base = f"{r:02d}-{p:02d}-{n:02d}"
        return f"{base}-{g}" if g else base

    def gravar_chapa_quente(self, pr_code):
        # SNAPSHOT FINAL: Copia apenas a Descrição para facilitar busca futura.
        # CORREÇÃO: Não alteramos mais a Unidade (i.Und). Mantemos o que veio na Nota/XML.

        sql_snapshot = """
            UPDATE i
            SET 
                i.Descricao = p.Descricao,
                i.ObsFiscal = CASE 
                    WHEN i.ObsFiscal IS NULL THEN 'SNAPSHOT: Dados gravados.' 
                    ELSE i.ObsFiscal + ' | SNAPSHOT: Dados gravados.' 
                END
            FROM RecebimentoItens i
            JOIN Produtos p ON i.Sku = p.Sku
            WHERE i.PrCode = ?
        """
        try:
            self.execute_non_query(sql_snapshot, (pr_code,))
            return True
        except Exception as e:
            print(f"Erro ao gravar histórico do PR {pr_code}: {e}")
            return False

    def get_analise_pr(self, pr_code):
        # 1. Carrega dados
        header = self.get_by_pr(pr_code)
        if not header: return None

        itens = self.list_itens_por_pr(pr_code)
        status = header.get("Status")

        # Dados da OC
        oc_str = header.get("Oc", "")
        dados_oc = None
        if oc_str and oc_str.lower() != "none":
            oc_num = oc_str.split(',')[0].strip()
            dados_oc = self.oc_repo.get_oc(oc_num)

        # 2. Configurações
        tol_val = getattr(self.global_policies, "tolerancia_valor_recebimento", 0.00)
        tol_tipo = getattr(self.global_policies, "tolerancia_tipo_recebimento", "Valor")

        resultado = {
            "fisico": [],
            "qualidade": [],
            "financeiro": [],
            "oc_status": "OK" if dados_oc else "SEM_OC",
            "totais": {
                "esperado": 0.0,
                "coletado": 0.0,
                "count_itens": len(itens)
            },
            "skus_problematicos": set()  # Agora armazena IDs para contagem correta
        }

        hoje = datetime.now()

        for i in itens:
            item_id = i.get('Id')
            sku = i.get('Sku')  # Pode ser None se não vinculado
            q_nota = float(i.get("Qtd", 0))
            q_real = float(i.get("QtdColetada", 0))
            preco_nota = float(i.get("Preco", 0))
            unid = i.get('Und', 'UN')

            resultado["totais"]["esperado"] += q_nota
            resultado["totais"]["coletado"] += q_real

            # --- 1. DEFINIÇÕES INICIAIS ---
            # Verifica se é bônus pelo Preço (0) OU pela Flag de CFOP (Brinde R$0,01)
            is_bonus = (preco_nota == 0) or (i.get('EhBonificacao') == 1)
            item_na_oc = False

            # Verifica se está na OC (se OC existir e SKU existir)
            if dados_oc and 'itens' in dados_oc and sku:
                if sku in dados_oc['itens']:
                    item_na_oc = True

            # --- A. ANÁLISE FÍSICA ---

            # 1. Checagem de Extra / Não Previsto
            if not item_na_oc:
                detalhe_extra = "Não previsto na OC"
                if not dados_oc:
                    detalhe_extra = "Sem OC vinculada"

                if is_bonus:
                    detalhe_extra = "Bonificação"

                # Adiciona como 'Extra'
                resultado["fisico"].append({
                    "sku": sku or "Item s/ Vínculo",
                    "tipo": "extra",
                    "is_bonus": is_bonus,
                    "detalhe": detalhe_extra
                })

                # Se não for bônus, é um problema que trava o recebimento
                if not is_bonus:
                    resultado["skus_problematicos"].add(item_id)

            # 2. Diferença de Quantidade (Sobra vs Falta)
            diff = q_real - q_nota

            # CASO 1: SOBRA (Erro Imediato)
            if diff > 0.001:
                resultado["fisico"].append({
                    "sku": sku or "Item s/ Vínculo",
                    "tipo": "divergencia",
                    "diff": diff,
                    "q_nota": q_nota,
                    "unid": unid
                })
                resultado["skus_problematicos"].add(item_id)

            # CASO 2: FALTA (Análise Condicional)
            elif diff < -0.001:
                is_falta_real = False

                if status == StatusPR.CONCLUIDO:
                    is_falta_real = True
                elif status == StatusPR.CANCELADO:
                    is_falta_real = False
                else:
                    # Só considera ERRO se já houve contagem parcial ou tentativa de erro
                    tentativas = int(i.get("TentativasErro") or 0)
                    if q_real > 0 or tentativas > 0:
                        is_falta_real = True

                if is_falta_real:
                    resultado["fisico"].append({
                        "Sku": sku or "Item s/ Vínculo",
                        "Tipo": "divergencia",
                        "diff": diff,
                        "q_nota": q_nota,
                        "unid": unid
                    })
                    resultado["skus_problematicos"].add(item_id)
                else:
                    # Se for item da OC ou Bonificação, mostra como "Esperado"
                    deve_exibir_pendencia = (item_na_oc or is_bonus)

                    if deve_exibir_pendencia:
                        resultado["fisico"].append({
                            "Sku": sku or "Item s/ Vínculo",
                            "Tipo": "pendente",
                            "q_nota": q_nota,
                            "unid": unid
                        })

            # --- B. ANÁLISE FINANCEIRA ---
            # Só valida preço se o item estiver na OC
            if item_na_oc and dados_oc:
                preco_oc = float(dados_oc['itens'][sku].get('Preco', 0))

                if tol_tipo == "Porcentagem":
                    delta_tol = preco_oc * (tol_val / 100.0)
                else:
                    delta_tol = tol_val

                if abs(preco_nota - preco_oc) > delta_tol:
                    resultado["financeiro"].append({
                        "Sku": sku, "preco_nota": preco_nota, "preco_oc": preco_oc
                    })
                    resultado["skus_problematicos"].add(item_id)

            # --- C. ANÁLISE QUALIDADE ---
            val_str = i.get("Val")
            if val_str and len(val_str) == 10:
                try:
                    dt_val = datetime.strptime(val_str, "%d/%m/%Y")
                    dias = (dt_val - hoje).days
                    if dias < 0:
                        resultado["qualidade"].append({"Sku": sku, "motivo": "vencido", "lote": i.get('Lote')})
                        resultado["skus_problematicos"].add(item_id)
                    elif dias < 30:
                        resultado["qualidade"].append({"Sku": sku, "motivo": "curto_prazo"})
                except:
                    pass

            dados_q = i.get("dados_qualidade", {}) or {}
            if dados_q.get("embalagem_integra") == "Não" or dados_q.get("material_integro") == "Não":
                resultado["qualidade"].append({"Sku": sku, "motivo": "avaria"})
                resultado["skus_problematicos"].add(item_id)

            # D. Divergências Visuais (NOVA LÓGICA TEXTO)
            # Substitua qualquer lógica antiga de JSON ou Header por isso:
            div_visual = i.get("DivergenciaVisual")
            status_item = i.get("Status")

            if div_visual and status_item == StatusPR.EM_ANALISE:
                resultado["fisico"].append({
                    "Sku": sku,
                    "Tipo": "visual",
                    "detalhe": div_visual  # Texto puro
                })
                resultado["skus_problematicos"].add(item_id)

        return resultado

    def get_dashboard_kpis(self):
        query = f"""
            SELECT 
                SUM(CASE WHEN Status = '{StatusPR.AGUARDANDO_CONF}' THEN 1 ELSE 0 END) as aguardando,
                SUM(CASE WHEN Status = '{StatusPR.EM_CONFERENCIA}' THEN 1 ELSE 0 END) as em_andamento,
                SUM(CASE WHEN Status IN ('{StatusPR.DIVERGENCIA}', '{StatusPR.EM_ANALISE}', '{StatusPR.BLOQUEADO_FISCAL}') THEN 1 ELSE 0 END) as problemas,
                SUM(CASE WHEN Status = '{StatusPR.PROCESSANDO}' THEN 1 ELSE 0 END) as processando
            FROM Recebimento
            WHERE Status NOT IN ('{StatusPR.CANCELADO}', '{StatusPR.CONCLUIDO}')
        """

        try:
            res = self.execute_query(query)
            if res:
                r = res[0]
                return {
                    "aguardando": r['aguardando'] or 0,
                    "em_andamento": r['em_andamento'] or 0,
                    "problemas": r['problemas'] or 0,
                    "processando": r['processando'] or 0
                }
            return {"aguardando": 0, "em_andamento": 0, "problemas": 0, "processando": 0}
        except Exception as e:
            print(f"Erro KPI: {e}")
            return {}

class VinculoService:
    def __init__(self, repo):
        self.repo = repo

    def vincular(self, item_id, sku_oc, usuario="Sistema"):
        # Vincula um item a um SKU e aprende esse vínculo para o futuro.
        # Não permite alteração se o PR estiver Concluído ou Cancelado

        # 1. BUSCA O CONTEXTO
        query_dados = """
                            SELECT i.CodOrig, r.Cnpj, r.Status, r.PrCode
                            FROM RecebimentoItens i
                            JOIN Recebimento r ON i.PrCode = r.PrCode
                            WHERE i.Id = ?
                        """
        dados = self.repo.execute_query(query_dados, (item_id,))

        if not dados:
            return False, "Item não encontrado."

        linha = dados[0]

        status_bloqueados = [StatusPR.CONCLUIDO, StatusPR.CANCELADO]
        if linha['Status'] in status_bloqueados:
            return False, f"Ação negada: O Recebimento {linha['PrCode']} já está {linha['Status']}."

        cod_orig = linha['CodOrig']
        cnpj = linha['Cnpj']

        produto_interno = self.repo.products_repo.get_by_sku(sku_oc)
        nova_descricao = produto_interno.get("Descricao", "") if produto_interno else "Descrição não encontrada"

        # 3. MONTA A TRANSAÇÃO
        cmds = []

        # A. Atualiza o ITEM do Recebimento (SKU + Descrição)
        cmds.append((
            "UPDATE RecebimentoItens SET Sku = ?, Descricao = ? WHERE Id = ?",
            (sku_oc, nova_descricao, item_id)
        ))

        cmds.append((
            "INSERT INTO ProdutosAlias (Cnpj, CodFornecedor, SkuInterno, CriadoPor) VALUES (?, ?, ?, ?)",
            (cnpj, cod_orig, sku_oc, usuario)
        ))

        # 4. EXECUTA TUDO
        try:
            self.repo.execute_transaction(cmds)
            self.repo.recalcular_status_geral(linha['PrCode'], f"{usuario} (Vínculo)")
            return True, "Vínculo realizado e descrição atualizada."
        except Exception as e:
            return False, f"Erro ao salvar: {str(e)}"

    def desvincular(self, item_id):
        # Desvincula um item do SKU e remove o vínculo da tabela

        # 1. BUSCA O CONTEXTO
        query_check = """
                    SELECT i.CodOrig, r.Cnpj, r.Status, r.PrCode
                    FROM RecebimentoItens i
                    JOIN Recebimento r ON i.PrCode = r.PrCode
                    WHERE i.Id = ?
                """
        dados = self.repo.execute_query(query_check, (item_id,))

        if not dados:
            return False, "Item não encontrado."

        linha = dados[0]
        # Usando StatusPR para verificar se está fechado
        pr_fechado = linha['Status'] in [StatusPR.CONCLUIDO, StatusPR.CANCELADO]

        # 2. MONTA A TRANSAÇÃO
        cmds = []

        # Remove o Alias (Futuro)
        cmds.append((
            "DELETE FROM ProdutosAlias WHERE Cnpj = ? AND CodFornecedor = ?",
            (linha['Cnpj'], linha['CodOrig'])
        ))

        # Se o PR estiver ABERTO, limpa o item (Passado/Presente)
        if not pr_fechado:
            cmds.append((
                "UPDATE RecebimentoItens SET Sku = NULL, Descricao = DescricaoXml WHERE Id = ?",
                (item_id,)
            ))

        # 3. EXECUTA
        try:
            self.repo.execute_transaction(cmds)

            if not pr_fechado:
                self.repo.recalcular_status_geral(linha['PrCode'], "Sistema")

            return True, "Vínculo removido"

        except Exception as e:
            return False, f"Erro ao desvincular: {str(e)}"

    def consultar_vinculo(self, cnpj, cod_orig):
        # Definição: Fazer um SELECT no ProdutosAlias para ver se existe vínculo conhecido.

        query = "SELECT SkuInterno FROM ProdutosAlias WHERE Cnpj = ? AND CodFornecedor = ?"
        resultado = self.repo.execute_query(query, (cnpj, cod_orig))

        if resultado:
            return resultado[0]['SkuInterno']
        return None

    def vinculo_automatico(self, item_id, ean_nota):
        # Definição:
        # - Procurar EAN da nota na coluna Ean na tabela ProdutoEmbalagens.
        # - Se encontrou, executa a função vincular.

        # 1. Procura o EAN na tabela ProdutoEmbalagens
        query = """
                    SELECT p.Sku 
                    FROM ProdutoEmbalagens pe
                    JOIN Produtos p ON pe.ProdutoId = p.Id
                    WHERE pe.Ean = ?
                """
        resultado = self.repo.execute_query(query, (ean_nota,))

        if resultado:
            sku_encontrado = resultado[0]['Sku']
            self.vincular(item_id, sku_encontrado)

    def vinculo_automatico_alias(self, item_id):
        # Consulta ProdutosAlias. Se encontrar vínculo, aplica.

        # 1. Busca contexto
        query_dados = """
                    SELECT i.CodOrig, r.Cnpj, i.Sku
                    FROM RecebimentoItens i
                    JOIN Recebimento r ON i.PrCode = r.PrCode
                    WHERE i.Id = ?
                """
        dados = self.repo.execute_query(query_dados, (item_id,))

        if not dados: return False
        linha = dados[0]

        # Se já tem SKU, aborta
        if linha['Sku']: return False

        # 2. Consulta Alias
        sku_encontrado = self.consultar_vinculo(linha['Cnpj'], linha['CodOrig'])

        if sku_encontrado:
            # 3. Aplica Update (Silencioso)
            try:
                self.repo.execute_non_query(
                    "UPDATE RecebimentoItens SET Sku = ? WHERE Id = ?",
                    (sku_encontrado, item_id)
                )
                return True
            except:
                return False

        return False