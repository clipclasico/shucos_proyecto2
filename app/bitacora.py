from app import consola, db, sesion

OPERACIONES = ("INSERT", "UPDATE", "DELETE")

_DESDE = """
    from bitacora b
    left join usuario u  on u.usuario_id = b.usuario_id
    left join empleado e on e.empleado_id = u.empleado_id
"""


def _alcance():
    if sesion.tiene_rol("administrador"):
        return [], []
    return ["e.sucursal_id = %s"], [sesion.sucursal_id]


def _where(condiciones):
    return ("where " + " and ".join(condiciones)) if condiciones else ""


def _mostrar_detalle(cambio_id):
    condiciones, params = _alcance()
    condiciones.append("b.bitacora_id = %s")
    params.append(cambio_id)
    filas = db.consultar(f"""
        select b.bitacora_id, b.fecha_hora, coalesce(u.username, '(sistema)') as usuario,
               b.tabla, b.operacion, b.registro_id, b.datos_antes, b.datos_despues
        {_DESDE}
        {_where(condiciones)}
    """, params)
    if not filas:
        consola.error("No existe ese cambio (o no tienes permiso para verlo).")
        return False

    c = filas[0]
    print(f"\nCambio #{c['bitacora_id']} | {c['fecha_hora']:%Y-%m-%d %H:%M:%S} | usuario: {c['usuario']} | "
          f"{c['tabla']} {c['operacion']} | registro: {c['registro_id'] or '-'}")
    antes = c["datos_antes"] or {}
    despues = c["datos_despues"] or {}

    if c["operacion"] == "UPDATE":
        cambios = [{"campo": k, "antes": antes.get(k), "despues": v}
                   for k, v in despues.items() if antes.get(k) != v]
        consola.mostrar_tabla(cambios, "El cambio no modifico ningun campo.")
    else:
        datos = despues if c["operacion"] == "INSERT" else antes
        titulo = "Datos insertados:" if c["operacion"] == "INSERT" else "Datos eliminados:"
        print(titulo)
        consola.mostrar_tabla([{"campo": k, "valor": v} for k, v in datos.items()])
    return True


def consultar_cambios():
    consola.titulo("CONSULTAR CAMBIOS")
    base, params_base = _alcance()

    tablas = [f["tabla"] for f in db.consultar(
        f"select distinct b.tabla {_DESDE} {_where(base)} order by 1", params_base)]
    if not tablas:
        consola.aviso("Todavia no hay cambios registrados.")
        consola.pausa()
        return
    print("Tablas con cambios: " + ", ".join(tablas))
    print("Deja en blanco (Enter) los filtros que no quieras usar.")

    condiciones, params = list(base), list(params_base)

    while True:
        tabla = consola.pedir_texto("Tabla", obligatorio=False)
        if tabla is None or tabla.lower() in tablas:
            break
        consola.error("Esa tabla no tiene cambios registrados.")
    if tabla:
        condiciones.append("b.tabla = %s")
        params.append(tabla.lower())

    usuario = consola.pedir_texto("Usuario", obligatorio=False)
    if usuario:
        condiciones.append("u.username ilike %s")
        params.append(f"%{usuario}%")

    while True:
        operacion = consola.pedir_texto("Operacion (INSERT, UPDATE o DELETE)", obligatorio=False)
        if operacion is None or operacion.upper() in OPERACIONES:
            break
        consola.error("Operacion no valida.")
    if operacion:
        condiciones.append("b.operacion = %s")
        params.append(operacion.upper())

    fecha = consola.pedir_fecha("Fecha", obligatorio=False)
    if fecha:
        condiciones.append("b.fecha_hora::date = %s")
        params.append(fecha)

    limite = consola.pedir_entero("Cuantos registros mostrar (Enter = 30)", minimo=1, maximo=200,
                                  obligatorio=False) or 30

    filas = db.consultar(f"""
        select b.bitacora_id as id, to_char(b.fecha_hora, 'YYYY-MM-DD HH24:MI:SS') as fecha,
               coalesce(u.username, '(sistema)') as usuario, b.tabla, b.operacion,
               coalesce(b.registro_id, '-') as registro
        {_DESDE}
        {_where(condiciones)}
        order by b.bitacora_id desc
        limit %s
    """, params + [limite])
    consola.mostrar_tabla(filas, "No hay cambios con esos filtros.")

    while filas:
        cambio_id = consola.pedir_entero("\nId de un cambio para ver su detalle (Enter para volver)",
                                         minimo=1, obligatorio=False)
        if cambio_id is None:
            break
        _mostrar_detalle(cambio_id)
    consola.pausa()


def ver_detalle():
    consola.titulo("DETALLE DE UN CAMBIO")
    cambio_id = consola.pedir_entero("Id del cambio (0 para cancelar)", minimo=0)
    if cambio_id == 0:
        return
    _mostrar_detalle(cambio_id)
    consola.pausa()


def menu_bitacora():
    acciones = [consultar_cambios, ver_detalle]
    while True:
        eleccion = consola.menu("BITACORA DE CAMBIOS", [
            "Consultar cambios (con filtros)",
            "Ver el detalle de un cambio por id",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()
