from datetime import datetime, timedelta

import psycopg2

from app import clientes, consola, db, sesion, sucursales

DURACION = timedelta(minutes=90)        
HORAS_SUGERIDAS = (12, 14, 16, 18, 20)  
ESTADOS = ("pendiente", "confirmada", "cancelada", "cumplida")


def _mensaje_error(e):
    if isinstance(e, psycopg2.errors.ExclusionViolation):
        return "Esa mesa ya fue reservada en ese horario. Intenta con otra mesa u otro horario."
    return getattr(e.diag, "message_primary", None) or str(e)


def _es_admin():
    return sesion.tiene_rol("administrador")


def _pedir_inicio():
    while True:
        inicio = consola.pedir_fecha_hora("Fecha y hora de la reserva")
        if inicio <= datetime.now():
            consola.error("La reserva debe ser en una fecha y hora futura.")
            continue
        return inicio


def _pedir_personas(sucursal_id):
    maximo = db.consultar(
        "select max(capacidad) as maximo from mesa where sucursal_id = %s", (sucursal_id,))[0]["maximo"]
    return consola.pedir_entero(f"Numero de personas (maximo {maximo})", minimo=1, maximo=maximo)


def _mesas_disponibles(sucursal_id, inicio, personas, excluir_reserva=None):
    return db.consultar("""
        select m.mesa_id as id, m.numero as mesa, m.capacidad
        from mesa m
        where m.sucursal_id = %s
          and m.capacidad >= %s
          and not exists (
              select 1
              from reserva r
              where r.mesa_id = m.mesa_id
                and r.estado <> 'cancelada'
                and r.reserva_id is distinct from %s
                and tsrange(r.fecha_hora_inicio, r.fecha_hora_fin)
                    && tsrange(%s::timestamp, %s::timestamp)
          )
        order by m.capacidad, m.numero
    """, (sucursal_id, personas, excluir_reserva, inicio, inicio + DURACION))


def _sugerir_horarios(sucursal_id, inicio, personas, excluir_reserva=None):
    opciones = []
    for hora in HORAS_SUGERIDAS:
        alterno = inicio.replace(hour=hora, minute=0, second=0, microsecond=0)
        if alterno == inicio or alterno <= datetime.now():
            continue
        libres = _mesas_disponibles(sucursal_id, alterno, personas, excluir_reserva)
        if libres:
            opciones.append({"Horario": alterno.strftime("%H:%M"), "Mesas libres": len(libres)})
    if opciones:
        consola.aviso(f"Horarios con mesa disponible el {inicio:%Y-%m-%d}:")
        consola.mostrar_tabla(opciones)
    else:
        consola.aviso("Tampoco hay mesas libres en los demas horarios de ese dia.")


def _elegir_mesa(mesas, mesa_actual_id=None):
    consola.mostrar_tabla([{"Mesa": m["mesa"], "Capacidad": m["capacidad"]} for m in mesas])
    por_numero = {m["mesa"]: m["id"] for m in mesas}
    sugerida = mesas[0]
    for m in mesas:  
        if m["id"] == mesa_actual_id:
            sugerida = m
    while True:
        numero = consola.pedir_entero(
            f"Numero de mesa (Enter = {sugerida['mesa']}, la mas ajustada)", obligatorio=False)
        if numero is None:
            return sugerida["id"]
        if numero in por_numero:
            return por_numero[numero]
        consola.error("Elige una mesa de la lista.")


def _cargar_reserva(reserva_id):
    sql = """
        select r.*, c.nombre as cliente, m.numero as mesa
        from reserva r
        join cliente c on c.cliente_id = r.cliente_id
        join mesa m    on m.mesa_id = r.mesa_id
        where r.reserva_id = %s
    """
    params = [reserva_id]
    if not _es_admin():
        sql += " and r.sucursal_id = %s"
        params.append(sesion.sucursal_id)
    filas = db.consultar(sql, params)
    return filas[0] if filas else None


def _listar_activas():
    condiciones = ["r.estado in ('pendiente', 'confirmada')"]
    params = []
    if not _es_admin():
        condiciones.append("r.sucursal_id = %s")
        params.append(sesion.sucursal_id)
    filas = db.consultar(f"""
        {_SELECT_LISTA}
        where {" and ".join(condiciones)}
        order by r.fecha_hora_inicio
        limit 40
    """, params)
    print("Reservas pendientes o confirmadas:")
    consola.mostrar_tabla(filas, "No hay reservas pendientes ni confirmadas.")
    return filas


def _pedir_reserva(mensaje):
    reserva_id = consola.pedir_entero(f"{mensaje} (0 para cancelar)", minimo=0)
    if reserva_id == 0:
        return None
    reserva = _cargar_reserva(reserva_id)
    if not reserva:
        consola.error("No existe esa reserva en tu sucursal.")
        consola.pausa()
    return reserva


