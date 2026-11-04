
from datetime import date
from app import consola, db, sesion, sucursales


def _es_admin():
    return sesion.tiene_rol("administrador")


def _filtro_sucursal():
    if _es_admin():
        return "", []
    return "where sucursal_id = %s", [sesion.sucursal_id]


def _banner():
    donde, params = _filtro_sucursal()
    bajos = db.consultar(f"select count(*) as n from v_alerta_inventario {donde}", params)[0]["n"]
    caducan = db.consultar(f"select count(*) as n from v_alerta_caducidad {donde}", params)[0]["n"]
    print()
    if bajos or caducan:
        consola.aviso(f"ALERTAS: {bajos} ingrediente(s) por terminarse | "
                      f"{caducan} lote(s) por caducar o vencidos")
    else:
        consola.exito("Sin alertas de inventario.")


def _buscar(sucursal_id, texto):
    return db.consultar("""
        select g.ingrediente_id as id, g.nombre as ingrediente, g.unidad_medida as unidad,
               e.existencias, e.capacidad_maxima as capacidad,
               round(e.existencias / e.capacidad_maxima * 100, 1) as porcentaje,
               case when e.existencias <= e.stock_minimo then 'POR TERMINARSE' else 'ok' end as estado,
               g.perecedero
        from v_existencias e
        join ingrediente g on g.ingrediente_id = e.ingrediente_id
        where e.sucursal_id = %s and g.nombre ilike %s
        order by e.existencias / e.capacidad_maxima, g.nombre
    """, (sucursal_id, f"%{texto or ''}%"))


def _mostrar_ingredientes(filas):
    consola.mostrar_tabla([{k: v for k, v in f.items() if k != "perecedero"} for f in filas],
                          "No se encontraron ingredientes.")


def _elegir_ingrediente(sucursal_id):
    while True:
        texto = consola.pedir_texto("Buscar ingrediente (Enter = todos, 0 para cancelar)", obligatorio=False)
        if texto == "0":
            return None
        filas = _buscar(sucursal_id, texto)
        if not filas:
            consola.error("No se encontraron ingredientes.")
            continue
        _mostrar_ingredientes(filas)
        por_id = {f["id"]: f for f in filas}
        elegido = consola.pedir_entero("Id del ingrediente (0 para buscar de nuevo)", minimo=0)
        if elegido == 0:
            continue
        if elegido in por_id:
            return por_id[elegido]
        consola.error("Ese id no esta en la lista.")


def _lotes(sucursal_id, ingrediente_id):
    return db.consultar("""
        select l.lote_id as lote,
               to_char(l.fecha_ingreso, 'YYYY-MM-DD') as ingreso,
               coalesce(to_char(l.fecha_caducidad, 'YYYY-MM-DD'), 'sin caducidad') as caduca,
               l.cantidad_inicial as inicial, l.cantidad_actual as actual,
               case when l.cantidad_actual = 0 then 'agotado'
                    when l.fecha_caducidad < current_date then 'VENCIDO'
                    when l.fecha_caducidad <= current_date + 3 then 'por caducar'
                    else 'ok' end as estado
        from lote_inventario l
        where l.sucursal_id = %s and l.ingrediente_id = %s
        order by l.fecha_caducidad nulls last, l.lote_id
    """, (sucursal_id, ingrediente_id))


def ver_existencias():
    consola.titulo("EXISTENCIAS")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    texto = consola.pedir_texto("Buscar ingrediente (Enter = todos)", obligatorio=False)
    _mostrar_ingredientes(_buscar(sucursal_id, texto))
    consola.pausa()


def ver_alertas():
    consola.titulo("ALERTAS DE INVENTARIO")
    donde, params = _filtro_sucursal()

    print("\nPOR TERMINARSE (existencias <= 15% de la capacidad maxima):")
    bajos = db.consultar(f"""
        select sucursal, ingrediente, unidad_medida as unidad, existencias,
               capacidad_maxima as capacidad, porcentaje
        from v_alerta_inventario {donde}
        order by porcentaje, sucursal, ingrediente
    """, params)
    consola.mostrar_tabla(bajos, "Ningun ingrediente esta por terminarse.")

    print("\nPOR CADUCAR O VENCIDOS (proximos 3 dias):")
    caducan = db.consultar(f"""
        select sucursal, ingrediente, lote_id as lote, cantidad_actual as cantidad,
               unidad_medida as unidad, to_char(fecha_caducidad, 'YYYY-MM-DD') as caduca,
               dias_restantes as dias, situacion
        from v_alerta_caducidad {donde}
        order by fecha_caducidad, sucursal, ingrediente
    """, params)
    consola.mostrar_tabla(caducan, "Ningun lote esta por caducar.")
    consola.pausa()


