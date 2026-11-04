create or replace function fn_bitacora()
returns trigger
language plpgsql
as $$
declare
    v_usuario  integer;
    v_antes    jsonb;
    v_despues  jsonb;
    v_id       text;
    i          integer;
begin
    v_usuario := nullif(current_setting('app.usuario_id', true), '')::integer;

    if tg_op in ('UPDATE', 'DELETE') then
        v_antes := to_jsonb(old);
    end if;
    if tg_op in ('INSERT', 'UPDATE') then
        v_despues := to_jsonb(new);
    end if;

    for i in 0 .. tg_nargs - 1 loop
        v_id := concat_ws('-', v_id, coalesce(v_despues, v_antes) ->> tg_argv[i]);
    end loop;

    insert into bitacora (usuario_id, tabla, registro_id, operacion, datos_antes, datos_despues)
    values (v_usuario, tg_table_name, v_id, tg_op, v_antes, v_despues);

    return null;
end;
$$;

create trigger trg_bitacora_reserva
    after insert or update or delete on reserva
    for each row execute function fn_bitacora('reserva_id');

create trigger trg_bitacora_pedido
    after insert or update or delete on pedido
    for each row execute function fn_bitacora('pedido_id');

create trigger trg_bitacora_detalle_pedido
    after insert or update or delete on detalle_pedido
    for each row execute function fn_bitacora('pedido_id', 'plato_id');

create trigger trg_bitacora_inventario
    after insert or update or delete on inventario
    for each row execute function fn_bitacora('sucursal_id', 'ingrediente_id');

create trigger trg_bitacora_lote_inventario
    after insert or update or delete on lote_inventario
    for each row execute function fn_bitacora('lote_id');

create trigger trg_bitacora_cliente
    after insert or update or delete on cliente
    for each row execute function fn_bitacora('cliente_id');

create trigger trg_bitacora_preferencia_cliente
    after insert or update or delete on preferencia_cliente
    for each row execute function fn_bitacora('preferencia_id');

create trigger trg_bitacora_plato
    after insert or update or delete on plato
    for each row execute function fn_bitacora('plato_id');

create or replace function fn_reserva_capacidad()
returns trigger
language plpgsql
as $$
declare
    v_capacidad integer;
begin
    select capacidad into v_capacidad from mesa where mesa_id = new.mesa_id;

    if new.num_personas > v_capacidad then
        raise exception 'La mesa % tiene capacidad para % personas y la reserva es para %',
            new.mesa_id, v_capacidad, new.num_personas;
    end if;
    return new;
end;
$$;

create trigger trg_reserva_capacidad
    before insert or update of mesa_id, num_personas on reserva
    for each row execute function fn_reserva_capacidad();

create or replace function fn_pedido_empleado_mesero()
returns trigger
language plpgsql
as $$
declare
    v_cargo varchar(20);
begin
    select cargo into v_cargo from empleado where empleado_id = new.empleado_id;

    if v_cargo is distinct from 'mesero' then
        raise exception 'El empleado % no es mesero y no puede atender pedidos', new.empleado_id;
    end if;
    return new;
end;
$$;

create trigger trg_pedido_empleado_mesero
    before insert or update of empleado_id on pedido
    for each row execute function fn_pedido_empleado_mesero();

create or replace function fn_pedido_validar()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'DELETE' then
        if old.estado <> 'abierto' then
            raise exception 'No se puede eliminar un pedido % (pedido %)', old.estado, old.pedido_id;
        end if;
        return old;
    end if;

    if old.estado <> 'abierto' then
        if new.estado <> old.estado then
            raise exception 'Un pedido % no puede cambiar de estado (pedido %)', old.estado, old.pedido_id;
        end if;
        if (new.sucursal_id, new.mesa_id, new.cliente_id, new.empleado_id, new.reserva_id, new.fecha_hora)
           is distinct from
           (old.sucursal_id, old.mesa_id, old.cliente_id, old.empleado_id, old.reserva_id, old.fecha_hora) then
            raise exception 'Un pedido % solo permite editar observaciones y calificacion (pedido %)',
                old.estado, old.pedido_id;
        end if;
    elsif new.estado = 'pagado' then
        if not exists (select 1 from detalle_pedido where pedido_id = new.pedido_id) then
            raise exception 'No se puede pagar un pedido sin platos (pedido %)', new.pedido_id;
        end if;
    end if;

    return new;
end;
$$;

create trigger trg_pedido_validar
    before update or delete on pedido
    for each row execute function fn_pedido_validar();

create or replace function fn_detalle_solo_abierto()
returns trigger
language plpgsql
as $$
declare
    v_pedido integer;
    v_estado varchar(10);
begin
    if tg_op = 'UPDATE' and new.pedido_id <> old.pedido_id then
        raise exception 'No se puede mover un detalle del pedido % a otro pedido', old.pedido_id;
    end if;

    v_pedido := case when tg_op = 'DELETE' then old.pedido_id else new.pedido_id end;

    select estado into v_estado from pedido where pedido_id = v_pedido for share;

    if v_estado <> 'abierto' then
        raise exception 'El pedido % esta % y no admite cambios en sus platos', v_pedido, v_estado;
    end if;

    return case when tg_op = 'DELETE' then old else new end;
