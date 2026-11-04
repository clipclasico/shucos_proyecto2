-- =====================================================================
-- Shucos El Sapo | CC3088 Base de Datos 1 | Proyecto 2
-- 03_datos_ejemplo.sql : datos de ejemplo (correr despues de 01 y 02)
--
-- Orden de ejecucion:  01_schema.sql  ->  02_triggers_vistas.sql  ->  03_datos_ejemplo.sql
--
-- Es REPETIBLE: vacia todas las tablas (y reinicia los ids) antes de cargar.
-- Las fechas son relativas a la fecha en que se corre el script, asi que
-- las alertas de caducidad y las reservas futuras siempre se ven vigentes.
--
-- Usuarios de prueba (contrasenas guardadas como hash bcrypt):
--   admin                         / admin123     (administrador)
--   juanesteban, juanjose, giovanni, julio / gerente123   (gerentes de cada sucursal)
--   carlos, lucia, diego, ...      / mesero123    (meseros)
-- =====================================================================

begin;

create extension if not exists pgcrypto;   -- crypt() y gen_salt() para el hash bcrypt

-- Resultados reproducibles
select setseed(0.42);

-- Se vacian las tablas para poder volver a correr el script
truncate table bitacora, preferencia_cliente, lote_inventario, inventario, receta,
    ingrediente, detalle_pedido, plato, pedido, reserva, mesa, cliente,
    usuario, empleado, sucursal
restart identity cascade;

-- Durante la carga del historial se desactivan los triggers de usuario
-- (bitacora, validaciones y descuento de inventario) para no llenar la
-- bitacora con datos de ejemplo ni gastar inventario con ventas pasadas.
-- Se vuelven a activar antes de terminar.
alter table pedido              disable trigger user;
alter table detalle_pedido      disable trigger user;
alter table reserva             disable trigger user;
alter table cliente             disable trigger user;
alter table preferencia_cliente disable trigger user;
alter table plato               disable trigger user;
alter table inventario          disable trigger user;
alter table lote_inventario     disable trigger user;

-- ---------------------------------------------------------------------
-- Sucursales (ids: 1 Zona 10, 2 Zona 1, 3 Zona 5, 4 Antigua)
-- ---------------------------------------------------------------------
insert into sucursal (nombre, direccion, telefono) values
    ('Zona 10', '6a avenida 12-34, zona 10, Ciudad de Guatemala', '2333-1010'),
    ('Zona 1',  '5a calle 8-20, zona 1, Ciudad de Guatemala',     '2222-0101'),
    ('Zona 5',  '12 calle 3-45, zona 5, Ciudad de Guatemala',     '2333-0505'),
    ('Antigua', '4a calle oriente 15, Antigua Guatemala',         '7832-0404');

-- ---------------------------------------------------------------------
-- Empleados: 1 gerente, 3 meseros y 1 chef por sucursal + 1 administrador
-- ---------------------------------------------------------------------
insert into empleado (sucursal_id, nombre, cargo, telefono, fecha_contratacion) values
    (1, 'Administrador Sapo',  'administrador', '5510-0001', current_date - 700),
    (1, 'Juan Esteban Lou',         'gerente',       '5510-1001', current_date - 600),
    (1, 'Carlos Mendez',       'mesero',        '5510-1002', current_date - 400),
    (1, 'Lucia Perez',         'mesero',        '5510-1003', current_date - 300),
    (1, 'Diego Ramirez',       'mesero',        '5510-1004', current_date - 150),
    (1, 'Jose Castillo',       'chef',          '5510-1005', current_date - 500),
    (2, 'Juan José Herrarte',       'gerente',       '5510-2001', current_date - 650),
    (2, 'Sofia Herrera',       'mesero',        '5510-2002', current_date - 380),
    (2, 'Andres Morales',      'mesero',        '5510-2003', current_date - 260),
    (2, 'Valeria Ruiz',        'mesero',        '5510-2004', current_date - 120),
    (2, 'Luis Orozco',         'chef',          '5510-2005', current_date - 480),
    (3, 'Giovanni Orozco',       'gerente',       '5510-3001', current_date - 550),
    (3, 'Fernando Cruz',       'mesero',        '5510-3002', current_date - 340),
    (3, 'Karla Vasquez',       'mesero',        '5510-3003', current_date - 220),
    (3, 'Mario Lemus',         'mesero',        '5510-3004', current_date - 90),
    (3, 'Pedro Aguilar',       'chef',          '5510-3005', current_date - 420),
    (4, 'Julio César de León',       'gerente',       '5510-4001', current_date - 520),
    (4, 'Hector Paz',          'mesero',        '5510-4002', current_date - 310),
    (4, 'Daniela Cifuentes',   'mesero',        '5510-4003', current_date - 200),
    (4, 'Oscar Tun',           'mesero',        '5510-4004', current_date - 80),
    (4, 'Rosa Chavez',         'chef',          '5510-4005', current_date - 450);

