from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql import func

from api.classes import ImageMetadata


class Base(DeclarativeBase):
    pass


class CachedImageMetadata(Base):
    __tablename__ = "cached_image"
    id: Mapped[str] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column()
    image_metadata: Mapped[ImageMetadata] = mapped_column()
    created: Mapped[datetime] = mapped_column(DateTime, default=func.now())
