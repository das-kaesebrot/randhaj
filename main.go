package main

import (
	"log"
	"net/http"

	"github.com/das-kaesebrot/randhaj/database"
)

func main() {
	if err := database.Init("sqlite:///"); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("Hello, World!"))
	})

	log.Println("Server starting on :8080")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatal(err)
	}
}
