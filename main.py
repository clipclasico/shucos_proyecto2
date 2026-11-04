from app import (auth, bitacora, clientes, consola, db, empleados, inventario, pedidos,
                 reportes, reservas, sesion)



TODOS = ("mesero", "gerente", "administrador")
JEFES = ("gerente", "administrador")

MODULOS = [
    ("Reservas",              TODOS,           reservas.menu_reservas),
    ("Pedidos",               TODOS,           pedidos.menu_pedidos),
    ("Historial de clientes", TODOS,           clientes.menu_clientes),
    ("Inventario",            JEFES,           inventario.menu_inventario),
    ("Bitacora de cambios",   JEFES,           bitacora.menu_bitacora),
    ("Reportes",              ("administrador",), reportes.menu_reportes),
    ("Empleados y usuarios",  ("administrador",), empleados.menu_empleados),
]


def menu_principal():
    disponibles = [m for m in MODULOS if sesion.rol in m[1]]
    while True:
        eleccion = consola.menu(
            f"MENU PRINCIPAL - {sesion.username} ({sesion.rol})",
            [m[0] for m in disponibles],
            texto_salida="Cerrar sesion",
        )
        if eleccion == 0:
            sesion.cerrar()
            consola.exito("Sesion cerrada.")
            return
        disponibles[eleccion - 1][2]()


def main():
    try:
        db.consultar("select 1")
    except Exception as e:
        consola.error(f"No se pudo conectar a la base de datos: {e}")
        consola.aviso("Revisa los datos de tu archivo .env y que PostgreSQL este encendido.")
        return

    while True:
        eleccion = consola.menu("SHUCOS EL SAPO", ["Iniciar sesion", "Registrarse"], texto_salida="Salir")
        if eleccion == 0:
            print("Hasta luego!")
            return
        if eleccion == 1:
            if auth.login():
                menu_principal()
        else:
            auth.registrar()


if __name__ == "__main__":
    main()