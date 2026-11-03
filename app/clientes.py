import psycopg2

from app import consola, db


def buscar(texto):
    patron = f"%{texto or ''}%"
    return db.consultar("""
        select cliente_id as id, nombre, telefono, correo
        from cliente
        where nombre ilike %s or telefono ilike %s or correo ilike %s
        order by nombre
        limit 30
    """, (patron, patron, patron))


def crear():
    consola.titulo("NUEVO CLIENTE")
    nombre = consola.pedir_texto("Nombre completo", max_len=100)
    telefono = consola.pedir_telefono("Telefono (Enter para omitir)")
    correo = consola.pedir_texto("Correo (Enter para omitir)", obligatorio=False, max_len=100)
    try:
        with db.transaccion() as cur:
            cur.execute(
                "insert into cliente (nombre, telefono, correo) values (%s, %s, %s) returning cliente_id",
                (nombre, telefono, correo.lower() if correo else None),
            )
            cliente_id = cur.fetchone()["cliente_id"]
    except psycopg2.errors.UniqueViolation:
        consola.error("Ya existe un cliente con ese correo.")
        return None
    consola.exito(f"Cliente registrado (id {cliente_id}).")
    return {"id": cliente_id, "nombre": nombre}


def elegir_cliente():
    while True:
        texto = consola.pedir_texto(
            "Buscar cliente por nombre, telefono o correo (Enter = ver la lista, 0 para cancelar)",
            obligatorio=False)
        if texto == "0":
            return None

        filas = buscar(texto)
        if filas:
            consola.mostrar_tabla(filas)
            cliente_id = consola.pedir_entero("Id del cliente (0 para buscar de nuevo)", minimo=0)
            if cliente_id == 0:
                if consola.confirmar("Registrar un cliente nuevo?"):
                    cliente = crear()
                    if cliente:
                        return cliente
                continue
            elegido = next((f for f in filas if f["id"] == cliente_id), None)
            if elegido:
                return {"id": elegido["id"], "nombre": elegido["nombre"]}
            consola.error("Ese id no esta en la lista.")
        else:
            consola.aviso("No se encontraron clientes.")
            if consola.confirmar("Registrar un cliente nuevo?"):
                cliente = crear()
                if cliente:
                    return cliente


TIPOS = {
    1: ("plato_favorito", "Plato favorito"),
    2: ("evitar_ingrediente", "Ingrediente a evitar"),
    3: ("mesa", "Mesa preferida"),
    4: ("nota", "Nota"),
}


def _mostrar_preferencias(cliente_id):
    filas = db.consultar("""
        select p.preferencia_id as id, p.tipo, coalesce(pl.nombre, '-') as plato,
               coalesce(p.descripcion, '-') as descripcion,
               to_char(p.fecha_registro, 'YYYY-MM-DD') as registrada
        from preferencia_cliente p
        left join plato pl on pl.plato_id = p.plato_id
        where p.cliente_id = %s
        order by p.preferencia_id
    """, (cliente_id,))
    consola.mostrar_tabla(filas, "Sin preferencias declaradas.")
    return filas


