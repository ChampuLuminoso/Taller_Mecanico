"""
Identidad, roles, perfiles y auditoría.

Idea central: UNA tabla de usuarios (quién inicia sesión) + roles (qué puede
hacer) + perfiles (datos propios de clientes y empleados). Ya no existen
IdJefe, IdSubjefe, etc. como columnas: "un jefe" es "un usuario con rol JEFE".
"""
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .validadores import validar_mayor_de_edad, validar_placa, validar_telefono_co


# ───────────────────────── Usuarios ─────────────────────────

class UsuarioManagerBase(BaseUserManager):
    """Ve a TODOS los usuarios. Solo lo usan el login y la vista privada de Fran."""

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)  # guarda un hash, nunca la contraseña
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class UsuariosVisiblesManager(UsuarioManagerBase):
    """Manager por defecto: excluye a Fran de TODA consulta normal
    (admin, reportes, listados, búsquedas). Así se oculta en el servidor."""

    def get_queryset(self):
        return super().get_queryset().exclude(es_fran=True)


class Usuario(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("correo", unique=True)
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField("acceso al admin", default=False)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, blank=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)  # eliminación lógica
    es_fran = models.BooleanField(default=False, editable=False)
    creado_en = models.DateTimeField(default=timezone.now)

    roles = models.ManyToManyField("Rol", through="UsuarioRol", through_fields=("usuario", "rol"),
                                   related_name="usuarios", blank=True)

    objects = UsuariosVisiblesManager()   # el primero declarado = manager por defecto
    todos = UsuarioManagerBase()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"

    class Meta:
        constraints = [
            # Solo puede existir UN usuario con es_fran = True. Lo garantiza la base de datos.
            models.UniqueConstraint(fields=["es_fran"], condition=Q(es_fran=True), name="un_solo_fran"),
        ]

    def __str__(self):
        return self.nombre_visible

    @property
    def nombre_visible(self):
        """Lo que ven los demás cuando este usuario aparece en un historial."""
        if self.es_fran:
            return "Gerencia"
        if self.email == settings.TALLER["EMAIL_SISTEMA"]:
            return "Sistema automático"
        perfil = getattr(self, "empleado", None) or getattr(self, "cliente", None)
        return f"{perfil.nombres} {perfil.apellidos}" if perfil else self.email

    @property
    def puede_entrar(self):
        return self.is_active and not self.bloqueado and self.eliminado_en is None

    def codigos_rol(self) -> set[str]:
        return set(self.roles.values_list("codigo", flat=True))

    @classmethod
    def sistema(cls):
        return cls.todos.get(email=settings.TALLER["EMAIL_SISTEMA"])


class Rol(models.Model):
    CLIENTE, EMPLEADO, SUBJEFE, JEFE, INGENIERO = "CLIENTE", "EMPLEADO", "SUBJEFE", "JEFE", "INGENIERO"
    CODIGOS = [
        (CLIENTE, "Cliente"),
        (EMPLEADO, "Empleado"),
        (SUBJEFE, "Subjefe"),
        (JEFE, "Jefe"),
        (INGENIERO, "Ingeniero / soporte técnico"),
    ]
    # Fran NO es un rol de esta lista: es una marca única en Usuario (es_fran).
    codigo = models.CharField(max_length=20, choices=CODIGOS, unique=True)
    nombre = models.CharField(max_length=60)

    class Meta:
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class UsuarioRol(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT)
    asignado_por = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name="roles_asignados"
    )
    asignado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["usuario", "rol"], name="rol_unico_por_usuario")]
        verbose_name = "rol de usuario"
        verbose_name_plural = "roles de usuario"


# ───────────────────────── Perfiles ─────────────────────────

