from datetime import date, datetime

from app import consola, db


def _pedir_sucursal():
    lista = db.consultar("select sucursal_id as id, nombre from sucursal where activa order by sucursal_id")
    consola.mostrar_tabla(lista)
    ids = {s["id"] for s in lista}
    while True:
        elegida = consola.pedir_entero("Id de la sucursal (Enter = todas)", obligatorio=False)
        if elegida is None or elegida in ids:
            return elegida
        consola.error("Ese id no esta en la lista.")


def _pedir_periodo():
    while True:
        desde = consola.pedir_fecha("Desde (Enter = sin limite)", obligatorio=False)
        hasta = consola.pedir_fecha("Hasta (Enter = sin limite)", obligatorio=False)
        if desde and hasta and desde > hasta:
            consola.error("La fecha inicial no puede ser mayor que la final.")
            continue
        return desde, hasta


def _pedir_mes():
    while True:
        texto = consola.pedir_texto("Mes (AAAA-MM, Enter = mes actual)", obligatorio=False)
        if texto is None:
            return date.today().replace(day=1)
        try:
            return datetime.strptime(texto + "-01", "%Y-%m-%d").date()
        except ValueError:
            consola.error("Formato invalido. Ejemplo: 2026-11")


def top_platos():
    consola.titulo("TOP 10 DE PLATOS MAS VENDIDOS")
    sucursal = _pedir_sucursal()
    desde, hasta = _pedir_periodo()
    filas = db.consultar("""
        with ventas as (
            select pl.nombre as plato,
                   sum(d.cantidad) as unidades,
                   sum(d.cantidad * d.precio_unitario) as ingresos
            from detalle_pedido d
            join pedido p on p.pedido_id = d.pedido_id
            join plato pl on pl.plato_id = d.plato_id
            where p.estado = 'pagado'
              and (%(sucursal)s::int is null or p.sucursal_id = %(sucursal)s::int)
              and (%(desde)s::date is null or p.fecha_hora::date >= %(desde)s::date)
              and (%(hasta)s::date is null or p.fecha_hora::date <= %(hasta)s::date)
            group by pl.plato_id, pl.nombre
        )
        select rank() over (order by unidades desc) as puesto,
               plato,
               unidades,
               to_char(ingresos, '"Q"FM999,990.00') as ingresos,
               round(unidades * 100.0 / sum(unidades) over (), 1) as pct_unidades
        from ventas
        order by unidades desc, plato
        limit 10
    """, {"sucursal": sucursal, "desde": desde, "hasta": hasta})
    consola.mostrar_tabla(filas, "No hay ventas en ese periodo.")
    consola.pausa()


def top_clientes_frecuentes():
    consola.titulo("TOP 10 DE CLIENTES MAS FRECUENTES")
    desde, hasta = _pedir_periodo()
    filas = db.consultar("""
        with visitas as (
            select p.cliente_id, count(*) as visitas,
                   sum(t.total) as gastado, max(p.fecha_hora) as ultima
            from pedido p
            join v_pedido_total t on t.pedido_id = p.pedido_id
            where p.estado = 'pagado'
              and p.cliente_id is not null
              and (%(desde)s::date is null or p.fecha_hora::date >= %(desde)s::date)
              and (%(hasta)s::date is null or p.fecha_hora::date <= %(hasta)s::date)
            group by p.cliente_id
        )
        select rank() over (order by v.visitas desc, v.gastado desc) as puesto,
               c.nombre as cliente,
               v.visitas,
               to_char(v.gastado, '"Q"FM999,990.00') as gastado,
               to_char(v.ultima, 'YYYY-MM-DD') as ultima_visita
        from visitas v
        join cliente c on c.cliente_id = v.cliente_id
        order by v.visitas desc, v.gastado desc
        limit 10
    """, {"desde": desde, "hasta": hasta})
    consola.mostrar_tabla(filas, "No hay visitas de clientes en ese periodo.")
    consola.pausa()


def top_clientes_reservas():
    consola.titulo("TOP 5 DE CLIENTES CON MAS RESERVAS")
    desde, hasta = _pedir_periodo()
    filas = db.consultar("""
        with top_clientes as (
            select c.cliente_id, c.nombre,
                   count(*) filter (where r.estado <> 'cancelada') as reservas,
                   count(*) filter (where r.estado = 'cancelada') as canceladas
            from cliente c
            join reserva r on r.cliente_id = c.cliente_id
            where (%(desde)s::date is null or r.fecha_hora_inicio::date >= %(desde)s::date)
              and (%(hasta)s::date is null or r.fecha_hora_inicio::date <= %(hasta)s::date)
            group by c.cliente_id, c.nombre
            order by reservas desc, c.nombre
            limit 5
        )
        select rank() over (order by t.reservas desc) as puesto,
               t.nombre as cliente, t.reservas, t.canceladas,
               coalesce(string_agg(p.plato || ' (' || p.veces || ')', ', ' order by p.posicion),
                        'sin pedidos todavia') as platos_favoritos
        from top_clientes t
        left join v_preferencia_calculada p
            on p.cliente_id = t.cliente_id and p.posicion <= 3
        group by t.cliente_id, t.nombre, t.reservas, t.canceladas
        order by t.reservas desc, t.nombre
    """, {"desde": desde, "hasta": hasta})
    consola.mostrar_tabla(filas, "No hay reservas en ese periodo.")
    print("Reservas = sin contar las canceladas. Platos favoritos = los 3 mas pedidos (veces).")
    consola.pausa()


