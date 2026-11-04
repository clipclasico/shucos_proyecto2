import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from app import sesion

load_dotenv()


def conectar():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "shucos_el_sapo"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
    except UnicodeDecodeError as e:
        crudo = e.object if isinstance(e.object, bytes) else b""
        mensaje = crudo.decode("cp1252", errors="replace").strip() or "usuario, contrasena, puerto o base incorrectos"
        raise ConnectionError(mensaje) from None


@contextmanager
def transaccion():
    conn = conectar()
    try:
        with conn: 
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if sesion.usuario_id is not None:
                    cur.execute("select set_config('app.usuario_id', %s, true)",
                                (str(sesion.usuario_id),))
                yield cur
    finally:
        conn.close()


def consultar(sql, params=None):
    with transaccion() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def ejecutar(sql, params=None):
    with transaccion() as cur:
        cur.execute(sql, params)
        return cur.rowcount
