package models

import (
	"time"
)

// https://gorm.io/docs/models.html
type Image struct {
	ID               string `gorm:"primaryKey"`
	OriginalFilename string `gorm:"uniqueIndex;not null"`
	CreatedAt        time.Time
	UpdatedAt        time.Time
	Metadata         *ImageMetadata `gorm:"foreignKey:ID;references:ID;constraint:OnDelete:CASCADE"`
}

type ImageMetadata struct {
	ID             string `gorm:"primaryKey"`
	OriginalWidth  int
	OriginalHeight int
	MediaType      string
	Format         string
	Extension      string
	CreatedAt      time.Time
	UpdatedAt      time.Time
}