def insumos_mensual():
    consola.titulo("REPORTE MENSUAL DE INSUMOS")
    sucursal = _pedir_sucursal()
    mes = _pedir_mes()
    params = {"sucursal": sucursal, "mes": mes}

    print(f"\nLOTES CON EXISTENCIAS QUE CADUCAN EN {mes:%Y-%m}:")
    caducan = db.consultar("""
        with mes as (
            select %(mes)s::date as inicio,
                   (%(mes)s::date + interval '1 month')::date as fin
        )
        select s.nombre as sucursal, g.nombre as ingrediente, l.lote_id as lote,
               l.cantidad_actual as cantidad, g.unidad_medida as unidad,
               to_char(l.fecha_caducidad, 'YYYY-MM-DD') as caduca,
               case when l.fecha_caducidad < current_date then 'vencido' else 'por caducar' end as situacion
        from lote_inventario l
        join ingrediente g on g.ingrediente_id = l.ingrediente_id
        join sucursal s    on s.sucursal_id = l.sucursal_id
        cross join mes
        where l.cantidad_actual > 0
          and l.fecha_caducidad >= mes.inicio
          and l.fecha_caducidad < mes.fin
          and (%(sucursal)s::int is null or l.sucursal_id = %(sucursal)s::int)
        order by l.fecha_caducidad, s.nombre, g.nombre
    """, params)
    consola.mostrar_tabla(caducan, "Ningun lote con existencias caduca en ese mes.")

    print("\nINGREDIENTES POR TERMINARSE (estado actual, <= 15% de la capacidad):")
    bajos = db.consultar("""
        select sucursal, ingrediente, unidad_medida as unidad, existencias,
               capacidad_maxima as capacidad, porcentaje
        from v_alerta_inventario
        where %(sucursal)s::int is null or sucursal_id = %(sucursal)s::int
        order by porcentaje, sucursal, ingrediente
    """, params)
    consola.mostrar_tabla(bajos, "Ningun ingrediente esta por terminarse.")
    consola.pausa()


def comportamiento_sucursales():
    consola.titulo("COMPORTAMIENTO DE SUCURSALES")
    desde, hasta = _pedir_periodo()
    filas = db.consultar("""
        with res as (
            select sucursal_id,
                   count(*) filter (where estado <> 'cancelada') as reservas,
                   count(*) filter (where estado = 'cancelada') as canceladas
            from reserva
            where (%(desde)s::date is null or fecha_hora_inicio::date >= %(desde)s::date)
              and (%(hasta)s::date is null or fecha_hora_inicio::date <= %(hasta)s::date)
            group by sucursal_id
        ),
        ven as (
            select p.sucursal_id, count(*) as pedidos, sum(t.total) as ventas,
                   round(avg(t.total), 2) as ticket_promedio,
                   round(avg(p.calificacion), 1) as calificacion
            from pedido p
            join v_pedido_total t on t.pedido_id = p.pedido_id
            where p.estado = 'pagado'
              and (%(desde)s::date is null or p.fecha_hora::date >= %(desde)s::date)
              and (%(hasta)s::date is null or p.fecha_hora::date <= %(hasta)s::date)
            group by p.sucursal_id
        )
        select s.nombre as sucursal,
               coalesce(r.reservas, 0) as reservas,
               coalesce(r.canceladas, 0) as canceladas,
               coalesce(v.pedidos, 0) as pedidos,
               to_char(coalesce(v.ventas, 0), '"Q"FM999,990.00') as ventas,
               to_char(coalesce(v.ticket_promedio, 0), '"Q"FM999,990.00') as ticket_promedio,
               v.calificacion,
               rank() over (order by coalesce(r.reservas, 0) desc) as puesto_reservas,
               rank() over (order by coalesce(v.ventas, 0) desc) as puesto_ventas
        from sucursal s
        left join res r on r.sucursal_id = s.sucursal_id
        left join ven v on v.sucursal_id = s.sucursal_id
        order by coalesce(v.ventas, 0) desc, s.nombre
    """, {"desde": desde, "hasta": hasta})
    consola.mostrar_tabla(filas, "No hay datos en ese periodo.")
    print("Reservas = sin contar las canceladas. Ventas = pedidos pagados. Ticket = venta promedio por pedido.")
    consola.pausa()


def menu_reportes():
    acciones = [top_platos, top_clientes_frecuentes, top_clientes_reservas,
                insumos_mensual, comportamiento_sucursales]
    while True:
        eleccion = consola.menu("REPORTES", [
            "Top 10 de platos mas vendidos",
            "Top 10 de clientes mas frecuentes",
            "Top 5 de clientes con mas reservas y sus platos favoritos",
            "Reporte mensual de insumos por terminarse o caducar",
            "Comportamiento de sucursales (reservas y ventas)",
        ])
        if eleccion == 0:
            return
        acciones[eleccion - 1]()