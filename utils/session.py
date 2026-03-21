class SessaoAtual:
    _instancia = None

    # Padrao Singleton: Garante que so existe uma sessao na memoria do sistema inteiro
    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super(SessaoAtual, cls).__new__(cls)
            cls._instancia.limpar()
        return cls._instancia

    def limpar(self):
        # Limpa os dados (usado ao iniciar o sistema ou ao fazer Logout)
        self.usuario_id = None
        self.nome = None
        self.permissoes = {}

    def iniciar_login(self, usuario_id, nome, permissoes):
        # Preenche a sessao com os dados vindos do banco de dados
        self.usuario_id = usuario_id
        self.nome = nome
        self.permissoes = permissoes if permissoes else {}

    def esta_logado(self):
        return self.usuario_id is not None

    def tem_permissao(self, modulo, acao_chave=None):
        # 1. Se for o Super Admin (o hash que criamos no SQL), pode tudo
        if self.permissoes.get("admin_total") is True:
            return True

        # 2. Verifica se o usuario tem acesso ao modulo (a "pasta")
        if modulo not in self.permissoes:
            return False

        # Se a verificacao for apenas para o modulo (ex: exibir o botao no menu lateral)
        if acao_chave is None:
            return True

        # 3. Verifica a acao especifica (o checkbox) dentro do modulo
        acoes_permitidas = self.permissoes[modulo].get("acoes", [])
        return acao_chave in acoes_permitidas

# Instanciamos a sessao aqui para que ela funcione como uma variavel global.
# Qualquer arquivo do sistema so precisa importar esta variavel 'sessao'.
sessao = SessaoAtual()