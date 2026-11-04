import bcrypt
from psycopg2 import errors

from app import consola, db, sesion

MAX_INTENTOS = 3


def _hashear(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verificar(password, hash_guardado):
    return bcrypt.checkpw(password.encode(), hash_guardado.encode())


def registrar():
    
    consola.titulo("REGISTRO DE USUARIO")

    elegibles = db.consultar("""
        select e.empleado_id as id, e.nombre, e.cargo, s.nombre as sucursal
        from empleado e
        join sucursal s on s.sucursal_id = e.sucursal_id
        left join usuario u on u.empleado_id = e.empleado_id
        where u.usuario_id is null
          and e.activo
          and e.cargo in ('mesero', 'gerente', 'administrador')
        order by e.empleado_id
    """)
    if not elegibles:
        consola.aviso("No hay empleados pendientes de registro.")
        consola.pausa()
        return

    print("Empleados sin cuenta:")
    consola.mostrar_tabla(elegibles)
    ids = {f["id"] for f in elegibles}

    while True:
        empleado_id = consola.pedir_entero("Id del empleado (0 para cancelar)", minimo=0)
        if empleado_id == 0:
            return
        if empleado_id in ids:
            break
        consola.error("Ese id no esta en la lista.")
    empleado = next(f for f in elegibles if f["id"] == empleado_id)

    crear_cuenta(empleado_id, empleado["nombre"], empleado["cargo"])
    consola.pausa()


def crear_cuenta(empleado_id, nombre, cargo):
   
    while True:
        username = consola.pedir_texto("Nombre de usuario", max_len=40).lower()
        if db.consultar("select 1 from usuario where username = %s", (username,)):
            consola.error("Ese nombre de usuario ya existe.")
            continue
        break

    while True:
        password = consola.pedir_password("Contrasena")
        if not password:
            consola.error("La contrasena no puede estar vacia.")
            continue
        if password != consola.pedir_password("Repite la contrasena"):
            consola.error("Las contrasenas no coinciden.")
            continue
        break

    try:
        db.ejecutar(
            "insert into usuario (empleado_id, username, password_hash, rol) values (%s, %s, %s, %s)",
            (empleado_id, username, _hashear(password), cargo),
        )
    except errors.UniqueViolation:
        consola.error("Ese empleado o ese usuario ya tiene cuenta.")
        return False
    consola.exito(f"Cuenta creada para {nombre} con rol {cargo}.")
    return True


def login():
    consola.titulo("INICIAR SESION")

    for _ in range(MAX_INTENTOS):
        username = consola.pedir_texto("Usuario").lower()
        password = consola.pedir_password()

        filas = db.consultar("""
            select u.usuario_id, u.username, u.password_hash, u.rol, u.activo,
                   e.empleado_id, e.nombre, e.sucursal_id, s.nombre as sucursal
            from usuario u
            join empleado e on e.empleado_id = u.empleado_id
            join sucursal s on s.sucursal_id = e.sucursal_id
            where u.username = %s
        """, (username,))
        u = filas[0] if filas else None

        if u and u["activo"] and _verificar(password, u["password_hash"]):
            sesion.iniciar(u["usuario_id"], u["username"], u["rol"], u["empleado_id"], u["sucursal_id"])
            consola.exito(f"Bienvenido, {u['nombre']} ({u['rol']}) - sucursal {u['sucursal']}")
            return True

        consola.error("Usuario o contrasena incorrectos.")

    consola.aviso("Demasiados intentos. Volviendo al menu inicial.")
    return False
