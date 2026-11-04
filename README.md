# Shucos El Sapo

**Integrantes:**
- Julio César de León - 25785
- Giovanni Orozco - 251162
- Juan José Herrarte - 25690
- Juan Esteban Lou - 251050

## Qué ve cada rol:
- **Mesero:** reservas, pedidos y clientes.
- **Gerente:** lo del mesero, más inventario y bitácora de su sucursal.
- **Administrador:** todo.

## Lo necesario

- Python 3.10+
- PostgreSQL
- Las librerías de `requirements.txt` (psycopg2-binary, bcrypt, python-dotenv, tabulate)

## Cómo correr el proyecto

**1. Bajar el proyecto**

```
git clone https://github.com/clipclasico/shucos_proyecto2.git
cd shucos_proyecto2
```

**2. Instalar las librerías**

```
pip install -r requirements.txt
```

**3. Crear la base de datos**

Crear la base de datos desde pgAdmin (clic derecho en Databases > Create > Database) con el nombre de  ``` proyecto2 ```

**4. Configurar la conexión**

Copiar el archivo env.example y llamarlo .env. RECOMENDADO: 
``` copy env.example .env ```.
Adentro poner los datos de PostgreSQL:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=proyecto2
DB_USER=postgres
DB_PASSWORD=su_contraseña
```

**5. Cargar las tablas y los datos**

Abrir Query Tool desde pgAdmin, cargar o copiar cada archivo de la carpeta de ``` sql ```, ejecutándolos en orden que están llamados (01, 02, 03). 


Cosas a tomar en cuenta:
- El `01` borra y vuelve a crear las tablas, así que sirve para empezar de cero.
- El `03` se puede volver ya que borra los datos y los carga otra vez.
- Las fechas de los datos de ejemplo se calculan a partir del día en que se corre el script, para que las alertas siempre se vean.

**6. Abrir la aplicación**

Desde la carpeta principal del proyecto (no desde adentro de `app/`):

```
python main.py
```

## Usuarios de prueba

| Usuario | Contraseña | Rol |
|---|---|---|
| admin | admin123 | administrador |
| juanesteban | gerente123 | gerente (Zona 10) - Juan Esteban Lou |
| juanjose | gerente123 | gerente (Zona 1) - Juan José Herrarte |
| giovanni | gerente123 | gerente (Zona 5) - Giovanni Orozco |
| julio | gerente123 | gerente (Antigua) - Julio César de León |
| carlos, lucia, diego | mesero123 | mesero (Zona 10) |
| sofia, andres, valeria | mesero123 | mesero (Zona 1) |
| fernando, karla, mario | mesero123 | mesero (Zona 5) |
| hector, daniela, oscar | mesero123 | mesero (Antigua) |

Los chefs no tienen cuenta.

## Cómo está armada la base de datos

- Un pedido cuenta como una visita del cliente.
- Las existencias de un insumo son la suma de sus lotes que no están vencidos. No se guarda un total aparte.
- Al pagar un pedido, un trigger descuenta el inventario y usa primero el lote que vence más pronto. Si no alcanza, el pago se cancela completo.
- Una mesa no puede tener dos reservas al mismo tiempo.
- Un pedido pagado ya no se puede cambiar, solo se le puede agregar la calificación y las observaciones.
- Los platos favoritos de un cliente se calculan con sus pedidos pagados.
- La bitácora se llena sola con triggers.
- La tabla de usuarios no se audita para no guardar las contraseñas.

El diagrama ER y la documentación del modelo están en la carpeta `docs/`.

## Cosas que no hace

- No hay recuperación de contraseña.
- No se guarda historial de existencias, así que en el reporte mensual lo de "por terminarse" muestra el inventario de hoy.
- No hay devoluciones después de pagar.