end;
$$;

create trigger trg_detalle_solo_abierto
    before insert or update or delete on detalle_pedido
    for each row execute function fn_detalle_solo_abierto();

create or replace function fn_pedido_pagado()
returns trigger
language plpgsql
as $$
declare
    r           record;
    l           record;
    v_pendiente numeric;
    v_tomar     numeric;
    v_nombre    varchar(60);
begin
    if new.reserva_id is not null then
        update reserva set estado = 'cumplida' where reserva_id = new.reserva_id;
    end if;

    for r in
        select rc.ingrediente_id, sum(rc.cantidad * d.cantidad) as requerido
        from detalle_pedido d
        join receta rc on rc.plato_id = d.plato_id
        where d.pedido_id = new.pedido_id
        group by rc.ingrediente_id
        order by rc.ingrediente_id
    loop
        v_pendiente := r.requerido;

        for l in
            select lote_id, cantidad_actual
            from lote_inventario
            where sucursal_id = new.sucursal_id
              and ingrediente_id = r.ingrediente_id
              and cantidad_actual > 0
              and (fecha_caducidad is null or fecha_caducidad >= current_date)
            order by fecha_caducidad nulls last, lote_id
            for update
        loop
            exit when v_pendiente <= 0;
            v_tomar := least(l.cantidad_actual, v_pendiente);

            update lote_inventario
            set cantidad_actual = cantidad_actual - v_tomar
            where lote_id = l.lote_id;

            v_pendiente := v_pendiente - v_tomar;
        end loop;

        if v_pendiente > 0 then
            select nombre into v_nombre from ingrediente where ingrediente_id = r.ingrediente_id;
            raise exception 'Existencias insuficientes de % en la sucursal % (faltan %)',
                v_nombre, new.sucursal_id, v_pendiente;
        end if;
    end loop;

    return null;
end;
$$;

create trigger trg_pedido_pagado
    after update of estado on pedido
    for each row
    when (old.estado = 'abierto' and new.estado = 'pagado')
    execute function fn_pedido_pagado();

create or replace view v_pedido_total as
select p.pedido_id, p.sucursal_id, p.cliente_id, p.mesa_id, p.empleado_id,
       p.fecha_hora, p.estado,
       coalesce(sum(d.cantidad * d.precio_unitario), 0) as total
from pedido p
left join detalle_pedido d on d.pedido_id = p.pedido_id
group by p.pedido_id;

create or replace view v_existencias as
select i.sucursal_id, i.ingrediente_id,
       coalesce(sum(l.cantidad_actual) filter (
           where l.fecha_caducidad is null or l.fecha_caducidad >= current_date
       ), 0) as existencias,
       i.capacidad_maxima,
       i.stock_minimo
from inventario i
left join lote_inventario l
       on l.sucursal_id = i.sucursal_id and l.ingrediente_id = i.ingrediente_id
group by i.sucursal_id, i.ingrediente_id, i.capacidad_maxima, i.stock_minimo;

create or replace view v_alerta_inventario as
select s.nombre as sucursal, g.nombre as ingrediente, g.unidad_medida,
       e.sucursal_id, e.ingrediente_id,
       e.existencias, e.capacidad_maxima,
       round(e.existencias / e.capacidad_maxima * 100, 1) as porcentaje
from v_existencias e
join sucursal s    on s.sucursal_id = e.sucursal_id
join ingrediente g on g.ingrediente_id = e.ingrediente_id
where e.existencias <= e.stock_minimo;

create or replace view v_alerta_caducidad as
select s.nombre as sucursal, g.nombre as ingrediente, g.unidad_medida,
       l.sucursal_id, l.ingrediente_id, l.lote_id,
       l.cantidad_actual, l.fecha_caducidad,
       l.fecha_caducidad - current_date as dias_restantes,
       case when l.fecha_caducidad < current_date then 'vencido' else 'por_caducar' end as situacion
from lote_inventario l
join sucursal s    on s.sucursal_id = l.sucursal_id
join ingrediente g on g.ingrediente_id = l.ingrediente_id
where l.cantidad_actual > 0
  and l.fecha_caducidad is not null
  and l.fecha_caducidad <= current_date + 3;

create or replace view v_preferencia_calculada as
select cliente_id, plato_id, plato, veces,
       row_number() over (partition by cliente_id order by veces desc, plato) as posicion
from (
    select p.cliente_id, d.plato_id, pl.nombre as plato, sum(d.cantidad) as veces
    from pedido p
    join detalle_pedido d on d.pedido_id = p.pedido_id
    join plato pl         on pl.plato_id = d.plato_id
    where p.estado = 'pagado' and p.cliente_id is not null
    group by p.cliente_id, d.plato_id, pl.nombre
) t;

create or replace view v_historial_visitas as
select p.cliente_id, p.pedido_id, s.nombre as sucursal, p.fecha_hora,
       t.total, p.observaciones, p.calificacion
from pedido p
join sucursal s       on s.sucursal_id = p.sucursal_id
join v_pedido_total t on t.pedido_id = p.pedido_id
where p.estado = 'pagado' and p.cliente_id is not null;
