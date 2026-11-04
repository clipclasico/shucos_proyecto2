import psycopg2

from app import clientes, consola, db, sesion, sucursales


def _mensaje_error(e):
    return getattr(e.diag, "message_primary", None) or str(e)


def _es_admin():
    return sesion.tiene_rol("administrador")


def _cargar_pedido(pedido_id):
    sql = """
        select p.*, s.nombre as sucursal, m.numero as mesa, c.nombre as cliente,
               e.nombre as mesero, t.total
        from pedido p
        join sucursal s       on s.sucursal_id = p.sucursal_id
        left join mesa m      on m.mesa_id = p.mesa_id
        left join cliente c   on c.cliente_id = p.cliente_id
        join empleado e       on e.empleado_id = p.empleado_id
        join v_pedido_total t on t.pedido_id = p.pedido_id
        where p.pedido_id = %s
    """
    params = [pedido_id]
    if not _es_admin():
        sql += " and p.sucursal_id = %s"
        params.append(sesion.sucursal_id)
    filas = db.consultar(sql, params)
    return filas[0] if filas else None


def _listar(solo_abiertos, limite=None):
    condiciones, params = [], []
    if solo_abiertos:
        condiciones.append("p.estado = 'abierto'")
    if not _es_admin():
        condiciones.append("p.sucursal_id = %s")
        params.append(sesion.sucursal_id)
    where = ("where " + " and ".join(condiciones)) if condiciones else ""
    orden = "p.fecha_hora" if solo_abiertos else "p.fecha_hora desc"
    tope = f"limit {int(limite)}" if limite else ""

    filas = db.consultar(f"""
        select p.pedido_id as id, s.nombre as sucursal, p.estado,
               coalesce(m.numero::text, 'Para llevar') as mesa,
               coalesce(c.nombre, '-') as cliente, e.nombre as mesero,
               to_char(p.fecha_hora, 'YYYY-MM-DD HH24:MI') as fecha, t.total
        from pedido p
        join sucursal s       on s.sucursal_id = p.sucursal_id
        left join mesa m      on m.mesa_id = p.mesa_id
        left join cliente c   on c.cliente_id = p.cliente_id
        join empleado e       on e.empleado_id = p.empleado_id
        join v_pedido_total t on t.pedido_id = p.pedido_id
        {where}
        order by {orden}
        {tope}
    """, params)
    consola.mostrar_tabla(filas, "No hay pedidos para mostrar.")
    return filas


def _pedir_pedido(mensaje, solo_abierto=True):
    pedido_id = consola.pedir_entero(f"{mensaje} (0 para cancelar)", minimo=0)
    if pedido_id == 0:
        return None
    pedido = _cargar_pedido(pedido_id)
    if not pedido:
        consola.error("No existe ese pedido en tu sucursal.")
        consola.pausa()
        return None
    if solo_abierto and pedido["estado"] != "abierto":
        consola.error(f"El pedido #{pedido_id} esta {pedido['estado']}: solo se usan pedidos abiertos.")
        consola.pausa()
        return None
    return pedido


def _lineas(pedido_id):
    return db.consultar("""
        select pl.plato_id as id, pl.nombre as plato, d.cantidad,
               d.precio_unitario as precio, d.cantidad * d.precio_unitario as subtotal
        from detalle_pedido d
        join plato pl on pl.plato_id = d.plato_id
        where d.pedido_id = %s
        order by pl.plato_id
    """, (pedido_id,))


def _mostrar_cuenta(pedido_id):
    pedido = _cargar_pedido(pedido_id)
    donde = f"mesa {pedido['mesa']}" if pedido["mesa"] is not None else "para llevar"
    print(f"\nPedido #{pedido_id} | {pedido['sucursal']} | {donde} | "
          f"cliente: {pedido['cliente'] or '-'} | mesero: {pedido['mesero']} | {pedido['estado']}")
    consola.mostrar_tabla(_lineas(pedido_id), "Todavia no hay platos en este pedido.")
    print(f"TOTAL: Q{pedido['total']:.2f}")


def _elegir_mesero(sucursal_id):
    if sesion.tiene_rol("mesero"):
        return sesion.empleado_id
    meseros = db.consultar("""
        select empleado_id as id, nombre from empleado
        where sucursal_id = %s and cargo = 'mesero' and activo
        order by nombre
    """, (sucursal_id,))
    if not meseros:
        consola.error("Esa sucursal no tiene meseros activos.")
        return None
    consola.mostrar_tabla(meseros)
    ids = {m["id"] for m in meseros}
    while True:
        elegido = consola.pedir_entero("Id del mesero que atiende (0 para cancelar)", minimo=0)
        if elegido == 0:
            return None
        if elegido in ids:
            return elegido
        consola.error("Ese id no esta en la lista.")


