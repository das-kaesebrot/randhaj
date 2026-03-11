package config

import (
	"fmt"
	"log"
	"os"
	"strconv"
)

const (
	envPrefix = "RANDHAJ"
)

type Config struct {
	ImageDir                        string
	CacheDir                        string
	CacheDBFile                     string
	SubmissionsDir                  string
	SubmissionsDiskUsageLimit       float64
	SiteTitle                       string
	SiteEmoji                       string
	DefaultCardImageID              string
	LogLevel                        string
	MaxInitialCacheGeneratorWorkers int
	ServerPort                      string
}

func Load() *Config {
	return &Config{
		ImageDir:                        getEnv("IMAGE_DIR", "assets/images"),
		CacheDir:                        getEnv("CACHE_DIR", "cache"),
		CacheDBFile:                     getEnv("CACHE_DB_FILE", ".randhaj-cache.db"),
		SubmissionsDir:                  getEnv("SUBMISSIONS_DIR", "submissions"),
		SubmissionsDiskUsageLimit:       getEnvAsFloat("SUBMISSIONS_DIR_DISK_USAGE_LIMIT", 0.9),
		SiteTitle:                       getEnv("SITE_TITLE", "Random image"),
		SiteEmoji:                       getEnv("SITE_EMOJI", "🦈"),
		DefaultCardImageID:              getEnv("DEFAULT_CARD_IMAGE", ""),
		LogLevel:                        getEnv("LOG_LEVEL", "INFO"),
		MaxInitialCacheGeneratorWorkers: getEnvAsInt("MAX_INITIAL_CACHE_GENERATOR_WORKERS", 4),
		ServerPort:                      getEnv("PORT", "8080"),
	}
}

func getEnv(key, defaultValue string) string {
	value := os.Getenv(fmt.Sprintf("%s_%s", envPrefix, key))
	if value == "" {
		return defaultValue
	}
	return value
}

func getEnvAsInt(key string, defaultValue int) int {
	value := getEnv(key, "")
	if value == "" {
		return defaultValue
	}

	intValue, err := strconv.Atoi(value)
	if err != nil {
		log.Fatalf("Invalid value for %s: %s (expected int, got %q)", addPrefix(key), err, value)
	}
	return intValue
}

func getEnvAsFloat(key string, defaultValue float64) float64 {
	value := getEnv(key, "")
	if value == "" {
		return defaultValue
	}

	floatValue, err := strconv.ParseFloat(value, 64)
	if err != nil {
		log.Fatalf("Invalid value for %s: %s (expected float, got %q)", addPrefix(key), err, value)
	}

	return floatValue
}

func addPrefix(key string) string {
	return fmt.Sprintf("%s_%s", envPrefix, key)
}