-- ---------------------------------------------------------------------
-- Usuarios (administrador, gerentes y meseros; los chefs no tienen cuenta)
-- username = primer nombre en minusculas (admin para el administrador).
-- Si dos empleados comparten primer nombre, a esos se les une el segundo nombre
-- y se quitan las tildes (Juan Esteban -> juanesteban, Juan Jose -> juanjose),
-- porque el usuario debe ser unico.
-- ---------------------------------------------------------------------
insert into usuario (empleado_id, username, password_hash, rol)
select t.empleado_id,
       case when t.cargo = 'administrador' then 'admin'
            when t.repetidos > 1 then translate(t.primero || t.segundo, 'áéíóúüñ', 'aeiouun')
            else t.primero end,
       crypt(case t.cargo when 'administrador' then 'admin123'
                          when 'gerente'       then 'gerente123'
                          else 'mesero123' end,
             gen_salt('bf', 10)),
       t.cargo
from (
    select e.empleado_id, e.cargo,
           lower(split_part(e.nombre, ' ', 1)) as primero,
           lower(split_part(e.nombre, ' ', 2)) as segundo,
           count(*) over (partition by lower(split_part(e.nombre, ' ', 1))) as repetidos
    from empleado e
    where e.cargo in ('administrador', 'gerente', 'mesero')
) t;

-- ---------------------------------------------------------------------
-- Mesas: 8 por sucursal (capacidades 2,2,4,4,4,6,6,8)
-- ---------------------------------------------------------------------
insert into mesa (sucursal_id, numero, capacidad)
select s.sucursal_id, n, (array[2, 2, 4, 4, 4, 6, 6, 8])[n]
from sucursal s
cross join generate_series(1, 8) as n;

-- ---------------------------------------------------------------------
-- Menu (igual en todas las sucursales). ids 1..11 en este orden.
-- ---------------------------------------------------------------------
insert into plato (nombre, categoria, precio) values
    ('Shuco Clasico',          'shuco',  15.00),
    ('Shuco de Longaniza',     'shuco',  18.00),
    ('Shuco de Chorizo',       'shuco',  18.00),
    ('Shuco de Carne Adobada', 'shuco',  22.00),
    ('Shuco de Pollo',         'shuco',  20.00),
    ('Shuco Mixto',            'shuco',  25.00),
    ('Shuco Marciano',         'shuco',  12.00),
    ('Tortrix',                'snack',   8.00),
    ('Plataninas',             'snack',   8.00),
    ('Gaseosa',                'bebida', 10.00),
    ('Agua Pura',              'bebida',  6.00);

-- ---------------------------------------------------------------------
-- Ingredientes (17)
-- ---------------------------------------------------------------------
insert into ingrediente (nombre, unidad_medida, perecedero) values
    ('pan',            'unidad', true),
    ('salchicha',      'unidad', true),
    ('longaniza',      'unidad', true),
    ('chorizo',        'unidad', true),
    ('carne adobada',  'g',      true),
    ('pollo',          'g',      true),
    ('guacamole',      'g',      true),
    ('repollo',        'g',      true),
    ('mayonesa',       'g',      true),
    ('mostaza',        'g',      true),
    ('ketchup',        'g',      true),
    ('salsa picante',  'g',      true),
    ('queso',          'g',      true),
    ('tortrix',        'unidad', false),
    ('plataninas',     'unidad', false),
    ('gaseosa',        'unidad', false),
    ('agua pura',      'unidad', false);

