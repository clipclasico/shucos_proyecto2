from app import consola, db, sesion


def elegir():
    if not sesion.tiene_rol("administrador"):
        return sesion.sucursal_id

    lista = db.consultar("select sucursal_id as id, nombre from sucursal where activa order by sucursal_id")
    consola.mostrar_tabla(lista)
    ids = {s["id"] for s in lista}
    while True:
        elegida = consola.pedir_entero("Id de la sucursal (0 para cancelar)", minimo=0)
        if elegida == 0:
            return None
        if elegida in ids:
            return elegida
        consola.error("Ese id no esta en la lista.")