def ver_lotes():
    consola.titulo("LOTES DE UN INGREDIENTE")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    ingrediente = _elegir_ingrediente(sucursal_id)
    if ingrediente is None:
        return
    print(f"\nLotes de {ingrediente['ingrediente']} ({ingrediente['unidad']}):")
    consola.mostrar_tabla(_lotes(sucursal_id, ingrediente["id"]), "Este ingrediente no tiene lotes.")
    consola.pausa()


def registrar_ingreso():
    consola.titulo("REGISTRAR INGRESO DE LOTE")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    ingrediente = _elegir_ingrediente(sucursal_id)
    if ingrediente is None:
        return

    disponible = ingrediente["capacidad"] - ingrediente["existencias"]
    if disponible <= 0:
        consola.error("Ese ingrediente ya esta en su capacidad maxima.")
        consola.pausa()
        return
    consola.aviso(f"Se pueden ingresar hasta {float(disponible):g} {ingrediente['unidad']}.")

    while True:
        cantidad = consola.pedir_entero(f"Cantidad a ingresar ({ingrediente['unidad']})", minimo=1)
        if cantidad <= disponible:
            break
        consola.error(f"Eso supera la capacidad maxima. Maximo: {float(disponible):g}.")

    while True:
        texto = "Fecha de caducidad" if ingrediente["perecedero"] else "Fecha de caducidad (Enter si no caduca)"
        caducidad = consola.pedir_fecha(texto, obligatorio=ingrediente["perecedero"])
        if caducidad is None or caducidad >= date.today():
            break
        consola.error("La fecha de caducidad no puede ser anterior a hoy.")

    with db.transaccion() as cur:
        cur.execute("""
            insert into lote_inventario (sucursal_id, ingrediente_id, cantidad_inicial,
                                         cantidad_actual, fecha_caducidad)
            values (%s, %s, %s, %s, %s)
            returning lote_id
        """, (sucursal_id, ingrediente["id"], cantidad, cantidad, caducidad))
        lote_id = cur.fetchone()["lote_id"]
    consola.exito(f"Lote #{lote_id} registrado: {cantidad} {ingrediente['unidad']} de {ingrediente['ingrediente']}.")
    consola.pausa()


def ajustar_lote():
    consola.titulo("AJUSTAR O DAR DE BAJA UN LOTE")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    ingrediente = _elegir_ingrediente(sucursal_id)
    if ingrediente is None:
        return

    lotes = _lotes(sucursal_id, ingrediente["id"])
    if not lotes:
        consola.aviso("Este ingrediente no tiene lotes.")
        consola.pausa()
        return
    consola.mostrar_tabla(lotes)
    por_id = {l["lote"]: l for l in lotes}
    while True:
        lote_id = consola.pedir_entero("Id del lote (0 para cancelar)", minimo=0)
        if lote_id == 0:
            return
        if lote_id in por_id:
            break
        consola.error("Ese lote no esta en la lista.")

    lote = por_id[lote_id]
    nueva = consola.pedir_entero(f"Nueva cantidad (0 = dar de baja; maximo {int(lote['inicial'])})",
                                 minimo=0, maximo=int(lote["inicial"]))
    if not consola.confirmar(f"Cambiar el lote #{lote_id} de {lote['actual']} a {nueva}?"):
        return
    db.ejecutar("update lote_inventario set cantidad_actual = %s where lote_id = %s", (nueva, lote_id))
    consola.exito(f"Lote #{lote_id} actualizado.")
    consola.pausa()


def configurar_capacidad():
    consola.titulo("CAPACIDAD MAXIMA")
    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    ingrediente = _elegir_ingrediente(sucursal_id)
    if ingrediente is None:
        return

    print(f"\n{ingrediente['ingrediente']}: capacidad actual {ingrediente['capacidad']} "
          f"{ingrediente['unidad']} | existencias {ingrediente['existencias']} | "
          f"alerta cuando baje de {float(ingrediente['capacidad']) * 0.15:g}")
    nueva = consola.pedir_entero("Nueva capacidad maxima (0 para cancelar)", minimo=0)
    if nueva == 0:
        return
    if nueva < ingrediente["existencias"]:
        consola.error("La capacidad no puede ser menor que las existencias actuales.")
        consola.pausa()
        return
    db.ejecutar("update inventario set capacidad_maxima = %s where sucursal_id = %s and ingrediente_id = %s",
                (nueva, sucursal_id, ingrediente["id"]))
    consola.exito(f"Capacidad actualizada. Nueva alerta: {nueva * 0.15:g} {ingrediente['unidad']}.")
    consola.pausa()


def menu_inventario():
    acciones = [ver_existencias, ver_alertas, ver_lotes, registrar_ingreso, ajustar_lote, configurar_capacidad]
    while True:
        _banner()
        eleccion = consola.menu("INVENTARIO", [
            "Ver existencias (buscar ingrediente)",
            "Alertas: por terminarse y por caducar",
            "Ver lotes de un ingrediente",
            "Registrar ingreso de lote",
            "Ajustar o dar de baja un lote",
            "Configurar capacidad maxima",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()

