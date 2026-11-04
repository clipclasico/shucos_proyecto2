
usuario_id = None
username = None
rol = None
empleado_id = None
sucursal_id = None


def iniciar(p_usuario_id, p_username, p_rol, p_empleado_id=None, p_sucursal_id=None):
    global usuario_id, username, rol, empleado_id, sucursal_id
    usuario_id = p_usuario_id
    username = p_username
    rol = p_rol
    empleado_id = p_empleado_id
    sucursal_id = p_sucursal_id


def cerrar():
    iniciar(None, None, None, None, None)


def activa():
    return usuario_id is not None


def tiene_rol(*roles):
    return rol in roles