def _mostrar_ficha(cliente_id):
    c = db.consultar("select * from cliente where cliente_id = %s", (cliente_id,))[0]
    consola.titulo(c["nombre"].upper())
    print(f"Telefono: {c['telefono'] or '-'} | Correo: {c['correo'] or '-'} | "
          f"Cliente desde: {c['fecha_registro']:%Y-%m-%d}")

    v = db.consultar("""
        select count(*) as visitas, coalesce(sum(total), 0) as gastado,
               round(avg(calificacion), 1) as calificacion, max(fecha_hora) as ultima
        from v_historial_visitas
        where cliente_id = %s
    """, (cliente_id,))[0]
    r = db.consultar("""
        select count(*) as reservas, count(*) filter (where estado = 'cancelada') as canceladas
        from reserva
        where cliente_id = %s
    """, (cliente_id,))[0]
    ultima = f"{v['ultima']:%Y-%m-%d}" if v["ultima"] else "-"
    print(f"Visitas: {v['visitas']} | Total gastado: Q{v['gastado']:.2f} | "
          f"Calificacion promedio: {v['calificacion'] or '-'} | Ultima visita: {ultima}")
    print(f"Reservas: {r['reservas']} (canceladas: {r['canceladas']})")

    print("\nPLATOS FAVORITOS (segun sus pedidos pagados):")
    consola.mostrar_tabla(db.consultar("""
        select posicion as puesto, plato, veces
        from v_preferencia_calculada
        where cliente_id = %s and posicion <= 3
        order by posicion
    """, (cliente_id,)), "Todavia no tiene pedidos pagados.")

    print("\nPREFERENCIAS DECLARADAS:")
    _mostrar_preferencias(cliente_id)

    print("\nULTIMAS VISITAS:")
    consola.mostrar_tabla(_ultimas_visitas(cliente_id), "Todavia no tiene visitas.")

    print("\nULTIMAS RESERVAS:")
    consola.mostrar_tabla(db.consultar("""
        select r.reserva_id as id, to_char(r.fecha_hora_inicio, 'YYYY-MM-DD HH24:MI') as fecha,
               s.nombre as sucursal, m.numero as mesa, r.num_personas as personas, r.estado
        from reserva r
        join sucursal s on s.sucursal_id = r.sucursal_id
        join mesa m    on m.mesa_id = r.mesa_id
        where r.cliente_id = %s
        order by r.fecha_hora_inicio desc
        limit 10
    """, (cliente_id,)), "Todavia no tiene reservas.")


def _ultimas_visitas(cliente_id):
    return db.consultar("""
        select pedido_id as pedido, to_char(fecha_hora, 'YYYY-MM-DD HH24:MI') as fecha, sucursal,
               total, coalesce(calificacion::text, '-') as calificacion,
               coalesce(observaciones, '-') as observaciones
        from v_historial_visitas
        where cliente_id = %s
        order by fecha_hora desc
        limit 10
    """, (cliente_id,))


def ver_historial():
    cliente = elegir_cliente()
    if cliente is None:
        return
    _mostrar_ficha(cliente["id"])
    consola.pausa()


def nuevo_cliente():
    crear()
    consola.pausa()


def editar_cliente():
    consola.titulo("EDITAR DATOS DE UN CLIENTE")
    cliente = elegir_cliente()
    if cliente is None:
        return
    actual = db.consultar("select nombre, telefono, correo from cliente where cliente_id = %s",
                          (cliente["id"],))[0]
    print(f"\nActual -> nombre: {actual['nombre']} | telefono: {actual['telefono'] or '-'} | "
          f"correo: {actual['correo'] or '-'}")
    print("Deja en blanco (Enter) lo que no quieras cambiar.")
    nombre = consola.pedir_texto("Nuevo nombre", obligatorio=False, max_len=100)
    telefono = consola.pedir_telefono("Nuevo telefono")
    correo = consola.pedir_texto("Nuevo correo", obligatorio=False, max_len=100)
    if not (nombre or telefono or correo):
        consola.aviso("No hay cambios que guardar.")
        consola.pausa()
        return
    try:
        db.ejecutar("""
            update cliente
            set nombre = coalesce(%s, nombre), telefono = coalesce(%s, telefono),
                correo = coalesce(%s, correo)
            where cliente_id = %s
        """, (nombre, telefono, correo.lower() if correo else None, cliente["id"]))
    except psycopg2.errors.UniqueViolation:
        consola.error("Ya existe otro cliente con ese correo.")
    else:
        consola.exito("Datos actualizados.")
    consola.pausa()


