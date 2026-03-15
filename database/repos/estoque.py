import random
from datetime import datetime
from ..base import BaseRepo
from .movimentacao import MovementsRepo
from utils.constants import StatusPR
import string


class LocationsRepo(BaseRepo):
    def __init__(self):
        super().__init__("Locais")

    def add(self, **kwargs):
        # Extração direta (TitleCase)
        nome = str(kwargs.get("Nome", "")).strip()
        if not nome: raise ValueError("Nome obrigatório.")

        tipo = kwargs.get("Tipo")
        cnpj = str(kwargs.get("Cnpj", "")).strip()
        obs = str(kwargs.get("Obs", "")).strip()
        eh_padrao = kwargs.get("EhPadrao", False)
        ativo = kwargs.get("Ativo", True)

        if eh_padrao:
            self.execute_non_query("UPDATE Locais SET EhPadrao=0")

        query = """
            INSERT INTO Locais (Nome, Tipo, Cnpj, Obs, Ativo, EhPadrao, Cadastro, Alteracao, CriadoPor, RowVersion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Admin', 1)
        """
        try:
            self.execute_non_query(query, (
                nome, tipo, cnpj, obs,
                1 if ativo else 0,
                1 if eh_padrao else 0,
                datetime.now(), datetime.now()
            ))
        except Exception as e:
            if "UNIQUE" in str(e): raise ValueError("Já existe um local com este nome.")
            raise e

    def update(self, id_local, **kwargs):
        # Busca dados atuais
        res = self.execute_query("SELECT * FROM Locais WHERE Id=?", (id_local,))
        if not res: raise ValueError("Local não encontrado.")
        curr = res[0]

        # Extrai novos valores (TitleCase) ou mantém os antigos (curr)
        n_nome = str(kwargs.get("Nome", curr["Nome"])).strip()
        n_tipo = kwargs.get("Tipo", curr["Tipo"])
        n_cnpj = str(kwargs.get("Cnpj", curr["Cnpj"] or "")).strip()
        n_obs = str(kwargs.get("Obs", curr["Obs"] or "")).strip()

        # Para booleanos, usamos get explícito pois False é um valor válido
        n_ativo = kwargs.get("Ativo", bool(curr["Ativo"]))
        n_padrao = kwargs.get("EhPadrao", bool(curr["EhPadrao"]))

        # Lógica de detecção de mudanças (mantida como solicitado)
        def mudou(db, new):
            if isinstance(new, bool): return bool(db) != new
            return str(db or "").strip() != str(new or "").strip()

        changed = (
                mudou(curr['Nome'], n_nome) or
                mudou(curr['Tipo'], n_tipo) or
                mudou(curr['Cnpj'], n_cnpj) or
                mudou(curr['Obs'], n_obs) or
                mudou(curr['Ativo'], n_ativo) or
                mudou(curr['EhPadrao'], n_padrao)
        )

        if not changed: return False

        if n_padrao:
            self.execute_non_query("UPDATE Locais SET EhPadrao=0")

        query = """
            UPDATE Locais SET Nome=?, Tipo=?, Cnpj=?, Obs=?, Ativo=?, EhPadrao=?, 
                              Alteracao=?, RowVersion=RowVersion+1
            WHERE Id=?
        """
        try:
            self.execute_non_query(query, (n_nome, n_tipo, n_cnpj, n_obs,
                                           1 if n_ativo else 0, 1 if n_padrao else 0,
                                           datetime.now(), id_local))
            return True
        except Exception as e:
            raise ValueError("Erro ao atualizar ou nome duplicado.")

    def get_padrao(self):
        res = self.execute_query("SELECT Nome FROM Locais WHERE Ativo=1 AND EhPadrao=1")
        return res[0]['Nome'] if res else ""

    def delete(self, id_local):
        self.execute_non_query("DELETE FROM Locais WHERE Id=?", (id_local,))
        return True

    def get_by_nome(self, nome: str):
        res = self.execute_query("SELECT * FROM Locais WHERE Nome=?", (nome.strip(),))
        return res[0] if res else None

    def list(self, page=1, page_size=1000, filters=None):
        return super().list(page, page_size, filters)


class AddressesRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("Enderecos")
        self.event_bus = event_bus

    @staticmethod
    def format_visual(tipo, rua, predio, nivel, grupo=""):
        letras = string.ascii_uppercase
        g_suffix = f"-{grupo}" if grupo else ""

        if tipo in ["Estante", "Picking"]:
            # Converte nível numérico para letra (1=A, 2=B...)
            # max(0, n-1) protege contra nível 0 ou negativo
            letra_nivel = letras[max(0, int(nivel) - 1) % 26]
            return f"{int(rua):02d}-{int(predio):02d}-{letra_nivel}{g_suffix}"

        elif tipo == "Gaiola":
            return f"GAIOLA-{int(rua):02d}"

        else:
            # Padrão Porta-Pallet / Blocado
            return f"{int(rua):02d}-{int(predio):02d}-{int(nivel):02d}{g_suffix}"

    def _parse_visual_to_query(self, visual_str):
        parts = visual_str.split('-')

        # Caso GAIOLA (Ex: GAIOLA-05)
        if parts[0].upper() == "GAIOLA":
            if len(parts) < 2: return None, None
            try:
                rua = int(parts[1])
                return "Tipo='Gaiola' AND Rua=?", (rua,)
            except:
                return None, None

        # Caso Padrão ou Estante (Ex: 01-02-03 ou 01-02-A)
        if len(parts) >= 3:
            try:
                rua = int(parts[0])
                predio = int(parts[1])
                terceira_parte = parts[2]
                grupo = parts[3] if len(parts) > 3 else ""

                # Tenta detectar se é número ou letra
                if terceira_parte.isdigit():
                    nivel = int(terceira_parte)
                    # Busca exata para numéricos
                    sql = "Rua=? AND Predio=? AND Nivel=?"
                    params = [rua, predio, nivel]
                else:
                    # É letra (Estante/Picking). Precisamos converter A -> 1
                    # Ord('A') = 65. Então 65 - 64 = 1.
                    nivel = ord(terceira_parte.upper()) - 64
                    sql = "Rua=? AND Predio=? AND Nivel=?"
                    params = [rua, predio, nivel]

                if grupo:
                    sql += " AND GrupoBloqueio=?"
                    params.append(grupo)
                else:
                    sql += " AND (GrupoBloqueio IS NULL OR GrupoBloqueio='')"

                return sql, tuple(params)

            except:
                pass

        return None, None

    def _check_duplicate(self, area, rua, predio, nivel, grupo, exclude_id=None):
        sql = """SELECT COUNT(*) as Qtd FROM Enderecos 
                 WHERE Area=? AND Rua=? AND Predio=? AND Nivel=? AND GrupoBloqueio=?"""
        params = [area.strip().upper(), rua, predio, nivel, str(grupo).strip().upper()]

        if exclude_id:
            sql += " AND Id != ?"
            params.append(exclude_id)

        res = self.execute_query(sql, tuple(params))
        return res[0]['Qtd'] > 0

    def add(self, **kwargs):
        # 1. Extração Padronizada (TitleCase)
        area = str(kwargs.get("Area", "")).strip().upper()
        rua = int(kwargs.get("Rua", 0))
        predio = int(kwargs.get("Predio", 0))
        nivel = int(kwargs.get("Nivel", 0))
        tipo = kwargs.get("Tipo")
        grupo = str(kwargs.get("GrupoBloqueio", "")).strip().upper()

        # Opcionais / Defaults
        cap_tipo = kwargs.get("CapacidadeTipo", "Qtd")
        cap_val = float(kwargs.get("CapacidadeVal", 1.0))
        comp_util = int(kwargs.get("ComprimentoUtil", 0))
        uso = kwargs.get("Uso", "Pulmão")
        sku_fixo = kwargs.get("SkuFixo", "")
        cap_picking = float(kwargs.get("CapacidadePicking", 0))
        und_picking = kwargs.get("UnidadePicking", "")
        carga_max = float(kwargs.get("CargaMaxKg", 0))

        if self._check_duplicate(area, rua, predio, nivel, grupo):
            raise ValueError("Endereço já existe.")

        query = """
                INSERT INTO Enderecos (
                    Area, Rua, Predio, Nivel, Tipo, GrupoBloqueio,
                    CapacidadeTipo, CapacidadeVal, ComprimentoUtil, 
                    Ativo, Uso, SkuFixo, CapacidadePicking, UnidadePicking, CargaMaxKg,
                    Cadastro, CriadoPor, RowVersion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'Admin', 1)
            """
        self.execute_non_query(query, (
            area, rua, predio, nivel, tipo, grupo,
            cap_tipo, cap_val, comp_util,
            uso, sku_fixo, cap_picking, und_picking, carga_max, datetime.now()
        ))

    def update(self, uid, **kwargs):
        # 1. Extração Padronizada
        area = str(kwargs.get("Area", "")).strip().upper()
        rua = int(kwargs.get("Rua", 0))
        predio = int(kwargs.get("Predio", 0))
        nivel = int(kwargs.get("Nivel", 0))
        grupo = str(kwargs.get("GrupoBloqueio", "")).strip().upper()

        tipo = kwargs.get("Tipo")
        cap_tipo = kwargs.get("CapacidadeTipo")
        cap_val = kwargs.get("CapacidadeVal")
        comp_util = kwargs.get("ComprimentoUtil")
        ativo = kwargs.get("Ativo")
        uso = kwargs.get("Uso")
        sku_fixo = kwargs.get("SkuFixo")
        cap_picking = kwargs.get("CapacidadePicking")
        und_picking = kwargs.get("UnidadePicking")
        carga_max = kwargs.get("CargaMaxKg")

        if self._check_duplicate(area, rua, predio, nivel, grupo, exclude_id=uid):
            raise ValueError("Endereço duplicado.")

        query = """
                UPDATE Enderecos SET 
                    Area=?, Rua=?, Predio=?, Nivel=?, Tipo=?, GrupoBloqueio=?,
                    CapacidadeTipo=?, CapacidadeVal=?, ComprimentoUtil=?, 
                    Ativo=?, Uso=?, SkuFixo=?, CapacidadePicking=?, UnidadePicking=?, CargaMaxKg=?, 
                    Alteracao=?, RowVersion=RowVersion+1
                WHERE Id=?
            """
        self.execute_non_query(query, (
            area, rua, predio, nivel, tipo, grupo,
            cap_tipo, cap_val, comp_util,
            1 if ativo else 0, uso, sku_fixo, cap_picking, und_picking, carga_max,
            datetime.now(), uid
        ))

    def delete(self, uid):
        # 1. Busca dados do endereço
        row_res = self.execute_query("SELECT * FROM Enderecos WHERE Id=?", (uid,))
        if not row_res: return
        row = row_res[0]

        # --- USO DO HELPER (Item 2) ---
        visual = self.format_visual(
            row.get("Tipo"), row.get("Rua"), row.get("Predio"),
            row.get("Nivel"), row.get("GrupoBloqueio", "")
        )

        # 2. Valida saldo via SQL Direto
        tem_saldo = self.execute_query("SELECT COUNT(*) as Qtd FROM Lpns WHERE Endereco=? AND QtdAtual > 0", (visual,))

        if tem_saldo[0]['Qtd'] > 0:
            raise ValueError(f"O endereço {visual} possui saldo.")

        self.execute_non_query("DELETE FROM Enderecos WHERE Id=?", (uid,))

    def gerar_lote(self, config):
        count, erros = 0, 0
        for r in range(int(config['rua_ini']), int(config['rua_fim']) + 1):
            for p in range(int(config['pred_ini']), int(config['pred_fim']) + 1):
                for n in range(int(config['niv_ini']), int(config['niv_fim']) + 1):
                    try:
                        self.add(area=config['area'], rua=r, predio=p, nivel=n, tipo=config['tipo'],
                                 cap_tipo=config['cap_tipo'], cap_val=config['cap_val'], grupo=config['grupo'],
                                 comp_util=config['comp_util'])
                        count += 1
                    except ValueError:
                        erros += 1
        return count, erros

    def get_skus_with_fixed_address(self):
        # Traz apenas endereços ativos com SKU Fixo
        query = "SELECT SkuFixo, Tipo, Rua, Predio, Nivel, GrupoBloqueio FROM Enderecos WHERE SkuFixo IS NOT NULL AND SkuFixo != '' AND Ativo = 1 ORDER BY Rua, Predio, Nivel, GrupoBloqueio"
        rows = self.execute_query(query)
        result = {}

        for r in rows:
            sku = r['SkuFixo']
            visual = self.format_visual(r['Tipo'], r['Rua'], r['Predio'], r['Nivel'], r.get('GrupoBloqueio'))

            if sku in result:
                result[sku] += f", {visual}"
            else:
                result[sku] = visual
        return result

    def check_capacity_availability(self, endereco_visual):
        """
        Verifica se cabe mais caixa no endereço.
        OTIMIZADO: Usa busca direta no banco em vez de scan linear em memória.
        """
        # 1. Parsing Inteligente (Item 1)
        where_clause, params = self._parse_visual_to_query(endereco_visual)

        target_row = None

        if where_clause:
            # Busca Otimizada: Vai direto no registro certo
            query = f"SELECT TOP 1 * FROM Enderecos WHERE {where_clause} AND Ativo=1"
            res = self.execute_query(query, params)
            if res:
                target_row = res[0]
        else:
            # Fallback: Se o parser falhar (ex: formato estranho), faz o scan antigo (lento), mas seguro.
            # Isso garante que não quebra endereços legados.
            print(f"Aviso: Scan linear acionado para {endereco_visual}")
            all_addrs = self.execute_query("SELECT * FROM Enderecos WHERE Ativo=1")
            for r in all_addrs:
                vis = self.format_visual(r.get("Tipo"), r["Rua"], r["Predio"], r["Nivel"], r.get("GrupoBloqueio"))
                if vis == endereco_visual:
                    target_row = r
                    break

        if not target_row:
            return False, "Endereço não cadastrado."

        cap_max = float(target_row.get("CapacidadeVal", 1.0))

        # 2. Contagem de Ocupação (Via SQL Direto na tabela Lpns)
        qtd_res = self.execute_query(
            "SELECT COUNT(DISTINCT Lpn) as Q FROM Lpns WHERE Endereco=? AND QtdAtual > 0",
            (endereco_visual,)
        )
        qtd_atual = qtd_res[0]['Q']

        if qtd_atual >= cap_max:
            return False, f"Endereço Cheio ({qtd_atual}/{int(cap_max)} Caixas)."

        return True, ""