-- ---------------------------------------------------------------------
-- Recetas (cantidad por plato, en la unidad del ingrediente)
-- ---------------------------------------------------------------------
insert into receta (plato_id, ingrediente_id, cantidad)
select p.plato_id, g.ingrediente_id, r.cantidad
from (values
    ('Shuco Clasico',          'pan', 1), ('Shuco Clasico', 'salchicha', 1), ('Shuco Clasico', 'guacamole', 40),
    ('Shuco Clasico',          'repollo', 20), ('Shuco Clasico', 'mayonesa', 10), ('Shuco Clasico', 'mostaza', 5),
    ('Shuco Clasico',          'ketchup', 10),
    ('Shuco de Longaniza',     'pan', 1), ('Shuco de Longaniza', 'longaniza', 1), ('Shuco de Longaniza', 'guacamole', 40),
    ('Shuco de Longaniza',     'repollo', 20), ('Shuco de Longaniza', 'mostaza', 5), ('Shuco de Longaniza', 'salsa picante', 5),
    ('Shuco de Chorizo',       'pan', 1), ('Shuco de Chorizo', 'chorizo', 1), ('Shuco de Chorizo', 'guacamole', 40),
    ('Shuco de Chorizo',       'repollo', 20), ('Shuco de Chorizo', 'mayonesa', 10), ('Shuco de Chorizo', 'salsa picante', 5),
    ('Shuco de Carne Adobada', 'pan', 1), ('Shuco de Carne Adobada', 'carne adobada', 80), ('Shuco de Carne Adobada', 'guacamole', 40),
    ('Shuco de Carne Adobada', 'repollo', 20), ('Shuco de Carne Adobada', 'mayonesa', 10), ('Shuco de Carne Adobada', 'ketchup', 10),
    ('Shuco de Pollo',         'pan', 1), ('Shuco de Pollo', 'pollo', 80), ('Shuco de Pollo', 'guacamole', 40),
    ('Shuco de Pollo',         'repollo', 20), ('Shuco de Pollo', 'mayonesa', 10), ('Shuco de Pollo', 'mostaza', 5),
    ('Shuco Mixto',            'pan', 1), ('Shuco Mixto', 'salchicha', 1), ('Shuco Mixto', 'longaniza', 1),
    ('Shuco Mixto',            'guacamole', 40), ('Shuco Mixto', 'repollo', 20), ('Shuco Mixto', 'mayonesa', 10),
    ('Shuco Mixto',            'mostaza', 5), ('Shuco Mixto', 'ketchup', 10), ('Shuco Mixto', 'queso', 20),
    ('Shuco Marciano',         'pan', 1), ('Shuco Marciano', 'salchicha', 1), ('Shuco Marciano', 'mayonesa', 10),
    ('Shuco Marciano',         'mostaza', 5), ('Shuco Marciano', 'ketchup', 10),
    ('Tortrix',                'tortrix', 1),
    ('Plataninas',             'plataninas', 1),
    ('Gaseosa',                'gaseosa', 1),
    ('Agua Pura',              'agua pura', 1)
) as r(plato, ingrediente, cantidad)
join plato p       on p.nombre = r.plato
join ingrediente g on g.nombre = r.ingrediente;

-- ---------------------------------------------------------------------
-- Inventario: todas las sucursales manejan los 17 ingredientes
-- ---------------------------------------------------------------------
insert into inventario (sucursal_id, ingrediente_id, capacidad_maxima)
select s.sucursal_id, g.ingrediente_id, c.capacidad
from sucursal s
cross join ingrediente g
join (values
    ('pan', 200), ('salchicha', 200), ('longaniza', 150), ('chorizo', 150),
    ('carne adobada', 8000), ('pollo', 8000), ('guacamole', 5000), ('repollo', 4000),
    ('mayonesa', 3000), ('mostaza', 1500), ('ketchup', 3000), ('salsa picante', 1500),
    ('queso', 3000), ('tortrix', 100), ('plataninas', 100), ('gaseosa', 150), ('agua pura', 150)
) as c(nombre, capacidad) on c.nombre = g.nombre;

-- Lotes: un lote viejo (ingresado hace 10 dias) y uno nuevo (hace 2 dias)
insert into lote_inventario (sucursal_id, ingrediente_id, cantidad_inicial, cantidad_actual, fecha_ingreso, fecha_caducidad)
select i.sucursal_id, i.ingrediente_id,
       round(i.capacidad_maxima * 0.5, 2),
       round((i.capacidad_maxima * 0.5 * (0.5 + random() * 0.4))::numeric, 2),
       current_date - 10,
       current_date + case when g.perecedero then 6 else 120 end