def _agregar_preferencia(cliente_id):
    eleccion = consola.menu("TIPO DE PREFERENCIA", [t[1] for t in TIPOS.values()], texto_salida="Cancelar")
    if eleccion == 0:
        return
    tipo = TIPOS[eleccion][0]

    plato_id = None
    if tipo == "plato_favorito":
        platos = db.consultar("select plato_id as id, nombre, categoria from plato where activo order by plato_id")
        consola.mostrar_tabla(platos)
        ids = {p["id"] for p in platos}
        while True:
            plato_id = consola.pedir_entero("Id del plato (0 para cancelar)", minimo=0)
            if plato_id == 0:
                return
            if plato_id in ids:
                break
            consola.error("Ese id no esta en el menu.")
        descripcion = consola.pedir_texto("Comentario (Enter para omitir)", obligatorio=False, max_len=200)
    else:
        descripcion = consola.pedir_texto("Descripcion", max_len=200)

    db.ejecutar("""
        insert into preferencia_cliente (cliente_id, plato_id, tipo, descripcion)
        values (%s, %s, %s, %s)
    """, (cliente_id, plato_id, tipo, descripcion))
    consola.exito("Preferencia guardada.")


def _eliminar_preferencia(cliente_id, filas):
    if not filas:
        consola.aviso("Este cliente no tiene preferencias declaradas.")
        return
    ids = {f["id"] for f in filas}
    while True:
        preferencia_id = consola.pedir_entero("Id de la preferencia a eliminar (0 para cancelar)", minimo=0)
        if preferencia_id == 0:
            return
        if preferencia_id in ids:
            break
        consola.error("Ese id no esta en la lista.")
    if consola.confirmar("Eliminar esa preferencia?"):
        db.ejecutar("delete from preferencia_cliente where preferencia_id = %s and cliente_id = %s",
                    (preferencia_id, cliente_id))
        consola.exito("Preferencia eliminada.")


def gestionar_preferencias():
    consola.titulo("PREFERENCIAS DE UN CLIENTE")
    cliente = elegir_cliente()
    if cliente is None:
        return
    while True:
        print(f"\nPreferencias declaradas de {cliente['nombre']}:")
        filas = _mostrar_preferencias(cliente["id"])
        eleccion = consola.menu("PREFERENCIAS", ["Agregar preferencia", "Eliminar preferencia"],
                                texto_salida="Listo")
        if eleccion == 0:
            return
        if eleccion == 1:
            _agregar_preferencia(cliente["id"])
        else:
            _eliminar_preferencia(cliente["id"], filas)


def agregar_observacion():
    consola.titulo("OBSERVACIONES DE UNA VISITA")
    cliente = elegir_cliente()
    if cliente is None:
        return
    visitas = _ultimas_visitas(cliente["id"])
    if not visitas:
        consola.aviso("Este cliente todavia no tiene visitas.")
        consola.pausa()
        return
    consola.mostrar_tabla(visitas)
    ids = {v["pedido"] for v in visitas}
    while True:
        pedido_id = consola.pedir_entero("Id del pedido (0 para cancelar)", minimo=0)
        if pedido_id == 0:
            return
        if pedido_id in ids:
            break
        consola.error("Ese pedido no esta en la lista.")

    print("Deja en blanco (Enter) lo que no quieras cambiar.")
    calificacion = consola.pedir_entero("Calificacion de 1 a 5", minimo=1, maximo=5, obligatorio=False)
    observaciones = consola.pedir_texto("Observaciones de la experiencia", obligatorio=False)
    if calificacion is None and not observaciones:
        consola.aviso("No hay cambios que guardar.")
        consola.pausa()
        return
    db.ejecutar("""
        update pedido
        set calificacion = coalesce(%s, calificacion), observaciones = coalesce(%s, observaciones)
        where pedido_id = %s
    """, (calificacion, observaciones, pedido_id))
    consola.exito("Visita actualizada.")
    consola.pausa()


def menu_clientes():
    acciones = [ver_historial, nuevo_cliente, editar_cliente, gestionar_preferencias, agregar_observacion]
    while True:
        eleccion = consola.menu("CLIENTES E HISTORIAL", [
            "Ver historial de un cliente",
            "Registrar cliente nuevo",
            "Editar datos de un cliente",
            "Preferencias del cliente",
            "Agregar observacion a una visita",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()