class LpnRepo(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__("Lpns")
        self.event_bus = event_bus

        if self.event_bus:
            # O Estoque também ouve quando o Recebimento termina!
            self.event_bus.subscribe("recebimento_concluido", lambda data: self.liberar_lpns_do_recebimento(data['pr']))

    def generate_id(self):
        while True:
            raw_digits = [int(d) for d in random.choices("0123456789", k=7)]
            total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(raw_digits)))
            check_digit = (10 - (total % 10)) if (total % 10) != 0 else 0
            new_id = f"{''.join(map(str, raw_digits))}-{check_digit}"

            # Verifica se já existe algum registro com esse LPN
            res = self.execute_query("SELECT COUNT(*) as Q FROM Lpns WHERE Lpn=?", (new_id,))
            if res[0]['Q'] == 0: return new_id

    def create_blank_lpn(self):
        new_id = self.generate_id()
        query = """
                INSERT INTO Lpns (Lpn, Origem, Sku, Descricao, Emb, Lote, Validade, Endereco, 
                                  QtdOriginal, QtdAtual, Status, Cadastro, CriadoPor, RowVersion)
                VALUES (?, 'SISTEMA', '', '', '', '', NULL, '', 0, 0, 'Gerada', ?, 'Admin', 1)
            """
        self.execute_non_query(query, (new_id, datetime.now()))
        return new_id

    def add_item_to_lpn(self, lpn_code, sku, qtd, unidade, descricao="", lote="", validade=None):
        res = self.execute_query("SELECT TOP 1 Endereco, Status FROM Lpns WHERE Lpn=?", (lpn_code,))
        if not res: raise ValueError("LPN não encontrado.")
        endereco_atual = res[0]['Endereco']
        status_atual = res[0]['Status']

        query = """INSERT INTO Lpns (Lpn, Sku, Descricao, QtdOriginal, QtdAtual, Lote, Validade, Endereco, Status, Cadastro, CriadoPor, RowVersion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Admin', 1)"""
        self.execute_non_query(query, (
        lpn_code, sku, descricao, qtd, qtd, lote, validade, endereco_atual, status_atual, datetime.now()))

        if self.event_bus:
            self.event_bus.publish("lpn_updated", {"lpn": lpn_code, "endereco": endereco_atual})

    def atualizar_ou_criar_lpn_transacao(self, lpn_code, item_data, qtd, dados_conf, cmds, usuario, data_hora):
        # Verifica existência (Leitura síncrona para decidir INSERT ou UPDATE)
        res = self.execute_query("SELECT COUNT(*) as Q FROM Lpns WHERE Lpn=?", (lpn_code,))
        existe = res[0]['Q'] > 0

        sku = item_data.get("Sku")
        desc = item_data.get("Descricao")
        pr_ref = item_data.get("PrCode") or item_data.get("pr")

        # Resgate seguro de Lote
        lote = dados_conf.get("lote")
        if lote is None: lote = dados_conf.get("Lote")
        if lote is None: lote = item_data.get("Lote")
        if lote is None: lote = ""

        # Resgate seguro de Validade
        validade = dados_conf.get("validade")
        if validade is None: validade = dados_conf.get("Validade")
        if validade is None: validade = item_data.get("Val")
        if validade is None: validade = item_data.get("Validade")

        # Formata para o banco evitar registrar "nulo" por falta de formatação
        if validade == "__/__/____" or validade == "" or validade == "-":
            validade = None
        elif validade and len(validade) == 10 and validade[2] == '/':
            try:
                validade = datetime.strptime(validade, "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                pass

        if existe:
            # UPDATE: Reaproveita o LPN existente
            sql = """
                        UPDATE Lpns 
                        SET Sku=?, Descricao=?, QtdAtual=?, QtdOriginal=?, 
                            Lote=?, Validade=?, PrRef=?, Origem=?, 
                            Status='Aguardando Armazenamento', 
                            Endereco='RECEBIMENTO', Obs=NULL,
                            AtualizadoPor=?, Alteracao=?, RowVersion=RowVersion+1
                        WHERE Lpn=?
                    """
            params = (sku, desc, float(qtd), float(qtd), lote, validade, pr_ref, pr_ref, usuario, data_hora, lpn_code)
            cmds.append((sql, params))
        else:
            # INSERT: Cria novo LPN
            sql = """
                INSERT INTO Lpns (Lpn, Sku, Descricao, QtdOriginal, QtdAtual, Status, 
                                  Lote, Validade, Endereco, PrRef, Origem, CriadoPor, Cadastro, RowVersion)
                VALUES (?, ?, ?, ?, ?, 'Aguardando Armazenamento', 
                        ?, ?, 'RECEBIMENTO', ?, ?, ?, ?, 1)
            """
            # Nota: Usamos pr_ref no campo 'Origem' para rastrear de qual Recebimento veio
            params = (lpn_code, sku, desc, float(qtd), float(qtd), lote, validade, pr_ref, pr_ref, usuario, data_hora)
            cmds.append((sql, params))

    def move_lpn(self, lpn_code, novo_endereco, usuario="Sistema"):
        # Move TODOS os itens da caixa para o novo endereço e gera histórico"""

        # 1. Descobre onde ele estava antes (para o histórico)
        res = self.execute_query("SELECT TOP 1 Endereco FROM Lpns WHERE Lpn=?", (lpn_code,))
        if not res: raise ValueError("LPN não existe.")
        end_antigo = res[0]['Endereco']

        if end_antigo == novo_endereco:
            return  # Não faz nada se for o mesmo lugar

        # 2. Atualiza a posição física
        query = """
            UPDATE Lpns 
            SET Endereco = ?, 
                EnderecoAnterior = Endereco,
                Alteracao = ?,
                AtualizadoPor = ?
            WHERE Lpn = ? AND Status NOT IN ('Expedido', 'Cancelado')
        """
        self.execute_non_query(query, (novo_endereco, datetime.now(), usuario, lpn_code))

        # 3. GRAVA NO HISTÓRICO (A novidade!)
        # Instancia o repo de movimentos rapidinho só para registrar
        mov_repo = MovementsRepo()

        # Atualizado para usar Chaves TitleCase
        mov_repo.registrar(
            Usuario=usuario,
            TipoOperacao="Movimentacao",
            Lpn=lpn_code,
            Sku="",
            QtdMovimentada=0,
            Origem=end_antigo,
            Destino=novo_endereco,
            Obs="Movimentação de LPN via Sistema"
        )

        if self.event_bus:
            self.event_bus.publish("lpn_moved", {"lpn": lpn_code, "de": end_antigo, "para": novo_endereco})

    def get_content(self, lpn_code):
        # Retorna tudo o que tem dentro da caixa
        query = """
            SELECT Id, Sku, Descricao, QtdAtual, Lote, Endereco 
            FROM Lpns 
            WHERE Lpn = ? AND QtdAtual > 0
        """
        return self.execute_query(query, (lpn_code,))

    def delete(self, lpn_code, motivo="Cancelamento Manual"):
        row_res = self.execute_query("SELECT TOP 1 * FROM Lpns WHERE Lpn=?", (lpn_code,))
        if not row_res: raise ValueError("LPN não encontrado.")

        query = "UPDATE Lpns SET QtdAnterior=QtdAtual, EnderecoAnterior=Endereco, QtdAtual=0, Endereco='CANCELADOS', Status=?, Obs=?, Alteracao=?, AtualizadoPor='Admin' WHERE Lpn=?"

        self.execute_non_query(query, (StatusPR.CANCELADO, motivo, datetime.now(), lpn_code))

        if self.event_bus:
            self.event_bus.publish("lpn_deleted", {"lpn": lpn_code, "endereco_anterior": row_res[0].get("Endereco")})

        return True

    def excluir_lpns_do_recebimento(self, pr_code, motivo="Cancelamento do Recebimento"):
        query_busca = "SELECT Lpn FROM Lpns WHERE PrRef = ? AND Status != ?"

        lpns = self.execute_query(query_busca, (pr_code, StatusPR.CANCELADO))

        count = 0
        for row in lpns:
            try:
                self.delete(row['Lpn'], motivo=motivo)
                count += 1
            except Exception as e:
                print(f"Erro ao excluir LPN {row['Lpn']} do PR {pr_code}: {e}")

        return count

    def validar_lpn_virgem(self, lpn_codigo):
        # Valida se é um LPN recém criado (sem itens ou com status Gerada)
        res = self.execute_query("SELECT Status FROM Lpns WHERE Lpn=?", (str(lpn_codigo).strip(),))
        if not res: return False, "LPN não encontrado."
        # Pega o status da primeira linha (assume que todas tem o mesmo status)
        if res[0]['Status'] != "Gerada": return False, f"Status inválido: {res[0]['Status']}."
        return True, ""

    def desmembrar_lpn(self, lpn_origem, qtd_separar, novo_lote=None, nova_fabricacao=None, nova_validade=None,
                       usuario="Sistema"):

        from .sistema import GlobalPolicies

        # 1. Busca dados do LPN Original
        query_busca = "SELECT * FROM Lpns WHERE Lpn = ? AND QtdAtual > 0"
        dados = self.execute_query(query_busca, (lpn_origem,))

        if not dados:
            return False, "LPN de origem não encontrado ou vazio."

        orig = dados[0]
        # Não lemos mais qtd_atual_orig para conta de subtração (atomicidade),
        # apenas para validar se tem saldo suficiente antes de tentar.
        saldo_estimado = float(orig['QtdAtual'])

        # 2. Validações Prévias
        if qtd_separar <= 0:
            return False, "A quantidade deve ser maior que zero."

        if qtd_separar >= saldo_estimado:
            return False, "Para mover todo o saldo, use a função de Movimentação."

        # 3. Definição de Dados do Novo LPN
        novo_lpn_code = self.generate_id()

        # Se não informou, herda do pai. Se informou, usa o novo.
        lote_final = novo_lote.strip() if novo_lote else orig['Lote']
        fab_final = nova_fabricacao if nova_fabricacao else orig.get(
            'Fabricacao')  # Assumindo que coluna existe ou é None
        val_final = nova_validade if nova_validade else orig['Validade']

        # --- LÓGICA DE BLOQUEIO NO NASCIMENTO ---
        gp = GlobalPolicies()
        status_novo = orig['Status']  # Herda por padrão (ex: Armazenado)

        # Se tiver validade e política de bloqueio ativa
        if val_final and gp.bloquear_vencido:
            # Converte string ISO (AAAA-MM-DD) para data se necessário
            dt_val = val_final
            if isinstance(val_final, str):
                try:
                    dt_val = datetime.strptime(val_final, "%Y-%m-%d")
                except:
                    pass  # Se falhar conversão, ignora validação por hora

            # Se venceu ontem ou antes
            if isinstance(dt_val, datetime) and dt_val.date() < datetime.now().date():
                status_novo = 'Bloqueado'
        # ----------------------------------------

        mov_repo = MovementsRepo()

        try:
            # A. Cria o Novo LPN (INSERT)
            # Adicionei o campo Fabricacao (se existir no banco)
            query_insert = """
                INSERT INTO Lpns (Lpn, Sku, Descricao, QtdOriginal, QtdAtual, Lote, Fabricacao, Validade, 
                                  Endereco, PrRef, Status, CriadoPor, Cadastro, Origem, RowVersion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """
            agora = datetime.now()
            origem_novo = f"SPLIT-{lpn_origem}"

            self.execute_non_query(query_insert, (
                novo_lpn_code, orig['Sku'], orig['Descricao'], qtd_separar, qtd_separar,
                lote_final, fab_final, val_final, orig['Endereco'], orig['PrRef'],
                status_novo, usuario, agora, origem_novo
            ))

            # B. Subtrai do LPN Original (UPDATE ATÔMICO)
            # A cláusula "AND QtdAtual >= ?" garante que não negative se alguém mexeu no mesmo milissegundo
            query_update = "UPDATE Lpns SET QtdAtual = QtdAtual - ? WHERE Id = ? AND QtdAtual >= ?"
            rows_affected = self.execute_non_query_count(query_update, (qtd_separar, orig['Id'], qtd_separar))

            if rows_affected == 0:
                # Se não atualizou nada, é porque o saldo mudou no meio do caminho (Concorrência)
                # Precisamos desfazer o INSERT (Rollback manual simplificado)
                self.execute_non_query("DELETE FROM Lpns WHERE Lpn = ?", (novo_lpn_code,))
                return False, "Erro de concorrência: O saldo do LPN mudou durante a operação. Tente novamente."

            # C. Registra Movimentações (Kardex) - ATUALIZADO PARA TITLECASE
            mov_repo.registrar(
                Usuario=usuario,
                TipoOperacao="Desmembramento-Saida",
                Lpn=lpn_origem,
                Sku=orig['Sku'],
                QtdMovimentada=-qtd_separar,
                Origem=orig['Endereco'],
                Destino="NOVO-LPN",
                Obs=f"Separado para {novo_lpn_code}"
            )

            mov_repo.registrar(
                Usuario=usuario,
                TipoOperacao="Desmembramento-Entrada",
                Lpn=novo_lpn_code,
                Sku=orig['Sku'],
                QtdMovimentada=qtd_separar,
                Origem=f"LPN-{lpn_origem}",
                Destino=orig['Endereco'],
                Obs="Criado via Desmembramento"
            )

            if self.event_bus:
                self.event_bus.publish("lpn_created", {"lpn": novo_lpn_code, "endereco": orig['Endereco']})

            return True, novo_lpn_code

        except Exception as e:
            print(f"Erro ao desmembrar: {e}")
            return False, str(e)

    def liberar_lpns_do_recebimento(self, pr_code):
        # NOVO: Sincroniza as informações consolidadas da conferência (Lote, Validade, Fabricação)
        # do Item para o LPN. Isso garante que, em recebimentos parciais ou divergentes,
        # o LPN receba a informação correta antes de ir para o estoque.
        query_sync = """
            UPDATE L
            SET L.Lote = I.Lote,
                L.Validade = I.Val,
                L.Fabricacao = I.Fab,
                L.Descricao = I.Descricao,
                L.Sku = I.Sku
            FROM Lpns L
            JOIN RecebimentoItens I ON L.PrRef = I.PrCode AND L.Sku = I.Sku
            WHERE L.PrRef = ? AND L.Status = 'Aguardando Armazenamento'
        """
        try:
            self.execute_non_query(query_sync, (pr_code,))
        except Exception as e:
            print(f"Erro ao sincronizar dados do LPN para o PR {pr_code}: {e}")


class AreasRepo(BaseRepo):
    def __init__(self):
        super().__init__("Areas")

    def add(self, **kwargs):
        nome = str(kwargs.get("Nome", "")).strip().upper()
        descricao = str(kwargs.get("Descricao", "")).strip()

        try:
            query = "INSERT INTO Areas (Nome, Descricao, Ativo, Cadastro, CriadoPor, RowVersion) VALUES (?, ?, 1, ?, 'Admin', 1)"
            self.execute_non_query(query, (nome, descricao, datetime.now()))
        except Exception as e:
            if "UNIQUE" in str(e): raise ValueError("Esta Área já existe.")
            raise e

    def update(self, id_area, **kwargs):
        nome = str(kwargs.get("Nome", "")).strip().upper()
        descricao = str(kwargs.get("Descricao", "")).strip()
        ativo = kwargs.get("Ativo", True)

        query = "UPDATE Areas SET Nome=?, Descricao=?, Ativo=?, Alteracao=?, AtualizadoPor='Admin', RowVersion=RowVersion+1 WHERE Id=?"
        try:
            self.execute_non_query(query, (nome, descricao, 1 if ativo else 0, datetime.now(), id_area))
        except Exception:
            raise ValueError("Erro ao atualizar Área.")

    def delete(self, id_area):
        # Verifica se tem endereço usando antes de apagar
        res = self.execute_query("SELECT TOP 1 Id FROM Enderecos WHERE Area = (SELECT Nome FROM Areas WHERE Id=?)", (id_area,))
        if res: raise ValueError("Não é possível excluir: Existem endereços vinculados a esta Área.")
        self.execute_non_query("DELETE FROM Areas WHERE Id=?", (id_area,))