class Cliente(models.Model):
    TIPOS_DOC = [("CC", "Cédula de ciudadanía"), ("CE", "Cédula de extranjería"),
                 ("PPT", "Permiso por protección temporal"), ("PA", "Pasaporte")]

    # Null: un jefe puede crear un cliente de mostrador que nunca se registra en la web.
    usuario = models.OneToOneField(Usuario, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="cliente")
    tipo_documento = models.CharField(max_length=3, choices=TIPOS_DOC, blank=True)
    numero_documento = models.CharField(max_length=20, blank=True)
    nombres = models.CharField(max_length=80)
    apellidos = models.CharField(max_length=80)
    telefono = models.CharField(max_length=20, validators=[validar_telefono_co])
    email = models.EmailField(blank=True)
    fecha_nacimiento = models.DateField(validators=[validar_mayor_de_edad])

    # Ley 1581: prueba del consentimiento (cuándo y qué versión de la política aceptó).
    acepta_datos_en = models.DateTimeField()
    version_politica = models.CharField(max_length=20)
    acepta_marketing = models.BooleanField(default=False)  # autorización aparte y opcional

    anonimizado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_documento", "numero_documento"],
                condition=~Q(numero_documento=""),
                name="documento_cliente_unico",
            ),
        ]

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"

    def anonimizar(self):
        """Derecho de supresión (Ley 1581) sin romper la contabilidad:
        los pedidos siguen existiendo, pero ya no se sabe de quién eran."""
        self.nombres, self.apellidos = "Cliente", f"anonimizado #{self.pk}"
        self.telefono = "0000000000"
        self.email = self.numero_documento = self.tipo_documento = ""
        self.anonimizado_en = timezone.now()
        self.save()
        self.direcciones.all().delete()
        self.vehiculos.update(activo=False)
        if self.usuario:
            u = self.usuario
            u.email = f"anonimo-{u.pk}@borrado.invalid"
            u.set_unusable_password()
            u.is_active, u.eliminado_en = False, timezone.now()
            u.save()


class Direccion(models.Model):
    LOCALIDADES = [(n, n) for n in [
        "Usaquén", "Chapinero", "Santa Fe", "San Cristóbal", "Usme", "Tunjuelito", "Bosa",
        "Kennedy", "Fontibón", "Engativá", "Suba", "Barrios Unidos", "Teusaquillo",
        "Los Mártires", "Antonio Nariño", "Puente Aranda", "La Candelaria",
        "Rafael Uribe Uribe", "Ciudad Bolívar", "Sumapaz",
    ]]
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="direcciones")
    ciudad = models.CharField(max_length=60, default="Bogotá D.C.")
    localidad = models.CharField(max_length=30, choices=LOCALIDADES)
    barrio = models.CharField(max_length=80)
    direccion = models.CharField(max_length=150)
    indicaciones = models.CharField(max_length=200, blank=True)  # "casa esquinera, portón azul"
    principal = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "direcciones"
        constraints = [
            models.UniqueConstraint(fields=["cliente"], condition=Q(principal=True),
                                    name="una_direccion_principal"),
        ]

    def __str__(self):
        return f"{self.direccion}, {self.barrio} ({self.localidad})"


class Vehiculo(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="vehiculos")
    placa = models.CharField(max_length=6, unique=True, validators=[validar_placa])
    marca = models.CharField(max_length=40)
    modelo = models.CharField(max_length=60)
    anio = models.PositiveSmallIntegerField("año")
    activo = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        self.placa = (self.placa or "").upper().replace(" ", "").replace("-", "")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.placa} · {self.marca} {self.modelo} {self.anio}"


class Empleado(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.PROTECT, related_name="empleado")
    nombres = models.CharField(max_length=80)
    apellidos = models.CharField(max_length=80)
    numero_documento = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, validators=[validar_telefono_co])
    cargo = models.CharField(max_length=60)
    hace_domicilios = models.BooleanField(default=False)  # por ahora los empleados entregan los pedidos
    fecha_ingreso = models.DateField(default=timezone.localdate)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"


# ───────────────────────── Auditoría ─────────────────────────

class RegistroAuditoriaBase(models.Model):
    """Solo se inserta: no se edita ni se borra (también lo bloquea un trigger en Postgres)."""
    usuario = models.ForeignKey(Usuario, null=True, on_delete=models.PROTECT, related_name="+")
    accion = models.CharField(max_length=60)          # "crear", "editar", "bloquear_usuario"...
    entidad = models.CharField(max_length=60)         # "Producto", "Apartado"...
    entidad_id = models.CharField(max_length=40, blank=True)
    antes = models.JSONField(null=True, blank=True)
    despues = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("La auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La auditoría no se puede borrar.")


class Auditoria(RegistroAuditoriaBase):
    """Acciones de todos (jefes incluidos). La ven los Jefes y Fran."""

    class Meta(RegistroAuditoriaBase.Meta):
        verbose_name_plural = "auditoría"


class AuditoriaFran(RegistroAuditoriaBase):
    """Acciones de Fran. Separada para que no aparezca en la auditoría de los jefes."""

    class Meta(RegistroAuditoriaBase.Meta):
        verbose_name_plural = "auditoría privada"
