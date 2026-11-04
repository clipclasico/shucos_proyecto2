from datetime import datetime
from getpass import getpass

from tabulate import tabulate


def titulo(texto):
    print()
    print("=" * 62)
    print(texto.center(62))
    print("=" * 62)


def exito(mensaje):
    print(f"[OK] {mensaje}")


def error(mensaje):
    print(f"[ERROR] {mensaje}")


def aviso(mensaje):
    print(f"[!] {mensaje}")


def pausa():
    input("\nPresiona Enter para continuar...")


def pedir_texto(mensaje, obligatorio=True, max_len=None):
    while True:
        valor = input(f"{mensaje}: ").strip()
        if not valor:
            if obligatorio:
                error("Este campo es obligatorio.")
                continue
            return None
        if max_len and len(valor) > max_len:
            error(f"Maximo {max_len} caracteres.")
            continue
        return valor


def pedir_entero(mensaje, minimo=None, maximo=None, obligatorio=True):
    while True:
        texto = input(f"{mensaje}: ").strip()
        if not texto and not obligatorio:
            return None
        try:
            numero = int(texto)
        except ValueError:
            error("Escribe un numero entero.")
            continue
        if minimo is not None and numero < minimo:
            error(f"El valor minimo es {minimo}.")
            continue
        if maximo is not None and numero > maximo:
            error(f"El valor maximo es {maximo}.")
            continue
        return numero


def pedir_fecha(mensaje, obligatorio=True):
    while True:
        texto = input(f"{mensaje} (AAAA-MM-DD): ").strip()
        if not texto and not obligatorio:
            return None
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            error("Fecha invalida. Ejemplo: 2026-11-05")


def pedir_fecha_hora(mensaje):
    while True:
        texto = input(f"{mensaje} (AAAA-MM-DD HH:MM): ").strip()
        try:
            return datetime.strptime(texto, "%Y-%m-%d %H:%M")
        except ValueError:
            error("Formato invalido. Ejemplo: 2026-11-05 19:30")


def pedir_password(mensaje="Contrasena"):
    return getpass(f"{mensaje}: ")


def confirmar(mensaje):
    while True:
        respuesta = input(f"{mensaje} (s/n): ").strip().lower()
        if respuesta in ("s", "si"):
            return True
        if respuesta in ("n", "no"):
            return False
        error("Responde s o n.")


def menu(titulo_menu, opciones, texto_salida="Volver"):
    titulo(titulo_menu)
    for i, texto in enumerate(opciones, start=1):
        print(f"  {i}. {texto}")
    print(f"  0. {texto_salida}")
    return pedir_entero("\nElige una opcion", minimo=0, maximo=len(opciones))


def mostrar_tabla(filas, vacio="No hay resultados."):
    if not filas:
        aviso(vacio)
        return
    print(tabulate([dict(f) for f in filas], headers="keys", tablefmt="grid"))
