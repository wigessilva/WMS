import socket
from datetime import datetime
from .helpers import log_exception # Importa o logger do arquivo vizinho

# Tenta importar win32print (pode falhar se não estiver instalado/windows)
try:
    import win32print
except ImportError:
    win32print = None

def get_windows_printers():
    if not win32print:
        return []
    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags)
        return [p[2] for p in printers]
    except Exception:
        return []

def imprimir_etiqueta_lpn(printer_data, lpn_codigo):
    zpl_template = """
    ^XA
    ^PW800^LL800^MD15^PON
    ^FO10,10^GB780,780,4^FS
    ^FO0,50^A0N,30,30^FB800,1,0,C,0^FDLPN DE ESTOQUE^FS
    ^FO215,120^BY3,3,240^BCN,240,N,N,N^FD{lpn}^FS
    ^FO0,480^A0N,180,90^FB800,1,0,C,0^FD{lpn}^FS
    ^FO0,720^A0N,25,25^FB800,1,0,C,0^FDGerado em: {data}^FS
    ^XZ
    """
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    zpl_final = zpl_template.format(lpn=lpn_codigo, data=agora)

    tipo = printer_data.get("Tipo", "windows")
    caminho = printer_data.get("Caminho", "")

    try:
        if tipo == "rede":
            ip = caminho
            porta = int(printer_data.get("Porta", 9100))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((ip, porta))
                s.sendall(zpl_final.encode('utf-8'))
        else:
            if not win32print:
                print("Biblioteca win32print não disponível.")
                return
            hPrinter = win32print.OpenPrinter(caminho)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("LPN Label", None, "RAW"))
                try:
                    win32print.StartPagePrinter(hPrinter)
                    win32print.WritePrinter(hPrinter, zpl_final.encode('utf-8'))
                    win32print.EndPagePrinter(hPrinter)
                finally:
                    win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
    except Exception as e:
        log_exception(e, f"Erro ao imprimir LPN {lpn_codigo}")
        raise e

def imprimir_etiqueta_endereco(printer_data, dados_end):
    tipo = dados_end.get("Tipo", "Porta-Palete")
    rua = int(dados_end.get("Rua", 0))
    pred = int(dados_end.get("Predio", 0))
    niv = int(dados_end.get("Nivel", 0))
    grupo = dados_end.get("GrupoBloqueio", "")

    import string
    letras = string.ascii_uppercase

    if tipo == "Estante" or tipo == "Picking":
        idx = max(0, niv - 1) % 26
        letra = letras[idx]
        texto_topo = f"RUA {rua:02d} - PREDIO {pred:02d}"
        texto_destaque = f"{letra}-{grupo}" if grupo else f"{letra}"
        codigo_barras = f"{rua:02d}-{pred:02d}-{letra}{grupo}"
        font_size = "110,110"
    else:
        texto_topo = f"AREA: {dados_end.get('area', 'GERAL')}"
        base_addr = f"{rua:02d}-{pred:02d}-{niv:02d}"
        if grupo:
            texto_destaque = f"{base_addr}-{grupo}"
        else:
            texto_destaque = base_addr
        codigo_barras = texto_destaque
        font_size = "90,90"

    zpl = f"""
    ^XA
    ^PW640^LL400
    ^MD15^PON
    ^FO10,10^GB620,380,4^FS
    ^FO0,35^A0N,25,25^FB640,1,0,C,0^FD{texto_topo}^FS
    ^FO0,80^A0N,{font_size}^FB640,1,0,C,0^FD{texto_destaque}^FS
    ^FO120,210^BY3,3,100^BCN,100,N,N,N^FD{codigo_barras}^FS
    ^FO0,325^A0N,25,25^FB640,1,0,C,0^FD{codigo_barras}^FS
    ^XZ
    """

    tipo_conn = printer_data.get("Tipo", "windows")
    caminho = printer_data.get("Caminho", "")

    try:
        if tipo_conn == "rede":
            ip = caminho
            porta = int(printer_data.get("Porta", 9100))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((ip, porta))
                s.sendall(zpl.encode('utf-8'))
        else:
            if not win32print: return
            hPrinter = win32print.OpenPrinter(caminho)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("Label 80x50", None, "RAW"))
                try:
                    win32print.StartPagePrinter(hPrinter)
                    win32print.WritePrinter(hPrinter, zpl.encode('utf-8'))
                    win32print.EndPagePrinter(hPrinter)
                finally:
                    win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
    except Exception as e:
        log_exception(e, f"Erro imp endereço {codigo_barras}")
        raise e