from inventario i
join ingrediente g on g.ingrediente_id = i.ingrediente_id
union all
select i.sucursal_id, i.ingrediente_id,
       round(i.capacidad_maxima * 0.5, 2),
       round((i.capacidad_maxima * 0.5 * (0.8 + random() * 0.2))::numeric, 2),
       current_date - 2,
       current_date + case when g.perecedero then 12 else 150 end
from inventario i
join ingrediente g on g.ingrediente_id = i.ingrediente_id;

-- Casos para que las ALERTAS se vean en la demo:
-- (a) existencias <= 15% de la capacidad: guacamole en Zona 1, salchicha en Zona 5, tortrix en Antigua
update lote_inventario set cantidad_actual = least(cantidad_actual, 200)
where sucursal_id = 2 and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'guacamole');

update lote_inventario set cantidad_actual = least(cantidad_actual, 10)
where sucursal_id = 3 and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'salchicha');

update lote_inventario set cantidad_actual = least(cantidad_actual, 4)
where sucursal_id = 4 and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'tortrix');

-- (b) lotes por caducar: pan en Zona 10 (2 dias) y pollo en Zona 5 (1 dia)
update lote_inventario set fecha_caducidad = current_date + 2
where sucursal_id = 1 and fecha_ingreso = current_date - 10
  and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'pan');

update lote_inventario set fecha_caducidad = current_date + 1
where sucursal_id = 3 and fecha_ingreso = current_date - 10
  and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'pollo');

-- (c) lote vencido con existencias: repollo en Zona 1 (vencio ayer)
update lote_inventario set fecha_caducidad = current_date - 1
where sucursal_id = 2 and fecha_ingreso = current_date - 10
  and ingrediente_id = (select ingrediente_id from ingrediente where nombre = 'repollo');

-- ---------------------------------------------------------------------
-- Clientes (25). Los ids bajos son los mas frecuentes en el historial.
-- ---------------------------------------------------------------------
insert into cliente (nombre, telefono, correo, fecha_registro)
select n,
       '5' || lpad((1000000 + floor(random() * 8999999))::int::text, 7, '0'),
       lower(replace(n, ' ', '.')) || '@example.com',
       now() - (60 + floor(random() * 60))::int * interval '1 day'
from unnest(array[
    'Ana Lucia Garcia', 'Mynor Estrada', 'Brenda Colindres', 'Kevin Alvarado', 'Gabriela Sandoval',
    'Luis Fernando Rojas', 'Andrea Monterroso', 'Josue Barrientos', 'Mishelle Aguilar', 'Pablo Cabrera',
    'Daniela Fuentes', 'Rodrigo Villatoro', 'Camila Arevalo', 'Esteban Marroquin', 'Paola Samayoa',
    'Julio Rosales', 'Maria Jose Ortiz', 'Cristian Lima', 'Fernanda Reyes', 'Alejandro Pineda',
    'Sara Melgar', 'Byron Giron', 'Wendy Solis', 'Marvin Coc', 'Lesly Mazariegos'
]) as n;

-- Preferencias DECLARADAS por los clientes
insert into preferencia_cliente (cliente_id, plato_id, tipo, descripcion) values
    (1,  null, 'evitar_ingrediente', 'sin picante'),
    (1,  (select plato_id from plato where nombre = 'Shuco Clasico'),          'plato_favorito', null),
    (2,  (select plato_id from plato where nombre = 'Shuco Mixto'),            'plato_favorito', null),
    (3,  null, 'mesa', 'prefiere mesa junto a la ventana'),
    (4,  null, 'evitar_ingrediente', 'sin mayonesa'),
    (5,  null, 'nota', 'viene casi siempre en grupo grande'),
    (6,  (select plato_id from plato where nombre = 'Shuco Marciano'),         'plato_favorito', null),
    (7,  null, 'evitar_ingrediente', 'sin repollo'),
    (8,  (select plato_id from plato where nombre = 'Shuco de Pollo'),         'plato_favorito', null),
    (9,  null, 'nota', 'pide la salsa picante aparte'),
    (10, (select plato_id from plato where nombre = 'Shuco de Longaniza'),     'plato_favorito', null),
    (11, null, 'mesa', 'prefiere mesas para dos'),
    (12, null, 'evitar_ingrediente', 'sin queso'),
    (13, (select plato_id from plato where nombre = 'Shuco de Chorizo'),       'plato_favorito', null),
    (14, null, 'nota', 'cliente frecuente de la sucursal de Antigua'),
    (15, null, 'evitar_ingrediente', 'sin mostaza');