def _resumen(r):
    print(f"\nReserva #{r['reserva_id']} | {r['cliente']} | mesa {r['mesa']} | "
          f"{r['fecha_hora_inicio']:%Y-%m-%d %H:%M} | {r['num_personas']} personas | {r['estado']}")


_SELECT_LISTA = """
    select r.reserva_id as id, s.nombre as sucursal,
           to_char(r.fecha_hora_inicio, 'YYYY-MM-DD HH24:MI') as inicio,
           m.numero as mesa, r.num_personas as personas, c.nombre as cliente, r.estado,
           case when r.estado in ('pendiente', 'confirmada') and r.fecha_hora_fin < localtimestamp
                then 'paso sin atender' else '' end as alerta
    from reserva r
    join sucursal s on s.sucursal_id = r.sucursal_id
    join mesa m     on m.mesa_id = r.mesa_id
    join cliente c  on c.cliente_id = r.cliente_id
"""


def nueva_reserva():
    consola.titulo("NUEVA RESERVA")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    cliente = clientes.elegir_cliente()
    if cliente is None:
        return

    inicio = _pedir_inicio()
    personas = _pedir_personas(sucursal_id)

    mesas = _mesas_disponibles(sucursal_id, inicio, personas)
    if not mesas:
        consola.aviso("No hay mesas disponibles para ese horario y esa cantidad de personas.")
        _sugerir_horarios(sucursal_id, inicio, personas)
        consola.pausa()
        return

    mesa_id = _elegir_mesa(mesas)
    try:
        with db.transaccion() as cur:
            cur.execute("""
                insert into reserva (sucursal_id, cliente_id, mesa_id, fecha_hora_inicio,
                                     fecha_hora_fin, num_personas, estado)
                values (%s, %s, %s, %s, %s, %s, 'confirmada')
                returning reserva_id
            """, (sucursal_id, cliente["id"], mesa_id, inicio, inicio + DURACION, personas))
            reserva_id = cur.fetchone()["reserva_id"]
    except psycopg2.Error as e:
        consola.error(_mensaje_error(e))
    else:
        consola.exito(f"Reserva #{reserva_id} confirmada para {cliente['nombre']} "
                      f"el {inicio:%Y-%m-%d a las %H:%M} ({personas} personas).")
    consola.pausa()


def ver_disponibilidad():
    consola.titulo("DISPONIBILIDAD DE MESAS")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    inicio = _pedir_inicio()
    personas = _pedir_personas(sucursal_id)

    mesas = _mesas_disponibles(sucursal_id, inicio, personas)
    if mesas:
        consola.exito(f"{len(mesas)} mesa(s) libres el {inicio:%Y-%m-%d a las %H:%M}:")
        consola.mostrar_tabla([{"Mesa": m["mesa"], "Capacidad": m["capacidad"]} for m in mesas])
    else:
        consola.aviso("No hay mesas disponibles para ese horario y esa cantidad de personas.")
        _sugerir_horarios(sucursal_id, inicio, personas)
    consola.pausa()


def buscar_reservas():
    consola.titulo("BUSCAR RESERVAS")
    print("Deja en blanco (Enter) los filtros que no quieras usar.")
    print("Sin ningun filtro se muestran las reservas de hoy en adelante;")
    print("para ver las anteriores usa una fecha o el historial de reservas.")
    fecha = consola.pedir_fecha("Fecha", obligatorio=False)
    texto = consola.pedir_texto("Nombre del cliente", obligatorio=False)
    estado = None
    while True:
        estado = consola.pedir_texto(f"Estado ({', '.join(ESTADOS)})", obligatorio=False)
        if estado is None or estado.lower() in ESTADOS:
            break
        consola.error("Estado no valido.")

    condiciones, params = [], []
    if not _es_admin():
        condiciones.append("r.sucursal_id = %s")
        params.append(sesion.sucursal_id)
    if fecha:
        condiciones.append("r.fecha_hora_inicio::date = %s")
        params.append(fecha)
    elif not texto and not estado:
        condiciones.append("r.fecha_hora_inicio >= current_date") 
    if texto:
        condiciones.append("c.nombre ilike %s")
        params.append(f"%{texto}%")
    if estado:
        condiciones.append("r.estado = %s")
        params.append(estado.lower())

    where = ("where " + " and ".join(condiciones)) if condiciones else ""
    filas = db.consultar(f"""
        {_SELECT_LISTA}
        {where}
        order by r.fecha_hora_inicio
        limit 50
    """, params)
    consola.mostrar_tabla(filas, "No se encontraron reservas con esos filtros.")
    if len(filas) == 50:
        consola.aviso("Se muestran las primeras 50. Usa filtros para acotar la busqueda.")
    consola.pausa()


