from datetime import datetime

from utils.constants import StatusPR
from ..base import BaseRepo


class UnitsRepo(BaseRepo):
    def __init__(self):
        super().__init__("Unidades")

    def add(self, sigla: str, descricao: str, decimais_sim_nao: str):
        decimais = 1 if str(decimais_sim_nao).strip().upper() == "SIM" else 0

        # MUDEI AQUI: GETDATE() virou ?
        query = """
            INSERT INTO Unidades (Sigla, Descricao, Decimais, Cadastro, RowVersion)
            VALUES (?, ?, ?, ?, 1)
        """
        try:
            # MUDEI AQUI: Adicionei datetime.now() na lista de parâmetros
            self.execute_non_query(query, (sigla, descricao, decimais, datetime.now()))
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError("Já existe uma unidade com esta sigla.")
            raise e

    def update(self, old_sigla: str, new_sigla: str, descricao: str, decimais_sim_nao: str):
        # CORREÇÃO: Converte para maiúsculo aqui também
        decimais = 1 if str(decimais_sim_nao).strip().upper() == "SIM" else 0

        query = """
            UPDATE Unidades 
            SET Sigla=?, Descricao=?, Decimais=?, Alteracao=?, RowVersion=RowVersion+1
            WHERE Sigla=?
        """
        try:
            self.execute_non_query(query, (new_sigla, descricao, decimais, datetime.now(), old_sigla))
            return True
        except Exception as e:
            raise ValueError("Erro ao atualizar ou sigla duplicada.")

    def delete(self, sigla: str):
        # 1. Verificação de Segurança: Unidade Principal
        # Verifica se algum produto usa essa unidade como padrão
        query_prod = "SELECT COUNT(*) as Qtd FROM Produtos WHERE Unidade = ?"
        res_prod = self.execute_query(query_prod, (sigla,))
        if res_prod and res_prod[0]['Qtd'] > 0:
            qtd = res_prod[0]['Qtd']
            raise ValueError(f"Não é possível excluir '{sigla}'.\nEla é a unidade principal de {qtd} produto(s).")

        # 2. Verificação de Segurança: Embalagens (Fatores)
        # Verifica se algum produto tem uma caixa/conversão usando essa unidade
        query_emb = "SELECT COUNT(*) as Qtd FROM ProdutoEmbalagens WHERE Unidade = ?"
        res_emb = self.execute_query(query_emb, (sigla,))
        if res_emb and res_emb[0]['Qtd'] > 0:
            qtd = res_emb[0]['Qtd']
            termo = "produto" if qtd == 1 else "produtos"
            raise ValueError(f"Não é possível excluir '{sigla}'.\nEla é usada na embalagem de {qtd} {termo}.")

        # 3. Se passou pelas verificações, pode excluir
        query = "DELETE FROM Unidades WHERE Sigla = ?"
        self.execute_non_query(query, (sigla,))
        return True

    def get_by_sigla(self, sigla: str):
        res = self.execute_query("SELECT * FROM Unidades WHERE Sigla = ?", (sigla,))
        return res[0] if res else None


class FamiliesRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("Familias")
        self.event_bus = event_bus

    def add(self, nome: str, descricao: str, **kwargs):
        vida_util = kwargs.get("VidaUtil")
        criado_por = kwargs.get("Usuario", "Admin")
        area_pref = kwargs.get("AreaPreferencial")

        # Políticas
        val_mode = kwargs.get("ValidadeModo", "Herdar")
        lote_mode = kwargs.get("LoteModo", "Herdar")
        giro_mode = kwargs.get("GiroModo", "Herdar")
        var_consumo = kwargs.get("VariavelConsumo", "Herdar")
        val_min = kwargs.get("ValidadeMinimaDias")

        # Bloqueios
        b_vencido = kwargs.get("BlockVencido")
        b_semval = kwargs.get("BlockSemValidade")
        b_semlote = kwargs.get("BlockSemLote")
        b_qualidade = kwargs.get("BlockRepQualidade")

        try:
            query = """
                            INSERT INTO Familias (
                                Nome, Descricao, VidaUtil, CriadoPor, Cadastro, RowVersion, 
                                ValidadeModo, LoteModo, GiroModo, VariavelConsumo, ValidadeMinimaDias,
                                BlockVencido, BlockSemValidade, BlockSemLote, BlockRepQualidade,
                                AreaPreferencial  -- <--- ADICIONE NO INSERT
                            )
                            VALUES (?, ?, ?, ?, ?, 1, 
                                    ?, ?, ?, ?, ?,
                                    ?, ?, ?, ?,
                                    ?)
                        """
            params = (
                nome.strip(), descricao.strip(), vida_util, criado_por, datetime.now(),
                val_mode, lote_mode, giro_mode, var_consumo, val_min,
                b_vencido, b_semval, b_semlote, b_qualidade,
                area_pref
            )
            self.execute_non_query(query, params)
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError("Família já existente.")
            raise e

    def update(self, old_nome: str, **kwargs):
        # 1. Busca os dados atuais no banco para comparar
        current = self.get_by_nome(old_nome)
        if not current: raise ValueError("Família não encontrada.")

        # 2. Prepara os valores novos (Inputs)
        new_nome = kwargs.get("new_nome", old_nome).strip()
        descricao = (kwargs.get("Descricao") or "").strip()
        vida_util = kwargs.get("VidaUtil")
        usuario = kwargs.get("Usuario", "Admin")
        area_pref = kwargs.get("AreaPreferencial")

        # Políticas
        val_mode = kwargs.get("ValidadeModo")
        lote_mode = kwargs.get("LoteModo")
        giro_mode = kwargs.get("GiroModo")
        var_consumo = kwargs.get("VariavelConsumo")
        val_min = kwargs.get("ValidadeMinimaDias")

        # Bloqueios (Converte para bool para garantir comparação certa)
        b_vencido = bool(kwargs.get("BlockVencido"))
        b_semval = bool(kwargs.get("BlockSemValidade"))
        b_semlote = bool(kwargs.get("BlockSemLote"))
        b_qualidade = bool(kwargs.get("BlockRepQualidade"))

        # 3. Função auxiliar para comparar (trata texto, número e None)
        def mudou(valor_banco, valor_novo):
            # Se for booleano (bloqueios), compara direto
            if isinstance(valor_novo, bool):
                return bool(valor_banco) != valor_novo
            # Para textos e números, converte para string e compara
            v1 = str(valor_banco) if valor_banco is not None else ""
            v2 = str(valor_novo) if valor_novo is not None else ""
            return v1.strip() != v2.strip()

        # 4. Verifica se algo mudou
        teve_alteracao = (
                mudou(current['Nome'], new_nome) or
                mudou(current['Descricao'], descricao) or
                mudou(current['VidaUtil'], vida_util) or
                mudou(current['ValidadeModo'], val_mode) or
                mudou(current['LoteModo'], lote_mode) or
                mudou(current['GiroModo'], giro_mode) or
                mudou(current['VariavelConsumo'], var_consumo) or
                mudou(current['ValidadeMinimaDias'], val_min) or
                mudou(current['BlockVencido'], b_vencido) or
                mudou(current['BlockSemValidade'], b_semval) or
                mudou(current['BlockSemLote'], b_semlote) or
                mudou(current['BlockRepQualidade'], b_qualidade) or
                mudou(current.get('AreaPreferencial'), area_pref)
        )

        if not teve_alteracao:
            return False

        # 5. Se mudou, executa o UPDATE (Código corrigido com a data certa)
        query = """
            UPDATE Familias 
            SET Nome=?, Descricao=?, VidaUtil=?, 
                ValidadeModo=?, LoteModo=?, GiroModo=?, VariavelConsumo=?, ValidadeMinimaDias=?,
                BlockVencido=?, BlockSemValidade=?, BlockSemLote=?, BlockRepQualidade=?, AreaPreferencial=?,
                Alteracao=?, RowVersion=RowVersion+1, AtualizadoPor=?
            WHERE Nome=?
        """

        params = (
            new_nome, descricao, vida_util,
            val_mode, lote_mode, giro_mode, var_consumo, val_min,
            b_vencido, b_semval, b_semlote, b_qualidade, area_pref,
            datetime.now(),
            usuario,
            old_nome
        )

        try:
            self.execute_non_query(query, params)
            if self.event_bus:
                self.event_bus.publish("familia_alterada", {"Familia": new_nome})
            return True
        except Exception as e:
            print(f"Erro SQL Update Família: {e}")
            raise ValueError(f"Erro ao atualizar: {e}")

    def delete(self, nome: str):
        # 1. VERIFICAÇÃO: Produtos vinculados
        query_check = "SELECT COUNT(*) as Qtd FROM Produtos WHERE Familia = ?"
        res = self.execute_query(query_check, (nome,))

        if res and res[0]['Qtd'] > 0:
            qtd = res[0]['Qtd']
            termo = "produto" if qtd == 1 else "produtos"
            raise ValueError(f"Não é possível excluir a família '{nome}'.\nEla está vinculada a {qtd} {termo}.")

        # 2. Se não tem vínculos, exclui
        self.execute_non_query("DELETE FROM Familias WHERE Nome=?", (nome,))
        return True

    def get_by_nome(self, nome: str):
        if not nome: return None
        res = self.execute_query("SELECT * FROM Familias WHERE Nome=?", (str(nome).strip(),))
        return res[0] if res else None

    def set_validade_modo(self, nome: str, modo: str):
        if modo not in ("Herdar", "Validade opcional", "Validade obrigatória"):
            raise ValueError("Modo inválido.")
        query = "UPDATE Familias SET ValidadeModo=?, Alteracao=?, RowVersion=RowVersion+1 WHERE Nome=?"
        self.execute_non_query(query, (modo, datetime.now(), nome))
        return True

    def count_exceptions(self, g_policies):
        self._rows = self.execute_query("SELECT * FROM Familias")
        g_val = g_policies.modo_validade or "Validade opcional"
        g_giro = str(getattr(g_policies, "modelo_giro", "FEFO")).upper()
        g_lote = str(getattr(g_policies, "modo_lote", "Lote opcional"))
        g_blk_v = bool(getattr(g_policies, "bloquear_vencido", False))
        g_blk_s = bool(getattr(g_policies, "bloquear_sem_validade_obrigatoria", False))
        g_blk_l = bool(getattr(g_policies, "bloquear_sem_lote_obrigatorio", False))
        g_blk_q = bool(getattr(g_policies, "bloquear_reprovacao_qualidade", False))

        counts = {"validade": 0, "bloqueio": 0, "giro": 0, "lote": 0}

        for r in self._rows:
            if r.get("ValidadeModo", "Herdar") not in ("Herdar", g_val): counts["validade"] += 1
            if r.get("GiroModo") and str(r.get("GiroModo")) not in ("Herdar", "None", "") and str(
                r.get("GiroModo")).upper() != g_giro: counts["giro"] += 1
            if r.get("LoteModo") and str(r.get("LoteModo")) not in ("Herdar", "None", "") and str(
                r.get("LoteModo")) != g_lote: counts["lote"] += 1

            # Bloqueios
            is_redundant = True
            if not all(r.get(k) is None for k in
                       ("BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade")):
                if r.get("BlockVencido") is not None and bool(r.get("BlockVencido")) != g_blk_v:
                    is_redundant = False
                elif r.get("BlockSemValidade") is not None and bool(r.get("BlockSemValidade")) != g_blk_s:
                    is_redundant = False
                elif r.get("BlockSemLote") is not None and bool(r.get("BlockSemLote")) != g_blk_l:
                    is_redundant = False
                elif r.get("BlockRepQualidade") is not None and bool(r.get("BlockRepQualidade")) != g_blk_q:
                    is_redundant = False

            if not is_redundant: counts["bloqueio"] += 1
        return counts

    def get_resolved_report(self, global_policies, filter_exceptions_only=True):
        self._rows = self.execute_query("SELECT * FROM Familias")
        g_val = global_policies.modo_validade or "Validade opcional"
        g_lote = getattr(global_policies, "modo_lote", "Lote opcional")
        g_giro = getattr(global_policies, "modelo_giro", "FEFO")
        gb = {
            "vencimento": bool(getattr(global_policies, "bloquear_vencido", False)),
            "sem_validade": bool(getattr(global_policies, "bloquear_sem_validade_obrigatoria", False)),
            "sem_lote": bool(getattr(global_policies, "bloquear_sem_lote_obrigatorio", False)),
            "rep_qualidade": bool(getattr(global_policies, "bloquear_reprovacao_qualidade", False))
        }
        resolved_rows = []
        for r in self._rows:
            processed = dict(r)
            has_exception = False

            def resolve(key, glob, pfx=""):
                is_prop = (r.get(key) is not None and str(r.get(key)) not in ("Herdar", "None"))
                val = r.get(key) if is_prop else glob
                return str(val).replace(pfx, "") + (" (Própria)" if is_prop else " (Herdada)"), is_prop

            processed["validade"], e1 = resolve("ValidadeModo", g_val, "Validade ")
            processed["lote"], e2 = resolve("LoteModo", g_lote, "Lote ")
            processed["giro"], e3 = resolve("GiroModo", g_giro)

            # Bloqueios Bool
            for k_db, k_gb in [("BlockVencido", "vencimento"), ("BlockSemValidade", "sem_validade"),
                               ("BlockSemLote", "sem_lote"), ("BlockRepQualidade", "rep_qualidade")]:
                is_p = r.get(k_db) is not None
                val = r.get(k_db) if is_p else gb[k_gb]
                processed[k_gb] = ("Sim" if val else "Não") + (" (Própria)" if is_p else " (Herdada)")
                if is_p: has_exception = True

            if not filter_exceptions_only or has_exception:
                resolved_rows.append(processed)
        return resolved_rows


class ProductsRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("Produtos")
        self.event_bus = event_bus

    def _safe_float(self, val):
        if val is None or val == "":
            return None  # Retorna None para o banco salvar como NULL
        try:
            return float(str(val).replace(',', '.'))
        except (ValueError, TypeError):
            return 0.0

    def add(self, **kwargs):
        # Captura os dados usando as chaves exatas do Banco (TitleCase)
        sku = str(kwargs.get("Sku")).strip()
        descricao = str(kwargs.get("Descricao")).strip()
        ean = str(kwargs.get("Ean") or "").strip()
        cod_fornecedor = str(kwargs.get("CodFornecedor") or "").strip()
        familia = str(kwargs.get("Familia")).strip()
        unidade = str(kwargs.get("Unidade")).strip()
        referencia = str(kwargs.get("Referencia") or "").strip()
        area_pref = kwargs.get("AreaPreferencial")
        area_mode = kwargs.get("AreaPreferencialModo", "Herdar")
        val_min = kwargs.get("ValidadeMinimaDias")
        vida_util = kwargs.get("VidaUtil")
        b_vencido = kwargs.get("BlockVencido")
        b_semval = kwargs.get("BlockSemValidade")
        b_semlote = kwargs.get("BlockSemLote")
        b_qualidade = kwargs.get("BlockRepQualidade")

        # Status e Bloqueios
        ativo = kwargs.get("Ativo", True)
        bloqueado = kwargs.get("Bloqueado", False)
        motivo = kwargs.get("MotivoBloqueio", "")
        obs = kwargs.get("ObsBloqueio", "")
        usuario = kwargs.get("Usuario", "Admin")

        # Camadas (Embalagens)
        camadas = kwargs.get("Camadas", [])

        cmds = []
        agora = datetime.now()

        query_prod = """
                                    INSERT INTO Produtos (
                                        Sku, Descricao, Ean, CodFornecedor, 
                                        Familia, FamiliaId,
                                        Unidade, UnidadeId,
                                        Referencia, 
                                        Cadastro, RowVersion, 
                                        ValidadeModo, LoteModo, GiroModo, VariavelConsumo, ValidadeMinimaDias,
                                        VidaUtil,
                                        BlockVencido, BlockSemValidade, BlockSemLote, BlockRepQualidade,
                                        Ativo, Bloqueado, MotivoBloqueio, ObsBloqueio,
                                        CriadoPor, AtualizadoPor, AreaPreferencial, AreaPreferencialModo
                                    )
                                    VALUES (
                                        ?, ?, ?, ?, 
                                        ?, (SELECT Id FROM Familias WHERE Nome = ?),
                                        ?, (SELECT Id FROM Unidades WHERE Sigla = ?),
                                        ?, 
                                        ?, 1, 
                                        'Herdar', 'Herdar', 'Herdar', 'Herdar', ?,
                                        ?,  -- <--- Apenas o placeholder do valor
                                        ?, ?, ?, ?,
                                        ?, ?, ?, ?,
                                        ?, ?, ?, ?
                                    )
                                """

        params_prod = (
            sku, descricao, ean, cod_fornecedor,
            familia, familia,
            unidade, unidade,
            referencia,
            agora,
            val_min,
            vida_util,
            b_vencido, b_semval, b_semlote, b_qualidade,
            ativo, bloqueado, motivo, obs,
            usuario, usuario, area_pref, area_mode
        )
        cmds.append((query_prod, params_prod))

        # 3. Insere Embalagens (Lógica mantida, apenas verificando se as chaves internas das camadas já estão TitleCase)
        for c in camadas:
            # A interface já manda TitleCase nas camadas (Ean, Unidade, FatorConversao...),
            # então o código original do loop funcionará, apenas certifique-se de usar TitleCase aqui também:

            raw_ean = str(c.get('Ean', '')).strip()
            c_ean = raw_ean if raw_ean else None
            c_und = str(c.get('Unidade', 'CX')).strip()
            c_tipo = str(c.get('Tipo', 'CAIXA')).strip()

            c_fator = self._safe_float(c.get('FatorConversao', 1)) or 1.0
            larg = self._safe_float(c.get('Largura'))
            alt = self._safe_float(c.get('Altura'))
            comp = self._safe_float(c.get('Comprimento'))
            peso = self._safe_float(c.get('PesoBruto'))

            larg_un = c.get('LarguraUn', 'mm')
            alt_un = c.get('AlturaUn', 'mm')
            comp_un = c.get('ComprimentoUn', 'mm')
            padrao = 1 if c.get('EhPadrao') else 0

            # Query SQL de embalagens... (Mantenha como está, pois já está correta)
            # Query SQL de embalagens
            sql_emb = """
                            INSERT INTO ProdutoEmbalagens (
                                ProdutoId, 
                                Ean, Unidade, FatorConversao, Tipo,
                                Largura, LarguraUn, Altura, AlturaUn, Comprimento, ComprimentoUn,
                                PesoBruto, EhPadrao, CriadoPor, Cadastro
                            )
                            VALUES (
                                (SELECT Id FROM Produtos WHERE Sku = ?), 
                                ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?
                            )
                        """

            cmds.append((sql_emb, (
                sku, c_ean, c_und, c_fator, c_tipo,
                larg, larg_un, alt, alt_un, comp, comp_un,
                peso, padrao, usuario, agora
            )))

        try:
            self.execute_transaction(cmds)
            if self.event_bus:
                self.event_bus.publish("produto_alterado", {"Sku": sku})
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Erro: O SKU '{sku}' ou EAN já está cadastrado.")
            raise e

    def update(self, old_sku, **kwargs):
        # 1. Busca dados atuais
        current = self.get_by_sku(old_sku)
        if not current: raise ValueError("Produto não encontrado.")

        prod_id = current['Id']
        usuario = kwargs.get("Usuario", "Admin")

        # 2. Prepara valores novos para a tabela Pai
        new_sku = kwargs.get("new_sku", kwargs.get("sku", kwargs.get("Sku", old_sku))).strip()
        desc = (kwargs.get("Descricao") or "").strip()
        ean = (kwargs.get("Ean") or "").strip()
        cod_forn = (kwargs.get("CodFornecedor") or "").strip()
        fam = (kwargs.get("familia") or kwargs.get("Familia") or "").strip()
        und = (kwargs.get("unidade") or kwargs.get("Unidade") or "").strip()
        ref = (kwargs.get("referencia") or kwargs.get("Referencia") or "").strip()
        area_pref = kwargs.get("AreaPreferencial")
        area_mode = kwargs.get("AreaPreferencialModo")

        # Políticas
        val_mode = kwargs.get("ValidadeModo")
        lote_mode = kwargs.get("LoteModo")
        giro_mode = kwargs.get("GiroModo")
        var_consumo = kwargs.get("VariavelConsumo")
        val_min = kwargs.get("ValidadeMinimaDias")
        vida_util = kwargs.get("VidaUtil")
        b_vencido = bool(kwargs.get("BlockVencido"))
        b_semval = bool(kwargs.get("BlockSemValidade"))
        b_semlote = bool(kwargs.get("BlockSemLote"))
        b_qualidade = bool(kwargs.get("BlockRepQualidade"))

        # Status
        ativo = bool(kwargs.get("Ativo", True))
        bloqueado = bool(kwargs.get("Bloqueado"))
        motivo = (kwargs.get("MotivoBloqueio") or "").strip()
        obs = (kwargs.get("ObsBloqueio") or "").strip()

        # 3. Comparação de Camadas (Lista vs Lista)
        new_camadas = kwargs.get("Camadas", [])
        current_camadas = current.get('Camadas', [])

        # Normaliza para garantir que a comparação ignore diferenças sutis de tipos (float vs string)
        def normalize_layers(layers):
            norm = []
            for l in layers:
                # Cria uma assinatura única da camada baseada em seus valores cruciais
                signature = (
                    str(l.get('Unidade', '')).strip().upper(),
                    float(l.get('FatorConversao', 1) or 1),
                    str(l.get('Tipo', 'CAIXA')).strip().upper(),
                    str(l.get('Ean', '')).strip(),
                    bool(l.get('EhPadrao')),
                    float(l.get('Largura') or 0),
                    float(l.get('Altura') or 0),
                    float(l.get('Comprimento') or 0),
                    float(l.get('PesoBruto') or 0)
                )
                norm.append(signature)
            # Ordena pela unidade para que a ordem da lista não gere falso positivo
            return sorted(norm, key=lambda x: x[0])

        camadas_mudaram = normalize_layers(new_camadas) != normalize_layers(current_camadas)

        def mudou(db, new):
            if isinstance(new, bool): return bool(db) != new
            v1 = str(db) if db is not None else ""
            v2 = str(new) if new is not None else ""
            return v1.strip() != v2.strip()

        changed = (
                mudou(current['Sku'], new_sku) or
                mudou(current['Descricao'], desc) or
                mudou(current['Ean'], ean) or
                mudou(current['CodFornecedor'], cod_forn) or
                mudou(current['Familia'], fam) or
                mudou(current['Unidade'], und) or
                mudou(current['Referencia'], ref) or
                mudou(current['ValidadeModo'], val_mode) or
                mudou(current['LoteModo'], lote_mode) or
                mudou(current['GiroModo'], giro_mode) or
                mudou(current['VariavelConsumo'], var_consumo) or
                mudou(current.get('Ativo', True), ativo) or
                mudou(current['Bloqueado'], bloqueado) or
                mudou(current['MotivoBloqueio'], motivo) or
                mudou(current['ObsBloqueio'], obs) or
                mudou(current.get('AreaPreferencial', 'Herdar'), area_pref) or
                mudou(current.get('AreaPreferencialModo', 'Herdar'), area_mode) or
                mudou(current['ValidadeMinimaDias'], val_min) or
                mudou(current['ValidadeMinimaDias'], val_min) or
                mudou(current.get('VidaUtil'), vida_util) or
                mudou(current.get('BlockVencido'), b_vencido) or
                mudou(current.get('BlockVencido'), b_vencido) or
                mudou(current.get('BlockSemValidade'), b_semval) or
                mudou(current.get('BlockSemLote'), b_semlote) or
                mudou(current.get('BlockRepQualidade'), b_qualidade) or
                camadas_mudaram
        )

        if not changed: return False

        cmds = []
        agora = datetime.now()

        query_prod = """
                                            UPDATE Produtos SET 
                                                Sku=?, Descricao=?, Ean=?, CodFornecedor=?, 
                                                Familia=?, FamiliaId=(SELECT Id FROM Familias WHERE Nome=?),
                                                Unidade=?, UnidadeId=(SELECT Id FROM Unidades WHERE Sigla=?),
                                                Referencia=?, 
                                                ValidadeModo=?, LoteModo=?, GiroModo=?, VariavelConsumo=?, ValidadeMinimaDias=?,
                                                VidaUtil=?, 
                                                BlockVencido=?, BlockSemValidade=?, BlockSemLote=?, BlockRepQualidade=?,
                                                Ativo=?, Bloqueado=?, MotivoBloqueio=?, ObsBloqueio=?, 
                                                AreaPreferencial=?, AreaPreferencialModo=?,
                                                Alteracao=?, RowVersion=RowVersion+1, AtualizadoPor=?
                                            WHERE Id=?
                                        """
        params_prod = (
            new_sku, desc, ean, cod_forn,
            fam, fam,
            und, und,
            ref,
            val_mode, lote_mode, giro_mode, var_consumo, val_min,
            vida_util,
            b_vencido, b_semval, b_semlote, b_qualidade,
            ativo, bloqueado, motivo, obs,
            area_pref, area_mode,
            agora, usuario, prod_id
        )
        cmds.append((query_prod, params_prod))

        # B. Update Embalagens
        if camadas_mudaram:
            cmds.append(("DELETE FROM ProdutoEmbalagens WHERE ProdutoId=?", (prod_id,)))

            for c in new_camadas:
                raw_ean = str(c.get('Ean', '')).strip()
                c_ean = raw_ean if raw_ean else None
                c_und = str(c.get('Unidade', 'CX')).strip()
                c_tipo = str(c.get('Tipo', 'CAIXA')).strip()

                # CORREÇÃO 3: Uso do _safe_float aqui também
                c_fator = self._safe_float(c.get('FatorConversao', 1)) or 1.0
                larg = self._safe_float(c.get('Largura'))
                alt = self._safe_float(c.get('Altura'))
                comp = self._safe_float(c.get('Comprimento'))
                peso = self._safe_float(c.get('PesoBruto'))

                larg_un = c.get('LarguraUn', 'mm')
                alt_un = c.get('AlturaUn', 'mm')
                comp_un = c.get('ComprimentoUn', 'mm')
                padrao = 1 if c.get('EhPadrao') else 0

                criado_por = c.get('CriadoPor') or usuario
                data_cadastro = c.get('Cadastro') or agora
                if isinstance(data_cadastro, str):
                    try:
                        data_cadastro = datetime.strptime(data_cadastro, "%d/%m/%Y %H:%M")
                    except (ValueError, TypeError):
                        pass

                sql_emb = """
                                            INSERT INTO ProdutoEmbalagens (
                                                ProdutoId, Ean, Unidade, FatorConversao, Tipo,
                                                Largura, LarguraUn, Altura, AlturaUn, Comprimento, ComprimentoUn,
                                                PesoBruto, EhPadrao, CriadoPor, Cadastro, AtualizadoPor, Alteracao
                                            )
                                            VALUES (
                                                ?, ?, ?, ?, ?, ?,
                                                ?, ?, ?, ?, ?, ?,
                                                ?, ?, ?, ?, ?
                                            )
                                        """
                cmds.append((sql_emb, (
                    prod_id, c_ean, c_und, c_fator, c_tipo,
                    larg, larg_un, alt, alt_un, comp, comp_un,
                    peso, padrao, criado_por, data_cadastro, usuario, agora
                )))

        try:
            self.execute_transaction(cmds)
            if self.event_bus:
                sku_final = kwargs.get("new_sku", kwargs.get("Sku", old_sku)).strip()
                self.event_bus.publish("produto_alterado", {"Sku": sku_final})
            return True
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Erro: O SKU '{new_sku}' ou EAN já está em uso.")
            raise ValueError(f"Erro ao atualizar: {e}")

    def delete(self, sku: str):
        sku = str(sku).strip()

        # 1. VERIFICAÇÃO: Estoque Físico (LPNs Ativos)
        query_stock = "SELECT COUNT(*) as Qtd FROM Lpns WHERE Sku = ? AND QtdAtual > 0 AND Status != 'Cancelado'"
        res_stock = self.execute_query(query_stock, (sku,))
        if res_stock and res_stock[0]['Qtd'] > 0:
            raise ValueError(f"Não é possível excluir o produto '{sku}'.\nExiste saldo em estoque (LPNs).")

        # 2. VERIFICAÇÃO: Recebimento em Andamento
        # (Status diferente de Concluído ou Cancelado)
        query_rec = """
            SELECT COUNT(*) as Qtd 
            FROM RecebimentoItens i
            JOIN Recebimento r ON i.PrCode = r.PrCode
            WHERE i.Sku = ? AND r.Status NOT IN ('Concluído', 'Cancelado', 'Recusado')
        """
        res_rec = self.execute_query(query_rec, (sku,))
        if res_rec and res_rec[0]['Qtd'] > 0:
            raise ValueError(f"Não é possível excluir.\nO produto está em um Recebimento aberto.")

        # --- SE CHEGOU AQUI, É SEGURO EXCLUIR ---

        # 3. Limpeza em Cascata (Filhos)
        # Removemos embalagens e alias, pois o produto deixará de existir.

        # A. Remove Embalagens
        self.execute_non_query("DELETE FROM ProdutoEmbalagens WHERE ProdutoId = (SELECT Id FROM Produtos WHERE Sku=?)",
                               (sku,))

        # B. Remove Alias (Vínculos de Fornecedor)
        # Nota: Se quiser ser mais rígido, poderia bloquear se tiver alias, mas geralmente exclui-se junto.
        self.execute_non_query("DELETE FROM ProdutosAlias WHERE SkuInterno = ?", (sku,))

        # C. Remove o Produto
        self.execute_non_query("DELETE FROM Produtos WHERE Sku=?", (sku,))

        return True

    def get_by_sku(self, sku):
        if not sku: return None
        res = self.execute_query("SELECT * FROM Produtos WHERE Sku=?", (str(sku).strip(),))
        if not res: return None

        row = dict(res[0])

        # Busca Embalagens
        sql_emb = """
                    SELECT 
                        Id, Ean, Unidade, FatorConversao, Tipo,
                        Largura, LarguraUn, Altura, AlturaUn,
                        Comprimento, ComprimentoUn, PesoBruto,
                        EhPadrao, CriadoPor, Cadastro,
                        AtualizadoPor, Alteracao
                    FROM ProdutoEmbalagens 
                    WHERE ProdutoId = ?
                """
        embalagens = self.execute_query(sql_emb, (row['Id'],))

        # Tratamento de dados (Limpeza)
        for e in embalagens:
            # FIX 1: Converte 'None' do banco para string vazia ''
            if e['Ean'] is None:
                e['Ean'] = ""

            # FIX 2: Garante boleano (0/1 -> False/True)
            e['EhPadrao'] = bool(e['EhPadrao'])

            # FIX 3: Garante floats (para evitar erro de conversão na tela)
            e['Largura'] = float(e['Largura'] or 0)
            e['Altura'] = float(e['Altura'] or 0)
            e['Comprimento'] = float(e['Comprimento'] or 0)
            e['PesoBruto'] = float(e['PesoBruto'] or 0)

        row["Camadas"] = [dict(e) for e in embalagens]
        return row

    def get_by_ean(self, ean_buscado):
        if not ean_buscado: return None
        # Limpeza do EAN (remove zeros à esquerda e espaços)
        clean = str(ean_buscado).strip().upper().lstrip("0")
        if not clean: return None

        # 1. Tenta encontrar na Tabela Principal (Unidade Padrão)
        # Nota: Se o seu banco salva EANs com zeros à esquerda, remova o .lstrip("0") acima.
        res = self.execute_query("SELECT Sku FROM Produtos WHERE Ean = ?", (clean,))

        if res:
            # Encontrou! Reutiliza a lógica completa de carga do SKU
            return self.get_by_sku(res[0]['Sku'])

        # 2. Se não achou, tenta encontrar nas Embalagens (Caixas/Pallets)
        # Faz um JOIN para pegar o SKU do produto pai
        query_filha = """
            SELECT p.Sku 
            FROM Produtos p
            JOIN ProdutoEmbalagens pe ON p.Id = pe.ProdutoId
            WHERE pe.Ean = ?
        """
        res = self.execute_query(query_filha, (clean,))

        if res:
            return self.get_by_sku(res[0]['Sku'])

        # 3. Não encontrou nada
        return None

    # --- MÉTODOS AVANÇADOS (RESTAURADOS) ---
    def set_validade_modo(self, sku: str, modo: str):
        if modo not in ("Herdar", "Validade opcional", "Validade obrigatória"):
            raise ValueError("Modo inválido.")
        row = self.get_by_sku(sku)
        if not row: raise ValueError("Produto não encontrado.")
        row["ValidadeModo"] = modo
        row["Alteracao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        row["RowVersion"] = int(row.get("RowVersion", 0)) + 1
        query = "UPDATE Produtos SET ValidadeModo=?, Alteracao=?, RowVersion=RowVersion+1 WHERE Sku=?"
        self.execute_non_query(query, (modo, datetime.now(), sku))
        return True

    def tem_movimentacao(self, sku: str) -> bool:
        # Placeholder para lógica futura
        return False

    def atualizar_ean_auto(self, sku, novo_ean, origem_info="Sistema"):
        row = self.get_by_sku(sku)
        if not row: return False, "SKU não encontrado."
        novo_ean_limpo = str(novo_ean).strip().upper()
        if len(novo_ean_limpo) == 14 and novo_ean_limpo[0] in "12345678":
            return False, "GTIN-14 (Caixa) detectado."
        if len(novo_ean_limpo) == 14 and novo_ean_limpo.startswith("0"):
            novo_ean_limpo = novo_ean_limpo.lstrip("0")

        row["Ean"] = novo_ean_limpo
        row["Alteracao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        row["AtualizadoPor"] = f"Auto-Learn ({origem_info})"
        row["RowVersion"] = int(row.get("RowVersion", 0)) + 1
        return True, f"EAN atualizado."

    def identificar_por_codigo(self, codigo_bipado):
        # Limpeza padrão (remove zeros à esquerda, converte para maiúsculo)
        clean_code = str(codigo_bipado).strip().upper().lstrip("0")
        if not clean_code: return None, None

        # --- TENTATIVA 1: É a Unidade Principal? (Busca na tabela Produtos) ---
        query_prod = "SELECT * FROM Produtos WHERE Ean = ?"
        # Nota: Se o seu banco guarda EANs com zeros à esquerda, remova o .lstrip("0") lá em cima.
        # Assumindo que o banco está higienizado (sem zeros à esquerda):
        res_prod = self.execute_query(query_prod, (clean_code,))

        if res_prod:
            row = dict(res_prod[0])
            # Preenchemos as camadas do produto para não quebrar a lógica de UI
            row["Camadas"] = self._get_camadas_helper(row['Id'])

            # Retorna o produto e diz: "Isso é uma UNIDADE (fator 1)"
            return row, {"Unidade": row.get("Unidade", "UN"), "FatorConversao": 1.0, "Tipo": "UNIDADE"}

        # --- TENTATIVA 2: É uma Embalagem/Caixa? (Busca INDEXADA na tabela filha) ---
        # O JOIN traz os dados da embalagem (fator, tipo) E os dados do produto pai (p.*) numa única ida ao banco.
        query_emb = """
            SELECT e.FatorConversao, e.Unidade as UndEmb, e.Tipo as TipoEmb, p.*
            FROM ProdutoEmbalagens e
            JOIN Produtos p ON e.ProdutoId = p.Id
            WHERE e.Ean = ?
        """
        res_emb = self.execute_query(query_emb, (clean_code,))

        if res_emb:
            row = dict(res_emb[0])

            # Preparamos os dados de conversão específicos desta embalagem bipada
            dados_identificacao = {
                "Unidade": row["UndEmb"],  # Ex: CX
                "FatorConversao": float(row["FatorConversao"]),  # Ex: 12.0
                "Tipo": row["TipoEmb"] or "CAIXA"  # Ex: CAIXA
            }

            # O 'row' contém os dados do Produto (p.*), mas precisamos preencher a lista de camadas
            # para o caso da tela precisar exibir "outras caixas deste mesmo produto"
            row["Camadas"] = self._get_camadas_helper(row['Id'])

            return row, dados_identificacao

        # Se não achou em lugar nenhum
        return None, None

    def _get_camadas_helper(self, produto_id):
        # Método auxiliar para evitar repetição de código SQL
        sql = "SELECT Ean, Unidade, FatorConversao, Tipo FROM ProdutoEmbalagens WHERE ProdutoId = ?"
        return [dict(e) for e in self.execute_query(sql, (produto_id,))]

    # --- CONVERSOR UNIVERSAL INTELIGENTE (COM ALIAS) ---
    def _resolver_alias_unidade(self, unidade_raw):
        # Método auxiliar: Verifica se existe um 'apelido' para a unidade na tabela UnidadesAlias.
        # Ex: Se entrar 'ROL' (da NFe) e tiver um alias para 'RL', retorna 'RL'.
        # Se não achar alias, assume que a unidade já está no padrão interno.

        if not unidade_raw: return ""
        u_upper = str(unidade_raw).strip().upper()

        # Consulta a tabela de tradução de unidades (De-Para)
        query = "SELECT UInterna FROM UnidadesAlias WHERE UXml = ?"
        res = self.execute_query(query, (u_upper,))

        if res:
            return str(res[0]['UInterna']).strip().upper()  # Retorna a tradução (ex: RL)

        return u_upper  # Retorna o original se não tiver alias

    def _get_fator_focado(self, produto_id, unidade_buscada):
        # Retorna o fator de conversão, resolvendo automaticamente aliases de NFe.

        # 1. TRADUÇÃO: Primeiro, descobre o nome real da unidade
        u_efetiva = self._resolver_alias_unidade(unidade_buscada)

        # 2. BUSCA: Agora busca usando o nome correto (ex: busca 'RL' e não 'ROL')
        query_emb = "SELECT FatorConversao, Tipo FROM ProdutoEmbalagens WHERE ProdutoId = ? AND Unidade = ?"
        res_emb = self.execute_query(query_emb, (produto_id, u_efetiva))

        if res_emb:
            tipo = str(res_emb[0]['Tipo']).strip().upper()
            if tipo == 'BASE':
                return 1.0
            return float(res_emb[0]['FatorConversao'])

        # Se falhar, o erro mostra a unidade que tentamos buscar (já traduzida, se houve tradução)
        erro_msg = f"Unidade '{unidade_buscada}'"
        if u_efetiva != unidade_buscada:
            erro_msg += f" (traduzida para '{u_efetiva}')"

        raise ValueError(f"{erro_msg} não está cadastrada para este produto.")

    def converter_unidades(self, sku: str, qtd: float, und_origem: str, und_destino: str):
        # Converte quantidades entre unidades, suportando aliases de NFe automaticamente.

        prod = self.get_by_sku(sku)
        if not prod:
            return {"sucesso": False, "erro": "Produto não encontrado"}

        try:
            prod_id = prod['Id']

            # O _get_fator_focado agora já trata 'ROL' -> 'RL' internamente
            fator_origem = self._get_fator_focado(prod_id, und_origem)
            fator_destino = self._get_fator_focado(prod_id, und_destino)

            qtd_em_base = float(qtd) * fator_origem
            qtd_final = qtd_em_base / fator_destino

            return {
                "sucesso": True,
                "sku": sku,
                "qtd_entrada": float(qtd),
                "und_entrada": und_origem,
                "und_saida": und_destino,
                "qtd_convertida": qtd_final,
                "fator_origem": fator_origem,
                "fator_destino": fator_destino,
                "detalhe": f"Conversão: {qtd} {und_origem} -> {qtd_final:.4f} {und_destino}"
            }

        except ValueError as ve:
            return {"sucesso": False, "erro": str(ve)}
        except Exception as e:
            return {"sucesso": False, "erro": f"Erro técnico: {str(e)}"}

    def count_exceptions(self, g_policies, families_repo_instance):
        self._rows = self.execute_query("SELECT * FROM Produtos")
        g_val = g_policies.modo_validade or "Validade opcional"
        g_giro = str(getattr(g_policies, "modelo_giro", "FEFO")).upper()
        g_lote = str(getattr(g_policies, "modo_lote", "Lote opcional"))
        # Globais de bloqueio
        g_blk = {
            "vencimento": bool(getattr(g_policies, "bloquear_vencido", False)),
            "sem_validade": bool(getattr(g_policies, "bloquear_sem_validade_obrigatoria", False)),
            "sem_lote": bool(getattr(g_policies, "bloquear_sem_lote_obrigatorio", False)),
            "rep_qualidade": bool(getattr(g_policies, "bloquear_reprovacao_qualidade", False))
        }

        counts = {"validade": 0, "bloqueio": 0, "giro": 0, "lote": 0}
        fam_cache = {}

        for r in self._rows:
            fam_name = r.get("Familia", "")
            if fam_name not in fam_cache: fam_cache[fam_name] = families_repo_instance.get_by_nome(fam_name)
            f_row = fam_cache[fam_name]

            # Validade
            p_val = r.get("ValidadeModo", "Herdar")
            if p_val != "Herdar":
                parent = f_row.get("ValidadeModo") if (f_row and f_row.get("ValidadeModo") != "Herdar") else g_val
                if p_val != parent: counts["validade"] += 1

            # Giro
            p_giro = r.get("GiroModo")
            if p_giro and str(p_giro) not in ("Herdar", "None", ""):
                parent = str(f_row.get("GiroModo")).upper() if (
                            f_row and f_row.get("GiroModo") not in ("Herdar", "None", "")) else g_giro
                if str(p_giro).upper() != parent: counts["giro"] += 1

            # Bloqueios (Simplificado: Se tem qq config própria, conta como exceção potencial)
            has_own = any(r.get(k) is not None for k in
                          ("BlockVencido", "BlockSemValidade", "BlockSemLote", "BlockRepQualidade"))
            if has_own: counts["bloqueio"] += 1

        return counts

    def get_resolved_report(self, global_policies, families_repo_instance, filter_exceptions_only=True):
        self._rows = self.execute_query("SELECT * FROM Produtos")
        # Globais
        globais = {
            "ValidadeModo": global_policies.modo_validade or "Validade opcional",
            "LoteModo": getattr(global_policies, "modo_lote", "Lote opcional"),
            "GiroModo": getattr(global_policies, "modelo_giro", "FEFO")
        }
        gb = {
            "vencimento": bool(getattr(global_policies, "bloquear_vencido", False)),
            "sem_validade": bool(getattr(global_policies, "bloquear_sem_validade_obrigatoria", False)),
            "sem_lote": bool(getattr(global_policies, "bloquear_sem_lote_obrigatorio", False)),
            "rep_qualidade": bool(getattr(global_policies, "bloquear_reprovacao_qualidade", False))
        }
        fam_map = {f["Nome"]: f for f in families_repo_instance._rows}
        resolved = []

        for r in self._rows:
            f_row = fam_map.get(r.get("Familia"))
            processed = dict(r)
            has_exc = False

            def resolve(key, pfx=""):
                is_p = (r.get(key) is not None and str(r.get(key)) not in ("Herdar", "None"))
                if is_p:
                    val = r.get(key)
                else:
                    f_val = f_row.get(key) if f_row else None
                    if f_val is not None and str(f_val) not in ("Herdar", "None"):
                        val = f_val
                    else:
                        val = globais[key]
                return str(val).replace(pfx, "") + (" (Própria)" if is_p else " (Herdada)"), is_p

            processed["validade"], e1 = resolve("ValidadeModo", "Validade ")
            processed["lote"], e2 = resolve("LoteModo", "Lote ")
            processed["giro"], e3 = resolve("GiroModo")

            # Bool Resolutions
            for k_db, k_gb in [("BlockVencido", "vencimento"), ("BlockSemValidade", "sem_validade"),
                               ("BlockSemLote", "sem_lote"), ("BlockRepQualidade", "rep_qualidade")]:
                is_p = r.get(k_db) is not None
                if is_p:
                    val = r.get(k_db)
                else:
                    val = f_row.get(k_db) if (f_row and f_row.get(k_db) is not None) else gb[k_gb]
                processed[k_gb] = ("Sim" if val else "Não") + (" (Própria)" if is_p else " (Herdada)")
                if is_p: has_exc = True

            if not filter_exceptions_only or has_exc: resolved.append(processed)
        return resolved


class ProductAliasRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("ProdutosAlias")
        self.event_bus = event_bus

    def add_alias(self, cnpj_fornecedor, cod_fornecedor, sku_interno, usuario="Sistema"):
        clean_cnpj = ''.join(filter(str.isdigit, str(cnpj_fornecedor)))

        # 1. Verifica se já existe
        existe = self.get_sku_interno(clean_cnpj, cod_fornecedor)

        if existe:
            # BLOQUEIA A EDIÇÃO (Filosofia de Imutabilidade)
            # O usuário deve excluir explicitamente na interface antes de recriar,
            # evitando vícios de alterar vínculos sem conferência física.
            raise ValueError(
                f"O vínculo para o código '{cod_fornecedor}' já existe. Exclua o registro antigo antes de criar um novo.")

        # 2. INSERE NOVO (Apenas colunas de criação)
        agora = datetime.now()
        query = """
            INSERT INTO ProdutosAlias (Cnpj, CodFornecedor, SkuInterno, Cadastro, CriadoPor) 
            VALUES (?, ?, ?, ?, ?)
        """
        self.execute_non_query(query, (clean_cnpj, cod_fornecedor, sku_interno, agora, usuario))

        if self.event_bus:
            self.event_bus.publish("alias_produto_criado", {
                "Cnpj": clean_cnpj,
                "CodFornecedor": cod_fornecedor
            })

    def get_sku_interno(self, cnpj_fornecedor, cod_fornecedor):
        clean_cnpj = ''.join(filter(str.isdigit, str(cnpj_fornecedor)))
        res = self.execute_query("SELECT SkuInterno FROM ProdutosAlias WHERE Cnpj=? AND CodFornecedor=?",
                                 (clean_cnpj, cod_fornecedor))
        return res[0]['SkuInterno'] if res else None

    # --- NOVO MÉTODO PARA LISTAGEM COMPLETA ---
    def get_all(self):
        # CORREÇÃO: Adicionado 'pa.CriadoPor' na seleção
        query = """
            SELECT pa.Id, pa.Cnpj, pa.CodFornecedor, pa.SkuInterno, pa.Cadastro,
                   pa.CriadoPor, 
                   p.Descricao as DescricaoInterna, p.Unidade
            FROM ProdutosAlias pa
            LEFT JOIN Produtos p ON pa.SkuInterno = p.Sku
            ORDER BY pa.Cadastro DESC
        """
        return self.execute_query(query)

    def delete(self, id_alias, recebimento_repo=None):

        # Se o repositório de recebimento foi injetado, usamos ele para limpar os itens
        if recebimento_repo:
            # 1. Recupera dados do Alias
            dados_alias = self.execute_query("SELECT Cnpj, CodFornecedor FROM ProdutosAlias WHERE Id=?", (id_alias,))

            if dados_alias:
                cnpj_alvo = dados_alias[0]['Cnpj']
                cod_alvo = dados_alias[0]['CodFornecedor']

                # 2. Busca IDs de itens em aberto (usando StatusPR)
                # Usamos f-string para injetar as constantes de status
                sql_itens = f"""
                    SELECT i.Id 
                    FROM RecebimentoItens i
                    JOIN Recebimento r ON i.PrCode = r.PrCode
                    WHERE i.CodOrig = ? 
                      AND REPLACE(REPLACE(REPLACE(r.Cnpj, '.', ''), '/', ''), '-', '') = ?
                      AND r.Status NOT IN ('{StatusPR.CONCLUIDO}', '{StatusPR.CANCELADO}')
                """

                itens_afetados = recebimento_repo.execute_query(sql_itens, (cod_alvo, cnpj_alvo))

                # 3. Chama a função desvincular (que agora reverte a descrição)
                for item in itens_afetados:
                    recebimento_repo.vinculo_service.desvincular(item['Id'])

        # Garante a exclusão do registro de alias (limpeza final)
        self.execute_non_query("DELETE FROM ProdutosAlias WHERE Id=?", (id_alias,))

        return True, 0

class UnitAliasRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("UnidadesAlias")
        self.event_bus = event_bus

    def add_alias(self, u_xml, u_interna):
        u_xml = u_xml.strip().upper()
        # Verifica e Atualiza ou Insere
        check = self.execute_query("SELECT Id FROM UnidadesAlias WHERE UXml=?", (u_xml,))
        if check:
            self.execute_non_query("UPDATE UnidadesAlias SET UInterna=? WHERE UXml=?", (u_interna, u_xml))
        else:
            self.execute_non_query("INSERT INTO UnidadesAlias (UXml, UInterna, Cadastro) VALUES (?, ?, ?)",
                                   (u_xml, u_interna, datetime.now()))
        if self.event_bus:
            self.event_bus.publish("alias_unidade_alterado", {"xml": u_xml})

    def get_internal(self, u_xml_raw):
        if not u_xml_raw: return "UN"
        target = u_xml_raw.strip().upper()
        res = self.execute_query("SELECT UInterna FROM UnidadesAlias WHERE UXml=?", (target,))
        return res[0]['UInterna'] if res else u_xml_raw

    def delete(self, id_alias):
        self.execute_non_query("DELETE FROM UnidadesAlias WHERE Id=?", (id_alias,))
        return True
