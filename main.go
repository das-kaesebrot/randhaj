package main

import (
	"fmt"
	"log"
	"net/http"

	"github.com/das-kaesebrot/randhaj/config"
	"github.com/das-kaesebrot/randhaj/database"
)

func main() {
	cfg := config.Load()

	dbPath := fmt.Sprintf("sqlite://%s", cfg.CacheDBFile)
	if err := database.Init(dbPath); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("Hello, World!"))
	})

	log.Printf("Server starting on :%d", cfg.ServerPort)
	if err := http.ListenAndServe(fmt.Sprintf(":%d", cfg.ServerPort), nil); err != nil {
		log.Fatal(err)
	}
}
