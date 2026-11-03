
create extension if not exists btree_gist;

-- sucursal
create table sucursal (
    sucursal_id  integer generated always as identity primary key,
    nombre       varchar(60)  not null unique,
    direccion    varchar(150) not null,
    telefono     varchar(20)
                 check (telefono ~ '^\+?[0-9][0-9 ()-]{6,18}[0-9]$'),
    activa       boolean      not null default true
);

-- empleado
create table empleado (
    empleado_id        integer generated always as identity primary key,
    sucursal_id        integer      not null references sucursal (sucursal_id),
    nombre             varchar(100) not null,
    cargo              varchar(20)  not null
                       check (cargo in ('mesero', 'chef', 'gerente', 'administrador')),
    telefono           varchar(20)
                       check (telefono ~ '^\+?[0-9][0-9 ()-]{6,18}[0-9]$'),
    fecha_contratacion date         not null default current_date,
    activo             boolean      not null default true,
    constraint empleado_id_sucursal_uq unique (empleado_id, sucursal_id)
);

-- usuario
create table usuario (
    usuario_id    integer generated always as identity primary key,
    empleado_id   integer      not null unique references empleado (empleado_id),
    username      varchar(40)  not null unique,
    password_hash varchar(100) not null,
    rol           varchar(15)  not null
                  check (rol in ('administrador', 'gerente', 'mesero')),
    activo        boolean      not null default true
);

-- cliente
create table cliente (
    cliente_id     integer generated always as identity primary key,
    nombre         varchar(100) not null,
    telefono       varchar(20)
                   check (telefono ~ '^\+?[0-9][0-9 ()-]{6,18}[0-9]$'),
    correo         varchar(100) unique,
    fecha_registro timestamp    not null default now()
);

-- mesa
create table mesa (
    mesa_id     integer generated always as identity primary key,
    sucursal_id integer not null references sucursal (sucursal_id),
    numero      integer not null check (numero > 0),
    capacidad   integer not null check (capacidad > 0),
    constraint mesa_sucursal_numero_uq unique (sucursal_id, numero),
    constraint mesa_id_sucursal_uq     unique (mesa_id, sucursal_id)
);

-- reserva
create table reserva (
    reserva_id        integer generated always as identity primary key,
    sucursal_id       integer   not null references sucursal (sucursal_id),
    cliente_id        integer   not null references cliente (cliente_id),
    mesa_id           integer   not null,
    fecha_hora_inicio timestamp not null,
    fecha_hora_fin    timestamp not null,
    num_personas      integer   not null check (num_personas > 0),
    estado            varchar(15) not null default 'pendiente'
                      check (estado in ('pendiente', 'confirmada', 'cancelada', 'cumplida')),
    constraint reserva_mesa_fk foreign key (mesa_id, sucursal_id)
        references mesa (mesa_id, sucursal_id),
    constraint reserva_id_sucursal_uq unique (reserva_id, sucursal_id),
    constraint reserva_horario_ck check (fecha_hora_fin > fecha_hora_inicio),
    constraint reserva_sin_traslape exclude using gist (
        mesa_id with =,
        tsrange(fecha_hora_inicio, fecha_hora_fin) with &&
    ) where (estado <> 'cancelada')
);

-- pedido
create table pedido (
    pedido_id     integer generated always as identity primary key,
    sucursal_id   integer   not null references sucursal (sucursal_id),
    mesa_id       integer,
    cliente_id    integer   references cliente (cliente_id),
    empleado_id   integer   not null,
    reserva_id    integer   unique,
    fecha_hora    timestamp not null default now(),
    estado        varchar(10) not null default 'abierto'
                  check (estado in ('abierto', 'pagado', 'cancelado')),
    observaciones text,
    calificacion  smallint  check (calificacion between 1 and 5),
    constraint pedido_mesa_fk foreign key (mesa_id, sucursal_id)
        references mesa (mesa_id, sucursal_id),
    constraint pedido_empleado_fk foreign key (empleado_id, sucursal_id)
        references empleado (empleado_id, sucursal_id),
    constraint pedido_reserva_fk foreign key (reserva_id, sucursal_id)
        references reserva (reserva_id, sucursal_id)
);

