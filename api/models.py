from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CachedImage(Base):
    __tablename__ = "cached_image"
    id: Mapped[str] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(unique=True)
    # Define 1-to-1 relationship
    image_metadata: Mapped["ImageMetadata"] = relationship(
        back_populates="image", cascade="all, delete-orphan"
    )


class ImageMetadata(Base):
    __tablename__ = "image_metadata"

    id: Mapped[str] = mapped_column(ForeignKey("cached_image.id"), primary_key=True)

    original_width: Mapped[int] = mapped_column()
    original_height: Mapped[int] = mapped_column()
    media_type: Mapped[str] = mapped_column()
    format: Mapped[str] = mapped_column()
    extension: Mapped[str] = mapped_column()

    image: Mapped[CachedImage] = relationship(back_populates="image_metadata")