def _elegir_reserva(cliente_id, sucursal_id):
    reservas = db.consultar("""
        select r.reserva_id as id, m.numero as mesa, r.mesa_id,
               to_char(r.fecha_hora_inicio, 'HH24:MI') as hora, r.num_personas as personas
        from reserva r
        join mesa m on m.mesa_id = r.mesa_id
        where r.cliente_id = %s and r.sucursal_id = %s
          and r.estado in ('pendiente', 'confirmada')
          and r.fecha_hora_inicio::date = current_date
          and not exists (select 1 from pedido p where p.reserva_id = r.reserva_id)
        order by r.fecha_hora_inicio
    """, (cliente_id, sucursal_id))
    if not reservas:
        return None

    consola.aviso("Este cliente tiene reservas para hoy:")
    consola.mostrar_tabla([{k: v for k, v in r.items() if k != "mesa_id"} for r in reservas])
    ids = {r["id"]: r for r in reservas}
    while True:
        elegida = consola.pedir_entero("Id de la reserva (Enter = no viene de una reserva)", obligatorio=False)
        if elegida is None:
            return None
        if elegida in ids:
            return ids[elegida]
        consola.error("Elige una reserva de la lista.")


def _elegir_mesa(sucursal_id):
    mesas = db.consultar("""
        select m.mesa_id as id, m.numero as mesa, m.capacidad,
               case when exists (select 1 from pedido p
                                 where p.mesa_id = m.mesa_id and p.estado = 'abierto')
                    then 'ocupada' else 'libre' end as estado
        from mesa m
        where m.sucursal_id = %s
        order by m.numero
    """, (sucursal_id,))
    consola.mostrar_tabla([{"Mesa": m["mesa"], "Capacidad": m["capacidad"], "Estado": m["estado"]}
                           for m in mesas])
    por_numero = {m["mesa"]: m for m in mesas}
    while True:
        numero = consola.pedir_entero("Numero de mesa (Enter = para llevar)", obligatorio=False)
        if numero is None:
            return None
        mesa = por_numero.get(numero)
        if not mesa:
            consola.error("Elige una mesa de la lista.")
            continue
        if mesa["estado"] == "ocupada" and not consola.confirmar(
                "Esa mesa ya tiene un pedido abierto. Abrir otro de todos modos?"):
            continue
        return mesa["id"]


def _agregar_plato(pedido_id):
    platos = db.consultar("""
        select plato_id as id, nombre, categoria, precio
        from plato
        where activo
        order by case categoria when 'shuco' then 1 when 'snack' then 2 else 3 end, plato_id
    """)
    consola.mostrar_tabla(platos)
    ids = {p["id"] for p in platos}
    while True:
        plato_id = consola.pedir_entero("Id del plato (0 para cancelar)", minimo=0)
        if plato_id == 0:
            return
        if plato_id in ids:
            break
        consola.error("Ese id no esta en el menu.")
    cantidad = consola.pedir_entero("Cantidad", minimo=1, maximo=20)

    db.ejecutar("""
        insert into detalle_pedido (pedido_id, plato_id, cantidad, precio_unitario)
        select %s, plato_id, %s, precio from plato where plato_id = %s
        on conflict (pedido_id, plato_id)
        do update set cantidad = detalle_pedido.cantidad + excluded.cantidad
    """, (pedido_id, cantidad, plato_id))
    consola.exito("Plato agregado.")


def _elegir_linea(pedido_id, mensaje):
    lineas = _lineas(pedido_id)
    if not lineas:
        consola.aviso("El pedido todavia no tiene platos.")
        return None
    ids = {l["id"] for l in lineas}
    while True:
        plato_id = consola.pedir_entero(f"{mensaje} (0 para cancelar)", minimo=0)
        if plato_id == 0:
            return None
        if plato_id in ids:
            return plato_id
        consola.error("Ese plato no esta en el pedido.")


def _cambiar_cantidad(pedido_id):
    plato_id = _elegir_linea(pedido_id, "Id del plato a cambiar")
    if plato_id is None:
        return
    cantidad = consola.pedir_entero("Nueva cantidad", minimo=1, maximo=50)
    db.ejecutar("update detalle_pedido set cantidad = %s where pedido_id = %s and plato_id = %s",
                (cantidad, pedido_id, plato_id))
    consola.exito("Cantidad actualizada.")


def _quitar_plato(pedido_id):
    plato_id = _elegir_linea(pedido_id, "Id del plato a quitar")
    if plato_id is None:
        return
    if consola.confirmar("Quitar ese plato del pedido?"):
        db.ejecutar("delete from detalle_pedido where pedido_id = %s and plato_id = %s",
                    (pedido_id, plato_id))
        consola.exito("Plato quitado.")


def _editar_platos(pedido_id):
    while True:
        _mostrar_cuenta(pedido_id)
        eleccion = consola.menu(f"PEDIDO #{pedido_id}",
                                ["Agregar plato", "Cambiar cantidad", "Quitar plato"],
                                texto_salida="Listo")
        if eleccion == 0:
            return
        try:
            if eleccion == 1:
                _agregar_plato(pedido_id)
            elif eleccion == 2:
                _cambiar_cantidad(pedido_id)
            else:
                _quitar_plato(pedido_id)
        except psycopg2.Error as e:
            consola.error(_mensaje_error(e))
            consola.pausa()


