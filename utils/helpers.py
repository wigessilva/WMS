import os
import sys
import logging
import traceback
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import tkinter as tk
from tkinter import ttk

from .constants import Colors

base_log_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
log_file = os.path.join(base_log_path, "sistema_erros.log")

logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)


def log_exception(e, context="Erro Geral"):
    # 1. Captura a mensagem de erro original
    raw_msg = f"[{context}] {str(e)}\n{traceback.format_exc()}"

    # 2. CENSOR AUTOMÁTICO: Procura por senhas na connection string
    # Vai procurar 'PWD=' ou 'UID=' seguido de qualquer coisa que nao seja um ponto e virgula
    # e substitui por 'PWD=***'
    safe_msg = re.sub(r'(PWD|UID|PASSWORD|USER)=[^;]+', r'\1=***', raw_msg, flags=re.IGNORECASE)

    # 3. Guarda a mensagem censurada e segura
    logging.error(safe_msg)
    print(safe_msg)

import datetime

class AuditManager:

    # Classe global para gerenciar colunas de auditoria em todo o sistema.
    # Centraliza a definição visual e o processamento de dados.

    @staticmethod
    def get_columns():
        # Retorna a definição das colunas para o StandardTable.
        return [
            {"id": "CriadoPor", "title": "Criado Por", "width": 100, "anchor": "center", "hidden": True},
            {"id": "Cadastro", "title": "Data Criação", "width": 130, "anchor": "center", "hidden": True},
            {"id": "AtualizadoPor", "title": "Atualizado Por", "width": 100, "anchor": "center", "hidden": True},
            {"id": "Alteracao", "title": "Última Alteração", "width": 130, "anchor": "center", "hidden": True},
            {"id": "Id", "title": "ID", "width": 50, "anchor": "center", "hidden": True},
            {"id": "RowVersion", "title": "RowVersion", "width": 80, "anchor": "center", "hidden": True},
        ]

    @staticmethod
    def process_row(row_raw: dict) -> dict:

        # Recebe a linha crua do Banco de Dados (dict) e retorna um dicionário
        # apenas com os campos de auditoria formatados e padronizados.

        audit_data = {}

        # Normaliza as chaves para minúsculo para evitar problemas de Case Sensitive (SQL Server)
        # Ex: Transforma 'CriadoPor' em 'criadopor' para facilitar a busca
        row_lower = {k.lower(): v for k, v in row_raw.items()}

        # --- 1. Mapeamento de Usuários ---
        audit_data["criado_por"] = row_lower.get("CriadoPor") or "-"
        audit_data["atualizado_por"] = row_lower.get("AtualizadoPor") or "-"
        audit_data["id"] = row_lower.get("Id") or ""
        audit_data["rowversion"] = row_lower.get("RowVersion") or ""

        # --- 2. Formatação de Datas ---
        def fmt_date(val):
            if not val:
                return "-"
            if isinstance(val, str):
                return val  # Já é string
            if isinstance(val, (datetime.date, datetime.datetime)):
                return val.strftime("%d/%m/%Y %H:%M")
            return str(val)

        audit_data["cadastro"] = fmt_date(row_lower.get("Cadastro"))
        audit_data["alteracao"] = fmt_date(row_lower.get("Alteracao"))

        return audit_data


class Utils:
    @staticmethod
    def safe_float(value_str):
        if not value_str: return 0.0
        try:
            return float(str(value_str).replace(",", ".").strip())
        except ValueError:
            return 0.0

    @staticmethod
    def safe_float_or_none(value_str):
        if not value_str or not str(value_str).strip(): return None
        try:
            return float(str(value_str).replace(",", ".").strip())
        except ValueError:
            return None

    @staticmethod
    def is_valid_gtin(ean_string):
        if not ean_string: return True
        code = ''.join(filter(str.isdigit, str(ean_string)))
        if len(code) not in (8, 12, 13, 14): return False
        digits = [int(d) for d in code]
        check_digit = digits[-1]
        data_digits = digits[:-1]
        total = 0
        for i, digit in enumerate(reversed(data_digits)):
            multiplier = 3 if i % 2 == 0 else 1
            total += digit * multiplier
        remainder = total % 10
        calculated_check = (10 - remainder) if remainder != 0 else 0
        return check_digit == calculated_check

    @staticmethod
    def hex_to_rgb(hex_str):
        if not hex_str or not isinstance(hex_str, str): return (255, 255, 255)
        hex_str = hex_str.lstrip("#")
        try:
            return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (255, 255, 255)

    @staticmethod
    def resolve_parent_bg(widget):
        def _resolve_parent_bg(parent):
            try:
                bg = parent.cget("background")
            except Exception:
                bg = ""
            if isinstance(bg, str) and bg.startswith("#") and len(bg) == 7:
                return bg
            try:
                style_name = parent.cget("style")
            except Exception:
                style_name = ""
            if not style_name:
                try:
                    style_name = parent.winfo_class()
                except Exception:
                    style_name = ""
            if style_name:
                try:
                    style = ttk.Style()
                    bg2 = style.lookup(style_name, "background")
                    if isinstance(bg2, str) and bg2.startswith("#") and len(bg2) == 7:
                        return bg2
                except Exception:
                    pass
            return Colors.BG_APP

        return _resolve_parent_bg(widget)

    @staticmethod
    def validar_decimais(unidade_nome, valor):
        if not unidade_nome: return True, ""
        try:
            val = float(valor)
            return True, ""
        except ValueError:
            return False, "Valor inválido"

    @staticmethod
    def calcular_vencimento(data_fabricacao_str, shelf_life, shelf_unit):
        if not data_fabricacao_str or not shelf_life: return ""
        try:
            dt_fab = datetime.strptime(data_fabricacao_str, "%d/%m/%Y")
            valor = int(shelf_life)
            if shelf_unit == "Meses":
                dt_venc = dt_fab + relativedelta(months=valor)
            else:
                dt_venc = dt_fab + timedelta(days=valor)
            return dt_venc.strftime("%d/%m/%Y")
        except:
            return ""

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_BASE = os.path.join(BASE_DIR, "assets", "icons")