-- ---------------------------------------------------------------------
-- Historial: reservas y pedidos pagados (generados con datos pseudoaleatorios)
-- Las sucursales tienen distinto volumen: Zona 10 35%, Zona 1 25%, Zona 5 20%, Antigua 20%
-- ---------------------------------------------------------------------
create or replace function pg_temp.sembrar_detalle(p_pedido integer)
returns void
language plpgsql
as $$
declare
    -- platos ordenados de mas a menos populares
    v_pop   integer[] := array[1, 10, 2, 3, 8, 6, 4, 5, 7, 9, 11];
    v_lineas integer := 1 + floor(random() * 4)::int;
    v_plato  integer;
    j        integer;
begin
    for j in 1 .. v_lineas loop
        v_plato := v_pop[1 + floor(11 * power(random(), 1.6))::int];
        insert into detalle_pedido (pedido_id, plato_id, cantidad, precio_unitario)
        select p_pedido, plato_id, 1 + floor(random() * 3)::int, precio
        from plato where plato_id = v_plato
        on conflict do nothing;
    end loop;
end;
$$;

do $$
declare
    v_obs      text[] := array['Todo muy rico', 'Excelente servicio', 'El shuco llego tibio',
                               'Mucha espera pero valio la pena', 'Pedimos para compartir',
                               'Cumpleanos en la mesa'];
    v_r        double precision;
    v_sucursal integer;
    v_mesa     integer;
    v_cliente  integer;
    v_mesero   integer;
    v_personas integer;
    v_fecha    timestamp;
    v_estado   varchar(15);
    v_reserva  integer;
    v_pedido   integer;
    i          integer;
begin
    -- Reservas pasadas (cumplidas con su pedido pagado, o canceladas)
    for i in 1 .. 90 loop
        v_r := random();
        v_sucursal := case when v_r < 0.35 then 1 when v_r < 0.60 then 2 when v_r < 0.80 then 3 else 4 end;
        v_personas := 1 + floor(random() * 6)::int;
        v_cliente  := 1 + floor(25 * power(random(), 2))::int;
        v_estado   := case when random() < 0.85 then 'cumplida' else 'cancelada' end;
        v_fecha    := (current_date - (1 + floor(random() * 45))::int)
                      + make_interval(hours => 12 + 2 * floor(random() * 5)::int);

        select mesa_id into v_mesa from mesa
        where sucursal_id = v_sucursal and capacidad >= v_personas
        order by random() limit 1;

        v_reserva := null;
        insert into reserva (sucursal_id, cliente_id, mesa_id, fecha_hora_inicio, fecha_hora_fin, num_personas, estado)
        values (v_sucursal, v_cliente, v_mesa, v_fecha, v_fecha + interval '90 minutes', v_personas, v_estado)
        on conflict do nothing
        returning reserva_id into v_reserva;

        if v_estado = 'cumplida' and v_reserva is not null then
            select empleado_id into v_mesero from empleado
            where sucursal_id = v_sucursal and cargo = 'mesero' order by random() limit 1;

            insert into pedido (sucursal_id, mesa_id, cliente_id, empleado_id, reserva_id,
                                fecha_hora, estado, observaciones, calificacion)
            values (v_sucursal, v_mesa, v_cliente, v_mesero, v_reserva,
                    v_fecha + interval '10 minutes', 'pagado',
                    case when random() < 0.35 then v_obs[1 + floor(random() * 6)::int] end,
                    case when random() < 0.6 then (3 + floor(random() * 3))::smallint end)
            returning pedido_id into v_pedido;

            perform pg_temp.sembrar_detalle(v_pedido);
        end if;
    end loop;

    -- Pedidos sin reserva (algunos para llevar, algunos de clientes no registrados)
    for i in 1 .. 250 loop
        v_r := random();
        v_sucursal := case when v_r < 0.35 then 1 when v_r < 0.60 then 2 when v_r < 0.80 then 3 else 4 end;
        v_cliente  := case when random() < 0.7 then 1 + floor(25 * power(random(), 2))::int end;
        v_mesa     := case when random() < 0.7
                           then (select mesa_id from mesa where sucursal_id = v_sucursal order by random() limit 1)
                      end;
        v_fecha    := (current_date - (1 + floor(random() * 60))::int)
                      + make_interval(hours => 11 + floor(random() * 11)::int, mins => floor(random() * 60)::int);

        select empleado_id into v_mesero from empleado
        where sucursal_id = v_sucursal and cargo = 'mesero' order by random() limit 1;

        insert into pedido (sucursal_id, mesa_id, cliente_id, empleado_id, fecha_hora, estado, observaciones, calificacion)
        values (v_sucursal, v_mesa, v_cliente, v_mesero, v_fecha, 'pagado',
                case when random() < 0.35 then v_obs[1 + floor(random() * 6)::int] end,
                case when random() < 0.6 then (3 + floor(random() * 3))::smallint end)
        returning pedido_id into v_pedido;

        perform pg_temp.sembrar_detalle(v_pedido);
    end loop;

    -- Reservas futuras (proximos 7 dias), para probar la disponibilidad de mesas
    for i in 1 .. 28 loop
        v_r := random();
        v_sucursal := case when v_r < 0.35 then 1 when v_r < 0.60 then 2 when v_r < 0.80 then 3 else 4 end;
        v_personas := 1 + floor(random() * 6)::int;
        v_cliente  := 1 + floor(25 * power(random(), 2))::int;
        v_fecha    := (current_date + (1 + floor(random() * 7))::int)
                      + make_interval(hours => 12 + 2 * floor(random() * 5)::int);

        select mesa_id into v_mesa from mesa
        where sucursal_id = v_sucursal and capacidad >= v_personas
        order by random() limit 1;

        insert into reserva (sucursal_id, cliente_id, mesa_id, fecha_hora_inicio, fecha_hora_fin, num_personas, estado)
        values (v_sucursal, v_cliente, v_mesa, v_fecha, v_fecha + interval '90 minutes', v_personas,
                case when random() < 0.5 then 'pendiente' else 'confirmada' end)
        on conflict do nothing;
    end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- Se reactivan los triggers