def nuevo_pedido():
    consola.titulo("NUEVO PEDIDO")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    empleado_id = _elegir_mesero(sucursal_id)
    if empleado_id is None:
        return

    cliente = None
    if consola.confirmar("El pedido es de un cliente registrado?"):
        cliente = clientes.elegir_cliente()
        if cliente is None:
            consola.aviso("Se continua sin cliente.")

    reserva = _elegir_reserva(cliente["id"], sucursal_id) if cliente else None
    mesa_id = reserva["mesa_id"] if reserva else _elegir_mesa(sucursal_id)

    try:
        with db.transaccion() as cur:
            cur.execute("""
                insert into pedido (sucursal_id, mesa_id, cliente_id, empleado_id, reserva_id)
                values (%s, %s, %s, %s, %s)
                returning pedido_id
            """, (sucursal_id, mesa_id, cliente["id"] if cliente else None, empleado_id,
                  reserva["id"] if reserva else None))
            pedido_id = cur.fetchone()["pedido_id"]
    except psycopg2.Error as e:
        consola.error(_mensaje_error(e))
        consola.pausa()
        return

    consola.exito(f"Pedido #{pedido_id} abierto.")
    _editar_platos(pedido_id)


def pedidos_abiertos():
    consola.titulo("PEDIDOS ABIERTOS")
    _listar(solo_abiertos=True)
    consola.pausa()


def editar_platos():
    consola.titulo("AGREGAR O EDITAR PLATOS")
    if not _listar(solo_abiertos=True):
        consola.pausa()
        return
    pedido = _pedir_pedido("Id del pedido")
    if pedido is not None:
        _editar_platos(pedido["pedido_id"])


def ver_cuenta():
    consola.titulo("VER CUENTA DE UN PEDIDO")
    print("Ultimos 10 pedidos:")
    _listar(solo_abiertos=False, limite=10)
    pedido = _pedir_pedido("Id del pedido", solo_abierto=False)
    if pedido is not None:
        _mostrar_cuenta(pedido["pedido_id"])
        if pedido["observaciones"] or pedido["calificacion"]:
            print(f"Calificacion: {pedido['calificacion'] or '-'} | "
                  f"Observaciones: {pedido['observaciones'] or '-'}")
        consola.pausa()


def pagar_pedido():
    consola.titulo("PAGAR PEDIDO")
    if not _listar(solo_abiertos=True):
        consola.pausa()
        return
    pedido = _pedir_pedido("Id del pedido a pagar")
    if pedido is None:
        return
    pedido_id = pedido["pedido_id"]

    _mostrar_cuenta(pedido_id)
    if not consola.confirmar(f"Cobrar Q{pedido['total']:.2f} y cerrar el pedido?"):
        return

    try:
        db.ejecutar("update pedido set estado = 'pagado' where pedido_id = %s", (pedido_id,))
    except psycopg2.Error as e:
        consola.error(_mensaje_error(e))
        consola.aviso("El pedido sigue abierto y el inventario no cambio.")
        consola.pausa()
        return

    consola.exito(f"Pedido #{pedido_id} pagado. Inventario actualizado.")
    if pedido["reserva_id"]:
        consola.exito(f"La reserva #{pedido['reserva_id']} quedo como cumplida.")

    calificacion = consola.pedir_entero("Calificacion del cliente de 1 a 5 (Enter para omitir)",
                                        minimo=1, maximo=5, obligatorio=False)
    observaciones = consola.pedir_texto("Observaciones de la experiencia (Enter para omitir)",
                                        obligatorio=False)
    if calificacion is not None or observaciones:
        db.ejecutar("update pedido set calificacion = %s, observaciones = %s where pedido_id = %s",
                    (calificacion, observaciones, pedido_id))
        consola.exito("Calificacion y observaciones guardadas.")
    consola.pausa()


def cancelar_pedido():
    consola.titulo("CANCELAR PEDIDO")
    if not _listar(solo_abiertos=True):
        consola.pausa()
        return
    pedido = _pedir_pedido("Id del pedido a cancelar")
    if pedido is None:
        return
    _mostrar_cuenta(pedido["pedido_id"])
    if consola.confirmar("Seguro que quieres cancelar este pedido?"):
        db.ejecutar("update pedido set estado = 'cancelado' where pedido_id = %s", (pedido["pedido_id"],))
        consola.exito(f"Pedido #{pedido['pedido_id']} cancelado.")
    consola.pausa()


def menu_pedidos():
    acciones = [nuevo_pedido, pedidos_abiertos, editar_platos, ver_cuenta, pagar_pedido, cancelar_pedido]
    while True:
        eleccion = consola.menu("PEDIDOS", [
            "Nuevo pedido",
            "Pedidos abiertos",
            "Agregar o editar platos de un pedido",
            "Ver cuenta de un pedido",
            "Pagar pedido",
            "Cancelar pedido",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()
