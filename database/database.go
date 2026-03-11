package database

import (
	"fmt"
	"log"
	"strings"

	"github.com/das-kaesebrot/randhaj/models"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

func Init(connectionString string) error {
	var err error

	// cut sqlite:// prefix if connection string contains it
	dbPath, _ := strings.CutPrefix(connectionString, "sqlite://")

	if dbPath == "/" {
		dbPath = "file::memory:?cache=shared"
	}

	log.Printf("Connecting to db '%s' '%s'", connectionString, dbPath)

	DB, err = gorm.Open(sqlite.Open(dbPath), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info),
	})
	if err != nil {
		return fmt.Errorf("failed to connect to db: %w", err)
	}

	// speed! https://sqlite.org/wal.html
	if err := DB.Exec("PRAGMA journal_mode=WAL").Error; err != nil {
		return fmt.Errorf("failed to set WAL mode: %w", err)
	}

	if err := DB.AutoMigrate(&models.Image{}, &models.ImageMetadata{}); err != nil {
		return fmt.Errorf("failed to auto-migrate: %w", err)
	}

	log.Println("Done initializing database")
	return nil
}