-- ---------------------------------------------------------------------
alter table pedido              enable trigger user;
alter table detalle_pedido      enable trigger user;
alter table reserva             enable trigger user;
alter table cliente             enable trigger user;
alter table preferencia_cliente enable trigger user;
alter table plato               enable trigger user;
alter table inventario          enable trigger user;
alter table lote_inventario     enable trigger user;

-- Dos pedidos ABIERTOS en Zona 10 (con triggers activos) para probar el pago
insert into pedido (sucursal_id, mesa_id, cliente_id, empleado_id)
select 1, m.mesa_id, t.cliente, e.empleado_id
from (values (1, 3), (2, 7)) as t(numero, cliente)
join mesa m     on m.sucursal_id = 1 and m.numero = t.numero
join empleado e on e.sucursal_id = 1 and e.nombre = 'Carlos Mendez';

insert into detalle_pedido (pedido_id, plato_id, cantidad, precio_unitario)
select p.pedido_id, pl.plato_id, 2, pl.precio
from pedido p
cross join plato pl
where p.estado = 'abierto' and pl.nombre in ('Shuco Clasico', 'Gaseosa');

commit;

-- ---------------------------------------------------------------------
-- Resumen de lo cargado
-- ---------------------------------------------------------------------
select 'sucursal' as tabla, count(*) as filas from sucursal
union all select 'empleado',        count(*) from empleado
union all select 'usuario',         count(*) from usuario
union all select 'cliente',         count(*) from cliente
union all select 'mesa',            count(*) from mesa
union all select 'plato',           count(*) from plato
union all select 'ingrediente',     count(*) from ingrediente
union all select 'receta',          count(*) from receta
union all select 'inventario',      count(*) from inventario
union all select 'lote_inventario', count(*) from lote_inventario
union all select 'reserva',         count(*) from reserva
union all select 'pedido',          count(*) from pedido
union all select 'detalle_pedido',  count(*) from detalle_pedido
union all select 'preferencia_cliente', count(*) from preferencia_cliente
union all select 'bitacora',        count(*) from bitacora;
