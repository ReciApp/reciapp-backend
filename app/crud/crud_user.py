from sqlalchemy.orm import Session
from app.models.user import Usuario
from app.schemas.user import UsuarioCreate, RecicladorCreate, UsuarioUpdate
from app.core.security import get_password_hash


def get_by_correo(db: Session, correo: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.correo == correo).first()


def get_by_id(db: Session, usuario_id: int) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


def get_by_dni(db: Session, dni: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.dni == dni).first()


def get_recicladores_pendientes(db: Session) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.rol == "reciclador", Usuario.estado_validacion == "pendiente")
        .all()
    )


def create_ciudadano(db: Session, data: UsuarioCreate) -> Usuario:
    usuario = Usuario(
        nombre=data.nombre,
        correo=data.correo,
        dni=data.dni,
        celular=data.celular,
        contrasena=get_password_hash(data.contrasena),
        rol="ciudadano",
        activo=True,
        verificado=False,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def create_reciclador(db: Session, data: RecicladorCreate) -> Usuario:
    # El reciclador inicia inactivo y pendiente de validación admin
    usuario = Usuario(
        nombre=data.nombre,
        correo=data.correo,
        dni=data.dni,
        celular=data.celular,
        contrasena=get_password_hash(data.contrasena),
        rol="reciclador",
        activo=False,
        verificado=False,
        zona_cobertura=data.zona_cobertura,
        disponibilidad_horaria=data.disponibilidad_horaria,
        estado_validacion="pendiente",
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def validar_reciclador(db: Session, usuario_id: int, accion: str) -> Usuario | None:
    usuario = get_by_id(db, usuario_id)
    if not usuario or usuario.rol != "reciclador":
        return None
    usuario.estado_validacion = accion
    usuario.activo = accion == "aprobado"
    db.commit()
    db.refresh(usuario)
    return usuario


def update_perfil(db: Session, usuario: Usuario, data: UsuarioUpdate) -> Usuario:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(usuario, field, value)
    db.commit()
    db.refresh(usuario)
    return usuario
