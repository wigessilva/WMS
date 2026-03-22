import tkinter as tk
import json
import os

from ui.components import PillButton, TextField
from database.repositories import usuarios_repo
from utils.session import sessao
from utils.constants import Colors

CONFIG_FILE = "local_settings.json"


class LoginWindow(tk.Toplevel):
    def __init__(self, master, on_success):
        super().__init__(master)
        self.on_success = on_success

        # Oculta a janela imediatamente ao criar, para não piscar no canto
        self.withdraw()

        self.title("WMS - Login")
        self.configure(bg=Colors.BG_APP)
        self.resizable(False, False)

        # Centraliza a janela fazendo a matemática antes de exibi-la
        w = 350
        h = 420
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw // 2) - (w // 2)
        y = (sh // 2) - (h // 2)

        self.geometry(f"{w}x{h}+{x}+{y}")

        # Revela a janela já na posição exata
        self.deiconify()

        # Se fechar a janela de login, mata o sistema inteiro
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ultimo_login = self._carregar_ultimo_login()

        # Container
        frm = tk.Frame(self, bg=Colors.BG_APP, padx=40, pady=40)
        frm.pack(fill="both", expand=True)

        # Cabeçalho
        tk.Label(frm, text="Bem-vindo!", font=("Segoe UI", 20, "bold"), bg=Colors.BG_APP, fg=Colors.PRIMARY).pack(
            pady=(0, 5))
        tk.Label(frm, text="Faça login para continuar", font=("Segoe UI", 10), bg=Colors.BG_APP,
                 fg=Colors.TEXT_HINT).pack(pady=(0, 30))

        # Campo de Login
        tk.Label(frm, text="Usuário", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 2))
        self.ent_login = TextField(frm, placeholder="Seu login", height=36)
        self.ent_login.pack(fill="x", pady=(0, 15))
        if ultimo_login:
            self.ent_login.insert(0, ultimo_login)

        # Campo de Senha
        tk.Label(frm, text="Senha", bg=Colors.BG_APP, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 2))
        self.ent_senha = TextField(frm, placeholder="", height=36)
        self.ent_senha._entry.config(show="●")
        self.ent_senha.pack(fill="x", pady=(0, 25))

        # Direciona o foco do teclado
        if ultimo_login:
            self.ent_senha.focus_set()
        else:
            self.ent_login.focus_set()

        # Botão Entrar
        self.btn_entrar = PillButton(frm, text="Entrar", variant="primary", command=self._fazer_login)
        self.btn_entrar.pack(fill="x", pady=(10, 0))

        # Permite logar apertando a tecla ENTER
        self.bind("<Return>", lambda e: self._fazer_login())

        # Label invisível para mostrar erros de senha incorreta
        self.lbl_erro = tk.Label(frm, text="", bg=Colors.BG_APP, fg=Colors.DANGER, font=("Segoe UI", 9))
        self.lbl_erro.pack(pady=(15, 0))

    def _carregar_ultimo_login(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("ultimo_login", "")
            except:
                pass
        return ""

    def _salvar_ultimo_login(self, login):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"ultimo_login": login}, f)
        except:
            pass

    def _fazer_login(self):
        login = self.ent_login.get().strip()
        senha = self.ent_senha.get().strip()

        if not login or not senha:
            self.lbl_erro.config(text="Preencha usuário e senha.", fg=Colors.DANGER)
            return

        self.lbl_erro.config(text="Autenticando...", fg=Colors.TEXT_HINT)
        self.update()

        try:
            # A tentativa de login agora está protegida
            usuario = usuarios_repo.autenticar(login, senha)

            if usuario:
                self._salvar_ultimo_login(login)
                sessao.iniciar_login(usuario["id"], usuario["nome"], usuario["permissoes"])
                self.on_success()
                self.destroy()
            else:
                self.lbl_erro.config(text="Usuário ou senha incorretos.", fg=Colors.DANGER)
                self.ent_senha.delete(0, 'end')
                self.ent_senha.focus_set()

        except Exception as e:
            # Se o banco de dados ou o código quebrar, ele te avisa aqui!
            self.lbl_erro.config(text=f"Erro de sistema: {str(e)}", fg=Colors.DANGER)
            print(f"Erro detalhado no login: {str(e)}")  # Também joga no terminal para ajudar

    def _on_close(self):
        self.master.destroy()