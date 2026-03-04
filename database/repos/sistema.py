import os
import sys
import json
from datetime import datetime
from ..base import BaseRepo

# Define PROJECT_ROOT para achar os arquivos JSON
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class PrintersRepo(BaseRepo):
    def __init__(self):
        super().__init__("Impressoras")

    def add(self, **kwargs):
        nome = str(kwargs.get("Nome", "")).strip()
        caminho = str(kwargs.get("Caminho", "")).strip()
        tipo = kwargs.get("Tipo", "windows")
        porta = kwargs.get("Porta", 9100)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Validação
        try:
            porta_int = int(porta)
        except ValueError:
            porta_int = 9100

        query = "INSERT INTO Impressoras (Nome, Caminho, Tipo, Porta, Cadastro, CriadoPor) VALUES (?, ?, ?, ?, ?, 'Admin')"
        self.execute_non_query(query, (nome, caminho, tipo, porta_int, agora))

    def update(self, id_prt, **kwargs):
        # Aqui, como é update, assumimos que os dados vieram.
        # Se quiser ser defensivo, pode usar fallback como no LocationsRepo.
        nome = str(kwargs.get("Nome", "")).strip()
        caminho = str(kwargs.get("Caminho", "")).strip()
        tipo = kwargs.get("Tipo", "windows")
        porta = kwargs.get("Porta", 9100)

        try:
            porta_int = int(porta)
        except ValueError:
            raise ValueError("A porta deve ser um número inteiro.")

        query = "UPDATE Impressoras SET Nome=?, Caminho=?, Tipo=?, Porta=? WHERE Id=?"
        self.execute_non_query(query, (nome, caminho, tipo, porta_int, id_prt))

    def delete(self, id_prt):
        self.execute_non_query("DELETE FROM Impressoras WHERE Id=?", (id_prt,))

    def get_all(self):
        return self.execute_query("SELECT * FROM Impressoras")

class PrinterConfig(BaseRepo):
    def __init__(self, printers_repo: PrintersRepo):
        super().__init__() # CORREÇÃO: Inicializa a base
        self.file_path = os.path.join(PROJECT_ROOT, "dados", "pref_impressoras.json")
        self.printers_repo = printers_repo
        self._cache = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except:
                self._cache = {}

    def get_default(self, context_key):
        return self._cache.get(context_key)

    def set_default(self, context_key, printer_name):
        self._cache[context_key] = printer_name
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar preferência de impressora: {e}")

class GlobalPolicies(BaseRepo):
    def __init__(self, event_bus=None):
        super().__init__() # CORREÇÃO: Isso cria o self.conn_str
        self.data_dir = os.path.join(PROJECT_ROOT, "dados")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.file_path = os.path.join(self.data_dir, "politicas_globais.json")

        # Defaults
        self.modo_validade = "Validade opcional"
        self.modo_lote = "Lote opcional"
        self.bloquear_vencido = False
        self.bloquear_sem_validade_obrigatoria = False
        self.bloquear_sem_lote_obrigatorio = False
        self.bloquear_reprovacao_qualidade = False
        self.modelo_giro = "FEFO"
        self.validade_minima_dias = None
        self.tolerancia_valor_recebimento = 0.00
        self.tolerancia_tipo_recebimento = "Valor"

        self.load()

    def save(self):
        data = {
            "modo_validade": self.modo_validade,
            "modo_lote": self.modo_lote,
            "bloquear_vencido": self.bloquear_vencido,
            "bloquear_sem_validade_obrigatoria": self.bloquear_sem_validade_obrigatoria,
            "bloquear_sem_lote_obrigatorio": self.bloquear_sem_lote_obrigatorio,
            "bloquear_reprovacao_qualidade": self.bloquear_reprovacao_qualidade,
            "modelo_giro": self.modelo_giro,
            "validade_minima_dias": self.validade_minima_dias,
            "tolerancia_valor_recebimento": self.tolerancia_valor_recebimento,
            "tolerancia_tipo_recebimento": self.tolerancia_tipo_recebimento
        }
        json_str = json.dumps(data)
        try:
            self.execute_non_query("UPDATE PoliticasGlobais SET ConfigJson=?, UltimaAtualizacao=? WHERE Id=1",
                                   (json_str, datetime.now()))
        except Exception as e:
            print(f"Erro SQL Policies: {e}")

    def load(self):
        try:
            res = self.execute_query("SELECT ConfigJson FROM PoliticasGlobais WHERE Id=1")
            if not res or not res[0].get('ConfigJson'): return

            data = json.loads(res[0]['ConfigJson'])
            self.modo_validade = data.get("modo_validade", self.modo_validade)
            self.modo_lote = data.get("modo_lote", self.modo_lote)
            self.bloquear_vencido = data.get("bloquear_vencido", self.bloquear_vencido)
            self.bloquear_sem_validade_obrigatoria = data.get("bloquear_sem_validade_obrigatoria",
                                                              self.bloquear_sem_validade_obrigatoria)
            self.bloquear_sem_lote_obrigatorio = data.get("bloquear_sem_lote_obrigatorio",
                                                          self.bloquear_sem_lote_obrigatorio)
            self.bloquear_reprovacao_qualidade = data.get("bloquear_reprovacao_qualidade",
                                                          self.bloquear_reprovacao_qualidade)
            self.modelo_giro = data.get("modelo_giro", self.modelo_giro)
            self.validade_minima_dias = data.get("validade_minima_dias", self.validade_minima_dias)
            self.tolerancia_valor_recebimento = data.get("tolerancia_valor_recebimento",
                                                         self.tolerancia_valor_recebimento)
            self.tolerancia_tipo_recebimento = data.get("tolerancia_tipo_recebimento", "Valor")
        except Exception as e:
            print(f"Erro ao carregar políticas SQL: {e}")