-- plato
create table plato (
    plato_id  integer generated always as identity primary key,
    nombre    varchar(60)   not null unique,
    categoria varchar(10)   not null
              check (categoria in ('shuco', 'snack', 'bebida')),
    precio    numeric(8, 2) not null check (precio >= 0),
    activo    boolean       not null default true
);

-- detalle_pedido
create table detalle_pedido (
    pedido_id       integer       not null references pedido (pedido_id),
    plato_id        integer       not null references plato (plato_id),
    cantidad        integer       not null check (cantidad > 0),
    precio_unitario numeric(8, 2) not null check (precio_unitario >= 0),
    primary key (pedido_id, plato_id)
);

-- ingrediente
create table ingrediente (
    ingrediente_id integer generated always as identity primary key,
    nombre         varchar(60) not null unique,
    unidad_medida  varchar(10) not null
                   check (unidad_medida in ('unidad', 'g', 'ml')),
    perecedero     boolean     not null default true
);

-- receta
create table receta (
    plato_id       integer       not null references plato (plato_id),
    ingrediente_id integer       not null references ingrediente (ingrediente_id),
    cantidad       numeric(10, 2) not null check (cantidad > 0),
    primary key (plato_id, ingrediente_id)
);

-- inventario
create table inventario (
    sucursal_id      integer        not null references sucursal (sucursal_id),
    ingrediente_id   integer        not null references ingrediente (ingrediente_id),
    capacidad_maxima numeric(10, 2) not null check (capacidad_maxima > 0),
    stock_minimo     numeric(10, 2) generated always as (capacidad_maxima * 0.15) stored,
    primary key (sucursal_id, ingrediente_id)
);

-- lote_inventario
create table lote_inventario (
    lote_id          integer generated always as identity primary key,
    sucursal_id      integer        not null,
    ingrediente_id   integer        not null,
    cantidad_inicial numeric(10, 2) not null check (cantidad_inicial > 0),
    cantidad_actual  numeric(10, 2) not null,
    fecha_ingreso    date           not null default current_date,
    fecha_caducidad  date,
    foreign key (sucursal_id, ingrediente_id)
        references inventario (sucursal_id, ingrediente_id),
    constraint lote_cantidad_ck
        check (cantidad_actual >= 0 and cantidad_actual <= cantidad_inicial),
    constraint lote_fechas_ck
        check (fecha_caducidad is null or fecha_caducidad >= fecha_ingreso)
);

-- preferencia_cliente
create table preferencia_cliente (
    preferencia_id integer generated always as identity primary key,
    cliente_id     integer      not null references cliente (cliente_id),
    plato_id       integer      references plato (plato_id),
    tipo           varchar(20)  not null
                   check (tipo in ('plato_favorito', 'evitar_ingrediente', 'mesa', 'nota')),
    descripcion    varchar(200),
    fecha_registro timestamp    not null default now(),
    constraint preferencia_plato_ck
        check ((tipo = 'plato_favorito') = (plato_id is not null))
);

-- bitacora
create table bitacora (
    bitacora_id   bigint generated always as identity primary key,
    usuario_id    integer     references usuario (usuario_id),
    tabla         varchar(50) not null,
    registro_id   text,
    operacion     varchar(6)  not null
                  check (operacion in ('INSERT', 'UPDATE', 'DELETE')),
    datos_antes   jsonb,
    datos_despues jsonb,
    fecha_hora    timestamp   not null default now()
);

-- Indices
create index idx_empleado_sucursal        on empleado (sucursal_id);
create index idx_reserva_cliente          on reserva (cliente_id);
create index idx_reserva_sucursal_inicio  on reserva (sucursal_id, fecha_hora_inicio);
create index idx_pedido_cliente           on pedido (cliente_id);
create index idx_pedido_sucursal_fecha    on pedido (sucursal_id, fecha_hora);
create index idx_detalle_plato            on detalle_pedido (plato_id);
create index idx_lote_fefo                on lote_inventario (sucursal_id, ingrediente_id, fecha_caducidad);
create index idx_lote_caducidad           on lote_inventario (fecha_caducidad);
create index idx_preferencia_cliente      on preferencia_cliente (cliente_id);
create index idx_bitacora_tabla_fecha     on bitacora (tabla, fecha_hora);