def ver_historial_reservas():
    consola.titulo("HISTORIAL DE RESERVAS")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    nombre = db.consultar("select nombre from sucursal where sucursal_id = %s", (sucursal_id,))[0]["nombre"]

    print(f"\nReservas de la sucursal {nombre}, por estado:")
    consola.mostrar_tabla(db.consultar("""
        select estado, count(*) as reservas
        from reserva
        where sucursal_id = %s
        group by estado
        order by estado
    """, (sucursal_id,)), "Esta sucursal todavia no tiene reservas.")

    limite = consola.pedir_entero("Cuantas reservas mostrar (Enter = 30)", minimo=1, maximo=200,
                                  obligatorio=False) or 30
    filas = db.consultar(f"""
        {_SELECT_LISTA}
        where r.sucursal_id = %s
        order by r.fecha_hora_inicio desc
        limit %s
    """, (sucursal_id, limite))
    print("\nSe muestran de la mas reciente a la mas antigua.")
    consola.mostrar_tabla(filas, "Esta sucursal todavia no tiene reservas.")
    consola.pausa()


def modificar_reserva():
    consola.titulo("MODIFICAR RESERVA")
    if not _listar_activas():
        consola.pausa()
        return
    reserva = _pedir_reserva("Id de la reserva a modificar")
    if reserva is None:
        return
    if reserva["estado"] not in ("pendiente", "confirmada") or reserva["fecha_hora_inicio"] <= datetime.now():
        consola.error("Solo se pueden modificar reservas pendientes o confirmadas que aun no han ocurrido.")
        consola.pausa()
        return

    _resumen(reserva)
    inicio = reserva["fecha_hora_inicio"]
    personas = reserva["num_personas"]
    if consola.confirmar("Cambiar fecha y hora?"):
        inicio = _pedir_inicio()
    if consola.confirmar("Cambiar numero de personas?"):
        personas = _pedir_personas(reserva["sucursal_id"])

    mesas = _mesas_disponibles(reserva["sucursal_id"], inicio, personas, reserva["reserva_id"])
    if not mesas:
        consola.aviso("No hay mesas disponibles con esos datos.")
        _sugerir_horarios(reserva["sucursal_id"], inicio, personas, reserva["reserva_id"])
        consola.pausa()
        return
    mesa_id = _elegir_mesa(mesas, reserva["mesa_id"])

    if (inicio, personas, mesa_id) == (reserva["fecha_hora_inicio"], reserva["num_personas"], reserva["mesa_id"]):
        consola.aviso("No hay cambios que guardar.")
        consola.pausa()
        return

    try:
        db.ejecutar("""
            update reserva
            set mesa_id = %s, fecha_hora_inicio = %s, fecha_hora_fin = %s, num_personas = %s
            where reserva_id = %s
        """, (mesa_id, inicio, inicio + DURACION, personas, reserva["reserva_id"]))
    except psycopg2.Error as e:
        consola.error(_mensaje_error(e))
    else:
        consola.exito(f"Reserva #{reserva['reserva_id']} actualizada.")
    consola.pausa()


def cambiar_estado():
    consola.titulo("CONFIRMAR O CANCELAR RESERVA")
    if not _listar_activas():
        consola.pausa()
        return
    reserva = _pedir_reserva("Id de la reserva")
    if reserva is None:
        return
    _resumen(reserva)

    if reserva["estado"] == "pendiente":
        acciones = [("Confirmar reserva", "confirmada"), ("Cancelar reserva", "cancelada")]
    elif reserva["estado"] == "confirmada":
        acciones = [("Cancelar reserva", "cancelada")]
    else:
        consola.error(f"Una reserva {reserva['estado']} ya no se puede cambiar.")
        consola.pausa()
        return

    eleccion = consola.menu(f"Reserva #{reserva['reserva_id']} ({reserva['estado']})",
                            [a[0] for a in acciones])
    if eleccion == 0:
        return
    nuevo_estado = acciones[eleccion - 1][1]
    if nuevo_estado == "cancelada" and not consola.confirmar("Seguro que quieres cancelar la reserva?"):
        return

    db.ejecutar("update reserva set estado = %s where reserva_id = %s",
                (nuevo_estado, reserva["reserva_id"]))
    consola.exito(f"Reserva #{reserva['reserva_id']} ahora esta {nuevo_estado}.")
    consola.pausa()


def menu_reservas():
    acciones = [nueva_reserva, ver_disponibilidad, buscar_reservas, ver_historial_reservas,
                modificar_reserva, cambiar_estado]
    while True:
        eleccion = consola.menu("RESERVAS", [
            "Nueva reserva",
            "Ver disponibilidad de mesas",
            "Buscar reservas (con filtros)",
            "Historial de reservas de la sucursal",
            "Modificar reserva",
            "Confirmar o cancelar reserva",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()