_ICON_CACHE = {}
_ICON_VARIANTS = {}
_PIL_OK = None


def _pil_ok():
    global _PIL_OK
    if _PIL_OK is None:
        try:
            import PIL, PIL.Image, PIL.ImageTk
            _PIL_OK = True
        except Exception:
            _PIL_OK = False
    return _PIL_OK


def _icon_base_name(name: str):
    if name == "proximo": return "anterior", True
    if name == "ultimo": return "primeiro", True
    return name, False


def load_icon(name: str, size: int = 16, color: str = None) -> tk.PhotoImage:
    key = (name, size)

    # 1. Carrega o ícone base (Cacheado)
    if key in _ICON_CACHE:
        img = _ICON_CACHE[key]
    else:
        base_name, flip = _icon_base_name(name)
        rel = os.path.join(str(size), f"{base_name}.png")

        # Tenta carregar do disco
        p1 = os.path.join(ICON_BASE, rel)
        p2_base = os.path.join(sys._MEIPASS, "assets", "icons") if hasattr(sys, "_MEIPASS") else None
        p2 = os.path.join(p2_base, rel) if p2_base else None

        img = None
        for path in (p1, p2):
            if path and os.path.exists(path):
                if _pil_ok():
                    from PIL import Image, ImageTk
                    im = Image.open(path).convert("RGBA")
                    if size > 0 and (im.width != size or im.height != size):
                        im = im.resize((size, size), Image.LANCZOS)
                    if flip:
                        im = im.transpose(Image.FLIP_LEFT_RIGHT)
                    img = ImageTk.PhotoImage(im)
                else:
                    img = tk.PhotoImage(file=path)

                img._icon_key = (name, size)
                _ICON_CACHE[key] = img
                break

        if img is None:
            # Fallback se não achar
            img = tk.PhotoImage(width=1, height=1)
            img._icon_key = (name, size)
            _ICON_CACHE[key] = img

    # 2. Se foi solicitada uma cor, aplica a tintura
    if color:
        return _tint_icon(img, color)

    return img


def _tint_icon(icon_img, color_hex):
    if not _pil_ok(): return icon_img
    key = getattr(icon_img, "_icon_key", None)
    if not key: return icon_img

    name, size = key
    vkey = (name, size, color_hex.lower())
    if vkey in _ICON_VARIANTS: return _ICON_VARIANTS[vkey]

    from PIL import Image, ImageTk
    base_name, flip = _icon_base_name(name)
    path = os.path.join(ICON_BASE, str(size), f"{base_name}.png")

    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return icon_img

    if size > 0: im = im.resize((size, size), Image.LANCZOS)
    if flip: im = im.transpose(Image.FLIP_LEFT_RIGHT)

    a = im.split()[-1]
    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    base = Image.new("RGBA", im.size, (r, g, b, 255))
    base.putalpha(a)
    out = ImageTk.PhotoImage(base)

    _ICON_VARIANTS[vkey] = out
    return out


class EventBus:
    def __init__(self):
        self._subscribers = {}

    def subscribe(self, event_name, callback):
        # Quem quiser ouvir um evento, se inscreve aqui."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def publish(self, event_name, data=None):
        # Avisa t0do mundo que o evento ocorreu.
        if event_name in self._subscribers:
            for callback in self._subscribers[event_name]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Erro no evento {event_name}: {e}")

# Instância global compartilhada
bus = EventBus()