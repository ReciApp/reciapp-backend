from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.security import create_access_token, verify_password
from app.crud import crud_user
from app.db.session import get_db
from app.schemas.user import RecicladorCreate, TokenOut, UsuarioCreate, UsuarioOut

router = APIRouter()


@router.post("/register", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def register_ciudadano(data: UsuarioCreate, db: Session = Depends(get_db)):
    if crud_user.get_by_correo(db, data.correo):
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    if data.dni and crud_user.get_by_dni(db, data.dni):
        raise HTTPException(status_code=400, detail="El DNI ya está registrado")
    data.rol = "ciudadano"
    return crud_user.create_ciudadano(db, data)


@router.post("/register/reciclador", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def register_reciclador(data: RecicladorCreate, db: Session = Depends(get_db)):
    if crud_user.get_by_correo(db, data.correo):
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    if data.dni and crud_user.get_by_dni(db, data.dni):
        raise HTTPException(status_code=400, detail="El DNI ya está registrado")
    return crud_user.create_reciclador(db, data)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Iniciar sesión",
    description="Ingresa tu **correo** en el campo *username* y tu **contraseña**.",
)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = crud_user.get_by_correo(db, form.username)
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    if not usuario or not verify_password(form.password, usuario.contrasena):
        raise invalid

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta pendiente de validación o desactivada",
        )

    token = create_access_token(
        data={"sub": str(usuario.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenOut(access_token=token)
