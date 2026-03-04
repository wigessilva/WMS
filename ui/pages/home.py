import tkinter as tk
from tkinter import ttk
from ui.components import Page

class HomePage(Page):
    def __init__(self, parent):
        super().__init__(parent, style="Main.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Bem-vindo! Escolha um menu à esquerda.",
                  font=("Segoe UI", 10)).grid(row=1, column=0, padx=20, sticky="w")