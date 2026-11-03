from app import auth, consola, db, sesion, sucursales

CARGOS = {1: "mesero", 2: "chef", 3: "gerente", 4: "administrador"}


def _listar():
    filas = db.consultar("""
        select e.empleado_id as id, e.nombre, e.cargo, s.nombre as sucursal,
               coalesce(u.username, '-') as usuario,
               case when e.activo then 'activo' else 'baja' end as estado
        from empleado e
        join sucursal s on s.sucursal_id = e.sucursal_id
        left join usuario u on u.empleado_id = e.empleado_id
        order by s.sucursal_id, e.cargo, e.nombre
    """)
    consola.mostrar_tabla(filas, "No hay empleados registrados.")
    return filas


def ver_empleados():
    consola.titulo("EMPLEADOS")
    _listar()
    consola.pausa()


def registrar_empleado():
    consola.titulo("REGISTRAR EMPLEADO")
    nombre = consola.pedir_texto("Nombre completo", max_len=100)

    eleccion = consola.menu("CARGO", [c.capitalize() for c in CARGOS.values()], texto_salida="Cancelar")
    if eleccion == 0:
        return
    cargo = CARGOS[eleccion]

    sucursal_id = sucursales.elegir()
    if sucursal_id is None:
        return
    telefono = consola.pedir_telefono("Telefono (Enter para omitir)")

    with db.transaccion() as cur:
        cur.execute("""
            insert into empleado (sucursal_id, nombre, cargo, telefono)
            values (%s, %s, %s, %s)
            returning empleado_id
        """, (sucursal_id, nombre, cargo, telefono))
        empleado_id = cur.fetchone()["empleado_id"]
    consola.exito(f"Empleado #{empleado_id} registrado como {cargo}.")

    if cargo == "chef":
        consola.aviso("Los chefs no tienen cuenta de acceso.")
    elif consola.confirmar("Crear su cuenta de acceso ahora?"):
        auth.crear_cuenta(empleado_id, nombre, cargo)
    consola.pausa()


def crear_cuenta_a_existente():
    auth.registrar()


def baja_o_reactivar():
    consola.titulo("DAR DE BAJA O REACTIVAR UN EMPLEADO")
    filas = _listar()
    por_id = {f["id"]: f for f in filas}
    while True:
        empleado_id = consola.pedir_entero("Id del empleado (0 para cancelar)", minimo=0)
        if empleado_id == 0:
            return
        if empleado_id in por_id:
            break
        consola.error("Ese id no esta en la lista.")

    empleado = por_id[empleado_id]
    if empleado_id == sesion.empleado_id:
        consola.error("No puedes darte de baja a ti mismo.")
        consola.pausa()
        return

    dar_de_baja = empleado["estado"] == "activo"
    if dar_de_baja:
        pregunta = f"Dar de baja a {empleado['nombre']}? Su cuenta tambien se desactiva."
    else:
        pregunta = f"Reactivar a {empleado['nombre']} (y su cuenta, si tiene)?"
    if not consola.confirmar(pregunta):
        return

    with db.transaccion() as cur:
        cur.execute("update empleado set activo = %s where empleado_id = %s", (not dar_de_baja, empleado_id))
        cur.execute("update usuario set activo = %s where empleado_id = %s", (not dar_de_baja, empleado_id))
    consola.exito(f"{empleado['nombre']} esta ahora de {'baja' if dar_de_baja else 'alta'}.")
    consola.pausa()


def menu_empleados():
    acciones = [ver_empleados, registrar_empleado, crear_cuenta_a_existente, baja_o_reactivar]
    while True:
        eleccion = consola.menu("EMPLEADOS Y USUARIOS", [
            "Ver empleados",
            "Registrar empleado (con su cuenta)",
            "Crear cuenta a un empleado existente",
            "Dar de baja o reactivar un empleado",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()