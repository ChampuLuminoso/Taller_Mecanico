"""Optimización de fotos de productos (la usan el formulario del producto y la carga en lote)."""
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

LADO_MAX = 1200
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def optimizar(archivo, nombre_base):
    """Valida y optimiza: máximo 3 MB, lado mayor 1200 px, formato WebP.
    Una foto de celular de 4 MB queda en ~100 KB y respeta la orientación con que se tomó."""
    if archivo.size > settings.TAMANO_MAX_IMAGEN_MB * 1024 * 1024:
        raise ValidationError(f"pesa más de {settings.TAMANO_MAX_IMAGEN_MB} MB")
    try:
        foto = ImageOps.exif_transpose(Image.open(archivo))
        foto.load()
    except (UnidentifiedImageError, OSError):
        raise ValidationError("no es una imagen que se pueda abrir (usa JPG, PNG o WebP)")
    foto = foto.convert("RGB")
    foto.thumbnail((LADO_MAX, LADO_MAX))
    salida = BytesIO()
    foto.save(salida, "WEBP", quality=82)
    return ContentFile(salida.getvalue(), name=f"{Path(nombre_base).stem.lower()}.webp")
